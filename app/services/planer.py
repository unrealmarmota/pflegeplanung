"""
Automatische Dienstplanung mit OR-Tools Constraint Programming
"""
import logging
from ortools.sat.python import cp_model
from datetime import date, timedelta, datetime
from calendar import monthrange
from app import db
from app.models import (
    Mitarbeiter, Dienst, Dienstplan, DienstplanStatus,
    MitarbeiterWunsch, WunschTyp, Regel, RegelTyp,
    MitarbeiterDienstPraeferenz, MitarbeiterDienstEinschraenkung, TagTyp,
    Einstellungen
)

# Logger für dieses Modul
logger = logging.getLogger(__name__)


class DienstPlaner:
    """Optimierungsbasierte Dienstplanung"""

    def __init__(self):
        self.model = None
        self.solver = None
        self.shifts = {}  # (mitarbeiter_id, tag, dienst_id) -> BoolVar
        self.has_shift_vars = {}  # (mitarbeiter_id, tag) -> BoolVar (1 = arbeitet an diesem Tag)
        self.diagnose_info = []  # Sammelt Diagnose-Informationen
        self.soft_penalties = []  # Sammelt Soft-Constraint-Penalties für Objective
        self.vollzeit_stunden = 38.5
        # Vormonat-Daten für monatsübergreifende Constraints
        self.vormonat_dienste = {}  # (ma_id, tag_offset) -> dienst_id, tag_offset: 0=letzter Tag, -1=vorletzter
        self.vormonat_jahr = None
        self.vormonat_monat = None
        self.vormonat_letzter_tag = None
        self.hint_zuweisungen = set()  # Solution Hints aus vorherigem Plan

    def generiere_plan(self, jahr, monat, ueberschreiben=False, best_possible=True):
        """
        Generiert einen optimierten Dienstplan für einen Monat

        Args:
            jahr: Das Jahr
            monat: Der Monat (1-12)
            ueberschreiben: Bestehende Einträge löschen
            best_possible: Bei Fehlschlag trotzdem beste Teillösung speichern

        Returns:
            dict mit 'erfolg', 'eintraege', 'fehler', 'warnungen', 'diagnose'
        """
        logger.info(f"Starte Planung für {monat:02d}/{jahr} (überschreiben={ueberschreiben})")
        self.diagnose_info = []
        self.soft_penalties = []

        # Get data
        mitarbeiter = Mitarbeiter.query.filter_by(aktiv=True).all()
        alle_dienste = Dienst.query.all()
        # Nur planbare Dienste (keine Abwesenheiten wie Urlaub, Krank)
        dienste = [d for d in alle_dienste if not d.ist_abwesenheit]
        regeln = Regel.query.filter_by(aktiv=True).all()

        logger.info(f"Gefunden: {len(mitarbeiter)} aktive MA, {len(dienste)} planbare Dienste, "
                    f"{len(alle_dienste) - len(dienste)} Abwesenheits-Dienste, {len(regeln)} aktive Regeln")

        # Vollzeit-Stunden aus Einstellungen laden (nicht hardcoden)
        self.vollzeit_stunden = Einstellungen.get_float('basis_wochenstunden', 38.5)

        # Vormonat-Daten für monatsübergreifende Constraints laden
        self._lade_vormonat(jahr, monat)

        if not mitarbeiter:
            logger.warning("Planung abgebrochen: Keine aktiven Mitarbeiter")
            return {'erfolg': False, 'fehler': 'Keine aktiven Mitarbeiter vorhanden', 'eintraege': 0, 'warnungen': [], 'diagnose': []}

        if not dienste:
            logger.warning("Planung abgebrochen: Keine planbaren Dienste")
            return {'erfolg': False, 'fehler': 'Keine planbaren Dienste konfiguriert (alle sind Abwesenheiten)', 'eintraege': 0, 'warnungen': [], 'diagnose': []}

        # Calculate days in month
        _, num_days = monthrange(jahr, monat)
        tage = list(range(1, num_days + 1))

        # Delete existing entries if requested (save for hints first)
        self.hint_zuweisungen = set()
        if ueberschreiben:
            start_datum = date(jahr, monat, 1)
            ende_datum = date(jahr, monat, num_days)
            # Solution Hints: alten Plan laden bevor wir löschen
            for dp in Dienstplan.query.filter(
                Dienstplan.datum >= start_datum,
                Dienstplan.datum <= ende_datum
            ).all():
                self.hint_zuweisungen.add((dp.mitarbeiter_id, dp.datum.day, dp.dienst_id))
            try:
                Dienstplan.query.filter(
                    Dienstplan.datum >= start_datum,
                    Dienstplan.datum <= ende_datum
                ).delete()
                db.session.commit()
                logger.info(f"Bestehende Einträge für {monat:02d}/{jahr} gelöscht ({len(self.hint_zuweisungen)} Hints gesichert)")
            except Exception as e:
                db.session.rollback()
                logger.error(f"Fehler beim Löschen bestehender Einträge: {e}")
                return {
                    'erfolg': False,
                    'fehler': f'Fehler beim Löschen bestehender Einträge: {str(e)}',
                    'eintraege': 0,
                    'warnungen': [],
                    'diagnose': []
                }

        # Get existing entries (if not overwriting)
        bestehende = {}
        if not ueberschreiben:
            start_datum = date(jahr, monat, 1)
            ende_datum = date(jahr, monat, num_days)
            for dp in Dienstplan.query.filter(
                Dienstplan.datum >= start_datum,
                Dienstplan.datum <= ende_datum
            ).all():
                bestehende[(dp.mitarbeiter_id, dp.datum.day)] = dp.dienst_id

        # Get wishes (as lists to support multiple wishes per day)
        wuensche = {}
        start_datum = date(jahr, monat, 1)
        ende_datum = date(jahr, monat, num_days)
        for w in MitarbeiterWunsch.query.filter(
            MitarbeiterWunsch.datum >= start_datum,
            MitarbeiterWunsch.datum <= ende_datum
        ).all():
            key = (w.mitarbeiter_id, w.datum.day)
            if key not in wuensche:
                wuensche[key] = []
            wuensche[key].append(w)

        # Create the model
        self.model = cp_model.CpModel()
        self.shifts = {}

        # Create shift variables
        for m in mitarbeiter:
            for tag in tage:
                # Skip if already assigned
                if (m.id, tag) in bestehende:
                    continue

                for d in dienste:
                    var_name = f'shift_m{m.id}_t{tag}_d{d.id}'
                    self.shifts[(m.id, tag, d.id)] = self.model.NewBoolVar(var_name)

        # Wiederverwendbare Arbeitstag-Variablen erstellen (inkl. Vormonat)
        self._erstelle_arbeitstag_vars(mitarbeiter, dienste, tage, bestehende)

        # Solution Hints aus vorherigem Plan anwenden (schnellere Konvergenz)
        if self.hint_zuweisungen:
            for key, var in self.shifts.items():
                self.model.AddHint(var, 1 if key in self.hint_zuweisungen else 0)
            logger.info(f"Solution Hints angewendet: {len(self.hint_zuweisungen)} Zuweisungen")

        # Constraint 1: Each employee works at most one shift per day
        for m in mitarbeiter:
            for tag in tage:
                if (m.id, tag) in bestehende:
                    continue

                shifts_per_day = [
                    self.shifts[(m.id, tag, d.id)]
                    for d in dienste
                    if (m.id, tag, d.id) in self.shifts
                ]
                if shifts_per_day:
                    self.model.Add(sum(shifts_per_day) <= 1)

        # Constraint: Qualifikationsanforderungen pro Dienst
        self._apply_qualifikation_erforderlich(mitarbeiter, dienste, tage)

        # Constraint: Mitarbeiter-spezifische Dienst-Einschränkungen
        self._apply_mitarbeiter_einschraenkungen(mitarbeiter, dienste, tage, jahr, monat)

        # Constraint: Mindestanzahl qualifiziertes Personal pro Dienst (aus DienstQualifikation)
        self._apply_qualifikation_min_anzahl(mitarbeiter, dienste, tage, bestehende)

        # Apply rules as constraints
        self._apply_regeln(regeln, mitarbeiter, dienste, tage, jahr, monat, wuensche, bestehende)

        # Apply min/max besetzung from Dienst model
        self._apply_besetzung_constraints(mitarbeiter, dienste, tage, bestehende)

        # Objective: Maximize coverage and respect wishes
        # Weight hierarchy: Coverage(100) > Wishes(50/20) > Fairness(30/40) > Preferences(3/5)
        objective_terms = []

        # Coverage bonus: reward each assigned shift (high weight to prioritize staffing)
        for key, var in self.shifts.items():
            objective_terms.append(10 * var)

        # Wish penalties/bonuses
        for m in mitarbeiter:
            for tag in tage:
                if (m.id, tag) in wuensche:
                    for w in wuensche[(m.id, tag)]:
                        if w.wunsch_typ == WunschTyp.FREI:
                            # Penalty for working when wants to be free
                            for d in dienste:
                                if (m.id, tag, d.id) in self.shifts:
                                    objective_terms.append(-50 * self.shifts[(m.id, tag, d.id)])
                        elif w.wunsch_typ == WunschTyp.NICHT_VERFUEGBAR:
                            # Hard constraint - don't assign any shift
                            for d in dienste:
                                if (m.id, tag, d.id) in self.shifts:
                                    self.model.Add(self.shifts[(m.id, tag, d.id)] == 0)
                        elif w.wunsch_typ == WunschTyp.DIENST_AUSSCHLUSS and w.dienst_id:
                            # Hard constraint - don't assign this specific shift
                            if (m.id, tag, w.dienst_id) in self.shifts:
                                self.model.Add(self.shifts[(m.id, tag, w.dienst_id)] == 0)
                        elif w.wunsch_typ == WunschTyp.DIENST_WUNSCH and w.dienst_id:
                            # Bonus for respecting shift wish
                            if (m.id, tag, w.dienst_id) in self.shifts:
                                objective_terms.append(20 * self.shifts[(m.id, tag, w.dienst_id)])

        # Soft constraints for employee shift preferences (min/max per month)
        for m in mitarbeiter:
            for pref in m.dienst_praeferenzen:
                # Count shifts of this type for this employee
                shift_count_vars = [
                    self.shifts[(m.id, tag, pref.dienst_id)]
                    for tag in tage
                    if (m.id, tag, pref.dienst_id) in self.shifts
                ]

                if shift_count_vars:
                    total_shifts = sum(shift_count_vars)

                    # Soft bonus for meeting minimum (capped variable pattern)
                    if pref.min_pro_monat and pref.min_pro_monat > 0:
                        capped_min = self.model.NewIntVar(
                            0, pref.min_pro_monat,
                            f'pref_min_m{m.id}_d{pref.dienst_id}'
                        )
                        self.model.AddMinEquality(capped_min, [total_shifts, pref.min_pro_monat])
                        objective_terms.append(3 * capped_min)

                    # Soft penalty for exceeding maximum
                    if pref.max_pro_monat is not None:
                        over_max = self.model.NewIntVar(
                            0, len(tage),
                            f'pref_over_m{m.id}_d{pref.dienst_id}'
                        )
                        self.model.AddMaxEquality(over_max, [total_shifts - pref.max_pro_monat, 0])
                        objective_terms.append(-5 * over_max)

        # Soft-Constraint-Penalties hinzufügen
        objective_terms.extend(self.soft_penalties)

        if objective_terms:
            self.model.Maximize(sum(objective_terms))

        # Pre-solve diagnostics
        diagnose = self._diagnose_probleme(mitarbeiter, dienste, tage, bestehende)
        # Füge Diagnose-Infos aus Constraint-Anwendung hinzu
        diagnose.extend(self.diagnose_info)
        warnungen = []

        if diagnose:
            for d in diagnose:
                if d.get('schwere') == 'kritisch':
                    logger.warning(f"Diagnose [{d['typ']}]: {d['text']}")
                else:
                    logger.info(f"Diagnose [{d['typ']}]: {d['text']}")

        # Solve
        logger.info(f"Starte Solver mit {len(self.shifts)} Variablen...")
        self.solver = cp_model.CpSolver()
        self.solver.parameters.max_time_in_seconds = 60.0
        status = self.solver.Solve(self.model)
        logger.info(f"Solver beendet mit Status: {self.solver.StatusName(status)}")
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            logger.info(f"Objective-Wert: {self.solver.ObjectiveValue():.0f}")

        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            # Extract solution into dict for validation before DB write
            zuweisungen = {}  # {(ma_id, tag): dienst_id}
            for m in mitarbeiter:
                for tag in tage:
                    if (m.id, tag) in bestehende:
                        continue
                    for d in dienste:
                        if (m.id, tag, d.id) in self.shifts:
                            if self.solver.Value(self.shifts[(m.id, tag, d.id)]) == 1:
                                zuweisungen.setdefault((m.id, tag), []).append(d.id)

            # Post-solve validation
            validierungen = self._validiere_loesung(zuweisungen, mitarbeiter, dienste, tage, jahr, monat, wuensche, regeln)
            for v in validierungen:
                logger.warning(f"Post-Solve-Validierung: {v}")

            # Objective breakdown
            total_schichten = sum(len(d_ids) for d_ids in zuweisungen.values())
            frei_verletzt = 0
            wunsch_erfuellt = 0
            for (ma_id, tag), d_ids in zuweisungen.items():
                if (ma_id, tag) in wuensche:
                    for w in wuensche[(ma_id, tag)]:
                        if w.wunsch_typ == WunschTyp.FREI and d_ids:
                            frei_verletzt += 1
                        elif w.wunsch_typ == WunschTyp.DIENST_WUNSCH and w.dienst_id in d_ids:
                            wunsch_erfuellt += 1
            objective_breakdown = {
                'total_schichten': total_schichten,
                'objective_wert': self.solver.ObjectiveValue(),
                'solver_status': self.solver.StatusName(status),
                'frei_wuensche_verletzt': frei_verletzt,
                'dienst_wuensche_erfuellt': wunsch_erfuellt,
                'validierungsfehler': len(validierungen),
            }
            logger.info(f"Objective-Breakdown: {objective_breakdown}")

            # Write to database
            eintraege = 0
            for (ma_id, tag), dienst_ids in zuweisungen.items():
                for d_id in dienst_ids:
                    dp = Dienstplan(
                        datum=date(jahr, monat, tag),
                        mitarbeiter_id=ma_id,
                        dienst_id=d_id,
                        status=DienstplanStatus.GEPLANT
                    )
                    db.session.add(dp)
                    eintraege += 1

            try:
                db.session.commit()
                logger.info(f"Planung erfolgreich: {eintraege} Einträge erstellt")
            except Exception as e:
                db.session.rollback()
                logger.error(f"Fehler beim Speichern der Planung: {e}")
                return {
                    'erfolg': False,
                    'fehler': f'Datenbankfehler beim Speichern: {str(e)}',
                    'eintraege': 0,
                    'warnungen': [],
                    'diagnose': diagnose
                }

            # Check for under-staffing warnings
            warnungen = self._pruefe_besetzung(dienste, tage, jahr, monat)
            if warnungen:
                logger.warning(f"Besetzungsprobleme: {len(warnungen)} Warnungen")

            return {
                'erfolg': True,
                'eintraege': eintraege,
                'fehler': None,
                'warnungen': warnungen,
                'diagnose': diagnose,
                'validierungen': validierungen,
                'objective_breakdown': objective_breakdown
            }
        else:
            # INFEASIBLE - try best-possible mode
            logger.warning(f"Keine optimale Lösung gefunden, versuche Teillösung (best_possible={best_possible})")
            if best_possible:
                return self._generiere_best_possible(
                    jahr, monat, mitarbeiter, dienste, tage, bestehende, wuensche, diagnose
                )
            else:
                return {
                    'erfolg': False,
                    'fehler': 'Keine gültige Lösung gefunden. Prüfen Sie die Regeln und Ressourcen.',
                    'eintraege': 0,
                    'warnungen': [],
                    'diagnose': diagnose
                }

    def _validiere_loesung(self, zuweisungen, mitarbeiter, dienste, tage, jahr, monat, wuensche, regeln=None):
        """Validiert die extrahierte Lösung auf Constraint-Verletzungen.

        Verwendet die tatsächlich konfigurierten Regelwerte statt Hardcodes.
        """
        violations = []
        dienst_map = {d.id: d for d in dienste}
        ma_map = {m.id: m for m in mitarbeiter}

        # Regelwerte extrahieren (mit gesetzlichen Defaults)
        min_ruhezeit_stunden = 11
        max_folgetage = 6
        if regeln:
            for r in regeln:
                if r.typ == RegelTyp.MIN_RUHEZEIT:
                    min_ruhezeit_stunden = r.parameter.get('stunden', 11)
                elif r.typ == RegelTyp.MAX_TAGE_FOLGE:
                    max_folgetage = r.parameter.get('max', 5)

        # 1. Max 1 Schicht pro Tag pro MA
        for (ma_id, tag), dienst_ids in zuweisungen.items():
            if len(dienst_ids) > 1:
                violations.append(
                    f'MA {ma_id} Tag {tag}: {len(dienst_ids)} Schichten zugewiesen (max 1)'
                )

        # 2. NICHT_VERFUEGBAR verletzt?
        for (ma_id, tag), dienst_ids in zuweisungen.items():
            if (ma_id, tag) in wuensche:
                for w in wuensche[(ma_id, tag)]:
                    if w.wunsch_typ == WunschTyp.NICHT_VERFUEGBAR and dienst_ids:
                        violations.append(
                            f'MA {ma_id} Tag {tag}: Arbeitet trotz NICHT_VERFUEGBAR'
                        )

        # 3. Min-Besetzung pro Schicht/Tag
        for d in dienste:
            if d.min_besetzung:
                for tag in tage:
                    count = sum(
                        1 for (ma_id, t), d_ids in zuweisungen.items()
                        if t == tag and d.id in d_ids
                    )
                    if count < d.min_besetzung:
                        violations.append(
                            f'Dienst {d.name} Tag {tag}: Besetzung {count} < min {d.min_besetzung}'
                        )

        # 4. Ruhezeit zwischen Schichten (konfigurierter Wert)
        for m in mitarbeiter:
            for tag in tage[:-1]:
                naechster_tag = tag + 1
                if (m.id, tag) not in zuweisungen or (m.id, naechster_tag) not in zuweisungen:
                    continue
                for d1_id in zuweisungen[(m.id, tag)]:
                    for d2_id in zuweisungen[(m.id, naechster_tag)]:
                        d1 = dienst_map.get(d1_id)
                        d2 = dienst_map.get(d2_id)
                        if not d1 or not d2:
                            continue
                        ende = datetime.combine(date(jahr, monat, tag), d1.ende_zeit)
                        if d1.ende_zeit <= d1.start_zeit:
                            ende = datetime.combine(date(jahr, monat, naechster_tag), d1.ende_zeit)
                        start = datetime.combine(date(jahr, monat, naechster_tag), d2.start_zeit)
                        ruhezeit = (start - ende).total_seconds() / 3600
                        if ruhezeit < min_ruhezeit_stunden:
                            violations.append(
                                f'MA {m.id} Tag {tag}->{naechster_tag}: '
                                f'Ruhezeit {ruhezeit:.1f}h < {min_ruhezeit_stunden}h ({d1.name} -> {d2.name})'
                            )

        # 5. Max aufeinanderfolgende Arbeitstage (konfigurierter Wert + individuelle Overrides)
        for m in mitarbeiter:
            ma_max_folge = m.get_regel_wert('MAX_TAGE_FOLGE', max_folgetage)
            # Starte mit Vormonat-Arbeitstagen
            consecutive = 0
            if self.vormonat_dienste:
                for offset in range(0, -8, -1):  # 0, -1, -2, ..., -7
                    if (m.id, offset) in self.vormonat_dienste:
                        consecutive += 1
                    else:
                        break
            for tag in tage:
                if (m.id, tag) in zuweisungen and zuweisungen[(m.id, tag)]:
                    consecutive += 1
                    if consecutive > ma_max_folge:
                        violations.append(
                            f'MA {m.id} Tag {tag}: {consecutive} aufeinanderfolgende Arbeitstage (max {ma_max_folge})'
                        )
                else:
                    consecutive = 0

        return violations

    def _diagnose_probleme(self, mitarbeiter, dienste, tage, bestehende):
        """Analysiert potenzielle Probleme vor dem Lösen"""
        probleme = []

        # Check 1: Genug Personal für Mindestbesetzung?
        verfuegbare_ma_tage = len(mitarbeiter) * len(tage) - len(bestehende)
        min_benoetigte_schichten = sum(d.min_besetzung or 0 for d in dienste) * len(tage)

        if min_benoetigte_schichten > verfuegbare_ma_tage:
            probleme.append({
                'typ': 'UNTERBESETZUNG',
                'text': f'Zu wenig Personal: {len(mitarbeiter)} MA × {len(tage)} Tage = {verfuegbare_ma_tage} Schichten verfügbar, '
                        f'aber {min_benoetigte_schichten} Schichten benötigt (Mindestbesetzung aller Dienste).',
                'schwere': 'kritisch'
            })

        # Check 2: Qualifikationsanforderungen erfüllbar?
        for d in dienste:
            erforderliche_qualis = d.get_erforderliche_qualifikationen()
            if erforderliche_qualis:
                qualifizierte_ma = [m for m in mitarbeiter if d.kann_mitarbeiter_arbeiten(m)]
                if len(qualifizierte_ma) == 0:
                    probleme.append({
                        'typ': 'KEINE_QUALIFIKATION',
                        'text': f'Dienst "{d.name}": Kein Mitarbeiter hat die erforderliche Qualifikation '
                                f'({", ".join(q.name for q in erforderliche_qualis)}).',
                        'schwere': 'kritisch'
                    })
                elif len(qualifizierte_ma) < (d.min_besetzung or 1):
                    probleme.append({
                        'typ': 'ZU_WENIG_QUALIFIZIERT',
                        'text': f'Dienst "{d.name}": Nur {len(qualifizierte_ma)} qualifizierte MA, '
                                f'aber Mindestbesetzung ist {d.min_besetzung}.',
                        'schwere': 'warnung'
                    })

        # Check 3: Mindestbesetzung pro Dienst erreichbar?
        for d in dienste:
            qualifizierte_ma = [m for m in mitarbeiter if d.kann_mitarbeiter_arbeiten(m)]
            if d.min_besetzung and d.min_besetzung > 0:
                # Jeder MA kann max 1x pro Tag arbeiten
                max_pro_tag = len(qualifizierte_ma)
                if max_pro_tag < d.min_besetzung:
                    probleme.append({
                        'typ': 'BESETZUNG_UNMOEGLICH',
                        'text': f'Dienst "{d.name}": Mindestbesetzung {d.min_besetzung} kann nicht erreicht werden '
                                f'(nur {max_pro_tag} qualifizierte MA verfügbar).',
                        'schwere': 'kritisch'
                    })

        return probleme

    def _lade_vormonat(self, jahr, monat):
        """Lädt die letzten Tage des Vormonats für monatsübergreifende Constraints"""
        if monat == 1:
            vm_jahr, vm_monat = jahr - 1, 12
        else:
            vm_jahr, vm_monat = jahr, monat - 1

        _, vm_num_days = monthrange(vm_jahr, vm_monat)

        # Lade letzte 7 Tage des Vormonats
        lookback = 7
        start_tag = max(1, vm_num_days - lookback + 1)
        start_datum = date(vm_jahr, vm_monat, start_tag)
        ende_datum = date(vm_jahr, vm_monat, vm_num_days)

        vormonat_eintraege = Dienstplan.query.filter(
            Dienstplan.datum >= start_datum,
            Dienstplan.datum <= ende_datum
        ).all()

        # Speichere als (ma_id, tag_offset) -> dienst_id
        # tag_offset: 0 = letzter Tag Vormonat, -1 = vorletzter, etc.
        self.vormonat_dienste = {}
        for dp in vormonat_eintraege:
            tag_offset = dp.datum.day - vm_num_days  # Tag 31 von 31 -> 0, Tag 30 -> -1
            self.vormonat_dienste[(dp.mitarbeiter_id, tag_offset)] = dp.dienst_id

        self.vormonat_jahr = vm_jahr
        self.vormonat_monat = vm_monat
        self.vormonat_letzter_tag = vm_num_days

        logger.info(f"Vormonat {vm_monat:02d}/{vm_jahr}: {len(vormonat_eintraege)} Einträge für Cross-Month-Constraints")

    def _erstelle_arbeitstag_vars(self, mitarbeiter, dienste, tage, bestehende):
        """Erstellt wiederverwendbare has_shift BoolVars für jeden MA/Tag.

        Enthält auch fixierte Variablen für Vormonat-Tage (Cross-Month).
        Vermeidet redundante Variable-Erzeugung in Constraint-Methoden.
        """
        self.has_shift_vars = {}

        # Aktuelle Monatstage
        for m in mitarbeiter:
            for tag in tage:
                if (m.id, tag) in bestehende:
                    # Bereits zugewiesen = arbeitet
                    has_shift = self.model.NewBoolVar(f'has_shift_m{m.id}_t{tag}')
                    self.model.Add(has_shift == 1)
                    self.has_shift_vars[(m.id, tag)] = has_shift
                    continue

                day_shifts = [
                    self.shifts[(m.id, tag, d.id)]
                    for d in dienste
                    if (m.id, tag, d.id) in self.shifts
                ]
                if day_shifts:
                    has_shift = self.model.NewBoolVar(f'has_shift_m{m.id}_t{tag}')
                    self.model.Add(sum(day_shifts) >= 1).OnlyEnforceIf(has_shift)
                    self.model.Add(sum(day_shifts) == 0).OnlyEnforceIf(has_shift.Not())
                    self.has_shift_vars[(m.id, tag)] = has_shift

        # Vormonat-Tage (fixiert auf 1 wo gearbeitet wurde)
        for (ma_id, tag_offset), dienst_id in self.vormonat_dienste.items():
            fixed_var = self.model.NewBoolVar(f'vm_has_shift_m{ma_id}_t{tag_offset}')
            self.model.Add(fixed_var == 1)
            self.has_shift_vars[(ma_id, tag_offset)] = fixed_var

        logger.debug(f"Arbeitstag-Vars erstellt: {len(self.has_shift_vars)} "
                     f"(davon {len(self.vormonat_dienste)} Vormonat)")

    def _generiere_best_possible(self, jahr, monat, mitarbeiter, dienste, tage, bestehende, wuensche, diagnose):
        """Generiert beste mögliche Lösung ohne harte Besetzungs-Constraints"""
        logger.info("Erstelle Teillösung mit gelockerten Constraints...")
        warnungen = []
        warnungen.append('Vollständige Planung nicht möglich - erstelle beste Teillösung.')

        # Create new model with relaxed constraints
        self.model = cp_model.CpModel()
        self.shifts = {}
        self.soft_penalties = []  # Reset für neues Modell

        # Create shift variables
        for m in mitarbeiter:
            for tag in tage:
                if (m.id, tag) in bestehende:
                    continue
                for d in dienste:
                    var_name = f'shift_m{m.id}_t{tag}_d{d.id}'
                    self.shifts[(m.id, tag, d.id)] = self.model.NewBoolVar(var_name)

        # Arbeitstag-Vars neu erstellen für das relaxierte Modell (inkl. Vormonat)
        self._erstelle_arbeitstag_vars(mitarbeiter, dienste, tage, bestehende)

        # Constraint 1: Each employee works at most one shift per day (keep this hard)
        for m in mitarbeiter:
            for tag in tage:
                if (m.id, tag) in bestehende:
                    continue
                shifts_per_day = [
                    self.shifts[(m.id, tag, d.id)]
                    for d in dienste
                    if (m.id, tag, d.id) in self.shifts
                ]
                if shifts_per_day:
                    self.model.Add(sum(shifts_per_day) <= 1)

        # Constraint: Qualifikationsanforderungen pro Dienst (keep this hard)
        self._apply_qualifikation_erforderlich(mitarbeiter, dienste, tage)

        # Constraint: Mindestanzahl qualifiziertes Personal pro Dienst
        # Als Soft-Constraint mit hohem Bonus im Objective
        self._apply_qualifikation_min_anzahl_soft(mitarbeiter, dienste, tage, bestehende)

        # Constraint: Mitarbeiter-spezifische Dienst-Einschränkungen (keep this hard)
        self._apply_mitarbeiter_einschraenkungen(mitarbeiter, dienste, tage, jahr, monat)

        # Apply wishes as hard constraints
        for m in mitarbeiter:
            for tag in tage:
                if (m.id, tag) in wuensche:
                    for w in wuensche[(m.id, tag)]:
                        if w.wunsch_typ == WunschTyp.NICHT_VERFUEGBAR:
                            for d in dienste:
                                if (m.id, tag, d.id) in self.shifts:
                                    self.model.Add(self.shifts[(m.id, tag, d.id)] == 0)
                        elif w.wunsch_typ == WunschTyp.DIENST_AUSSCHLUSS and w.dienst_id:
                            if (m.id, tag, w.dienst_id) in self.shifts:
                                self.model.Add(self.shifts[(m.id, tag, w.dienst_id)] == 0)

        # Apply all rules including DIENST_BLOCK, FREIE_TAGE_NACH_BLOCK, MAX_NACHT_BLOECKE, etc.
        regeln = Regel.query.filter_by(aktiv=True).all()
        self._apply_regeln(regeln, mitarbeiter, dienste, tage, jahr, monat, wuensche, bestehende)

        # Constraint: Limit staff per shift to reasonable maximum (min_besetzung + 1)
        for d in dienste:
            max_besetzung = (d.min_besetzung or 0) + 1
            if max_besetzung < 1:
                max_besetzung = 1
            for tag in tage:
                shift_vars = [
                    self.shifts[(m.id, tag, d.id)]
                    for m in mitarbeiter
                    if (m.id, tag, d.id) in self.shifts
                ]
                if shift_vars:
                    self.model.Add(sum(shift_vars) <= max_besetzung)

        # Objective: Maximize coverage with fair distribution
        objective_terms = []

        # For each shift type per day: bonus for meeting min_besetzung
        for d in dienste:
            if not d.min_besetzung or d.min_besetzung == 0:
                continue

            for tag in tage:
                shift_vars = [
                    self.shifts[(m.id, tag, d.id)]
                    for m in mitarbeiter
                    if (m.id, tag, d.id) in self.shifts
                ]
                if shift_vars:
                    # Create variable for capped count: min(assigned, min_besetzung)
                    # This properly rewards filling positions up to min_besetzung
                    capped = self.model.NewIntVar(0, d.min_besetzung, f'capped_d{d.id}_t{tag}')
                    self.model.Add(capped <= sum(shift_vars))

                    # Big bonus for each position filled up to min_besetzung
                    objective_terms.append(100 * capped)

        # Fair distribution based on Stellenanteil (arbeitsstunden_woche)
        VOLLZEIT_STUNDEN = self.vollzeit_stunden
        VOLLZEIT_TAGE_MONAT = 18  # ~18 Arbeitstage bei Vollzeit

        for m in mitarbeiter:
            # Berechne max Arbeitstage basierend auf Stellenanteil
            stunden = m.arbeitsstunden_woche or VOLLZEIT_STUNDEN
            stellenanteil = stunden / VOLLZEIT_STUNDEN
            max_tage = int(VOLLZEIT_TAGE_MONAT * stellenanteil)
            min_tage = max(1, int(max_tage * 0.7))  # Mindestens 70% vom Soll

            # Zähle Arbeitstage
            arbeits_tage = []
            for tag in tage:
                day_worked = self.model.NewBoolVar(f'day_worked_m{m.id}_t{tag}')
                day_shifts = [
                    self.shifts[(m.id, tag, d.id)]
                    for d in dienste
                    if (m.id, tag, d.id) in self.shifts
                ]
                if day_shifts:
                    self.model.Add(sum(day_shifts) >= 1).OnlyEnforceIf(day_worked)
                    self.model.Add(sum(day_shifts) == 0).OnlyEnforceIf(day_worked.Not())
                    arbeits_tage.append(day_worked)

            if arbeits_tage:
                total_work_days = sum(arbeits_tage)

                # HARTE Obergrenze: Nicht mehr als max_tage (Überlastung vermeiden)
                self.model.Add(total_work_days <= max_tage)

                # Soft constraint: Bonus für jeden Arbeitstag bis zum Soll
                # Das motiviert den Solver, Mitarbeiter proportional einzusetzen
                for i, day_var in enumerate(arbeits_tage):
                    if i < max_tage:
                        objective_terms.append(5 * day_var)  # Bonus für Arbeit bis Soll

        # Wish bonuses/penalties
        for m in mitarbeiter:
            for tag in tage:
                if (m.id, tag) in wuensche:
                    for w in wuensche[(m.id, tag)]:
                        if w.wunsch_typ == WunschTyp.FREI:
                            for d in dienste:
                                if (m.id, tag, d.id) in self.shifts:
                                    objective_terms.append(-50 * self.shifts[(m.id, tag, d.id)])
                        elif w.wunsch_typ == WunschTyp.DIENST_WUNSCH and w.dienst_id:
                            if (m.id, tag, w.dienst_id) in self.shifts:
                                objective_terms.append(20 * self.shifts[(m.id, tag, w.dienst_id)])

        # Soft-Constraint-Penalties hinzufügen (Qualifikationen etc.)
        objective_terms.extend(self.soft_penalties)

        if objective_terms:
            self.model.Maximize(sum(objective_terms))

        # Solve relaxed model
        logger.info(f"Starte Solver (relaxed) mit {len(self.shifts)} Variablen...")
        self.solver = cp_model.CpSolver()
        self.solver.parameters.max_time_in_seconds = 60.0
        status = self.solver.Solve(self.model)
        logger.info(f"Solver (relaxed) beendet mit Status: {self.solver.StatusName(status)}")

        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            logger.info(f"Objective-Wert (relaxed): {self.solver.ObjectiveValue():.0f}")

            # Extract solution into dict for validation
            zuweisungen = {}
            for m in mitarbeiter:
                for tag in tage:
                    if (m.id, tag) in bestehende:
                        continue
                    for d in dienste:
                        if (m.id, tag, d.id) in self.shifts:
                            if self.solver.Value(self.shifts[(m.id, tag, d.id)]) == 1:
                                zuweisungen.setdefault((m.id, tag), []).append(d.id)

            # Post-solve validation
            regeln = Regel.query.filter_by(aktiv=True).all()
            validierungen = self._validiere_loesung(zuweisungen, mitarbeiter, dienste, tage, jahr, monat, wuensche, regeln)
            for v in validierungen:
                logger.warning(f"Post-Solve-Validierung (relaxed): {v}")

            # Objective breakdown
            total_schichten = sum(len(d_ids) for d_ids in zuweisungen.values())
            frei_verletzt = 0
            wunsch_erfuellt = 0
            for (ma_id, tag), d_ids in zuweisungen.items():
                if (ma_id, tag) in wuensche:
                    for w in wuensche[(ma_id, tag)]:
                        if w.wunsch_typ == WunschTyp.FREI and d_ids:
                            frei_verletzt += 1
                        elif w.wunsch_typ == WunschTyp.DIENST_WUNSCH and w.dienst_id in d_ids:
                            wunsch_erfuellt += 1
            objective_breakdown = {
                'total_schichten': total_schichten,
                'objective_wert': self.solver.ObjectiveValue(),
                'solver_status': self.solver.StatusName(status),
                'frei_wuensche_verletzt': frei_verletzt,
                'dienst_wuensche_erfuellt': wunsch_erfuellt,
                'validierungsfehler': len(validierungen),
                'teilweise': True,
            }
            logger.info(f"Objective-Breakdown (relaxed): {objective_breakdown}")

            # Write to database
            eintraege = 0
            for (ma_id, tag), dienst_ids in zuweisungen.items():
                for d_id in dienst_ids:
                    dp = Dienstplan(
                        datum=date(jahr, monat, tag),
                        mitarbeiter_id=ma_id,
                        dienst_id=d_id,
                        status=DienstplanStatus.GEPLANT
                    )
                    db.session.add(dp)
                    eintraege += 1

            try:
                db.session.commit()
                logger.info(f"Teillösung erfolgreich: {eintraege} Einträge erstellt")
            except Exception as e:
                db.session.rollback()
                logger.error(f"Fehler beim Speichern der Teillösung: {e}")
                return {
                    'erfolg': False,
                    'fehler': f'Datenbankfehler beim Speichern: {str(e)}',
                    'eintraege': 0,
                    'warnungen': warnungen,
                    'diagnose': diagnose
                }

            # Check what's missing
            besetzungs_probleme = self._pruefe_besetzung(dienste, tage, jahr, monat)
            warnungen.extend(besetzungs_probleme)
            if besetzungs_probleme:
                logger.warning(f"Besetzungsprobleme: {len(besetzungs_probleme)} Warnungen")

            return {
                'erfolg': True,
                'teilweise': True,
                'eintraege': eintraege,
                'fehler': None,
                'warnungen': warnungen,
                'diagnose': diagnose,
                'validierungen': validierungen,
                'objective_breakdown': objective_breakdown
            }
        else:
            logger.error("Auch Teillösung nicht möglich")
            return {
                'erfolg': False,
                'fehler': 'Auch Teillösung nicht möglich. Prüfen Sie Qualifikationsanforderungen und Mitarbeiterverfügbarkeit.',
                'eintraege': 0,
                'warnungen': warnungen,
                'diagnose': diagnose
            }

    def _pruefe_besetzung(self, dienste, tage, jahr, monat):
        """Prüft die aktuelle Besetzung und meldet Unterbesetzungen"""
        probleme = []

        for d in dienste:
            if not d.min_besetzung or d.min_besetzung == 0:
                continue

            for tag in tage:
                datum = date(jahr, monat, tag)
                anzahl = Dienstplan.query.filter_by(datum=datum, dienst_id=d.id).count()

                if anzahl < d.min_besetzung:
                    probleme.append(
                        f'{datum.strftime("%d.%m.")}: {d.name} unterbesetzt ({anzahl}/{d.min_besetzung})'
                    )

        return probleme

    def _apply_regeln(self, regeln, mitarbeiter, dienste, tage, jahr, monat, wuensche, bestehende):
        """Wendet alle aktiven Regeln als Constraints an"""
        logger.debug(f"Wende {len(regeln)} Regeln an...")

        for regel in regeln:
            if not regel.aktiv:
                continue

            params = regel.parameter

            if regel.typ == RegelTyp.MAX_TAGE_FOLGE:
                self._constraint_max_tage_folge(mitarbeiter, dienste, tage, params.get('max', 5))

            elif regel.typ == RegelTyp.MIN_RUHEZEIT:
                self._constraint_min_ruhezeit(mitarbeiter, dienste, tage, jahr, monat, params.get('stunden', 11))

            elif regel.typ == RegelTyp.MIN_PERSONAL_DIENST:
                dienst_id = params.get('dienst_id')
                min_personal = params.get('min', 3)
                if dienst_id:
                    self._constraint_min_personal(mitarbeiter, tage, dienst_id, min_personal, bestehende)

            elif regel.typ == RegelTyp.WOCHENENDE_ROTATION:
                self._constraint_wochenende_rotation(mitarbeiter, dienste, tage, jahr, monat, params.get('max', 2))

            elif regel.typ == RegelTyp.KEIN_NACHT_VOR_FRUEH:
                self._constraint_kein_nacht_vor_frueh(mitarbeiter, dienste, tage, jahr, monat)

            elif regel.typ == RegelTyp.QUALIFIKATION_PFLICHT:
                dienst_id = params.get('dienst_id')
                qual_id = params.get('qualifikation_id')
                min_anzahl = params.get('min', 1)
                if dienst_id and qual_id:
                    self._constraint_qualifikation_pflicht(mitarbeiter, tage, dienst_id, qual_id, min_anzahl, bestehende)

            elif regel.typ == RegelTyp.DIENST_BLOCK:
                dienst_id = params.get('dienst_id')
                min_folge = params.get('min_folge', 2)
                max_folge = params.get('max_folge', 4)
                if dienst_id:
                    self._constraint_dienst_block(mitarbeiter, tage, dienst_id, min_folge, max_folge, regel.prioritaet)

            elif regel.typ == RegelTyp.KEIN_WECHSEL_VON_NACH:
                von_dienst_id = params.get('von_dienst_id')
                nach_dienst_id = params.get('nach_dienst_id')
                if von_dienst_id and nach_dienst_id:
                    self._constraint_kein_wechsel(mitarbeiter, tage, von_dienst_id, nach_dienst_id, regel.prioritaet)

            elif regel.typ == RegelTyp.MAX_DIENST_PRO_WOCHE:
                dienst_id = params.get('dienst_id')
                max_pro_woche = params.get('max', 3)
                if dienst_id:
                    self._constraint_max_dienst_pro_woche(mitarbeiter, tage, jahr, monat, dienst_id, max_pro_woche, regel.prioritaet)

            elif regel.typ == RegelTyp.FREIE_TAGE_NACH_BLOCK:
                dienst_id = params.get('dienst_id')
                min_frei = params.get('min_frei', 2)
                if dienst_id:
                    self._constraint_freie_tage_nach_block(mitarbeiter, dienste, tage, dienst_id, min_frei, regel.prioritaet)

            elif regel.typ == RegelTyp.KEIN_WOCHENENDE:
                dienst_id = params.get('dienst_id')
                if dienst_id:
                    self._constraint_kein_wochenende(tage, jahr, monat, dienst_id)

            elif regel.typ == RegelTyp.MAX_NACHT_BLOECKE:
                min_bloecke = params.get('min', 2)
                max_bloecke = params.get('max', 3)
                nacht_dienst_ids = self._get_nacht_dienst_ids(dienste)
                if nacht_dienst_ids:
                    self._constraint_nacht_bloecke(mitarbeiter, tage, nacht_dienst_ids, min_bloecke, max_bloecke)

            elif regel.typ == RegelTyp.MAX_NAECHTE_MONAT:
                max_naechte = params.get('max', 8)
                nacht_dienst_ids = self._get_nacht_dienst_ids(dienste)
                if nacht_dienst_ids:
                    self._constraint_max_naechte_monat(mitarbeiter, tage, nacht_dienst_ids, max_naechte)

            elif regel.typ == RegelTyp.MAX_WOCHENSTUNDEN:
                max_stunden = params.get('stunden', 48)
                self._constraint_max_wochenstunden(mitarbeiter, dienste, tage, jahr, monat, max_stunden)

            elif regel.typ == RegelTyp.MIN_NAECHTE_MONAT:
                min_naechte = params.get('min', 4)
                nacht_dienst_ids = self._get_nacht_dienst_ids(dienste)
                if nacht_dienst_ids:
                    self._constraint_min_naechte_monat(mitarbeiter, tage, nacht_dienst_ids, min_naechte, regel.prioritaet)

            elif regel.typ == RegelTyp.MIN_WOCHENENDEN_MONAT:
                min_we = params.get('min', 1)
                self._constraint_min_wochenenden_monat(mitarbeiter, dienste, tage, jahr, monat, min_we, regel.prioritaet)

    def _get_nacht_dienst_ids(self, dienste):
        """Erkennt Nachtdienste anhand der Uhrzeit (nicht Kurzname)"""
        nacht_ids = []
        for d in dienste:
            # Nachtdienst = Start >= 20:00 ODER Ende <= 06:00
            if d.start_zeit.hour >= 20 or d.ende_zeit.hour <= 6:
                nacht_ids.append(d.id)
        return nacht_ids

    def _constraint_max_wochenstunden(self, mitarbeiter, dienste, tage, jahr, monat, max_stunden):
        """Maximale Wochenstunden pro Mitarbeiter (gesetzliche Grenze)"""
        from datetime import date as dt_date

        # Gruppiere Tage nach Kalenderwoche
        wochen = {}
        for tag in tage:
            d = dt_date(jahr, monat, tag)
            kw = d.isocalendar()[1]
            if kw not in wochen:
                wochen[kw] = []
            wochen[kw].append(tag)

        for m in mitarbeiter:
            for kw, kw_tage in wochen.items():
                # Berechne Stunden pro Woche
                stunden_vars = []
                for tag in kw_tage:
                    for d in dienste:
                        if (m.id, tag, d.id) in self.shifts:
                            # Stunden * 10 um Dezimalstellen zu vermeiden (OR-Tools braucht Integer)
                            stunden_x10 = int(d.get_dauer_stunden() * 10)
                            stunden_vars.append(stunden_x10 * self.shifts[(m.id, tag, d.id)])

                if stunden_vars:
                    # max_stunden * 10 wegen Skalierung
                    self.model.Add(sum(stunden_vars) <= max_stunden * 10)

    def _constraint_max_tage_folge(self, mitarbeiter, dienste, tage, max_tage):
        """Maximal X aufeinanderfolgende Arbeitstage (mit individuellem Override).

        Nutzt vorberechnete has_shift_vars (inkl. Vormonat für Cross-Month).
        """
        for m in mitarbeiter:
            ma_max_tage = m.get_regel_wert('MAX_TAGE_FOLGE', max_tage)

            # Erweiterte Startposition: zurück in Vormonat für monatsübergreifende Fenster
            min_start = 1 - ma_max_tage  # z.B. -4 bei max_tage=5
            max_start = tage[-1] - ma_max_tage  # Letzter gültiger Fenster-Start

            for start_tag in range(min_start, max_start + 1):
                consecutive_shifts = []
                for offset in range(ma_max_tage + 1):
                    tag = start_tag + offset
                    if (m.id, tag) in self.has_shift_vars:
                        consecutive_shifts.append(self.has_shift_vars[(m.id, tag)])

                if len(consecutive_shifts) > ma_max_tage:
                    self.model.Add(sum(consecutive_shifts) <= ma_max_tage)

    def _constraint_min_ruhezeit(self, mitarbeiter, dienste, tage, jahr, monat, min_stunden):
        """Mindest-Ruhezeit zwischen Diensten - prüft ALLE Dienstpaare.

        Berücksichtigt auch den letzten Dienst des Vormonats (Cross-Month).
        """
        dienst_map = {d.id: d for d in dienste}

        # Cross-Month: Ruhezeit vom letzten Vormonatstag zu Tag 1
        if self.vormonat_dienste and self.vormonat_letzter_tag:
            for m in mitarbeiter:
                if (m.id, 0) not in self.vormonat_dienste:
                    continue  # Hat am letzten VM-Tag nicht gearbeitet

                d1_id = self.vormonat_dienste[(m.id, 0)]
                d1 = dienst_map.get(d1_id)
                if not d1:
                    continue

                vm_last_date = date(self.vormonat_jahr, self.vormonat_monat, self.vormonat_letzter_tag)
                first_date = date(jahr, monat, 1)

                for d2 in dienste:
                    if (m.id, 1, d2.id) not in self.shifts:
                        continue

                    ende = datetime.combine(vm_last_date, d1.ende_zeit)
                    if d1.ende_zeit <= d1.start_zeit:
                        # Nachtdienst: endet am nächsten Tag (= 1. des aktuellen Monats)
                        ende = datetime.combine(first_date, d1.ende_zeit)

                    start = datetime.combine(first_date, d2.start_zeit)
                    ruhezeit = (start - ende).total_seconds() / 3600

                    if ruhezeit < min_stunden:
                        # Fixierter Vormonat-Dienst -> harter Ausschluss
                        self.model.Add(self.shifts[(m.id, 1, d2.id)] == 0)

        # Innerhalb des Monats: alle Dienstpaare prüfen
        for m in mitarbeiter:
            for tag in tage[:-1]:  # All days except last
                naechster_tag = tag + 1
                for d1 in dienste:
                    if (m.id, tag, d1.id) not in self.shifts:
                        continue
                    for d2 in dienste:
                        if (m.id, naechster_tag, d2.id) not in self.shifts:
                            continue

                        # Calculate actual rest time between d1 ending and d2 starting
                        ende = datetime.combine(date(jahr, monat, tag), d1.ende_zeit)
                        # If shift ends after midnight (e.g. 02:00), end is next day
                        if d1.ende_zeit <= d1.start_zeit:
                            ende = datetime.combine(date(jahr, monat, naechster_tag), d1.ende_zeit)

                        start = datetime.combine(date(jahr, monat, naechster_tag), d2.start_zeit)
                        ruhezeit = (start - ende).total_seconds() / 3600

                        if ruhezeit < min_stunden:
                            self.model.Add(
                                self.shifts[(m.id, tag, d1.id)] +
                                self.shifts[(m.id, naechster_tag, d2.id)] <= 1
                                )

    def _constraint_min_personal(self, mitarbeiter, tage, dienst_id, min_personal, bestehende):
        """Mindestbesetzung pro Dienst"""
        for tag in tage:
            # Count existing assignments
            existing_count = sum(
                1 for (mid, t), did in bestehende.items()
                if t == tag and did == dienst_id
            )

            # Variables for this shift
            shift_vars = [
                self.shifts[(m.id, tag, dienst_id)]
                for m in mitarbeiter
                if (m.id, tag, dienst_id) in self.shifts
            ]

            if shift_vars:
                self.model.Add(sum(shift_vars) >= max(0, min_personal - existing_count))

    def _constraint_wochenende_rotation(self, mitarbeiter, dienste, tage, jahr, monat, max_wochenenden):
        """Maximale Wochenenden pro Monat - mit automatischer Anpassung wenn nötig"""
        # Find weekend days
        wochenend_tage = []
        for tag in tage:
            d = date(jahr, monat, tag)
            if d.weekday() >= 5:  # Saturday or Sunday
                wochenend_tage.append(tag)

        # Group by weekend
        wochenenden = []
        current_we = []
        for tag in wochenend_tage:
            if not current_we or tag - current_we[-1] <= 1:
                current_we.append(tag)
            else:
                if current_we:
                    wochenenden.append(current_we)
                current_we = [tag]
        if current_we:
            wochenenden.append(current_we)

        # Automatische Anpassung: Berechne minimale WE pro MA
        anzahl_wochenenden = len(wochenenden)
        min_besetzung_pro_tag = sum(d.min_besetzung or 0 for d in dienste)
        benoetigte_we_slots = anzahl_wochenenden * min_besetzung_pro_tag
        verfuegbare_we_slots = len(mitarbeiter) * max_wochenenden

        # Wenn nicht genug Slots, erhöhe automatisch
        if benoetigte_we_slots > verfuegbare_we_slots:
            import math
            min_noetig = math.ceil(benoetigte_we_slots / len(mitarbeiter))
            if min_noetig > max_wochenenden:
                self.diagnose_info.append({
                    'typ': 'WE_ANPASSUNG',
                    'text': f'Wochenend-Regel automatisch angepasst: {max_wochenenden} → {min_noetig} '
                            f'(Monat hat {anzahl_wochenenden} WE, brauche {benoetigte_we_slots} Slots, '
                            f'habe nur {verfuegbare_we_slots} bei max {max_wochenenden})',
                    'schwere': 'info'
                })
                max_wochenenden = min_noetig

        for m in mitarbeiter:
            # Individuelle Überschreibung prüfen
            ma_max_we = m.get_regel_wert('WOCHENENDE_ROTATION', max_wochenenden)

            we_worked_vars = []
            for we_tage in wochenenden:
                # Did employee work this weekend?
                we_shifts = []
                for tag in we_tage:
                    for d in dienste:
                        if (m.id, tag, d.id) in self.shifts:
                            we_shifts.append(self.shifts[(m.id, tag, d.id)])

                if we_shifts:
                    worked_we = self.model.NewBoolVar(f'worked_we_m{m.id}_we{we_tage[0]}')
                    self.model.Add(sum(we_shifts) >= 1).OnlyEnforceIf(worked_we)
                    self.model.Add(sum(we_shifts) == 0).OnlyEnforceIf(worked_we.Not())
                    we_worked_vars.append(worked_we)

            if we_worked_vars:
                self.model.Add(sum(we_worked_vars) <= ma_max_we)

    def _constraint_kein_nacht_vor_frueh(self, mitarbeiter, dienste, tage, jahr, monat):
        """Kein Frühdienst nach Nachtdienst"""
        # Find night and early shifts
        nacht_dienste = [d for d in dienste if 'nacht' in d.name.lower() or d.start_zeit.hour >= 20]
        frueh_dienste = [d for d in dienste if 'früh' in d.name.lower() or d.start_zeit.hour < 9]

        for m in mitarbeiter:
            for tag in tage[:-1]:
                naechster_tag = tag + 1
                for nd in nacht_dienste:
                    for fd in frueh_dienste:
                        if (m.id, tag, nd.id) in self.shifts and (m.id, naechster_tag, fd.id) in self.shifts:
                            self.model.Add(
                                self.shifts[(m.id, tag, nd.id)] +
                                self.shifts[(m.id, naechster_tag, fd.id)] <= 1
                            )

    def _constraint_qualifikation_pflicht(self, mitarbeiter, tage, dienst_id, qual_id, min_anzahl, bestehende):
        """Qualifikations-Pflicht für Dienst"""
        # Find qualified employees
        qualifizierte = [m for m in mitarbeiter if m.hat_qualifikation(qual_id)]

        for tag in tage:
            # Count existing qualified assignments
            existing_qual_count = sum(
                1 for (mid, t), did in bestehende.items()
                if t == tag and did == dienst_id and any(m.id == mid for m in qualifizierte)
            )

            # Variables for qualified staff on this shift
            qual_shift_vars = [
                self.shifts[(m.id, tag, dienst_id)]
                for m in qualifizierte
                if (m.id, tag, dienst_id) in self.shifts
            ]

            if qual_shift_vars:
                needed = max(0, min_anzahl - existing_qual_count)
                self.model.Add(sum(qual_shift_vars) >= needed)

    def _apply_qualifikation_erforderlich(self, mitarbeiter, dienste, tage):
        """Verhindert Zuweisung von Diensten an MA ohne erforderliche Qualifikation"""
        for d in dienste:
            # Prüfe ob der Dienst erforderliche Qualifikationen hat
            erforderliche = d.get_erforderliche_qualifikationen()
            if not erforderliche:
                continue  # Keine Einschränkung für diesen Dienst

            for m in mitarbeiter:
                # Wenn MA nicht die erforderliche Qualifikation hat, darf er nicht eingeplant werden
                if not d.kann_mitarbeiter_arbeiten(m):
                    for tag in tage:
                        if (m.id, tag, d.id) in self.shifts:
                            self.model.Add(self.shifts[(m.id, tag, d.id)] == 0)

    def _apply_qualifikation_min_anzahl(self, mitarbeiter, dienste, tage, bestehende):
        """Erzwingt Mindestanzahl qualifiziertes Personal pro Dienst (aus DienstQualifikation)"""
        for d in dienste:
            for dq in d.qualifikation_anforderungen:
                if dq.min_anzahl and dq.min_anzahl > 0:
                    # Finde alle MA mit dieser Qualifikation (inkl. inkludierte)
                    qualifizierte_ma = []
                    for m in mitarbeiter:
                        if m.hat_qualifikation(dq.qualifikation_id):
                            qualifizierte_ma.append(m)

                    for tag in tage:
                        # Zähle bereits bestehende qualifizierte Zuweisungen
                        existing_qual_count = sum(
                            1 for (mid, t), did in bestehende.items()
                            if t == tag and did == d.id and any(qm.id == mid for qm in qualifizierte_ma)
                        )

                        # Variablen für qualifizierte MA an diesem Tag/Dienst
                        qual_shift_vars = [
                            self.shifts[(m.id, tag, d.id)]
                            for m in qualifizierte_ma
                            if (m.id, tag, d.id) in self.shifts
                        ]

                        if qual_shift_vars:
                            needed = max(0, dq.min_anzahl - existing_qual_count)
                            if needed > 0:
                                self.model.Add(sum(qual_shift_vars) >= needed)

    def _apply_qualifikation_min_anzahl_soft(self, mitarbeiter, dienste, tage, bestehende):
        """Soft-Constraint für Mindestanzahl qualifiziertes Personal (hoher Bonus im Objective)

        Verwendet capped-Variablen um sicherzustellen, dass der Bonus nur für
        tatsächliche Erfüllung der Mindestanzahl gegeben wird.
        """
        for d in dienste:
            for dq in d.qualifikation_anforderungen:
                if dq.min_anzahl and dq.min_anzahl > 0:
                    # Finde alle MA mit dieser Qualifikation
                    qualifizierte_ma = [m for m in mitarbeiter if m.hat_qualifikation(dq.qualifikation_id)]

                    for tag in tage:
                        # Variablen für qualifizierte MA an diesem Tag/Dienst
                        qual_shift_vars = [
                            self.shifts[(m.id, tag, d.id)]
                            for m in qualifizierte_ma
                            if (m.id, tag, d.id) in self.shifts
                        ]

                        if qual_shift_vars:
                            # Erstelle capped variable: min(zugewiesene_qualifizierte, min_anzahl)
                            # Das gibt Bonus für jeden erfüllten Slot bis zum Minimum
                            qual_capped = self.model.NewIntVar(
                                0, dq.min_anzahl,
                                f'qual_capped_d{d.id}_q{dq.qualifikation_id}_t{tag}'
                            )
                            self.model.Add(qual_capped <= sum(qual_shift_vars))

                            # Hoher Bonus pro erfüllter Qualifikations-Position
                            self.soft_penalties.append(200 * qual_capped)

    def _apply_besetzung_constraints(self, mitarbeiter, dienste, tage, bestehende):
        """Wendet Min/Max-Besetzung aus Dienst-Model an"""
        for dienst in dienste:
            for tag in tage:
                # Count existing assignments
                existing_count = sum(
                    1 for (mid, t), did in bestehende.items()
                    if t == tag and did == dienst.id
                )

                # Variables for this shift
                shift_vars = [
                    self.shifts[(m.id, tag, dienst.id)]
                    for m in mitarbeiter
                    if (m.id, tag, dienst.id) in self.shifts
                ]

                if shift_vars:
                    # Minimum constraint
                    if dienst.min_besetzung and dienst.min_besetzung > 0:
                        needed = max(0, dienst.min_besetzung - existing_count)
                        self.model.Add(sum(shift_vars) >= needed)

                    # Maximum constraint
                    if dienst.max_besetzung is not None:
                        allowed = max(0, dienst.max_besetzung - existing_count)
                        self.model.Add(sum(shift_vars) <= allowed)

    def _constraint_dienst_block(self, mitarbeiter, tage, dienst_id, min_folge, max_folge, prioritaet):
        """Dienst nur als Block (z.B. Nächte nur als 2-4er Block)"""
        for m in mitarbeiter:
            for start_tag in tage:
                if (m.id, start_tag, dienst_id) not in self.shifts:
                    continue

                # Check if this is the START of a block (previous day no shift or doesn't exist)
                prev_tag = start_tag - 1
                is_block_start = self.model.NewBoolVar(f'block_start_m{m.id}_t{start_tag}_d{dienst_id}')

                if prev_tag < 1 or (m.id, prev_tag, dienst_id) not in self.shifts:
                    # Previous day doesn't exist or no variable - if we work today, it's a block start
                    self.model.Add(is_block_start == self.shifts[(m.id, start_tag, dienst_id)])
                else:
                    # Block starts if: we work today AND didn't work yesterday
                    self.model.Add(is_block_start == 1).OnlyEnforceIf([
                        self.shifts[(m.id, start_tag, dienst_id)],
                        self.shifts[(m.id, prev_tag, dienst_id)].Not()
                    ])
                    self.model.Add(is_block_start == 0).OnlyEnforceIf(
                        self.shifts[(m.id, start_tag, dienst_id)].Not()
                    )
                    self.model.Add(is_block_start == 0).OnlyEnforceIf(
                        self.shifts[(m.id, prev_tag, dienst_id)]
                    )

                # If block starts, ensure minimum consecutive days (for hard/soft rules)
                if prioritaet <= 2:  # Hard or soft
                    # Check if enough days remain for min_folge
                    can_complete_block = True
                    for offset in range(1, min_folge):
                        next_tag = start_tag + offset
                        if next_tag not in tage or (m.id, next_tag, dienst_id) not in self.shifts:
                            can_complete_block = False
                            break

                    if can_complete_block:
                        for offset in range(1, min_folge):
                            next_tag = start_tag + offset
                            # If block starts at start_tag, must work next_tag too
                            self.model.Add(
                                self.shifts[(m.id, next_tag, dienst_id)] >= is_block_start
                            )
                    else:
                        # Not enough days to complete min_folge block - prevent block start here
                        self.model.Add(is_block_start == 0)

                # Max block length: after max_folge days, must have a break
                if prioritaet <= 2 and max_folge:
                    break_tag = start_tag + max_folge
                    if break_tag in tage and (m.id, break_tag, dienst_id) in self.shifts:
                        # If block started at start_tag, must NOT work on break_tag
                        self.model.Add(
                            self.shifts[(m.id, break_tag, dienst_id)] <= 1 - is_block_start
                        )

    def _constraint_kein_wechsel(self, mitarbeiter, tage, von_dienst_id, nach_dienst_id, prioritaet):
        """Kein direkter Wechsel von einem Dienst zum anderen"""
        for m in mitarbeiter:
            for tag in tage[:-1]:
                naechster_tag = tag + 1
                if (m.id, tag, von_dienst_id) in self.shifts and (m.id, naechster_tag, nach_dienst_id) in self.shifts:
                    if prioritaet == 1:  # Hart
                        self.model.Add(
                            self.shifts[(m.id, tag, von_dienst_id)] +
                            self.shifts[(m.id, naechster_tag, nach_dienst_id)] <= 1
                        )
                    else:
                        # Weich: Penalty wenn beide Dienste zugewiesen werden
                        # Erstelle Hilfsvariable: both_assigned = von UND nach
                        both_assigned = self.model.NewBoolVar(
                            f'wechsel_m{m.id}_t{tag}_von{von_dienst_id}_nach{nach_dienst_id}'
                        )
                        self.model.Add(
                            self.shifts[(m.id, tag, von_dienst_id)] +
                            self.shifts[(m.id, naechster_tag, nach_dienst_id)] >= 2
                        ).OnlyEnforceIf(both_assigned)
                        self.model.Add(
                            self.shifts[(m.id, tag, von_dienst_id)] +
                            self.shifts[(m.id, naechster_tag, nach_dienst_id)] <= 1
                        ).OnlyEnforceIf(both_assigned.Not())
                        # Penalty: -20 für jeden unerwünschten Wechsel
                        self.soft_penalties.append(-20 * both_assigned)

    def _constraint_max_dienst_pro_woche(self, mitarbeiter, tage, jahr, monat, dienst_id, max_pro_woche, prioritaet):
        """Maximale Anzahl eines Dienstes pro Woche"""
        from datetime import date as dt_date

        # Group days by calendar week
        wochen = {}
        for tag in tage:
            d = dt_date(jahr, monat, tag)
            kw = d.isocalendar()[1]
            if kw not in wochen:
                wochen[kw] = []
            wochen[kw].append(tag)

        for m in mitarbeiter:
            for kw, kw_tage in wochen.items():
                shift_vars = [
                    self.shifts[(m.id, tag, dienst_id)]
                    for tag in kw_tage
                    if (m.id, tag, dienst_id) in self.shifts
                ]
                if shift_vars and prioritaet <= 2:  # Hart oder weich
                    self.model.Add(sum(shift_vars) <= max_pro_woche)

    def _constraint_freie_tage_nach_block(self, mitarbeiter, dienste, tage, dienst_id, min_frei, prioritaet):
        """Mindestens X freie Tage nach einem Blockdienst (Nacht etc.)"""
        if prioritaet > 2:  # Nur hart oder weich
            return

        for m in mitarbeiter:
            for tag in tage:
                if (m.id, tag, dienst_id) not in self.shifts:
                    continue

                works_today = self.shifts[(m.id, tag, dienst_id)]
                next_tag = tag + 1

                # Case 1: End of month or no variable for tomorrow
                if next_tag not in tage or (m.id, next_tag, dienst_id) not in self.shifts:
                    # Check if all required free days fall within this month
                    all_frei_in_month = all(
                        tag + offset in tage
                        for offset in range(1, min_frei + 1)
                    )
                    if all_frei_in_month:
                        # If works today, enforce free days
                        for offset in range(1, min_frei + 1):
                            frei_tag = tag + offset
                            for d in dienste:
                                if (m.id, frei_tag, d.id) in self.shifts:
                                    self.model.Add(works_today + self.shifts[(m.id, frei_tag, d.id)] <= 1)
                    else:
                        # Not enough days remaining - prevent block from ending here
                        # Block can only end if followed by min_frei free days
                        self.model.Add(works_today == 0)
                        self.diagnose_info.append({
                            'typ': 'BLOCK_MONATSENDE',
                            'schwere': 'info',
                            'nachricht': f'MA {m.id}: Blockdienst {dienst_id} an Tag {tag} '
                                        f'verhindert - nicht genug freie Tage bis Monatsende'
                        })
                    continue

                # Case 2: Both today and tomorrow variables exist
                works_tomorrow = self.shifts[(m.id, next_tag, dienst_id)]

                # Simpler approach: directly enforce
                # "If I work today but NOT tomorrow, then I can't work for min_frei days"
                # This is: works_today=1 AND works_tomorrow=0 => no work on frei_tag
                # Equivalent to: works_today + (1-works_tomorrow) + frei_tag_shift <= 2
                # Which is: works_today - works_tomorrow + frei_tag_shift <= 1

                # Check if all required free days fall within this month
                all_frei_in_month = all(
                    tag + offset in tage
                    for offset in range(1, min_frei + 1)
                )

                for offset in range(1, min_frei + 1):
                    frei_tag = tag + offset
                    if frei_tag in tage:
                        for d in dienste:
                            if (m.id, frei_tag, d.id) in self.shifts:
                                # works_today - works_tomorrow + frei_shift <= 1
                                # If works_today=1, works_tomorrow=0: frei_shift <= 0
                                # If works_today=1, works_tomorrow=1: frei_shift <= 1 (ok, in block)
                                # If works_today=0: frei_shift <= 1 (ok, didn't work)
                                self.model.Add(
                                    works_today - works_tomorrow + self.shifts[(m.id, frei_tag, d.id)] <= 1
                                )

                # If free days extend beyond month: prevent block from ending here
                if not all_frei_in_month:
                    # Block must NOT end at this day (must continue to next day or not work)
                    # works_today=1 AND works_tomorrow=0 is forbidden
                    self.model.Add(works_today <= works_tomorrow)

    def _constraint_kein_wochenende(self, tage, jahr, monat, dienst_id):
        """Verhindert einen Dienst am Wochenende (Samstag/Sonntag)"""
        for tag in tage:
            datum = date(jahr, monat, tag)
            # weekday() returns 5 for Saturday, 6 for Sunday
            if datum.weekday() >= 5:
                # Remove all shift variables for this day and dienst
                for key in list(self.shifts.keys()):
                    if key[1] == tag and key[2] == dienst_id:
                        # Force this shift to be 0
                        self.model.Add(self.shifts[key] == 0)

    def _constraint_nacht_bloecke(self, mitarbeiter, tage, nacht_dienst_ids, min_bloecke=2, max_bloecke=3):
        """Begrenzt die Anzahl der Nacht-Blöcke pro Mitarbeiter pro Monat.

        Ein Block beginnt wenn: Nacht an Tag X UND keine Nacht an Tag X-1

        Mit min_bloecke > 1 werden die Nächte auf mehrere Blöcke verteilt,
        z.B. min=2, max=3 bedeutet: 8 Nächte müssen auf 2-3 Blöcke verteilt werden.
        """
        for m in mitarbeiter:
            block_starts = []
            night_worked_vars = []  # Alle Nacht-Variablen für diesen MA

            for tag in tage:
                # Prüfe ob es Nacht-Variablen für diesen Tag gibt
                nacht_vars_heute = [
                    self.shifts[(m.id, tag, d_id)]
                    for d_id in nacht_dienst_ids
                    if (m.id, tag, d_id) in self.shifts
                ]

                if not nacht_vars_heute:
                    continue

                # works_night_today = 1 wenn irgendein Nachtdienst
                works_night_today = self.model.NewBoolVar(f'night_m{m.id}_t{tag}')
                self.model.Add(sum(nacht_vars_heute) >= 1).OnlyEnforceIf(works_night_today)
                self.model.Add(sum(nacht_vars_heute) == 0).OnlyEnforceIf(works_night_today.Not())
                night_worked_vars.append(works_night_today)

                prev_tag = tag - 1
                if prev_tag < 1:
                    # Erster Tag des Monats - wenn Nacht, dann Block-Start
                    block_starts.append(works_night_today)
                else:
                    # Prüfe ob gestern Nacht
                    nacht_vars_gestern = [
                        self.shifts[(m.id, prev_tag, d_id)]
                        for d_id in nacht_dienst_ids
                        if (m.id, prev_tag, d_id) in self.shifts
                    ]

                    if not nacht_vars_gestern:
                        # Gestern keine Nacht-Variable -> wenn heute Nacht, dann Block-Start
                        block_starts.append(works_night_today)
                    else:
                        # Block-Start = heute Nacht UND gestern keine Nacht
                        works_night_yesterday = self.model.NewBoolVar(f'night_m{m.id}_t{prev_tag}_prev')
                        self.model.Add(sum(nacht_vars_gestern) >= 1).OnlyEnforceIf(works_night_yesterday)
                        self.model.Add(sum(nacht_vars_gestern) == 0).OnlyEnforceIf(works_night_yesterday.Not())

                        # is_block_start = works_night_today AND NOT works_night_yesterday
                        is_block_start = self.model.NewBoolVar(f'block_start_m{m.id}_t{tag}')

                        # is_block_start => works_night_today
                        self.model.Add(works_night_today >= is_block_start)
                        # is_block_start => NOT works_night_yesterday
                        self.model.Add(works_night_yesterday <= 1 - is_block_start)
                        # works_night_today AND NOT works_night_yesterday => is_block_start
                        self.model.Add(is_block_start >= works_night_today - works_night_yesterday)

                        block_starts.append(is_block_start)

            if block_starts:
                # Maximum Blöcke
                self.model.Add(sum(block_starts) <= max_bloecke)

                # Minimum Blöcke - nur wenn MA überhaupt Nächte hat
                # Bedingung: Wenn mindestens 1 Nacht gearbeitet wird, müssen es mind. min_bloecke Blöcke sein
                if night_worked_vars and min_bloecke > 1:
                    # has_any_night = 1 wenn mindestens eine Nacht gearbeitet wird
                    has_any_night = self.model.NewBoolVar(f'has_night_m{m.id}')
                    self.model.Add(sum(night_worked_vars) >= 1).OnlyEnforceIf(has_any_night)
                    self.model.Add(sum(night_worked_vars) == 0).OnlyEnforceIf(has_any_night.Not())

                    # Wenn Nächte gearbeitet werden, dann mindestens min_bloecke Blöcke
                    # has_any_night => sum(block_starts) >= min_bloecke
                    self.model.Add(sum(block_starts) >= min_bloecke).OnlyEnforceIf(has_any_night)

    def _constraint_max_naechte_monat(self, mitarbeiter, tage, nacht_dienst_ids, max_naechte):
        """Begrenzt die absolute Anzahl an Nachtdiensten pro Mitarbeiter pro Monat."""
        for m in mitarbeiter:
            # Individuelle Überschreibung prüfen
            ma_max_naechte = m.get_regel_wert('MAX_NAECHTE_MONAT', max_naechte)

            nacht_vars = []
            for tag in tage:
                for d_id in nacht_dienst_ids:
                    if (m.id, tag, d_id) in self.shifts:
                        nacht_vars.append(self.shifts[(m.id, tag, d_id)])

            if nacht_vars:
                self.model.Add(sum(nacht_vars) <= ma_max_naechte)

    def _constraint_min_naechte_monat(self, mitarbeiter, tage, nacht_dienst_ids, min_naechte_vollzeit, prioritaet):
        """Mindestanzahl Nachtdienste pro Mitarbeiter für faire Verteilung.

        Der Wert wird proportional zum Stellenanteil angepasst.
        Als Soft-Constraint implementiert, da nicht jeder Nächte machen kann/will.
        """
        VOLLZEIT_STUNDEN = self.vollzeit_stunden

        for m in mitarbeiter:
            # Individuelle Überschreibung prüfen (0 = befreit von Nachtpflicht)
            if 'MIN_NAECHTE_MONAT' in m.regel_ausnahmen:
                min_naechte = m.regel_ausnahmen['MIN_NAECHTE_MONAT']
            else:
                # Berechne individuelles Minimum basierend auf Stellenanteil
                stunden = m.arbeitsstunden_woche or VOLLZEIT_STUNDEN
                stellenanteil = stunden / VOLLZEIT_STUNDEN
                min_naechte = max(0, int(min_naechte_vollzeit * stellenanteil))

            if min_naechte == 0:
                continue

            nacht_vars = []
            for tag in tage:
                for d_id in nacht_dienst_ids:
                    if (m.id, tag, d_id) in self.shifts:
                        nacht_vars.append(self.shifts[(m.id, tag, d_id)])

            if not nacht_vars:
                continue

            if prioritaet == 1:
                # Hart: Muss erfüllt werden
                self.model.Add(sum(nacht_vars) >= min_naechte)
            else:
                # Weich: Bonus für Erfüllung des Minimums
                # Erstelle capped variable: min(zugewiesene_naechte, min_naechte)
                nacht_capped = self.model.NewIntVar(0, min_naechte, f'nacht_min_m{m.id}')
                self.model.Add(nacht_capped <= sum(nacht_vars))
                # Bonus pro erfüllter Nacht bis zum Minimum (< Coverage-Gewicht)
                self.soft_penalties.append(30 * nacht_capped)

    def _constraint_min_wochenenden_monat(self, mitarbeiter, dienste, tage, jahr, monat, min_we_vollzeit, prioritaet):
        """Mindestanzahl Wochenenden pro Mitarbeiter für faire Verteilung.

        Der Wert wird proportional zum Stellenanteil angepasst.
        """
        VOLLZEIT_STUNDEN = self.vollzeit_stunden

        # Identifiziere Wochenend-Tage und gruppiere nach Wochenende
        wochenenden = []
        current_we = []
        for tag in tage:
            d = date(jahr, monat, tag)
            if d.weekday() >= 5:  # Samstag oder Sonntag
                current_we.append(tag)
            elif current_we:
                wochenenden.append(current_we)
                current_we = []
        if current_we:
            wochenenden.append(current_we)

        if not wochenenden:
            return

        for m in mitarbeiter:
            # Individuelle Überschreibung prüfen (0 = befreit von WE-Pflicht)
            if 'MIN_WOCHENENDEN_MONAT' in m.regel_ausnahmen:
                min_we = m.regel_ausnahmen['MIN_WOCHENENDEN_MONAT']
            else:
                # Berechne individuelles Minimum basierend auf Stellenanteil
                stunden = m.arbeitsstunden_woche or VOLLZEIT_STUNDEN
                stellenanteil = stunden / VOLLZEIT_STUNDEN
                min_we = max(0, int(min_we_vollzeit * stellenanteil + 0.5))  # Aufrunden bei >= 0.5

            if min_we == 0:
                continue

            # Zähle gearbeitete Wochenenden
            we_worked_vars = []
            for we_tage in wochenenden:
                we_shifts = []
                for tag in we_tage:
                    for d in dienste:
                        if (m.id, tag, d.id) in self.shifts:
                            we_shifts.append(self.shifts[(m.id, tag, d.id)])

                if we_shifts:
                    worked_we = self.model.NewBoolVar(f'worked_we_min_m{m.id}_we{we_tage[0]}')
                    self.model.Add(sum(we_shifts) >= 1).OnlyEnforceIf(worked_we)
                    self.model.Add(sum(we_shifts) == 0).OnlyEnforceIf(worked_we.Not())
                    we_worked_vars.append(worked_we)

            if not we_worked_vars:
                continue

            if prioritaet == 1:
                # Hart: Muss erfüllt werden
                self.model.Add(sum(we_worked_vars) >= min_we)
            else:
                # Weich: Bonus für Erfüllung des Minimums
                we_capped = self.model.NewIntVar(0, min_we, f'we_min_m{m.id}')
                self.model.Add(we_capped <= sum(we_worked_vars))
                # Bonus pro erfülltem Wochenende bis zum Minimum (< Coverage-Gewicht)
                self.soft_penalties.append(40 * we_capped)

    def _apply_mitarbeiter_einschraenkungen(self, mitarbeiter, dienste, tage, jahr, monat):
        """Wendet Mitarbeiter-spezifische Dienst-Einschränkungen an.

        Beispiel: Johannes darf am Wochenende NUR Frühdienst machen.
        Das bedeutet: An Wochenend-Tagen werden alle anderen Dienste für Johannes verboten.
        """
        for m in mitarbeiter:
            # Lade aktive Einschränkungen für diesen Mitarbeiter
            einschraenkungen = [e for e in m.dienst_einschraenkungen if e.aktiv]

            if not einschraenkungen:
                continue

            for tag in tage:
                datum = date(jahr, monat, tag)

                # Sammle alle Einschränkungen, die für dieses Datum gelten
                geltende_einschraenkungen = [
                    e for e in einschraenkungen if e.matches_date(datum)
                ]

                if not geltende_einschraenkungen:
                    continue

                # Sammle alle erlaubten Dienste für diesen Tag
                erlaubte_dienst_ids = set(e.nur_dienst_id for e in geltende_einschraenkungen)

                # Verbiete alle anderen Dienste
                for d in dienste:
                    if d.id not in erlaubte_dienst_ids:
                        if (m.id, tag, d.id) in self.shifts:
                            self.model.Add(self.shifts[(m.id, tag, d.id)] == 0)

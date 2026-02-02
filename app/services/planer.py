"""
Automatische Dienstplanung mit OR-Tools Constraint Programming
"""
from ortools.sat.python import cp_model
from datetime import date, timedelta, datetime
from calendar import monthrange
from app import db
from app.models import (
    Mitarbeiter, Dienst, Dienstplan, DienstplanStatus,
    MitarbeiterWunsch, WunschTyp, Regel, RegelTyp,
    MitarbeiterDienstPraeferenz, MitarbeiterDienstEinschraenkung, TagTyp
)


class DienstPlaner:
    """Optimierungsbasierte Dienstplanung"""

    def __init__(self):
        self.model = None
        self.solver = None
        self.shifts = {}  # (mitarbeiter_id, tag, dienst_id) -> BoolVar
        self.diagnose_info = []  # Sammelt Diagnose-Informationen

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
        self.diagnose_info = []

        # Get data
        mitarbeiter = Mitarbeiter.query.filter_by(aktiv=True).all()
        dienste = Dienst.query.all()
        regeln = Regel.query.filter_by(aktiv=True).all()

        if not mitarbeiter:
            return {'erfolg': False, 'fehler': 'Keine aktiven Mitarbeiter vorhanden', 'eintraege': 0, 'warnungen': [], 'diagnose': []}

        if not dienste:
            return {'erfolg': False, 'fehler': 'Keine Dienste konfiguriert', 'eintraege': 0, 'warnungen': [], 'diagnose': []}

        # Calculate days in month
        _, num_days = monthrange(jahr, monat)
        tage = list(range(1, num_days + 1))

        # Delete existing entries if requested
        if ueberschreiben:
            start_datum = date(jahr, monat, 1)
            ende_datum = date(jahr, monat, num_days)
            Dienstplan.query.filter(
                Dienstplan.datum >= start_datum,
                Dienstplan.datum <= ende_datum
            ).delete()
            db.session.commit()

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
        objective_terms = []

        # Coverage bonus: reward each assigned shift
        for key, var in self.shifts.items():
            objective_terms.append(var)

        # Wish penalties/bonuses
        for m in mitarbeiter:
            for tag in tage:
                if (m.id, tag) in wuensche:
                    for w in wuensche[(m.id, tag)]:
                        if w.wunsch_typ == WunschTyp.FREI:
                            # Penalty for working when wants to be free
                            for d in dienste:
                                if (m.id, tag, d.id) in self.shifts:
                                    objective_terms.append(-10 * self.shifts[(m.id, tag, d.id)])
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
                                objective_terms.append(5 * self.shifts[(m.id, tag, w.dienst_id)])

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

                    # Soft penalty for not meeting minimum
                    if pref.min_pro_monat and pref.min_pro_monat > 0:
                        # Add bonus for each shift up to minimum
                        for var in shift_count_vars[:pref.min_pro_monat]:
                            objective_terms.append(3 * var)

                    # Soft penalty for exceeding maximum
                    if pref.max_pro_monat is not None:
                        # Penalty for shifts beyond maximum
                        for i, var in enumerate(shift_count_vars):
                            if i >= pref.max_pro_monat:
                                objective_terms.append(-5 * var)

        if objective_terms:
            self.model.Maximize(sum(objective_terms))

        # Pre-solve diagnostics
        diagnose = self._diagnose_probleme(mitarbeiter, dienste, tage, bestehende)
        # Füge Diagnose-Infos aus Constraint-Anwendung hinzu
        diagnose.extend(self.diagnose_info)
        warnungen = []

        # Solve
        self.solver = cp_model.CpSolver()
        self.solver.parameters.max_time_in_seconds = 60.0
        status = self.solver.Solve(self.model)

        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            # Extract solution
            eintraege = 0
            for m in mitarbeiter:
                for tag in tage:
                    if (m.id, tag) in bestehende:
                        continue

                    for d in dienste:
                        if (m.id, tag, d.id) in self.shifts:
                            if self.solver.Value(self.shifts[(m.id, tag, d.id)]) == 1:
                                dp = Dienstplan(
                                    datum=date(jahr, monat, tag),
                                    mitarbeiter_id=m.id,
                                    dienst_id=d.id,
                                    status=DienstplanStatus.GEPLANT
                                )
                                db.session.add(dp)
                                eintraege += 1

            db.session.commit()

            # Check for under-staffing warnings
            warnungen = self._pruefe_besetzung(dienste, tage, jahr, monat)

            return {
                'erfolg': True,
                'eintraege': eintraege,
                'fehler': None,
                'warnungen': warnungen,
                'diagnose': diagnose
            }
        else:
            # INFEASIBLE - try best-possible mode
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

    def _generiere_best_possible(self, jahr, monat, mitarbeiter, dienste, tage, bestehende, wuensche, diagnose):
        """Generiert beste mögliche Lösung ohne harte Besetzungs-Constraints"""
        warnungen = []
        warnungen.append('Vollständige Planung nicht möglich - erstelle beste Teillösung.')

        # Create new model with relaxed constraints
        self.model = cp_model.CpModel()
        self.shifts = {}

        # Create shift variables
        for m in mitarbeiter:
            for tag in tage:
                if (m.id, tag) in bestehende:
                    continue
                for d in dienste:
                    var_name = f'shift_m{m.id}_t{tag}_d{d.id}'
                    self.shifts[(m.id, tag, d.id)] = self.model.NewBoolVar(var_name)

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
        VOLLZEIT_STUNDEN = 38.5
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
                                    objective_terms.append(-10 * self.shifts[(m.id, tag, d.id)])
                        elif w.wunsch_typ == WunschTyp.DIENST_WUNSCH and w.dienst_id:
                            if (m.id, tag, w.dienst_id) in self.shifts:
                                objective_terms.append(5 * self.shifts[(m.id, tag, w.dienst_id)])

        if objective_terms:
            self.model.Maximize(sum(objective_terms))

        # Solve relaxed model
        self.solver = cp_model.CpSolver()
        self.solver.parameters.max_time_in_seconds = 60.0
        status = self.solver.Solve(self.model)

        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            eintraege = 0
            for m in mitarbeiter:
                for tag in tage:
                    if (m.id, tag) in bestehende:
                        continue
                    for d in dienste:
                        if (m.id, tag, d.id) in self.shifts:
                            if self.solver.Value(self.shifts[(m.id, tag, d.id)]) == 1:
                                dp = Dienstplan(
                                    datum=date(jahr, monat, tag),
                                    mitarbeiter_id=m.id,
                                    dienst_id=d.id,
                                    status=DienstplanStatus.GEPLANT
                                )
                                db.session.add(dp)
                                eintraege += 1

            db.session.commit()

            # Check what's missing
            besetzungs_probleme = self._pruefe_besetzung(dienste, tage, jahr, monat)
            warnungen.extend(besetzungs_probleme)

            return {
                'erfolg': True,
                'teilweise': True,
                'eintraege': eintraege,
                'fehler': None,
                'warnungen': warnungen,
                'diagnose': diagnose
            }
        else:
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
                nacht_dienst_ids = [d.id for d in dienste if d.kurzname in ['N', 'ND']]
                if nacht_dienst_ids:
                    self._constraint_nacht_bloecke(mitarbeiter, tage, nacht_dienst_ids, min_bloecke, max_bloecke)

            elif regel.typ == RegelTyp.MAX_NAECHTE_MONAT:
                max_naechte = params.get('max', 8)
                nacht_dienst_ids = [d.id for d in dienste if d.kurzname in ['N', 'ND']]
                if nacht_dienst_ids:
                    self._constraint_max_naechte_monat(mitarbeiter, tage, nacht_dienst_ids, max_naechte)

    def _constraint_max_tage_folge(self, mitarbeiter, dienste, tage, max_tage):
        """Maximal X aufeinanderfolgende Arbeitstage"""
        for m in mitarbeiter:
            for start_tag in range(1, len(tage) - max_tage + 1):
                # If all days from start_tag to start_tag + max_tage have a shift,
                # at least one must be 0
                consecutive_shifts = []
                for offset in range(max_tage + 1):
                    tag = start_tag + offset
                    if tag > len(tage):
                        break
                    day_shifts = [
                        self.shifts[(m.id, tag, d.id)]
                        for d in dienste
                        if (m.id, tag, d.id) in self.shifts
                    ]
                    if day_shifts:
                        # At least one shift this day
                        has_shift = self.model.NewBoolVar(f'has_shift_m{m.id}_t{tag}')
                        self.model.Add(sum(day_shifts) >= 1).OnlyEnforceIf(has_shift)
                        self.model.Add(sum(day_shifts) == 0).OnlyEnforceIf(has_shift.Not())
                        consecutive_shifts.append(has_shift)

                if len(consecutive_shifts) > max_tage:
                    # At least one of these days must be free
                    self.model.Add(sum(consecutive_shifts) <= max_tage)

    def _constraint_min_ruhezeit(self, mitarbeiter, dienste, tage, jahr, monat, min_stunden):
        """Mindest-Ruhezeit zwischen Diensten"""
        # Find night shifts (ending after 22:00 or before 06:00)
        nacht_dienste = [d for d in dienste if d.ende_zeit.hour <= 6 or d.ende_zeit.hour >= 22]
        frueh_dienste = [d for d in dienste if d.start_zeit.hour < 10]

        for m in mitarbeiter:
            for tag in tage[:-1]:  # All days except last
                naechster_tag = tag + 1
                for nd in nacht_dienste:
                    for fd in frueh_dienste:
                        # Calculate rest time
                        ende = datetime.combine(date(jahr, monat, tag), nd.ende_zeit)
                        if nd.ende_zeit.hour <= 6:
                            ende = datetime.combine(date(jahr, monat, naechster_tag), nd.ende_zeit)

                        start = datetime.combine(date(jahr, monat, naechster_tag), fd.start_zeit)
                        ruhezeit = (start - ende).total_seconds() / 3600

                        if ruhezeit < min_stunden:
                            # Can't have night shift followed by early shift
                            if (m.id, tag, nd.id) in self.shifts and (m.id, naechster_tag, fd.id) in self.shifts:
                                self.model.Add(
                                    self.shifts[(m.id, tag, nd.id)] +
                                    self.shifts[(m.id, naechster_tag, fd.id)] <= 1
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
                self.model.Add(sum(we_worked_vars) <= max_wochenenden)

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
        from app.models import DienstQualifikation

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
                    for offset in range(1, min_folge):
                        next_tag = start_tag + offset
                        if next_tag in tage and (m.id, next_tag, dienst_id) in self.shifts:
                            # If block starts at start_tag, must work next_tag too
                            self.model.Add(
                                self.shifts[(m.id, next_tag, dienst_id)] >= is_block_start
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
                    # Weich/Optional: wird über Objective-Penalties gehandhabt (TODO)

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
                    # If works today, enforce free days
                    for offset in range(1, min_frei + 1):
                        frei_tag = tag + offset
                        if frei_tag in tage:
                            for d in dienste:
                                if (m.id, frei_tag, d.id) in self.shifts:
                                    self.model.Add(works_today + self.shifts[(m.id, frei_tag, d.id)] <= 1)
                    continue

                # Case 2: Both today and tomorrow variables exist
                works_tomorrow = self.shifts[(m.id, next_tag, dienst_id)]

                # Simpler approach: directly enforce
                # "If I work today but NOT tomorrow, then I can't work for min_frei days"
                # This is: works_today=1 AND works_tomorrow=0 => no work on frei_tag
                # Equivalent to: works_today + (1-works_tomorrow) + frei_tag_shift <= 2
                # Which is: works_today - works_tomorrow + frei_tag_shift <= 1

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
            nacht_vars = []
            for tag in tage:
                for d_id in nacht_dienst_ids:
                    if (m.id, tag, d_id) in self.shifts:
                        nacht_vars.append(self.shifts[(m.id, tag, d_id)])

            if nacht_vars:
                self.model.Add(sum(nacht_vars) <= max_naechte)

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

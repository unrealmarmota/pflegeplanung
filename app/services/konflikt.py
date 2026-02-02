"""
Konflikterkennung für Dienstpläne
"""
from datetime import date, datetime, timedelta
from calendar import monthrange
from collections import defaultdict
from app import db
from app.models import (
    Mitarbeiter, Dienst, Dienstplan, DienstQualifikation,
    MitarbeiterWunsch, WunschTyp, Regel, RegelTyp
)


class Konflikt:
    """Repräsentiert einen erkannten Konflikt"""

    def __init__(self, typ, beschreibung, schwere='warnung', datum=None, mitarbeiter=None, details=None):
        self.typ = typ
        self.beschreibung = beschreibung
        self.schwere = schwere  # 'kritisch', 'warnung', 'info'
        self.datum = datum
        self.mitarbeiter = mitarbeiter
        self.details = details

    def to_dict(self):
        return {
            'typ': self.typ,
            'beschreibung': self.beschreibung,
            'schwere': self.schwere,
            'datum': self.datum.isoformat() if self.datum else None,
            'mitarbeiter': self.mitarbeiter,
            'details': self.details
        }


class KonfliktErkennung:
    """Service zur Erkennung von Planungskonflikten"""

    def pruefe_monat(self, jahr, monat):
        """
        Prüft alle Dienstpläne eines Monats auf Konflikte

        Returns:
            Liste von Konflikt-Objekten
        """
        konflikte = []

        # Get date range
        _, num_days = monthrange(jahr, monat)
        start_datum = date(jahr, monat, 1)
        ende_datum = date(jahr, monat, num_days)

        # Load data
        dienstplaene = Dienstplan.query.filter(
            Dienstplan.datum >= start_datum,
            Dienstplan.datum <= ende_datum
        ).all()

        mitarbeiter = Mitarbeiter.query.filter_by(aktiv=True).all()
        dienste = Dienst.query.all()
        regeln = Regel.query.filter_by(aktiv=True).all()
        wuensche = MitarbeiterWunsch.query.filter(
            MitarbeiterWunsch.datum >= start_datum,
            MitarbeiterWunsch.datum <= ende_datum
        ).all()

        # Organize data
        plan_by_date_ma = defaultdict(list)  # (datum, ma_id) -> [dienstplan]
        plan_by_date = defaultdict(list)  # datum -> [dienstplan]

        for dp in dienstplaene:
            plan_by_date_ma[(dp.datum, dp.mitarbeiter_id)].append(dp)
            plan_by_date[dp.datum].append(dp)

        wunsch_by_date_ma = {}
        for w in wuensche:
            wunsch_by_date_ma[(w.datum, w.mitarbeiter_id)] = w

        # Check for conflicts
        konflikte.extend(self._pruefe_doppelbelegung(plan_by_date_ma))
        konflikte.extend(self._pruefe_unterbesetzung(plan_by_date, dienste, start_datum, ende_datum, regeln))
        konflikte.extend(self._pruefe_qualifikationsmangel(plan_by_date, dienste, start_datum, ende_datum))
        konflikte.extend(self._pruefe_ruhezeit(dienstplaene, mitarbeiter, regeln))
        konflikte.extend(self._pruefe_max_tage_folge(dienstplaene, mitarbeiter, regeln))
        konflikte.extend(self._pruefe_wochenende_rotation(dienstplaene, mitarbeiter, regeln, jahr, monat))
        konflikte.extend(self._pruefe_wunsch_konflikte(plan_by_date_ma, wunsch_by_date_ma))

        # Sort by severity
        schwere_order = {'kritisch': 0, 'warnung': 1, 'info': 2}
        konflikte.sort(key=lambda k: (schwere_order.get(k.schwere, 99), k.datum or date.min))

        return konflikte

    def _pruefe_doppelbelegung(self, plan_by_date_ma):
        """Prüft auf Doppelbelegung (Mitarbeiter mehrfach am gleichen Tag)"""
        konflikte = []

        for (datum, ma_id), plaene in plan_by_date_ma.items():
            if len(plaene) > 1:
                ma = Mitarbeiter.query.get(ma_id)
                dienste = [p.dienst.name for p in plaene]
                konflikte.append(Konflikt(
                    typ='Doppelbelegung',
                    beschreibung=f'{ma.name} ist mehrfach eingeplant',
                    schwere='kritisch',
                    datum=datum,
                    mitarbeiter=ma.name,
                    details=f'Dienste: {", ".join(dienste)}'
                ))

        return konflikte

    def _pruefe_unterbesetzung(self, plan_by_date, dienste, start_datum, ende_datum, regeln):
        """Prüft auf Unterbesetzung"""
        konflikte = []

        # Get minimum staffing rules
        min_personal_regeln = {}
        for r in regeln:
            if r.typ == RegelTyp.MIN_PERSONAL_DIENST and r.aktiv:
                params = r.parameter
                dienst_id = params.get('dienst_id')
                min_anzahl = params.get('min', 0)
                if dienst_id:
                    min_personal_regeln[dienst_id] = max(
                        min_personal_regeln.get(dienst_id, 0),
                        min_anzahl
                    )

        # Check each day
        current = start_datum
        while current <= ende_datum:
            tages_plaene = plan_by_date[current]
            dienst_counts = defaultdict(int)

            for dp in tages_plaene:
                dienst_counts[dp.dienst_id] += 1

            for dienst in dienste:
                min_required = min_personal_regeln.get(dienst.id, 0)
                actual = dienst_counts.get(dienst.id, 0)

                if actual < min_required:
                    konflikte.append(Konflikt(
                        typ='Unterbesetzung',
                        beschreibung=f'{dienst.name}: {actual}/{min_required} besetzt',
                        schwere='kritisch',
                        datum=current,
                        details=f'Es fehlen {min_required - actual} Mitarbeiter'
                    ))

            current += timedelta(days=1)

        return konflikte

    def _pruefe_qualifikationsmangel(self, plan_by_date, dienste, start_datum, ende_datum):
        """Prüft auf Qualifikationsmangel"""
        konflikte = []

        # Get qualification requirements per shift
        dienst_quals = {}
        for d in dienste:
            for dq in d.qualifikation_anforderungen:
                if d.id not in dienst_quals:
                    dienst_quals[d.id] = []
                dienst_quals[d.id].append((dq.qualifikation_id, dq.qualifikation.name, dq.min_anzahl))

        # Check each day
        current = start_datum
        while current <= ende_datum:
            tages_plaene = plan_by_date[current]

            # Group by shift
            plaene_by_dienst = defaultdict(list)
            for dp in tages_plaene:
                plaene_by_dienst[dp.dienst_id].append(dp)

            for dienst_id, quals in dienst_quals.items():
                for qual_id, qual_name, min_anzahl in quals:
                    # Count qualified staff
                    qualified_count = 0
                    for dp in plaene_by_dienst[dienst_id]:
                        if dp.mitarbeiter.hat_qualifikation(qual_id):
                            qualified_count += 1

                    if qualified_count < min_anzahl:
                        dienst = Dienst.query.get(dienst_id)
                        konflikte.append(Konflikt(
                            typ='Qualifikationsmangel',
                            beschreibung=f'{dienst.name}: Zu wenig {qual_name}',
                            schwere='kritisch',
                            datum=current,
                            details=f'{qualified_count}/{min_anzahl} mit Qualifikation "{qual_name}"'
                        ))

            current += timedelta(days=1)

        return konflikte

    def _pruefe_ruhezeit(self, dienstplaene, mitarbeiter, regeln):
        """Prüft Ruhezeiten zwischen Diensten"""
        konflikte = []

        # Find minimum rest time rule
        min_ruhezeit = 11  # Default
        for r in regeln:
            if r.typ == RegelTyp.MIN_RUHEZEIT and r.aktiv:
                min_ruhezeit = r.parameter.get('stunden', 11)
                break

        # Group schedules by employee
        plaene_by_ma = defaultdict(list)
        for dp in dienstplaene:
            plaene_by_ma[dp.mitarbeiter_id].append(dp)

        for ma_id, plaene in plaene_by_ma.items():
            # Sort by date
            plaene.sort(key=lambda p: p.datum)

            for i in range(len(plaene) - 1):
                dp1 = plaene[i]
                dp2 = plaene[i + 1]

                # Check if consecutive days
                if (dp2.datum - dp1.datum).days != 1:
                    continue

                # Calculate rest time
                ende1 = datetime.combine(dp1.datum, dp1.dienst.ende_zeit)
                if dp1.dienst.ende_zeit < dp1.dienst.start_zeit:
                    # Shift goes past midnight
                    ende1 = datetime.combine(dp1.datum + timedelta(days=1), dp1.dienst.ende_zeit)

                start2 = datetime.combine(dp2.datum, dp2.dienst.start_zeit)

                ruhezeit = (start2 - ende1).total_seconds() / 3600

                if ruhezeit < min_ruhezeit:
                    konflikte.append(Konflikt(
                        typ='Ruhezeit-Verletzung',
                        beschreibung=f'Nur {ruhezeit:.1f}h Ruhezeit (min. {min_ruhezeit}h)',
                        schwere='kritisch',
                        datum=dp2.datum,
                        mitarbeiter=dp1.mitarbeiter.name,
                        details=f'{dp1.dienst.name} -> {dp2.dienst.name}'
                    ))

        return konflikte

    def _pruefe_max_tage_folge(self, dienstplaene, mitarbeiter, regeln):
        """Prüft maximale aufeinanderfolgende Arbeitstage"""
        konflikte = []

        # Find max consecutive days rule
        max_tage = 5  # Default
        for r in regeln:
            if r.typ == RegelTyp.MAX_TAGE_FOLGE and r.aktiv:
                max_tage = r.parameter.get('max', 5)
                break

        # Group by employee
        plaene_by_ma = defaultdict(set)
        for dp in dienstplaene:
            plaene_by_ma[dp.mitarbeiter_id].add(dp.datum)

        for ma_id, tage in plaene_by_ma.items():
            if not tage:
                continue

            tage_sorted = sorted(tage)
            streak = 1
            streak_start = tage_sorted[0]

            for i in range(1, len(tage_sorted)):
                if (tage_sorted[i] - tage_sorted[i-1]).days == 1:
                    streak += 1
                else:
                    # Check if streak exceeded
                    if streak > max_tage:
                        ma = Mitarbeiter.query.get(ma_id)
                        konflikte.append(Konflikt(
                            typ='Zu viele Arbeitstage',
                            beschreibung=f'{streak} Tage am Stück (max. {max_tage})',
                            schwere='warnung',
                            datum=streak_start,
                            mitarbeiter=ma.name,
                            details=f'Von {streak_start.strftime("%d.%m.")} bis {tage_sorted[i-1].strftime("%d.%m.")}'
                        ))
                    streak = 1
                    streak_start = tage_sorted[i]

            # Check final streak
            if streak > max_tage:
                ma = Mitarbeiter.query.get(ma_id)
                konflikte.append(Konflikt(
                    typ='Zu viele Arbeitstage',
                    beschreibung=f'{streak} Tage am Stück (max. {max_tage})',
                    schwere='warnung',
                    datum=streak_start,
                    mitarbeiter=ma.name
                ))

        return konflikte

    def _pruefe_wochenende_rotation(self, dienstplaene, mitarbeiter, regeln, jahr, monat):
        """Prüft Wochenend-Rotation"""
        konflikte = []

        # Find weekend rotation rule
        max_wochenenden = 2  # Default
        for r in regeln:
            if r.typ == RegelTyp.WOCHENENDE_ROTATION and r.aktiv:
                max_wochenenden = r.parameter.get('max', 2)
                break

        # Identify weekend days
        _, num_days = monthrange(jahr, monat)
        wochenend_tage = set()
        for tag in range(1, num_days + 1):
            d = date(jahr, monat, tag)
            if d.weekday() >= 5:
                wochenend_tage.add(d)

        # Count weekend work per employee
        we_by_ma = defaultdict(set)
        for dp in dienstplaene:
            if dp.datum in wochenend_tage:
                # Track which weekend (use the Saturday date)
                saturday = dp.datum
                if dp.datum.weekday() == 6:  # Sunday
                    saturday = dp.datum - timedelta(days=1)
                we_by_ma[dp.mitarbeiter_id].add(saturday)

        for ma_id, wochenenden in we_by_ma.items():
            if len(wochenenden) > max_wochenenden:
                ma = Mitarbeiter.query.get(ma_id)
                konflikte.append(Konflikt(
                    typ='Wochenend-Überschreitung',
                    beschreibung=f'{len(wochenenden)} Wochenenden (max. {max_wochenenden})',
                    schwere='warnung',
                    mitarbeiter=ma.name,
                    details=f'Wochenenden: {", ".join(d.strftime("%d.%m.") for d in sorted(wochenenden))}'
                ))

        return konflikte

    def _pruefe_wunsch_konflikte(self, plan_by_date_ma, wunsch_by_date_ma):
        """Prüft auf Konflikte mit Mitarbeiterwünschen"""
        konflikte = []

        for (datum, ma_id), wunsch in wunsch_by_date_ma.items():
            plaene = plan_by_date_ma.get((datum, ma_id), [])

            if wunsch.wunsch_typ == WunschTyp.FREI and plaene:
                ma = Mitarbeiter.query.get(ma_id)
                konflikte.append(Konflikt(
                    typ='Wunsch-Konflikt',
                    beschreibung=f'Frei-Wunsch nicht berücksichtigt',
                    schwere='info',
                    datum=datum,
                    mitarbeiter=ma.name,
                    details=f'Eingeplant: {plaene[0].dienst.name}'
                ))

            elif wunsch.wunsch_typ == WunschTyp.NICHT_VERFUEGBAR and plaene:
                ma = Mitarbeiter.query.get(ma_id)
                konflikte.append(Konflikt(
                    typ='Verfügbarkeits-Konflikt',
                    beschreibung=f'Als nicht verfügbar markiert, aber eingeplant',
                    schwere='kritisch',
                    datum=datum,
                    mitarbeiter=ma.name,
                    details=f'Eingeplant: {plaene[0].dienst.name}'
                ))

            elif wunsch.wunsch_typ == WunschTyp.DIENST_WUNSCH and wunsch.dienst_id:
                if plaene and plaene[0].dienst_id != wunsch.dienst_id:
                    ma = Mitarbeiter.query.get(ma_id)
                    konflikte.append(Konflikt(
                        typ='Dienstwunsch-Konflikt',
                        beschreibung=f'Anderer Dienst als gewünscht',
                        schwere='info',
                        datum=datum,
                        mitarbeiter=ma.name,
                        details=f'Gewünscht: {wunsch.dienst.name}, Eingeplant: {plaene[0].dienst.name}'
                    ))

        return konflikte

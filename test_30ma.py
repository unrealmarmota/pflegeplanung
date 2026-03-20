#!/usr/bin/env python3
"""
Testlauf: 30 Mitarbeiter, 14 FWB, diverse Stellenanteile, Wünsche
"""
import os
import sys
import random
from datetime import date, time

# Temporäre Test-DB verwenden
os.environ['PFLEGEPLANUNG_DB_PATH'] = '/tmp/test_30ma.db'

# DB-Datei löschen falls vorhanden
if os.path.exists('/tmp/test_30ma.db'):
    os.remove('/tmp/test_30ma.db')

from app import create_app, db
from app.models import (
    Qualifikation, Mitarbeiter, MitarbeiterQualifikation,
    Dienst, DienstQualifikation, Regel, RegelTyp,
    MitarbeiterWunsch, WunschTyp, User
)
from app.services.planer import DienstPlaner

app = create_app('testing')

with app.app_context():
    db.create_all()

    # --- Qualifikationen ---
    qual_exam = Qualifikation(
        name='Examinierte Pflegekraft',
        beschreibung='3-jährige Ausbildung',
        farbe='#28a745'
    )
    qual_fwb = Qualifikation(
        name='Fachweiterbildung (FWB)',
        beschreibung='FWB Intensivpflege/Anästhesie',
        farbe='#dc3545',
        inkludiert_id=None  # wird nach flush gesetzt
    )
    qual_helfer = Qualifikation(
        name='Pflegehelferin',
        beschreibung='1-jährige Ausbildung',
        farbe='#6c757d'
    )
    qual_praxis = Qualifikation(
        name='Praxisanleiterin',
        beschreibung='Zusatzqualifikation',
        farbe='#007bff'
    )

    db.session.add_all([qual_exam, qual_fwb, qual_helfer, qual_praxis])
    db.session.flush()

    # FWB inkludiert Examinierte
    qual_fwb.inkludiert_id = qual_exam.id
    db.session.flush()

    # --- Dienste ---
    dienst_frueh = Dienst(
        name='Frühdienst', kurzname='F',
        start_zeit=time(6, 0), ende_zeit=time(14, 0),
        farbe='#ffc107', min_besetzung=4, max_besetzung=7
    )
    dienst_spaet = Dienst(
        name='Spätdienst', kurzname='S',
        start_zeit=time(14, 0), ende_zeit=time(22, 0),
        farbe='#17a2b8', min_besetzung=4, max_besetzung=7
    )
    dienst_nacht = Dienst(
        name='Nachtdienst', kurzname='N',
        start_zeit=time(22, 0), ende_zeit=time(6, 0),
        farbe='#343a40', min_besetzung=2, max_besetzung=3
    )

    db.session.add_all([dienst_frueh, dienst_spaet, dienst_nacht])
    db.session.flush()

    # Qualifikationsanforderungen pro Dienst
    # erforderlich=False: Helfer dürfen mitarbeiten, aber min_anzahl Examinierte pro Schicht
    for dienst, min_exam in [(dienst_frueh, 2), (dienst_spaet, 2), (dienst_nacht, 1)]:
        db.session.add(DienstQualifikation(
            dienst_id=dienst.id,
            qualifikation_id=qual_exam.id,
            min_anzahl=min_exam,
            erforderlich=False
        ))

    # --- 30 Mitarbeiter ---
    vornamen = [
        'Anna', 'Bernd', 'Clara', 'David', 'Eva',
        'Frank', 'Gabi', 'Hans', 'Inga', 'Jan',
        'Katrin', 'Lars', 'Maria', 'Norbert', 'Olga',
        'Peter', 'Rita', 'Stefan', 'Tanja', 'Uwe',
        'Vera', 'Werner', 'Xenia', 'Yannick', 'Zara',
        'Birgit', 'Carsten', 'Doris', 'Emil', 'Frieda'
    ]
    nachnamen = [
        'Müller', 'Schmidt', 'Weber', 'Fischer', 'Braun',
        'Meyer', 'Schulz', 'Wagner', 'Becker', 'Hoffmann',
        'Koch', 'Richter', 'Klein', 'Wolf', 'Schröder',
        'Neumann', 'Schwarz', 'Zimmermann', 'Krüger', 'Hartmann',
        'Lange', 'Schmitt', 'Krause', 'Lehmann', 'Köhler',
        'Maier', 'König', 'Walter', 'Jäger', 'Berger'
    ]

    # 16 Vollzeit (100%), Rest 50-80%
    stellenanteile = (
        [100.0] * 16 +
        [80.0] * 5 +
        [75.0] * 4 +
        [60.0] * 3 +
        [50.0] * 2
    )

    # Qualifikationen: 14 FWB (inkl. Exam), weitere Exam, Rest Helfer
    # FWB: Mitarbeiter 0-13
    # Nur Exam: Mitarbeiter 14-23
    # Helfer: Mitarbeiter 24-29
    mitarbeiter_liste = []

    for i in range(30):
        ma = Mitarbeiter(
            name=f'{vornamen[i]} {nachnamen[i]}',
            personalnummer=f'P{i+1:03d}',
            email=f'{vornamen[i].lower()}.{nachnamen[i].lower()}@pflege.de',
            stellenanteil=stellenanteile[i],
            eintrittsdatum=date(2020, 1, 1),
            aktiv=True
        )
        db.session.add(ma)
        db.session.flush()
        mitarbeiter_liste.append(ma)

        if i < 14:
            # FWB (inkludiert Exam)
            db.session.add(MitarbeiterQualifikation(
                mitarbeiter_id=ma.id,
                qualifikation_id=qual_fwb.id,
                erworben_am=date(2019, 1, 1)
            ))
        elif i < 24:
            # Nur Examiniert
            db.session.add(MitarbeiterQualifikation(
                mitarbeiter_id=ma.id,
                qualifikation_id=qual_exam.id,
                erworben_am=date(2019, 1, 1)
            ))
        else:
            # Pflegehelfer
            db.session.add(MitarbeiterQualifikation(
                mitarbeiter_id=ma.id,
                qualifikation_id=qual_helfer.id,
                erworben_am=date(2019, 1, 1)
            ))

        # 2 Praxisanleiter dazu
        if i in [0, 7]:
            db.session.add(MitarbeiterQualifikation(
                mitarbeiter_id=ma.id,
                qualifikation_id=qual_praxis.id,
                erworben_am=date(2020, 6, 1)
            ))

    # --- Wünsche für März 2026 ---
    # Einige Frei-Wünsche
    wuensche = [
        # Anna will am 6.+7. März frei (Freitag/Samstag)
        (mitarbeiter_liste[0], date(2026, 3, 6), WunschTyp.FREI),
        (mitarbeiter_liste[0], date(2026, 3, 7), WunschTyp.FREI),
        # Bernd ist am 10.-12. nicht verfügbar (Fortbildung)
        (mitarbeiter_liste[1], date(2026, 3, 10), WunschTyp.NICHT_VERFUEGBAR),
        (mitarbeiter_liste[1], date(2026, 3, 11), WunschTyp.NICHT_VERFUEGBAR),
        (mitarbeiter_liste[1], date(2026, 3, 12), WunschTyp.NICHT_VERFUEGBAR),
        # Clara will am 20. Frühdienst
        (mitarbeiter_liste[2], date(2026, 3, 20), WunschTyp.DIENST_WUNSCH),
        # Eva will am 15.+16. frei (Wochenende)
        (mitarbeiter_liste[4], date(2026, 3, 14), WunschTyp.FREI),
        (mitarbeiter_liste[4], date(2026, 3, 15), WunschTyp.FREI),
        # Lars ist am 25. nicht verfügbar
        (mitarbeiter_liste[11], date(2026, 3, 25), WunschTyp.NICHT_VERFUEGBAR),
        # Tanja will am 1.+2. frei
        (mitarbeiter_liste[18], date(2026, 3, 1), WunschTyp.FREI),
        (mitarbeiter_liste[18], date(2026, 3, 2), WunschTyp.FREI),
        # Vera nicht verfügbar 18.-20.
        (mitarbeiter_liste[20], date(2026, 3, 18), WunschTyp.NICHT_VERFUEGBAR),
        (mitarbeiter_liste[20], date(2026, 3, 19), WunschTyp.NICHT_VERFUEGBAR),
        (mitarbeiter_liste[20], date(2026, 3, 20), WunschTyp.NICHT_VERFUEGBAR),
    ]

    for ma, datum, typ in wuensche:
        w = MitarbeiterWunsch(
            mitarbeiter_id=ma.id,
            datum=datum,
            wunsch_typ=typ,
            dienst_id=dienst_frueh.id if typ == WunschTyp.DIENST_WUNSCH else None,
        )
        db.session.add(w)

    # --- Regeln ---
    regeln = [
        Regel(name='Max. 5 Tage hintereinander', typ=RegelTyp.MAX_TAGE_FOLGE,
              parameter={'max': 5}, prioritaet=1, aktiv=True),
        Regel(name='Min. 11h Ruhezeit', typ=RegelTyp.MIN_RUHEZEIT,
              parameter={'stunden': 11}, prioritaet=1, aktiv=True),
        Regel(name='Max. 48 Wochenstunden', typ=RegelTyp.MAX_WOCHENSTUNDEN,
              parameter={'stunden': 48}, prioritaet=1, aktiv=True),
        Regel(name='Mind. 4 Personen Frühdienst', typ=RegelTyp.MIN_PERSONAL_DIENST,
              parameter={'dienst_id': dienst_frueh.id, 'min': 4}, prioritaet=1, aktiv=True),
        Regel(name='Mind. 4 Personen Spätdienst', typ=RegelTyp.MIN_PERSONAL_DIENST,
              parameter={'dienst_id': dienst_spaet.id, 'min': 4}, prioritaet=1, aktiv=True),
        Regel(name='Mind. 2 Personen Nachtdienst', typ=RegelTyp.MIN_PERSONAL_DIENST,
              parameter={'dienst_id': dienst_nacht.id, 'min': 2}, prioritaet=1, aktiv=True),
        Regel(name='Max. 2 Wochenenden/Monat', typ=RegelTyp.WOCHENENDE_ROTATION,
              parameter={'max': 2}, prioritaet=2, aktiv=True),
        Regel(name='Kein Frühdienst nach Nacht', typ=RegelTyp.KEIN_NACHT_VOR_FRUEH,
              parameter={}, prioritaet=1, aktiv=True),
    ]
    db.session.add_all(regeln)
    db.session.commit()

    # --- Zusammenfassung ---
    fwb_count = MitarbeiterQualifikation.query.filter_by(qualifikation_id=qual_fwb.id).count()
    exam_count = MitarbeiterQualifikation.query.filter_by(qualifikation_id=qual_exam.id).count()
    helfer_count = MitarbeiterQualifikation.query.filter_by(qualifikation_id=qual_helfer.id).count()
    vz_count = Mitarbeiter.query.filter_by(stellenanteil=100.0).count()
    tz_count = Mitarbeiter.query.filter(Mitarbeiter.stellenanteil < 100.0).count()
    wunsch_count = MitarbeiterWunsch.query.count()

    print("=" * 60)
    print("TESTDATEN ERSTELLT")
    print("=" * 60)
    print(f"  Mitarbeiter:    {Mitarbeiter.query.count()}")
    print(f"    Vollzeit:     {vz_count}")
    print(f"    Teilzeit:     {tz_count}")
    print(f"  Qualifikationen:")
    print(f"    FWB:          {fwb_count}")
    print(f"    Examiniert:   {exam_count}")
    print(f"    Helfer:       {helfer_count}")
    print(f"  Wünsche:        {wunsch_count}")
    print(f"  Regeln:         {Regel.query.count()}")
    print(f"  Dienste:        {Dienst.query.count()}")
    print()

    # --- Planung starten ---
    print("=" * 60)
    print("STARTE PLANUNG FÜR MÄRZ 2026...")
    print("=" * 60)

    import time as time_module
    start = time_module.time()

    planer = DienstPlaner()
    result = planer.generiere_plan(2026, 3)

    dauer = time_module.time() - start

    print()
    print("=" * 60)
    print("ERGEBNIS")
    print("=" * 60)
    print(f"  Erfolg:         {result['erfolg']}")
    print(f"  Einträge:       {result.get('eintraege', 0)}")
    print(f"  Dauer:          {dauer:.1f}s")

    if not result['erfolg']:
        print(f"  Fehler:         {result.get('fehler', '?')}")
    else:
        # Statistik
        from app.models import Dienstplan
        from collections import Counter

        alle = Dienstplan.query.filter(
            Dienstplan.datum >= date(2026, 3, 1),
            Dienstplan.datum <= date(2026, 3, 31)
        ).all()

        dienst_counter = Counter()
        ma_counter = Counter()
        for dp in alle:
            dienst_counter[dp.dienst.kurzname] += 1
            ma_counter[dp.mitarbeiter.name] += 1

        print(f"\n  Dienst-Verteilung:")
        for k, v in sorted(dienst_counter.items()):
            print(f"    {k}: {v} Schichten")

        print(f"\n  Schichten pro Mitarbeiter (Top 10 / Bottom 5):")
        sorted_ma = sorted(ma_counter.items(), key=lambda x: -x[1])
        for name, count in sorted_ma[:10]:
            sa = Mitarbeiter.query.filter_by(name=name).first().stellenanteil
            print(f"    {name:25s} {count:3d} Schichten  ({sa:.0f}%)")
        print(f"    ...")
        for name, count in sorted_ma[-5:]:
            sa = Mitarbeiter.query.filter_by(name=name).first().stellenanteil
            print(f"    {name:25s} {count:3d} Schichten  ({sa:.0f}%)")

        # Wünsche prüfen
        print(f"\n  Wunsch-Erfüllung:")
        erfuellt = 0
        verletzt = 0
        for ma, datum, typ in wuensche:
            eintrag = Dienstplan.query.filter_by(
                mitarbeiter_id=ma.id, datum=datum
            ).first()
            if typ in (WunschTyp.FREI, WunschTyp.NICHT_VERFUEGBAR):
                if eintrag is None:
                    erfuellt += 1
                else:
                    verletzt += 1
                    print(f"    VERLETZT: {ma.name} am {datum} hat {eintrag.dienst.kurzname} (wollte frei)")
            elif typ == WunschTyp.DIENST_WUNSCH:
                if eintrag and eintrag.dienst_id == dienst_frueh.id:
                    erfuellt += 1
                else:
                    verletzt += 1
                    d = eintrag.dienst.kurzname if eintrag else 'frei'
                    print(f"    VERLETZT: {ma.name} am {datum} hat {d} (wollte F)")
        print(f"    Erfüllt: {erfuellt}/{erfuellt + verletzt}")

        # === QUALITÄTSPRÜFUNG ===
        print(f"\n  Qualitätsprüfung:")

        # Post-Solve Validierungen
        if 'validierungen' in result and result['validierungen']:
            print(f"    FEHLER: {len(result['validierungen'])} Validierungsfehler!")
            for v in result['validierungen']:
                print(f"      - {v}")
        else:
            print(f"    Keine Validierungsfehler")

        # Objective Breakdown
        if 'objective_breakdown' in result:
            ob = result['objective_breakdown']
            print(f"\n  Objective-Breakdown:")
            for k, v in ob.items():
                print(f"    {k}: {v}")

        # Max consecutive days check
        print(f"\n  Folgetage-Check (max 5):")
        from app.models import Dienstplan as DP
        fehler_folge = 0
        for ma in mitarbeiter_liste:
            consecutive = 0
            for tag in range(1, 32):
                d = date(2026, 3, tag)
                eintrag = DP.query.filter_by(mitarbeiter_id=ma.id, datum=d).first()
                if eintrag:
                    consecutive += 1
                    if consecutive > 5:
                        fehler_folge += 1
                        print(f"    FEHLER: {ma.name} hat {consecutive} Folgetage am {d}")
                else:
                    consecutive = 0
        if fehler_folge == 0:
            print(f"    OK - keine Verletzungen")

        # Rest time check (Spätdienst -> Frühdienst)
        print(f"\n  Ruhezeit-Check (min 11h):")
        fehler_ruhe = 0
        for ma in mitarbeiter_liste:
            for tag in range(1, 31):
                d1 = date(2026, 3, tag)
                d2 = date(2026, 3, tag + 1)
                e1 = DP.query.filter_by(mitarbeiter_id=ma.id, datum=d1).first()
                e2 = DP.query.filter_by(mitarbeiter_id=ma.id, datum=d2).first()
                if e1 and e2:
                    from datetime import datetime as dt
                    ende = dt.combine(d1, e1.dienst.ende_zeit)
                    if e1.dienst.ende_zeit <= e1.dienst.start_zeit:
                        ende = dt.combine(d2, e1.dienst.ende_zeit)
                    start = dt.combine(d2, e2.dienst.start_zeit)
                    ruhe = (start - ende).total_seconds() / 3600
                    if ruhe < 11:
                        fehler_ruhe += 1
                        print(f"    FEHLER: {ma.name} {d1}->{d2}: {ruhe:.1f}h "
                              f"({e1.dienst.kurzname}->{e2.dienst.kurzname})")
        if fehler_ruhe == 0:
            print(f"    OK - keine Verletzungen")

        # Min staffing check
        print(f"\n  Min-Besetzung-Check:")
        fehler_besetzung = 0
        for tag in range(1, 32):
            d = date(2026, 3, tag)
            for dienst_obj in [dienst_frueh, dienst_spaet, dienst_nacht]:
                count = DP.query.filter_by(datum=d, dienst_id=dienst_obj.id).count()
                if count < dienst_obj.min_besetzung:
                    fehler_besetzung += 1
                    print(f"    FEHLER: {d} {dienst_obj.kurzname}: {count}/{dienst_obj.min_besetzung}")
        if fehler_besetzung == 0:
            print(f"    OK - alle Schichten ausreichend besetzt")

    print()

# Aufräumen
db_path = app.config.get('SQLALCHEMY_DATABASE_URI', '').replace('sqlite:///', '')
if db_path and os.path.exists(db_path):
    os.remove(db_path)

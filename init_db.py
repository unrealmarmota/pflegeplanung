#!/usr/bin/env python3
"""
Initialisiert die Datenbank und fügt Beispieldaten hinzu
"""
from datetime import date, time
from app import create_app, db
from app.models import (
    Qualifikation, Mitarbeiter, MitarbeiterQualifikation,
    Dienst, DienstQualifikation, Regel, RegelTyp
)


def init_database():
    """Erstellt die Datenbank-Tabellen"""
    app = create_app('default')

    with app.app_context():
        db.create_all()
        print("Datenbank-Tabellen erstellt.")


def add_sample_data():
    """Fügt Beispieldaten hinzu"""
    app = create_app('default')

    with app.app_context():
        # Check if data already exists
        if Qualifikation.query.count() > 0:
            print("Datenbank enthält bereits Daten. Überspringe Beispieldaten.")
            return

        # Qualifikationen
        qual_examiniert = Qualifikation(
            name='Examinierte Pflegekraft',
            beschreibung='Dreijährige Ausbildung zur Pflegefachkraft',
            farbe='#28a745'
        )
        qual_helfer = Qualifikation(
            name='Pflegehelferin',
            beschreibung='Einjährige Ausbildung zur Pflegehelferin',
            farbe='#6c757d'
        )
        qual_praxisanleiter = Qualifikation(
            name='Praxisanleiterin',
            beschreibung='Zusatzqualifikation zur Anleitung von Auszubildenden',
            farbe='#007bff'
        )
        qual_wundmanagement = Qualifikation(
            name='Wundmanagement',
            beschreibung='Weiterbildung im Bereich Wundversorgung',
            farbe='#dc3545'
        )

        db.session.add_all([qual_examiniert, qual_helfer, qual_praxisanleiter, qual_wundmanagement])
        db.session.flush()

        # Dienste
        dienst_frueh = Dienst(
            name='Frühdienst',
            kurzname='F',
            start_zeit=time(6, 0),
            ende_zeit=time(14, 0),
            farbe='#ffc107',
            min_besetzung=3,
            max_besetzung=5
        )
        dienst_spaet = Dienst(
            name='Spätdienst',
            kurzname='S',
            start_zeit=time(14, 0),
            ende_zeit=time(22, 0),
            farbe='#17a2b8',
            min_besetzung=3,
            max_besetzung=5
        )
        dienst_nacht = Dienst(
            name='Nachtdienst',
            kurzname='N',
            start_zeit=time(22, 0),
            ende_zeit=time(6, 0),
            farbe='#343a40',
            min_besetzung=2,
            max_besetzung=3
        )

        db.session.add_all([dienst_frueh, dienst_spaet, dienst_nacht])
        db.session.flush()

        # Dienstqualifikationen (Mindestbesetzung mit qualifiziertem Personal)
        dq1 = DienstQualifikation(
            dienst_id=dienst_frueh.id,
            qualifikation_id=qual_examiniert.id,
            min_anzahl=2
        )
        dq2 = DienstQualifikation(
            dienst_id=dienst_spaet.id,
            qualifikation_id=qual_examiniert.id,
            min_anzahl=2
        )
        dq3 = DienstQualifikation(
            dienst_id=dienst_nacht.id,
            qualifikation_id=qual_examiniert.id,
            min_anzahl=1
        )

        db.session.add_all([dq1, dq2, dq3])

        # Mitarbeiter
        mitarbeiter_data = [
            ('Anna Müller', 'P001', 'anna.mueller@pflege.de', '+49 151 12345678', 38.5, [qual_examiniert.id, qual_praxisanleiter.id]),
            ('Bernd Schmidt', 'P002', 'bernd.schmidt@pflege.de', '+49 151 23456789', 40.0, [qual_examiniert.id]),
            ('Clara Weber', 'P003', 'clara.weber@pflege.de', '+49 151 34567890', 30.0, [qual_helfer.id]),
            ('David Fischer', 'P004', 'david.fischer@pflege.de', '+49 151 45678901', 38.5, [qual_examiniert.id, qual_wundmanagement.id]),
            ('Eva Braun', 'P005', 'eva.braun@pflege.de', '+49 151 56789012', 40.0, [qual_examiniert.id]),
            ('Frank Meyer', 'P006', 'frank.meyer@pflege.de', '+49 151 67890123', 20.0, [qual_helfer.id]),
            ('Gabi Schulz', 'P007', 'gabi.schulz@pflege.de', '+49 151 78901234', 38.5, [qual_examiniert.id]),
            ('Hans Wagner', 'P008', 'hans.wagner@pflege.de', '+49 151 89012345', 38.5, [qual_examiniert.id, qual_praxisanleiter.id]),
        ]

        for name, pnr, email, telefon, stunden, qual_ids in mitarbeiter_data:
            ma = Mitarbeiter(
                name=name,
                personalnummer=pnr,
                email=email,
                telefon=telefon,
                eintrittsdatum=date(2020, 1, 1),
                arbeitsstunden_woche=stunden,
                aktiv=True
            )
            db.session.add(ma)
            db.session.flush()

            for qual_id in qual_ids:
                mq = MitarbeiterQualifikation(
                    mitarbeiter_id=ma.id,
                    qualifikation_id=qual_id,
                    erworben_am=date(2019, 1, 1)
                )
                db.session.add(mq)

        # Regeln
        regeln = [
            Regel(
                name='Max. 5 Arbeitstage hintereinander',
                typ=RegelTyp.MAX_TAGE_FOLGE,
                parameter={'max': 5},
                prioritaet=1,
                aktiv=True
            ),
            Regel(
                name='Mindestens 11 Stunden Ruhezeit',
                typ=RegelTyp.MIN_RUHEZEIT,
                parameter={'stunden': 11},
                prioritaet=1,
                aktiv=True
            ),
            Regel(
                name='Max. 48 Wochenstunden',
                typ=RegelTyp.MAX_WOCHENSTUNDEN,
                parameter={'stunden': 48},
                prioritaet=1,
                aktiv=True
            ),
            Regel(
                name='Mind. 3 Personen im Frühdienst',
                typ=RegelTyp.MIN_PERSONAL_DIENST,
                parameter={'dienst_id': dienst_frueh.id, 'min': 3},
                prioritaet=1,
                aktiv=True
            ),
            Regel(
                name='Mind. 3 Personen im Spätdienst',
                typ=RegelTyp.MIN_PERSONAL_DIENST,
                parameter={'dienst_id': dienst_spaet.id, 'min': 3},
                prioritaet=1,
                aktiv=True
            ),
            Regel(
                name='Mind. 2 Personen im Nachtdienst',
                typ=RegelTyp.MIN_PERSONAL_DIENST,
                parameter={'dienst_id': dienst_nacht.id, 'min': 2},
                prioritaet=1,
                aktiv=True
            ),
            Regel(
                name='Max. 2 Wochenenden pro Monat',
                typ=RegelTyp.WOCHENENDE_ROTATION,
                parameter={'max': 2},
                prioritaet=2,
                aktiv=True
            ),
            Regel(
                name='Kein Frühdienst nach Nachtdienst',
                typ=RegelTyp.KEIN_NACHT_VOR_FRUEH,
                parameter={},
                prioritaet=1,
                aktiv=True
            ),
        ]

        db.session.add_all(regeln)
        db.session.commit()

        print("Beispieldaten erfolgreich hinzugefügt:")
        print(f"  - {Qualifikation.query.count()} Qualifikationen")
        print(f"  - {Dienst.query.count()} Dienste")
        print(f"  - {Mitarbeiter.query.count()} Mitarbeiter")
        print(f"  - {Regel.query.count()} Regeln")


if __name__ == '__main__':
    print("Initialisiere Pflegeplanungs-Datenbank...")
    init_database()
    add_sample_data()
    print("\nFertig! Starte die Anwendung mit: python run.py")

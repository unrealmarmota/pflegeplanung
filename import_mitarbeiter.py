#!/usr/bin/env python3
"""
Importiert die Mitarbeiterliste mit Qualifikationen
"""
from datetime import date
from app import create_app, db
from app.models import Qualifikation, Mitarbeiter, MitarbeiterQualifikation


# Mitarbeiterdaten: (Name, [Qualifikations-Kürzel])
MITARBEITER_DATEN = [
    ("Alisa Rössel", ["EX"]),
    ("Aslihan Bulut", ["EX", "FWB"]),
    ("Franca Fischer", ["EX"]),
    ("Celina Paulick", ["EX"]),
    ("Christian Matschinsky", ["EX", "FWB", "PAL"]),
    ("Dominic Steinbrenner", ["FWB"]),
    ("Marta Drawzeska", ["EX"]),
    ("Florian Rebmann", ["EX"]),
    ("Raquel Gebhardt", ["EX", "PAL"]),
    ("Griselidis Gimmel", ["EX"]),
    ("Ilicic Neira", ["EX", "PAL"]),
    ("Jana-Maria Köpke", ["EX"]),
    ("Johannes Rincker", ["EX", "FWB", "PAL"]),
    ("Jonas Breiling", ["EX", "FWB"]),
    ("Julia Käfer", ["EX"]),
    ("Julia Kaller", ["EX", "FWB", "PAL"]),
    ("Katrin Stickel", ["EX"]),
    ("Klaus Pulvermüller", ["EX", "FWB", "PAL", "LT"]),
    ("Konstanze Rahel Pyta", ["EX"]),
    ("Lora Schneider", ["EX"]),
    ("Stefan Dziamski", ["EX", "PAL"]),
    ("Maya Baumann", ["EX"]),
    ("Melis Tala Uguroglu", ["FWB", "PAL"]),
    ("Melissa Hadzic", ["EX"]),
    ("Miled Slimene", ["EX"]),
    ("Mónica Rosende", ["EX", "FWB", "PAL"]),
    ("Nrecaj Simon", ["EX"]),
    ("Patrick Steinberg", ["EX", "FWB"]),
    ("Reinhold Groß", ["EX", "FWB", "PAL", "LT"]),
    ("Sandra Sachs", ["EX", "FWB"]),
    ("Sina Schellroth", ["EX"]),
    ("Tahiri Verona", ["EX"]),
    ("Theresa Jöde", ["EX", "FWB"]),
]


def setup_qualifikationen():
    """Stellt sicher, dass alle benötigten Qualifikationen existieren"""
    qual_map = {}

    # Examinierte Pflegekraft (Basis)
    ex = Qualifikation.query.filter_by(name='Examinierte Pflegekraft').first()
    if not ex:
        ex = Qualifikation(
            name='Examinierte Pflegekraft',
            beschreibung='Dreijährige Ausbildung zur Pflegefachkraft',
            farbe='#28a745'
        )
        db.session.add(ex)
        db.session.flush()
        print("✓ Qualifikation 'Examinierte Pflegekraft' erstellt")
    qual_map['EX'] = ex

    # Fachweiterbildung (inkludiert EX)
    fwb = Qualifikation.query.filter_by(name='Fachweiterbildung').first()
    if not fwb:
        fwb = Qualifikation(
            name='Fachweiterbildung',
            beschreibung='Fachweiterbildung Intensiv- und Anästhesiepflege',
            farbe='#007bff',
            inkludiert_id=ex.id
        )
        db.session.add(fwb)
        db.session.flush()
        print("✓ Qualifikation 'Fachweiterbildung' erstellt (inkludiert EX)")
    elif fwb.inkludiert_id != ex.id:
        fwb.inkludiert_id = ex.id
        print("✓ Qualifikation 'Fachweiterbildung' aktualisiert (inkludiert jetzt EX)")
    qual_map['FWB'] = fwb

    # Praxisanleiterin
    pal = Qualifikation.query.filter_by(name='Praxisanleiterin').first()
    if not pal:
        pal = Qualifikation(
            name='Praxisanleiterin',
            beschreibung='Zusatzqualifikation zur Anleitung von Auszubildenden',
            farbe='#6f42c1'
        )
        db.session.add(pal)
        db.session.flush()
        print("✓ Qualifikation 'Praxisanleiterin' erstellt")
    qual_map['PAL'] = pal

    # Leitung
    lt = Qualifikation.query.filter_by(name='Leitung').first()
    if not lt:
        lt = Qualifikation(
            name='Leitung',
            beschreibung='Leitungsfunktion / Stationsleitung',
            farbe='#dc3545'
        )
        db.session.add(lt)
        db.session.flush()
        print("✓ Qualifikation 'Leitung' erstellt")
    qual_map['LT'] = lt

    db.session.commit()
    return qual_map


def generate_personalnummer(index):
    """Generiert eine Personalnummer"""
    return f"P{index:03d}"


def import_mitarbeiter(qual_map):
    """Importiert alle Mitarbeiter"""
    # Finde höchste existierende Personalnummer
    existing = Mitarbeiter.query.all()
    existing_names = {m.name for m in existing}
    max_pnr = 0
    for m in existing:
        if m.personalnummer.startswith('P'):
            try:
                num = int(m.personalnummer[1:])
                max_pnr = max(max_pnr, num)
            except ValueError:
                pass

    added = 0
    skipped = 0

    for name, quals in MITARBEITER_DATEN:
        # Prüfen ob Mitarbeiter schon existiert
        if name in existing_names:
            print(f"  Übersprungen (existiert): {name}")
            skipped += 1
            continue

        max_pnr += 1
        personalnummer = generate_personalnummer(max_pnr)

        ma = Mitarbeiter(
            name=name,
            personalnummer=personalnummer,
            stellenanteil=100.0,
            aktiv=True,
            eintrittsdatum=date.today()
        )
        db.session.add(ma)
        db.session.flush()

        # Qualifikationen zuweisen
        for qual_kuerzel in quals:
            if qual_kuerzel in qual_map:
                mq = MitarbeiterQualifikation(
                    mitarbeiter_id=ma.id,
                    qualifikation_id=qual_map[qual_kuerzel].id,
                    erworben_am=date.today()
                )
                db.session.add(mq)

        qual_str = ", ".join(quals)
        print(f"✓ {name} ({personalnummer}) - {qual_str}")
        added += 1

    db.session.commit()
    return added, skipped


def main():
    app = create_app()

    with app.app_context():
        print("=== Qualifikationen einrichten ===")
        qual_map = setup_qualifikationen()
        print()

        print("=== Mitarbeiter importieren ===")
        added, skipped = import_mitarbeiter(qual_map)
        print()

        print(f"=== Fertig ===")
        print(f"Hinzugefügt: {added}")
        print(f"Übersprungen: {skipped}")
        print(f"Gesamt in DB: {Mitarbeiter.query.count()}")


if __name__ == '__main__':
    main()

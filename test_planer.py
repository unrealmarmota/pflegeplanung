#!/usr/bin/env python3
"""Test-Skript für Diagnose der Planung"""
import sys
sys.path.insert(0, '.')

from app import create_app, db
from app.models import Mitarbeiter, Dienst, Qualifikation, Regel
from app.services.planer import DienstPlaner

app = create_app()

with app.app_context():
    print("=" * 60)
    print("DIAGNOSE DIENSTPLANUNG")
    print("=" * 60)

    # 1. Mitarbeiter-Übersicht
    mitarbeiter = Mitarbeiter.query.filter_by(aktiv=True).all()
    print(f"\n1. MITARBEITER: {len(mitarbeiter)} aktiv")

    # 2. Dienste-Übersicht
    dienste = Dienst.query.all()
    print(f"\n2. DIENSTE: {len(dienste)}")
    for d in dienste:
        erforderliche = d.get_erforderliche_qualifikationen()
        qualifizierte = [m for m in mitarbeiter if d.kann_mitarbeiter_arbeiten(m)]
        print(f"   {d.kurzname:5} ({d.name:20}): min={d.min_besetzung}, "
              f"erforderl.Quali: {[q.name for q in erforderliche] if erforderliche else '-'}, "
              f"qualifizierte MA: {len(qualifizierte)}")

    # 3. Regeln
    regeln = Regel.query.filter_by(aktiv=True).all()
    print(f"\n3. AKTIVE REGELN: {len(regeln)}")
    for r in regeln:
        prio = {1: 'HART', 2: 'WEICH', 3: 'OPTIONAL'}.get(r.prioritaet, '?')
        print(f"   - {r.name} ({r.typ.value}) [{prio}]")

    # 4. Kapazitätsberechnung
    min_pro_tag = sum(d.min_besetzung or 0 for d in dienste)
    print(f"\n4. KAPAZITÄT:")
    print(f"   Mindestbesetzung pro Tag: {min_pro_tag} Schichten")
    print(f"   Bei 28 Tagen: {min_pro_tag * 28} Schichten benötigt")
    print(f"   33 MA × 28 Tage = 924 mögliche Zuweisungen")
    print(f"   -> Durchschnitt: {min_pro_tag * 28 / 33:.1f} Schichten pro MA/Monat")

    # 5. Probleme identifizieren
    print(f"\n5. POTENZIELLE PROBLEME:")
    probleme = []

    for d in dienste:
        erforderliche = d.get_erforderliche_qualifikationen()
        if erforderliche:
            qualifizierte = [m for m in mitarbeiter if d.kann_mitarbeiter_arbeiten(m)]
            if len(qualifizierte) == 0:
                probleme.append(f"KRITISCH: {d.name} - NIEMAND qualifiziert!")
            elif d.min_besetzung and len(qualifizierte) < d.min_besetzung:
                probleme.append(f"KRITISCH: {d.name} - nur {len(qualifizierte)} qualifiziert, aber {d.min_besetzung} benötigt")

    if probleme:
        for p in probleme:
            print(f"   ❌ {p}")
    else:
        print("   ✓ Keine offensichtlichen Qualifikationsprobleme")

    # 6. Planung starten
    print(f"\n6. STARTE PLANUNG FÜR FEBRUAR 2026...")
    print("-" * 60)

    planer = DienstPlaner()
    result = planer.generiere_plan(2026, 2, ueberschreiben=True)

    print(f"\nERGEBNIS:")
    print(f"   Erfolg: {result['erfolg']}")
    print(f"   Teilweise: {result.get('teilweise', False)}")
    print(f"   Einträge: {result['eintraege']}")
    if result.get('fehler'):
        print(f"   Fehler: {result['fehler']}")

    if result.get('diagnose'):
        print(f"\n   DIAGNOSE:")
        for d in result['diagnose']:
            print(f"   - [{d['schwere'].upper()}] {d['text']}")

    if result.get('warnungen'):
        print(f"\n   WARNUNGEN ({len(result['warnungen'])} Stück):")
        for w in result['warnungen'][:10]:
            print(f"   - {w}")
        if len(result['warnungen']) > 10:
            print(f"   ... und {len(result['warnungen']) - 10} weitere")

    print("\n" + "=" * 60)

# Personalplanungs-Software für Pflegestationen

Eine Python-Web-Anwendung zur automatischen Dienstplanung von Pflegepersonal mit Qualifikationsverwaltung, regelbasierter automatischer Planung und Konflikterkennung.

## Features

- **Mitarbeiterverwaltung**: Verwaltung von Pflegepersonal mit Qualifikationen
- **Dienstverwaltung**: Flexible Konfiguration von Schichten (Früh-, Spät-, Nachtdienst)
- **Qualifikationsverwaltung**: Definition und Zuweisung von Berufsqualifikationen
- **Regelverwaltung**: Konfigurierbare Planungsregeln (Ruhezeiten, max. Arbeitstage, etc.)
- **Automatische Planung**: OR-Tools basierte Optimierung unter Berücksichtigung aller Constraints
- **Konflikterkennung**: Automatische Prüfung auf Regelverstöße und Konflikte
- **Wunschverwaltung**: Mitarbeiter können Wünsche für freie Tage eintragen
- **Export**: PDF und Excel Export der Dienstpläne

## Installation

### Voraussetzungen

- Python 3.11 oder höher
- pip (Python Package Manager)

### Schritte

1. **Virtuelle Umgebung erstellen** (empfohlen):
```bash
cd pflegeplanung
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# oder: venv\Scripts\activate  # Windows
```

2. **Abhängigkeiten installieren**:
```bash
pip install -r requirements.txt
```

3. **Datenbank initialisieren**:
```bash
python init_db.py
```

4. **Anwendung starten**:
```bash
python run.py
```

5. **Browser öffnen**:
```
http://localhost:5000
```

## Projektstruktur

```
pflegeplanung/
├── app/
│   ├── __init__.py          # Flask App-Factory
│   ├── models/              # Datenmodelle (SQLAlchemy)
│   ├── routes/              # API-Routen
│   ├── services/            # Business-Logik
│   ├── static/              # CSS, JavaScript
│   └── templates/           # HTML-Templates
├── tests/                   # Unit- und Integrationstests
├── config.py               # Konfiguration
├── requirements.txt        # Abhängigkeiten
├── init_db.py             # Datenbankinitialisierung
└── run.py                 # Startskript
```

## Datenmodell

### Mitarbeiter
- Name, Personalnummer, Kontaktdaten
- Wöchentliche Arbeitsstunden
- Zugewiesene Qualifikationen

### Qualifikationen
- Examinierte Pflegekraft, Pflegehelferin, Praxisanleiterin, etc.
- Gültigkeitszeitraum für Zertifizierungen

### Dienste
- Frei konfigurierbare Schichten
- Start- und Endzeit
- Qualifikationsanforderungen (z.B. mind. 2 Examinierte)

### Regeln
- Harte Regeln (müssen eingehalten werden)
- Weiche Regeln (sollten möglichst eingehalten werden)
- Verschiedene Regeltypen:
  - Max. aufeinanderfolgende Arbeitstage
  - Mindest-Ruhezeit zwischen Diensten
  - Maximale Wochenstunden
  - Mindestbesetzung pro Dienst
  - Wochenend-Rotation
  - Qualifikations-Pflicht
  - Urlaubs-Sperre

## Automatische Planung

Die automatische Planung verwendet Google OR-Tools für Constraint Programming:

1. **Constraints aus Regeln**: Alle aktiven Regeln werden als Constraints modelliert
2. **Mitarbeiterwünsche**: Frei-Wünsche und Nicht-Verfügbarkeit werden berücksichtigt
3. **Qualifikationen**: Dienste werden nur mit qualifiziertem Personal besetzt
4. **Faire Verteilung**: Optimierung für gleichmäßige Arbeitsbelastung

## Tests

Tests ausführen:
```bash
pytest
```

Mit Coverage:
```bash
pytest --cov=app tests/
```

## Konfiguration

Die Anwendung kann über Umgebungsvariablen konfiguriert werden:

- `FLASK_CONFIG`: `development`, `testing`, oder `production`
- `SECRET_KEY`: Geheimer Schlüssel für Sessions
- `DATABASE_URL`: Datenbank-URL (Standard: SQLite)

## Lizenz

Dieses Projekt ist für Lernzwecke erstellt.

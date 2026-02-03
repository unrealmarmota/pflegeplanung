#!/usr/bin/env python3
"""
Datenbank-Migration: Fügt neue Spalten hinzu ohne Daten zu verlieren
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'pflegeplanung.db')


def migrate():
    """Führt Migrationen durch"""
    if not os.path.exists(DB_PATH):
        print("Datenbank existiert nicht. Bitte erst init_db.py ausführen.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    migrations = [
        # Dienste: min_besetzung und max_besetzung
        ("dienste", "min_besetzung", "INTEGER DEFAULT 1"),
        ("dienste", "max_besetzung", "INTEGER"),
        ("dienste", "ist_abwesenheit", "BOOLEAN DEFAULT 0"),  # Urlaub, Krank - nicht auto-planbar

        # Qualifikationen: Hierarchie (inkludiert andere Qualifikation)
        ("qualifikationen", "inkludiert_id", "INTEGER REFERENCES qualifikationen(id)"),

        # Mitarbeiter: Stellenanteil statt feste Wochenstunden
        ("mitarbeiter", "stellenanteil", "REAL DEFAULT 100.0"),

        # DienstQualifikation: Erforderlich-Flag (nur MA mit dieser Quali dürfen Dienst machen)
        ("dienst_qualifikationen", "erforderlich", "BOOLEAN DEFAULT 1"),
    ]

    for table, column, col_type in migrations:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            print(f"✓ Spalte '{column}' zu '{table}' hinzugefügt")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                print(f"  Spalte '{column}' in '{table}' existiert bereits")
            else:
                print(f"✗ Fehler bei '{table}.{column}': {e}")

    # Erstelle MitarbeiterDienstPraeferenzen Tabelle falls nicht vorhanden
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mitarbeiter_dienst_praeferenzen (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mitarbeiter_id INTEGER NOT NULL,
                dienst_id INTEGER NOT NULL,
                min_pro_monat INTEGER DEFAULT 0,
                max_pro_monat INTEGER,
                FOREIGN KEY (mitarbeiter_id) REFERENCES mitarbeiter(id),
                FOREIGN KEY (dienst_id) REFERENCES dienste(id),
                UNIQUE (mitarbeiter_id, dienst_id)
            )
        """)
        print("✓ Tabelle 'mitarbeiter_dienst_praeferenzen' erstellt/geprüft")
    except sqlite3.OperationalError as e:
        print(f"  Tabelle existiert bereits oder Fehler: {e}")

    # Erstelle Einstellungen Tabelle falls nicht vorhanden
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS einstellungen (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schluessel VARCHAR(50) UNIQUE NOT NULL,
                wert VARCHAR(200) NOT NULL,
                beschreibung VARCHAR(200)
            )
        """)
        print("✓ Tabelle 'einstellungen' erstellt/geprüft")
    except sqlite3.OperationalError as e:
        print(f"  Tabelle existiert bereits oder Fehler: {e}")

    # Erstelle Feiertage Tabelle
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feiertage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                datum DATE UNIQUE NOT NULL,
                name VARCHAR(100) NOT NULL,
                bundesland VARCHAR(50) DEFAULT 'alle'
            )
        """)
        print("✓ Tabelle 'feiertage' erstellt/geprüft")
    except sqlite3.OperationalError as e:
        print(f"  Tabelle existiert bereits oder Fehler: {e}")

    # Erstelle Feiertags-Ausgleich Tabelle
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feiertags_ausgleich (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mitarbeiter_id INTEGER NOT NULL,
                feiertag_id INTEGER NOT NULL,
                gearbeitet_am DATE NOT NULL,
                ausgleich_am DATE,
                ausgleich_stunden REAL DEFAULT 0,
                status VARCHAR(20) DEFAULT 'offen',
                FOREIGN KEY (mitarbeiter_id) REFERENCES mitarbeiter(id),
                FOREIGN KEY (feiertag_id) REFERENCES feiertage(id)
            )
        """)
        print("✓ Tabelle 'feiertags_ausgleich' erstellt/geprüft")
    except sqlite3.OperationalError as e:
        print(f"  Tabelle existiert bereits oder Fehler: {e}")

    # Erstelle MitarbeiterDienstEinschraenkungen Tabelle
    # Ermöglicht: "MA darf an bestimmten Tagen nur bestimmte Dienste machen"
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mitarbeiter_dienst_einschraenkungen (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mitarbeiter_id INTEGER NOT NULL,
                tag_typ VARCHAR(20) NOT NULL,
                nur_dienst_id INTEGER NOT NULL,
                aktiv BOOLEAN DEFAULT 1,
                notiz VARCHAR(200),
                FOREIGN KEY (mitarbeiter_id) REFERENCES mitarbeiter(id),
                FOREIGN KEY (nur_dienst_id) REFERENCES dienste(id)
            )
        """)
        print("✓ Tabelle 'mitarbeiter_dienst_einschraenkungen' erstellt/geprüft")
    except sqlite3.OperationalError as e:
        print(f"  Tabelle existiert bereits oder Fehler: {e}")

    # Erstelle Users Tabelle für Login-System
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username VARCHAR(80) UNIQUE NOT NULL,
                password_hash VARCHAR(256) NOT NULL,
                is_admin BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_login DATETIME
            )
        """)
        print("✓ Tabelle 'users' erstellt/geprüft")
    except sqlite3.OperationalError as e:
        print(f"  Tabelle existiert bereits oder Fehler: {e}")

    conn.commit()
    conn.close()
    print("\nMigration abgeschlossen!")


if __name__ == '__main__':
    print("Starte Datenbank-Migration...")
    migrate()

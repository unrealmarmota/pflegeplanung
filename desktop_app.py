#!/usr/bin/env python3
"""
Desktop-App Wrapper für Pflegeplanung
Startet Flask im Hintergrund und öffnet ein natives Fenster
"""
import os
import sys
import shutil
import threading
import webview


def get_app_data_path():
    """Gibt den Pfad für App-Daten zurück (plattformspezifisch)"""
    if sys.platform == 'darwin':  # macOS
        path = os.path.expanduser('~/Library/Application Support/Pflegeplanung')
    elif sys.platform == 'win32':  # Windows
        path = os.path.join(os.environ.get('APPDATA', ''), 'Pflegeplanung')
    else:  # Linux
        path = os.path.expanduser('~/.pflegeplanung')

    # Ordner erstellen falls nicht vorhanden
    os.makedirs(path, exist_ok=True)
    return path


def get_bundle_path():
    """Gibt den Pfad zum App-Bundle zurück (für gebündelte Ressourcen)"""
    if getattr(sys, 'frozen', False):
        # Ausgeführt als gebündelte App
        return sys._MEIPASS
    else:
        # Ausgeführt als Script
        return os.path.dirname(os.path.abspath(__file__))


def setup_database():
    """Stellt sicher, dass die Datenbank am richtigen Ort liegt"""
    app_data = get_app_data_path()
    db_path = os.path.join(app_data, 'pflegeplanung.db')

    # Wenn noch keine Datenbank existiert, Vorlage kopieren
    if not os.path.exists(db_path):
        bundle_path = get_bundle_path()
        template_db = os.path.join(bundle_path, 'pflegeplanung.db')

        if os.path.exists(template_db):
            shutil.copy2(template_db, db_path)
            print(f"Datenbank kopiert nach: {db_path}")
        else:
            print(f"Keine Vorlage-Datenbank gefunden, wird neu erstellt: {db_path}")

    # Umgebungsvariable setzen für Flask-Config
    os.environ['PFLEGEPLANUNG_DB_PATH'] = db_path
    return db_path


def run_flask():
    """Flask-Server im Hintergrund starten"""
    from app import create_app, db
    app = create_app()

    # Bei erster Nutzung: Tabellen erstellen
    with app.app_context():
        db.create_all()

    app.run(host='127.0.0.1', port=5001, debug=False, use_reloader=False)


if __name__ == '__main__':
    # Datenbank einrichten
    db_path = setup_database()
    print(f"Verwende Datenbank: {db_path}")

    # Flask in separatem Thread starten
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Natives Fenster öffnen
    webview.create_window(
        'Pflegeplanung',
        'http://127.0.0.1:5001',
        width=1200,
        height=800,
        min_size=(800, 600)
    )
    webview.start()

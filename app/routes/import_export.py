"""
XLSX-Import Route für Dienstplanwünsche.
"""
import os
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
from app import db
from app.models import Mitarbeiter, Dienst
from app.services.xlsx_import import parse_xlsx, match_mitarbeiter, importiere_praeferenzen

bp = Blueprint('import_export', __name__, url_prefix='/import')

ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
UPLOAD_FOLDER = '/tmp/pflegeplanung_uploads'


def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _build_dienst_map():
    """Baut eine Zuordnung Kürzel → Dienst-Objekt."""
    dienste = Dienst.query.filter_by(ist_abwesenheit=False).all()
    dienst_map = {}

    for d in dienste:
        name_lower = d.name.lower()
        # Hauptdienste matchen (nicht S11)
        if 's11' in name_lower:
            continue
        if 'früh' in name_lower:
            dienst_map['F'] = d
        elif 'spät' in name_lower:
            dienst_map['S'] = d
        elif 'nacht' in name_lower:
            dienst_map['N'] = d
        elif 'kern' in name_lower:
            dienst_map['KD'] = d
        elif 'triage' in name_lower:
            dienst_map['T'] = d

    return dienst_map


@bp.route('/wuensche', methods=['GET'])
def upload_form():
    return render_template('import_export/upload.html')


@bp.route('/wuensche', methods=['POST'])
def upload_and_preview():
    if 'file' not in request.files:
        flash('Keine Datei ausgewählt.', 'danger')
        return redirect(url_for('import_export.upload_form'))

    file = request.files['file']
    if file.filename == '':
        flash('Keine Datei ausgewählt.', 'danger')
        return redirect(url_for('import_export.upload_form'))

    if not _allowed_file(file.filename):
        flash('Nur .xlsx-Dateien werden unterstützt.', 'danger')
        return redirect(url_for('import_export.upload_form'))

    # Datei temporär speichern
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    try:
        # Parsen
        parsed = parse_xlsx(filepath)

        # Mitarbeiter matchen
        mitarbeiter = Mitarbeiter.query.filter_by(aktiv=True).all()
        matched = match_mitarbeiter(parsed, mitarbeiter)

        # Alle MA für Dropdown (manuelle Zuordnung)
        alle_ma = [(m.id, m.name) for m in Mitarbeiter.query.order_by(Mitarbeiter.name).all()]

        # Dienst-Map für Anzeige
        dienst_map = _build_dienst_map()

        # Matched-Daten in Session speichern (für Confirm-Step)
        session['import_filepath'] = filepath
        session['import_matched'] = json.dumps([
            {
                'xlsx_name': m['xlsx_name'],
                'ma_id': m['ma_id'],
                'ma_name': m['ma_name'],
                'match_typ': m['match_typ'],
                'daten': m['daten'],
            }
            for m in matched
        ], default=str)

        return render_template('import_export/vorschau.html',
                               matched=matched,
                               alle_ma=alle_ma,
                               dienst_map=dienst_map)

    except Exception as e:
        flash(f'Fehler beim Lesen der Datei: {str(e)}', 'danger')
        return redirect(url_for('import_export.upload_form'))


@bp.route('/wuensche/confirm', methods=['POST'])
def confirm_import():
    filepath = session.get('import_filepath')
    matched_json = session.get('import_matched')

    if not filepath or not matched_json:
        flash('Keine Import-Daten vorhanden. Bitte erneut hochladen.', 'danger')
        return redirect(url_for('import_export.upload_form'))

    matched = json.loads(matched_json)

    # Manuelle Zuordnungen aus dem Formular übernehmen
    for i, eintrag in enumerate(matched):
        form_key = f'ma_id_{i}'
        if form_key in request.form:
            new_ma_id = request.form[form_key]
            if new_ma_id and new_ma_id != 'skip':
                eintrag['ma_id'] = int(new_ma_id)
                ma = Mitarbeiter.query.get(int(new_ma_id))
                eintrag['ma_name'] = ma.name if ma else None
            elif new_ma_id == 'skip':
                eintrag['ma_id'] = None

    # Dienst-Map bauen
    dienst_map = _build_dienst_map()

    # Import durchführen
    stats = importiere_praeferenzen(matched, dienst_map, db)

    # Temporäre Datei aufräumen
    try:
        os.remove(filepath)
    except OSError:
        pass

    # Session aufräumen
    session.pop('import_filepath', None)
    session.pop('import_matched', None)

    return render_template('import_export/ergebnis.html', stats=stats)

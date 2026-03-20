from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from app.models import Einstellungen

bp = Blueprint('einstellungen', __name__, url_prefix='/einstellungen')


@bp.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Basis-Wochenstunden speichern
        basis_stunden = request.form.get('basis_wochenstunden', '38.5')
        try:
            basis_stunden = float(basis_stunden)
            if basis_stunden <= 0 or basis_stunden > 60:
                raise ValueError("Ungültiger Wert")
            Einstellungen.set('basis_wochenstunden', basis_stunden)
        except ValueError:
            flash('Ungültiger Wert für Basis-Wochenstunden.', 'danger')

        # KI-Einstellungen speichern
        claude_api_key = request.form.get('claude_api_key', '').strip()
        if claude_api_key:
            # Nur speichern wenn nicht der maskierte Platzhalter
            if not claude_api_key.startswith('****'):
                Einstellungen.set('claude_api_key', claude_api_key)

        claude_modell = request.form.get('claude_modell', 'haiku')
        if claude_modell in ('haiku', 'sonnet', 'opus'):
            Einstellungen.set('claude_modell', claude_modell)

        ki_aktiv = 'ki_erklaerung_aktiv' in request.form
        Einstellungen.set('ki_erklaerung_aktiv', 'true' if ki_aktiv else 'false')

        flash('Einstellungen gespeichert.', 'success')
        return redirect(url_for('einstellungen.index'))

    # Aktuelle Werte laden
    basis_wochenstunden = Einstellungen.get_float('basis_wochenstunden', 38.5)

    # KI-Einstellungen
    claude_api_key_raw = Einstellungen.get('claude_api_key', '')
    # Maskiert anzeigen (nur letzte 4 Zeichen)
    if claude_api_key_raw and len(claude_api_key_raw) > 4:
        claude_api_key_masked = '****' + claude_api_key_raw[-4:]
    else:
        claude_api_key_masked = ''
    claude_modell = Einstellungen.get('claude_modell', 'haiku')
    ki_aktiv = Einstellungen.get('ki_erklaerung_aktiv', 'true').lower() in ('true', '1', 'ja')

    return render_template('einstellungen/index.html',
                           basis_wochenstunden=basis_wochenstunden,
                           claude_api_key=claude_api_key_masked,
                           claude_modell=claude_modell,
                           ki_aktiv=ki_aktiv)

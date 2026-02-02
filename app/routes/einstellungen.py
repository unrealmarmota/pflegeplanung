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
            flash('Einstellungen gespeichert.', 'success')
        except ValueError:
            flash('Ungültiger Wert für Basis-Wochenstunden.', 'danger')

        return redirect(url_for('einstellungen.index'))

    # Aktuelle Werte laden
    basis_wochenstunden = Einstellungen.get_float('basis_wochenstunden', 38.5)

    return render_template('einstellungen/index.html',
                           basis_wochenstunden=basis_wochenstunden)

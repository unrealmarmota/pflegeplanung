from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app import db
from app.models import Feiertag, FeiertagsAusgleich, Mitarbeiter, Dienstplan
from datetime import datetime, date

bp = Blueprint('feiertage', __name__, url_prefix='/feiertage')


@bp.route('/')
def index():
    """Liste aller Feiertage"""
    jahr = request.args.get('jahr', date.today().year, type=int)
    feiertage = Feiertag.query.filter(
        db.extract('year', Feiertag.datum) == jahr
    ).order_by(Feiertag.datum).all()

    return render_template('feiertage/index.html',
                           feiertage=feiertage,
                           jahr=jahr)


@bp.route('/init/<int:jahr>')
def init_jahr(jahr):
    """Initialisiert deutsche Feiertage für ein Jahr"""
    added = Feiertag.init_deutsche_feiertage(jahr)
    flash(f'{added} Feiertage für {jahr} hinzugefügt.', 'success')
    return redirect(url_for('feiertage.index', jahr=jahr))


@bp.route('/neu', methods=['GET', 'POST'])
def create():
    """Neuen Feiertag anlegen"""
    if request.method == 'POST':
        datum_str = request.form.get('datum')
        name = request.form.get('name', '').strip()

        if not datum_str or not name:
            flash('Datum und Name sind erforderlich.', 'danger')
            return redirect(url_for('feiertage.create'))

        try:
            datum = datetime.strptime(datum_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Ungültiges Datumsformat.', 'danger')
            return redirect(url_for('feiertage.create'))

        if Feiertag.query.filter_by(datum=datum).first():
            flash('Für dieses Datum existiert bereits ein Feiertag.', 'warning')
            return redirect(url_for('feiertage.create'))

        feiertag = Feiertag(datum=datum, name=name)
        db.session.add(feiertag)
        db.session.commit()

        flash(f'Feiertag "{name}" am {datum.strftime("%d.%m.%Y")} erstellt.', 'success')
        return redirect(url_for('feiertage.index', jahr=datum.year))

    return render_template('feiertage/form.html', feiertag=None)


@bp.route('/<int:id>/loeschen', methods=['POST'])
def delete(id):
    """Feiertag löschen"""
    feiertag = Feiertag.query.get_or_404(id)
    jahr = feiertag.datum.year
    name = feiertag.name
    db.session.delete(feiertag)
    db.session.commit()
    flash(f'Feiertag "{name}" gelöscht.', 'success')
    return redirect(url_for('feiertage.index', jahr=jahr))


@bp.route('/ausgleich')
def ausgleich_uebersicht():
    """Übersicht über Feiertagsausgleich aller Mitarbeiter"""
    jahr = request.args.get('jahr', date.today().year, type=int)

    # Finde alle Feiertage mit Dienstplan-Einträgen
    feiertage = Feiertag.query.filter(
        db.extract('year', Feiertag.datum) == jahr
    ).order_by(Feiertag.datum).all()

    ausgleich_daten = []
    for ft in feiertage:
        # Wer hat an diesem Feiertag gearbeitet?
        dienste = Dienstplan.query.filter_by(datum=ft.datum).all()
        for dp in dienste:
            # Prüfe ob Ausgleich schon erfasst
            existing = FeiertagsAusgleich.query.filter_by(
                mitarbeiter_id=dp.mitarbeiter_id,
                feiertag_id=ft.id
            ).first()

            ausgleich_daten.append({
                'feiertag': ft,
                'mitarbeiter': dp.mitarbeiter,
                'dienst': dp.dienst,
                'stunden': dp.dienst.get_dauer_stunden(),
                'ausgleich': existing
            })

    # Offene Ausgleiche zählen
    offene_ausgleiche = FeiertagsAusgleich.query.filter_by(status='offen').count()

    return render_template('feiertage/ausgleich.html',
                           ausgleich_daten=ausgleich_daten,
                           jahr=jahr,
                           offene_ausgleiche=offene_ausgleiche)


@bp.route('/ausgleich/erstellen', methods=['POST'])
def ausgleich_erstellen():
    """Erstellt Ausgleichsansprüche für Feiertagsarbeit"""
    jahr = request.form.get('jahr', date.today().year, type=int)

    feiertage = Feiertag.query.filter(
        db.extract('year', Feiertag.datum) == jahr
    ).all()

    erstellt = 0
    for ft in feiertage:
        dienste = Dienstplan.query.filter_by(datum=ft.datum).all()
        for dp in dienste:
            # Prüfe ob schon existiert
            existing = FeiertagsAusgleich.query.filter_by(
                mitarbeiter_id=dp.mitarbeiter_id,
                feiertag_id=ft.id
            ).first()

            if not existing:
                ausgleich = FeiertagsAusgleich(
                    mitarbeiter_id=dp.mitarbeiter_id,
                    feiertag_id=ft.id,
                    gearbeitet_am=ft.datum,
                    ausgleich_stunden=dp.dienst.get_dauer_stunden(),
                    status='offen'
                )
                db.session.add(ausgleich)
                erstellt += 1

    db.session.commit()
    flash(f'{erstellt} Ausgleichsansprüche erstellt.', 'success')
    return redirect(url_for('feiertage.ausgleich_uebersicht', jahr=jahr))


@bp.route('/ausgleich/<int:id>/planen', methods=['POST'])
def ausgleich_planen(id):
    """Plant einen Ausgleichstag"""
    ausgleich = FeiertagsAusgleich.query.get_or_404(id)

    datum_str = request.form.get('ausgleich_am')
    if datum_str:
        try:
            ausgleich.ausgleich_am = datetime.strptime(datum_str, '%Y-%m-%d').date()
            ausgleich.status = 'geplant'
            db.session.commit()
            flash('Ausgleichstag geplant.', 'success')
        except ValueError:
            flash('Ungültiges Datum.', 'danger')

    return redirect(url_for('feiertage.ausgleich_uebersicht'))


@bp.route('/ausgleich/<int:id>/genommen', methods=['POST'])
def ausgleich_genommen(id):
    """Markiert Ausgleich als genommen"""
    ausgleich = FeiertagsAusgleich.query.get_or_404(id)
    ausgleich.status = 'genommen'
    db.session.commit()
    flash('Ausgleich als genommen markiert.', 'success')
    return redirect(url_for('feiertage.ausgleich_uebersicht'))


@bp.route('/api/check/<datum_str>')
def api_check_feiertag(datum_str):
    """API: Prüft ob ein Datum ein Feiertag ist"""
    try:
        datum = datetime.strptime(datum_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Ungültiges Datum'}), 400

    feiertag = Feiertag.query.filter_by(datum=datum).first()
    if feiertag:
        return jsonify({
            'ist_feiertag': True,
            'name': feiertag.name
        })
    return jsonify({'ist_feiertag': False})

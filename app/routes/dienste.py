from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app import db
from app.models import Dienst, Qualifikation, DienstQualifikation
from datetime import datetime

bp = Blueprint('dienste', __name__, url_prefix='/dienste')


@bp.route('/')
def index():
    dienste = Dienst.query.order_by(Dienst.start_zeit).all()
    return render_template('dienste/index.html', dienste=dienste)


@bp.route('/neu', methods=['GET', 'POST'])
def create():
    qualifikationen = Qualifikation.query.order_by(Qualifikation.name).all()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        kurzname = request.form.get('kurzname', '').strip()
        start_zeit_str = request.form.get('start_zeit', '')
        ende_zeit_str = request.form.get('ende_zeit', '')
        farbe = request.form.get('farbe', '#0d6efd')

        if not name or not kurzname or not start_zeit_str or not ende_zeit_str:
            flash('Alle Pflichtfelder müssen ausgefüllt werden.', 'danger')
            return render_template('dienste/form.html',
                                   dienst=None,
                                   qualifikationen=qualifikationen)

        try:
            start_zeit = datetime.strptime(start_zeit_str, '%H:%M').time()
            ende_zeit = datetime.strptime(ende_zeit_str, '%H:%M').time()
        except ValueError:
            flash('Ungültiges Zeitformat.', 'danger')
            return render_template('dienste/form.html',
                                   dienst=None,
                                   qualifikationen=qualifikationen)

        min_besetzung = request.form.get('min_besetzung', '1')
        max_besetzung = request.form.get('max_besetzung', '')

        try:
            min_besetzung = int(min_besetzung) if min_besetzung else 1
        except ValueError:
            min_besetzung = 1

        try:
            max_besetzung = int(max_besetzung) if max_besetzung else None
        except ValueError:
            max_besetzung = None

        ist_abwesenheit = request.form.get('ist_abwesenheit') == 'on'

        dienst = Dienst(
            name=name,
            kurzname=kurzname,
            start_zeit=start_zeit,
            ende_zeit=ende_zeit,
            farbe=farbe,
            min_besetzung=min_besetzung,
            max_besetzung=max_besetzung,
            ist_abwesenheit=ist_abwesenheit
        )
        db.session.add(dienst)
        db.session.flush()

        # Add qualification requirements
        for qual in qualifikationen:
            min_anzahl = request.form.get(f'qual_{qual.id}_min', '0')
            erforderlich = request.form.get(f'qual_{qual.id}_erf') == '1'
            try:
                min_anzahl = int(min_anzahl)
            except ValueError:
                min_anzahl = 0

            if min_anzahl > 0 or erforderlich:
                dq = DienstQualifikation(
                    dienst_id=dienst.id,
                    qualifikation_id=qual.id,
                    min_anzahl=min_anzahl,
                    erforderlich=erforderlich
                )
                db.session.add(dq)

        db.session.commit()

        flash(f'Dienst "{name}" wurde erstellt.', 'success')
        return redirect(url_for('dienste.index'))

    return render_template('dienste/form.html',
                           dienst=None,
                           qualifikationen=qualifikationen)


@bp.route('/<int:id>/bearbeiten', methods=['GET', 'POST'])
def edit(id):
    dienst = Dienst.query.get_or_404(id)
    qualifikationen = Qualifikation.query.order_by(Qualifikation.name).all()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        kurzname = request.form.get('kurzname', '').strip()
        start_zeit_str = request.form.get('start_zeit', '')
        ende_zeit_str = request.form.get('ende_zeit', '')
        farbe = request.form.get('farbe', '#0d6efd')

        if not name or not kurzname or not start_zeit_str or not ende_zeit_str:
            flash('Alle Pflichtfelder müssen ausgefüllt werden.', 'danger')
            return render_template('dienste/form.html',
                                   dienst=dienst,
                                   qualifikationen=qualifikationen)

        try:
            start_zeit = datetime.strptime(start_zeit_str, '%H:%M').time()
            ende_zeit = datetime.strptime(ende_zeit_str, '%H:%M').time()
        except ValueError:
            flash('Ungültiges Zeitformat.', 'danger')
            return render_template('dienste/form.html',
                                   dienst=dienst,
                                   qualifikationen=qualifikationen)

        min_besetzung = request.form.get('min_besetzung', '1')
        max_besetzung = request.form.get('max_besetzung', '')

        try:
            min_besetzung = int(min_besetzung) if min_besetzung else 1
        except ValueError:
            min_besetzung = 1

        try:
            max_besetzung = int(max_besetzung) if max_besetzung else None
        except ValueError:
            max_besetzung = None

        ist_abwesenheit = request.form.get('ist_abwesenheit') == 'on'

        dienst.name = name
        dienst.kurzname = kurzname
        dienst.start_zeit = start_zeit
        dienst.ende_zeit = ende_zeit
        dienst.farbe = farbe
        dienst.min_besetzung = min_besetzung
        dienst.max_besetzung = max_besetzung
        dienst.ist_abwesenheit = ist_abwesenheit

        # Update qualification requirements
        DienstQualifikation.query.filter_by(dienst_id=id).delete()
        for qual in qualifikationen:
            min_anzahl = request.form.get(f'qual_{qual.id}_min', '0')
            erforderlich = request.form.get(f'qual_{qual.id}_erf') == '1'
            try:
                min_anzahl = int(min_anzahl)
            except ValueError:
                min_anzahl = 0

            if min_anzahl > 0 or erforderlich:
                dq = DienstQualifikation(
                    dienst_id=id,
                    qualifikation_id=qual.id,
                    min_anzahl=min_anzahl,
                    erforderlich=erforderlich
                )
                db.session.add(dq)

        db.session.commit()

        flash(f'Dienst "{name}" wurde aktualisiert.', 'success')
        return redirect(url_for('dienste.index'))

    return render_template('dienste/form.html',
                           dienst=dienst,
                           qualifikationen=qualifikationen)


@bp.route('/<int:id>/loeschen', methods=['POST'])
def delete(id):
    dienst = Dienst.query.get_or_404(id)
    name = dienst.name

    if dienst.dienstplaene:
        flash(f'Dienst "{name}" kann nicht gelöscht werden, da Dienstpläne existieren.', 'danger')
        return redirect(url_for('dienste.index'))

    db.session.delete(dienst)
    db.session.commit()

    flash(f'Dienst "{name}" wurde gelöscht.', 'success')
    return redirect(url_for('dienste.index'))


@bp.route('/api/list')
def api_list():
    dienste = Dienst.query.order_by(Dienst.start_zeit).all()
    return jsonify({
        'dienste': [d.to_dict() for d in dienste]
    })

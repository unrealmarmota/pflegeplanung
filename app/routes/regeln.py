from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app import db
from app.models import Regel, RegelTyp, Dienst, Qualifikation
from app.models.regel import REGEL_TYP_BESCHREIBUNGEN
import json

bp = Blueprint('regeln', __name__, url_prefix='/regeln')


@bp.route('/')
def index():
    regeln = Regel.query.order_by(Regel.prioritaet, Regel.name).all()
    return render_template('regeln/index.html', regeln=regeln)


@bp.route('/neu', methods=['GET', 'POST'])
def create():
    dienste = Dienst.query.order_by(Dienst.name).all()
    qualifikationen = Qualifikation.query.order_by(Qualifikation.name).all()
    regel_typen = [(rt.value, REGEL_TYP_BESCHREIBUNGEN[rt]) for rt in RegelTyp]

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        typ_value = request.form.get('typ', '')
        prioritaet = request.form.get('prioritaet', '1')
        aktiv = request.form.get('aktiv') == 'on'

        if not name or not typ_value:
            flash('Name und Regeltyp sind erforderlich.', 'danger')
            return render_template('regeln/form.html',
                                   regel=None,
                                   regel_typen=regel_typen,
                                   dienste=dienste,
                                   qualifikationen=qualifikationen)

        try:
            typ = RegelTyp(typ_value)
        except ValueError:
            flash('Ungültiger Regeltyp.', 'danger')
            return render_template('regeln/form.html',
                                   regel=None,
                                   regel_typen=regel_typen,
                                   dienste=dienste,
                                   qualifikationen=qualifikationen)

        try:
            prioritaet = int(prioritaet)
        except ValueError:
            prioritaet = 1

        # Build parameter dict from form
        parameter = build_parameter_from_form(typ, request.form)

        regel = Regel(
            name=name,
            typ=typ,
            parameter=parameter,
            prioritaet=prioritaet,
            aktiv=aktiv
        )
        db.session.add(regel)
        db.session.commit()

        flash(f'Regel "{name}" wurde erstellt.', 'success')
        return redirect(url_for('regeln.index'))

    return render_template('regeln/form.html',
                           regel=None,
                           regel_typen=regel_typen,
                           dienste=dienste,
                           qualifikationen=qualifikationen)


@bp.route('/<int:id>/bearbeiten', methods=['GET', 'POST'])
def edit(id):
    regel = Regel.query.get_or_404(id)
    dienste = Dienst.query.order_by(Dienst.name).all()
    qualifikationen = Qualifikation.query.order_by(Qualifikation.name).all()
    regel_typen = [(rt.value, REGEL_TYP_BESCHREIBUNGEN[rt]) for rt in RegelTyp]

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        typ_value = request.form.get('typ', '')
        prioritaet = request.form.get('prioritaet', '1')
        aktiv = request.form.get('aktiv') == 'on'

        if not name or not typ_value:
            flash('Name und Regeltyp sind erforderlich.', 'danger')
            return render_template('regeln/form.html',
                                   regel=regel,
                                   regel_typen=regel_typen,
                                   dienste=dienste,
                                   qualifikationen=qualifikationen)

        try:
            typ = RegelTyp(typ_value)
        except ValueError:
            flash('Ungültiger Regeltyp.', 'danger')
            return render_template('regeln/form.html',
                                   regel=regel,
                                   regel_typen=regel_typen,
                                   dienste=dienste,
                                   qualifikationen=qualifikationen)

        try:
            prioritaet = int(prioritaet)
        except ValueError:
            prioritaet = 1

        parameter = build_parameter_from_form(typ, request.form)

        regel.name = name
        regel.typ = typ
        regel.parameter = parameter
        regel.prioritaet = prioritaet
        regel.aktiv = aktiv
        db.session.commit()

        flash(f'Regel "{name}" wurde aktualisiert.', 'success')
        return redirect(url_for('regeln.index'))

    return render_template('regeln/form.html',
                           regel=regel,
                           regel_typen=regel_typen,
                           dienste=dienste,
                           qualifikationen=qualifikationen)


@bp.route('/<int:id>/loeschen', methods=['POST'])
def delete(id):
    regel = Regel.query.get_or_404(id)
    name = regel.name

    db.session.delete(regel)
    db.session.commit()

    flash(f'Regel "{name}" wurde gelöscht.', 'success')
    return redirect(url_for('regeln.index'))


@bp.route('/<int:id>/toggle', methods=['POST'])
def toggle(id):
    regel = Regel.query.get_or_404(id)
    regel.aktiv = not regel.aktiv
    db.session.commit()

    status = 'aktiviert' if regel.aktiv else 'deaktiviert'
    flash(f'Regel "{regel.name}" wurde {status}.', 'success')
    return redirect(url_for('regeln.index'))


@bp.route('/api/list')
def api_list():
    aktiv_only = request.args.get('aktiv', 'false').lower() == 'true'
    query = Regel.query.order_by(Regel.prioritaet, Regel.name)
    if aktiv_only:
        query = query.filter_by(aktiv=True)
    regeln = query.all()
    return jsonify({
        'regeln': [r.to_dict() for r in regeln]
    })


@bp.route('/api/typen')
def api_typen():
    """Returns rule types with their parameter definitions"""
    typen = {}
    for rt in RegelTyp:
        info = REGEL_TYP_BESCHREIBUNGEN[rt]
        typen[rt.value] = {
            'name': info['name'],
            'beschreibung': info['beschreibung'],
            'parameter': info['parameter']
        }
    return jsonify(typen)


def build_parameter_from_form(typ, form):
    """Build parameter dict from form data based on rule type"""
    parameter = {}
    param_defs = REGEL_TYP_BESCHREIBUNGEN.get(typ, {}).get('parameter', {})

    for key, config in param_defs.items():
        form_value = form.get(f'param_{key}', '')

        if config['typ'] == 'integer':
            try:
                parameter[key] = int(form_value) if form_value else config.get('default', 0)
            except ValueError:
                parameter[key] = config.get('default', 0)
        elif config['typ'] == 'date':
            parameter[key] = form_value if form_value else None
        elif config['typ'] in ('dienst', 'qualifikation'):
            try:
                parameter[key] = int(form_value) if form_value else None
            except ValueError:
                parameter[key] = None
        else:
            parameter[key] = form_value

    return parameter

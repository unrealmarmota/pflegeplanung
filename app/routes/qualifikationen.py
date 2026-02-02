from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app import db
from app.models import Qualifikation

bp = Blueprint('qualifikationen', __name__, url_prefix='/qualifikationen')


@bp.route('/')
def index():
    qualifikationen = Qualifikation.query.order_by(Qualifikation.name).all()
    return render_template('qualifikationen/index.html', qualifikationen=qualifikationen)


@bp.route('/neu', methods=['GET', 'POST'])
def create():
    alle_qualifikationen = Qualifikation.query.order_by(Qualifikation.name).all()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        beschreibung = request.form.get('beschreibung', '').strip()
        farbe = request.form.get('farbe', '#6c757d')
        inkludiert_id = request.form.get('inkludiert_id', '')
        inkludiert_id = int(inkludiert_id) if inkludiert_id else None

        if not name:
            flash('Name ist erforderlich.', 'danger')
            return render_template('qualifikationen/form.html', qualifikation=None,
                                   alle_qualifikationen=alle_qualifikationen)

        if Qualifikation.query.filter_by(name=name).first():
            flash('Eine Qualifikation mit diesem Namen existiert bereits.', 'danger')
            return render_template('qualifikationen/form.html', qualifikation=None,
                                   alle_qualifikationen=alle_qualifikationen)

        qualifikation = Qualifikation(
            name=name,
            beschreibung=beschreibung,
            farbe=farbe,
            inkludiert_id=inkludiert_id
        )
        db.session.add(qualifikation)
        db.session.commit()

        flash(f'Qualifikation "{name}" wurde erstellt.', 'success')
        return redirect(url_for('qualifikationen.index'))

    return render_template('qualifikationen/form.html', qualifikation=None,
                           alle_qualifikationen=alle_qualifikationen)


@bp.route('/<int:id>/bearbeiten', methods=['GET', 'POST'])
def edit(id):
    qualifikation = Qualifikation.query.get_or_404(id)
    # Exclude current qualifikation and any that already include this one (prevent cycles)
    alle_qualifikationen = Qualifikation.query.filter(Qualifikation.id != id).order_by(Qualifikation.name).all()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        beschreibung = request.form.get('beschreibung', '').strip()
        farbe = request.form.get('farbe', '#6c757d')
        inkludiert_id = request.form.get('inkludiert_id', '')
        inkludiert_id = int(inkludiert_id) if inkludiert_id else None

        if not name:
            flash('Name ist erforderlich.', 'danger')
            return render_template('qualifikationen/form.html', qualifikation=qualifikation,
                                   alle_qualifikationen=alle_qualifikationen)

        existing = Qualifikation.query.filter_by(name=name).first()
        if existing and existing.id != id:
            flash('Eine Qualifikation mit diesem Namen existiert bereits.', 'danger')
            return render_template('qualifikationen/form.html', qualifikation=qualifikation,
                                   alle_qualifikationen=alle_qualifikationen)

        # Prevent circular references
        if inkludiert_id:
            target = Qualifikation.query.get(inkludiert_id)
            if target:
                for inkl in target.get_alle_inkludierten():
                    if inkl.id == id:
                        flash('Zirkuläre Referenz: Diese Qualifikation wird bereits von der gewählten inkludiert.', 'danger')
                        return render_template('qualifikationen/form.html', qualifikation=qualifikation,
                                               alle_qualifikationen=alle_qualifikationen)

        qualifikation.name = name
        qualifikation.beschreibung = beschreibung
        qualifikation.farbe = farbe
        qualifikation.inkludiert_id = inkludiert_id
        db.session.commit()

        flash(f'Qualifikation "{name}" wurde aktualisiert.', 'success')
        return redirect(url_for('qualifikationen.index'))

    return render_template('qualifikationen/form.html', qualifikation=qualifikation,
                           alle_qualifikationen=alle_qualifikationen)


@bp.route('/<int:id>/loeschen', methods=['POST'])
def delete(id):
    qualifikation = Qualifikation.query.get_or_404(id)
    name = qualifikation.name

    # Check if qualifikation is in use
    if qualifikation.mitarbeiter:
        flash(f'Qualifikation "{name}" kann nicht gelöscht werden, da sie Mitarbeitern zugewiesen ist.', 'danger')
        return redirect(url_for('qualifikationen.index'))

    db.session.delete(qualifikation)
    db.session.commit()

    flash(f'Qualifikation "{name}" wurde gelöscht.', 'success')
    return redirect(url_for('qualifikationen.index'))


@bp.route('/api/list')
def api_list():
    qualifikationen = Qualifikation.query.order_by(Qualifikation.name).all()
    return jsonify({
        'qualifikationen': [q.to_dict() for q in qualifikationen]
    })

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app import db
from app.models import (
    Mitarbeiter, Qualifikation, MitarbeiterQualifikation, Dienst,
    MitarbeiterDienstPraeferenz, Einstellungen, MitarbeiterDienstEinschraenkung,
    TagTyp, TAG_TYP_NAMEN
)
from datetime import datetime, date

bp = Blueprint('mitarbeiter', __name__, url_prefix='/mitarbeiter')


@bp.route('/')
def index():
    mitarbeiter = Mitarbeiter.query.order_by(Mitarbeiter.name).all()
    qualifikationen = Qualifikation.query.order_by(Qualifikation.name).all()
    return render_template('mitarbeiter/index.html',
                           mitarbeiter=mitarbeiter,
                           qualifikationen=qualifikationen)


@bp.route('/neu', methods=['GET', 'POST'])
def create():
    qualifikationen = Qualifikation.query.order_by(Qualifikation.name).all()
    dienste = Dienst.query.order_by(Dienst.name).all()
    basis_wochenstunden = Einstellungen.get_float('basis_wochenstunden', 38.5)

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        personalnummer = request.form.get('personalnummer', '').strip()
        email = request.form.get('email', '').strip()
        telefon = request.form.get('telefon', '').strip()
        eintrittsdatum_str = request.form.get('eintrittsdatum', '')
        stellenanteil = request.form.get('stellenanteil', '100')
        aktiv = request.form.get('aktiv') == 'on'
        selected_qualifikationen = request.form.getlist('qualifikationen')

        if not name or not personalnummer:
            flash('Name und Personalnummer sind erforderlich.', 'danger')
            return render_template('mitarbeiter/form.html',
                                   mitarbeiter=None,
                                   qualifikationen=qualifikationen,
                                   dienste=dienste,
                                   basis_wochenstunden=basis_wochenstunden)

        if Mitarbeiter.query.filter_by(personalnummer=personalnummer).first():
            flash('Ein Mitarbeiter mit dieser Personalnummer existiert bereits.', 'danger')
            return render_template('mitarbeiter/form.html',
                                   mitarbeiter=None,
                                   qualifikationen=qualifikationen,
                                   dienste=dienste,
                                   basis_wochenstunden=basis_wochenstunden)

        eintrittsdatum = None
        if eintrittsdatum_str:
            eintrittsdatum = datetime.strptime(eintrittsdatum_str, '%Y-%m-%d').date()

        try:
            stellenanteil_float = float(stellenanteil)
        except ValueError:
            stellenanteil_float = 100.0

        mitarbeiter = Mitarbeiter(
            name=name,
            personalnummer=personalnummer,
            email=email or None,
            telefon=telefon or None,
            eintrittsdatum=eintrittsdatum,
            stellenanteil=stellenanteil_float,
            aktiv=aktiv
        )
        db.session.add(mitarbeiter)
        db.session.flush()

        # Add qualifications
        for qual_id in selected_qualifikationen:
            mq = MitarbeiterQualifikation(
                mitarbeiter_id=mitarbeiter.id,
                qualifikation_id=int(qual_id),
                erworben_am=date.today()
            )
            db.session.add(mq)

        # Add dienst preferences
        for dienst in dienste:
            min_val = request.form.get(f'dienst_{dienst.id}_min', '0')
            max_val = request.form.get(f'dienst_{dienst.id}_max', '')
            try:
                min_pro_monat = int(min_val) if min_val else 0
            except ValueError:
                min_pro_monat = 0
            try:
                max_pro_monat = int(max_val) if max_val else None
            except ValueError:
                max_pro_monat = None

            if min_pro_monat > 0 or max_pro_monat is not None:
                pref = MitarbeiterDienstPraeferenz(
                    mitarbeiter_id=mitarbeiter.id,
                    dienst_id=dienst.id,
                    min_pro_monat=min_pro_monat,
                    max_pro_monat=max_pro_monat
                )
                db.session.add(pref)

        db.session.commit()

        flash(f'Mitarbeiter "{name}" wurde erstellt.', 'success')
        return redirect(url_for('mitarbeiter.index'))

    return render_template('mitarbeiter/form.html',
                           mitarbeiter=None,
                           qualifikationen=qualifikationen,
                           dienste=dienste,
                           basis_wochenstunden=basis_wochenstunden)


@bp.route('/<int:id>/bearbeiten', methods=['GET', 'POST'])
def edit(id):
    mitarbeiter = Mitarbeiter.query.get_or_404(id)
    qualifikationen = Qualifikation.query.order_by(Qualifikation.name).all()
    dienste = Dienst.query.order_by(Dienst.name).all()
    basis_wochenstunden = Einstellungen.get_float('basis_wochenstunden', 38.5)

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        personalnummer = request.form.get('personalnummer', '').strip()
        email = request.form.get('email', '').strip()
        telefon = request.form.get('telefon', '').strip()
        eintrittsdatum_str = request.form.get('eintrittsdatum', '')
        stellenanteil = request.form.get('stellenanteil', '100')
        aktiv = request.form.get('aktiv') == 'on'
        selected_qualifikationen = request.form.getlist('qualifikationen')

        if not name or not personalnummer:
            flash('Name und Personalnummer sind erforderlich.', 'danger')
            return render_template('mitarbeiter/form.html',
                                   mitarbeiter=mitarbeiter,
                                   qualifikationen=qualifikationen,
                                   dienste=dienste,
                                   basis_wochenstunden=basis_wochenstunden)

        existing = Mitarbeiter.query.filter_by(personalnummer=personalnummer).first()
        if existing and existing.id != id:
            flash('Ein Mitarbeiter mit dieser Personalnummer existiert bereits.', 'danger')
            return render_template('mitarbeiter/form.html',
                                   mitarbeiter=mitarbeiter,
                                   qualifikationen=qualifikationen,
                                   dienste=dienste,
                                   basis_wochenstunden=basis_wochenstunden)

        eintrittsdatum = None
        if eintrittsdatum_str:
            eintrittsdatum = datetime.strptime(eintrittsdatum_str, '%Y-%m-%d').date()

        try:
            stellenanteil_float = float(stellenanteil)
        except ValueError:
            stellenanteil_float = 100.0

        mitarbeiter.name = name
        mitarbeiter.personalnummer = personalnummer
        mitarbeiter.email = email or None
        mitarbeiter.telefon = telefon or None
        mitarbeiter.eintrittsdatum = eintrittsdatum
        mitarbeiter.stellenanteil = stellenanteil_float
        mitarbeiter.aktiv = aktiv

        # Update qualifications
        MitarbeiterQualifikation.query.filter_by(mitarbeiter_id=id).delete()
        for qual_id in selected_qualifikationen:
            mq = MitarbeiterQualifikation(
                mitarbeiter_id=id,
                qualifikation_id=int(qual_id),
                erworben_am=date.today()
            )
            db.session.add(mq)

        # Update dienst preferences
        MitarbeiterDienstPraeferenz.query.filter_by(mitarbeiter_id=id).delete()
        for dienst in dienste:
            min_val = request.form.get(f'dienst_{dienst.id}_min', '0')
            max_val = request.form.get(f'dienst_{dienst.id}_max', '')
            try:
                min_pro_monat = int(min_val) if min_val else 0
            except ValueError:
                min_pro_monat = 0
            try:
                max_pro_monat = int(max_val) if max_val else None
            except ValueError:
                max_pro_monat = None

            if min_pro_monat > 0 or max_pro_monat is not None:
                pref = MitarbeiterDienstPraeferenz(
                    mitarbeiter_id=id,
                    dienst_id=dienst.id,
                    min_pro_monat=min_pro_monat,
                    max_pro_monat=max_pro_monat
                )
                db.session.add(pref)

        db.session.commit()

        flash(f'Mitarbeiter "{name}" wurde aktualisiert.', 'success')
        return redirect(url_for('mitarbeiter.index'))

    return render_template('mitarbeiter/form.html',
                           mitarbeiter=mitarbeiter,
                           qualifikationen=qualifikationen,
                           dienste=dienste,
                           basis_wochenstunden=basis_wochenstunden)


@bp.route('/<int:id>')
def detail(id):
    mitarbeiter = Mitarbeiter.query.get_or_404(id)
    return render_template('mitarbeiter/detail.html', mitarbeiter=mitarbeiter)


@bp.route('/<int:id>/loeschen', methods=['POST'])
def delete(id):
    mitarbeiter = Mitarbeiter.query.get_or_404(id)
    name = mitarbeiter.name

    # Check for existing schedules
    if mitarbeiter.dienstplaene:
        flash(f'Mitarbeiter "{name}" kann nicht gelöscht werden, da Dienstpläne existieren.', 'danger')
        return redirect(url_for('mitarbeiter.index'))

    db.session.delete(mitarbeiter)
    db.session.commit()

    flash(f'Mitarbeiter "{name}" wurde gelöscht.', 'success')
    return redirect(url_for('mitarbeiter.index'))


@bp.route('/api/list')
def api_list():
    aktiv_only = request.args.get('aktiv', 'true').lower() == 'true'
    query = Mitarbeiter.query.order_by(Mitarbeiter.name)
    if aktiv_only:
        query = query.filter_by(aktiv=True)
    mitarbeiter = query.all()
    return jsonify({
        'mitarbeiter': [m.to_dict() for m in mitarbeiter]
    })


# ===== Dienst-Einschränkungen =====

@bp.route('/<int:id>/einschraenkungen')
def einschraenkungen(id):
    """Zeigt alle Dienst-Einschränkungen eines Mitarbeiters"""
    mitarbeiter = Mitarbeiter.query.get_or_404(id)
    dienste = Dienst.query.order_by(Dienst.name).all()
    return render_template('mitarbeiter/einschraenkungen.html',
                           mitarbeiter=mitarbeiter,
                           dienste=dienste,
                           tag_typen=TagTyp,
                           tag_typ_namen=TAG_TYP_NAMEN)


@bp.route('/<int:id>/einschraenkungen/neu', methods=['POST'])
def einschraenkung_create(id):
    """Erstellt eine neue Dienst-Einschränkung"""
    mitarbeiter = Mitarbeiter.query.get_or_404(id)

    tag_typ_str = request.form.get('tag_typ')
    nur_dienst_id = request.form.get('nur_dienst_id')
    notiz = request.form.get('notiz', '').strip()

    if not tag_typ_str or not nur_dienst_id:
        flash('Tag-Typ und Dienst sind erforderlich.', 'danger')
        return redirect(url_for('mitarbeiter.einschraenkungen', id=id))

    try:
        tag_typ = TagTyp(tag_typ_str)
    except ValueError:
        flash('Ungültiger Tag-Typ.', 'danger')
        return redirect(url_for('mitarbeiter.einschraenkungen', id=id))

    # Prüfe ob bereits eine gleiche Einschränkung existiert
    existing = MitarbeiterDienstEinschraenkung.query.filter_by(
        mitarbeiter_id=id,
        tag_typ=tag_typ,
        nur_dienst_id=int(nur_dienst_id)
    ).first()

    if existing:
        flash('Diese Einschränkung existiert bereits.', 'warning')
        return redirect(url_for('mitarbeiter.einschraenkungen', id=id))

    einschraenkung = MitarbeiterDienstEinschraenkung(
        mitarbeiter_id=id,
        tag_typ=tag_typ,
        nur_dienst_id=int(nur_dienst_id),
        notiz=notiz or None,
        aktiv=True
    )
    db.session.add(einschraenkung)
    db.session.commit()

    dienst = Dienst.query.get(nur_dienst_id)
    flash(f'Einschränkung erstellt: {mitarbeiter.name} darf an "{TAG_TYP_NAMEN[tag_typ]}" nur {dienst.name} machen.', 'success')
    return redirect(url_for('mitarbeiter.einschraenkungen', id=id))


@bp.route('/<int:id>/einschraenkungen/<int:einschraenkung_id>/toggle', methods=['POST'])
def einschraenkung_toggle(id, einschraenkung_id):
    """Aktiviert/Deaktiviert eine Einschränkung"""
    einschraenkung = MitarbeiterDienstEinschraenkung.query.get_or_404(einschraenkung_id)

    if einschraenkung.mitarbeiter_id != id:
        flash('Einschränkung gehört nicht zu diesem Mitarbeiter.', 'danger')
        return redirect(url_for('mitarbeiter.einschraenkungen', id=id))

    einschraenkung.aktiv = not einschraenkung.aktiv
    db.session.commit()

    status = 'aktiviert' if einschraenkung.aktiv else 'deaktiviert'
    flash(f'Einschränkung {status}.', 'success')
    return redirect(url_for('mitarbeiter.einschraenkungen', id=id))


@bp.route('/<int:id>/einschraenkungen/<int:einschraenkung_id>/loeschen', methods=['POST'])
def einschraenkung_delete(id, einschraenkung_id):
    """Löscht eine Einschränkung"""
    einschraenkung = MitarbeiterDienstEinschraenkung.query.get_or_404(einschraenkung_id)

    if einschraenkung.mitarbeiter_id != id:
        flash('Einschränkung gehört nicht zu diesem Mitarbeiter.', 'danger')
        return redirect(url_for('mitarbeiter.einschraenkungen', id=id))

    db.session.delete(einschraenkung)
    db.session.commit()

    flash('Einschränkung gelöscht.', 'success')
    return redirect(url_for('mitarbeiter.einschraenkungen', id=id))


@bp.route('/<int:id>/einschraenkungen/api')
def einschraenkungen_api(id):
    """API: Gibt alle Einschränkungen eines Mitarbeiters zurück"""
    mitarbeiter = Mitarbeiter.query.get_or_404(id)
    return jsonify({
        'einschraenkungen': [e.to_dict() for e in mitarbeiter.dienst_einschraenkungen]
    })


# ===== Regel-Ausnahmen =====

# Verfügbare Regel-Ausnahmen mit Beschreibungen
REGEL_AUSNAHMEN_INFO = {
    'MAX_TAGE_FOLGE': {
        'name': 'Max. Arbeitstage am Stück',
        'beschreibung': 'Maximale aufeinanderfolgende Arbeitstage',
        'default': 5,
        'typ': 'int',
        'min': 1,
        'max': 14
    },
    'WOCHENENDE_ROTATION': {
        'name': 'Max. Wochenenden/Monat',
        'beschreibung': 'Maximale Wochenenden pro Monat',
        'default': 2,
        'typ': 'int',
        'min': 0,
        'max': 5
    },
    'MAX_NAECHTE_MONAT': {
        'name': 'Max. Nächte/Monat',
        'beschreibung': 'Maximale Nachtdienste pro Monat (0 = keine Nächte)',
        'default': 8,
        'typ': 'int',
        'min': 0,
        'max': 20
    },
    'MIN_NAECHTE_MONAT': {
        'name': 'Min. Nächte/Monat',
        'beschreibung': 'Mindest-Nachtdienste für Fairness (0 = befreit)',
        'default': 4,
        'typ': 'int',
        'min': 0,
        'max': 12
    },
    'MIN_WOCHENENDEN_MONAT': {
        'name': 'Min. Wochenenden/Monat',
        'beschreibung': 'Mindest-Wochenenden für Fairness (0 = befreit)',
        'default': 1,
        'typ': 'int',
        'min': 0,
        'max': 5
    },
    'NACHT_BLOCK_MIN': {
        'name': 'Min. Nächte am Stück',
        'beschreibung': 'Mindestanzahl aufeinanderfolgender Nächte pro Block',
        'default': 2,
        'typ': 'int',
        'min': 1,
        'max': 7
    },
    'NACHT_BLOCK_MAX': {
        'name': 'Max. Nächte am Stück',
        'beschreibung': 'Maximale aufeinanderfolgende Nächte pro Block',
        'default': 4,
        'typ': 'int',
        'min': 1,
        'max': 7
    }
}


@bp.route('/<int:id>/regel-ausnahmen')
def regel_ausnahmen(id):
    """Zeigt und bearbeitet individuelle Regel-Ausnahmen eines Mitarbeiters"""
    mitarbeiter = Mitarbeiter.query.get_or_404(id)
    return render_template('mitarbeiter/regel_ausnahmen.html',
                           mitarbeiter=mitarbeiter,
                           regel_info=REGEL_AUSNAHMEN_INFO)


@bp.route('/<int:id>/regel-ausnahmen/speichern', methods=['POST'])
def regel_ausnahmen_speichern(id):
    """Speichert die Regel-Ausnahmen"""
    mitarbeiter = Mitarbeiter.query.get_or_404(id)

    neue_ausnahmen = {}
    for regel_key, info in REGEL_AUSNAHMEN_INFO.items():
        # Checkbox: Hat der MA eine Ausnahme für diese Regel?
        hat_ausnahme = request.form.get(f'hat_{regel_key}') == 'on'

        if hat_ausnahme:
            wert_str = request.form.get(f'wert_{regel_key}', '')
            try:
                wert = int(wert_str)
                # Validiere Bereich
                wert = max(info['min'], min(info['max'], wert))
                neue_ausnahmen[regel_key] = wert
            except (ValueError, TypeError):
                pass  # Ungültiger Wert, ignorieren

    mitarbeiter.regel_ausnahmen = neue_ausnahmen
    db.session.commit()

    if neue_ausnahmen:
        flash(f'Regel-Ausnahmen für {mitarbeiter.name} gespeichert: {len(neue_ausnahmen)} Ausnahme(n).', 'success')
    else:
        flash(f'Alle Regel-Ausnahmen für {mitarbeiter.name} entfernt. Es gelten die globalen Regeln.', 'info')

    return redirect(url_for('mitarbeiter.regel_ausnahmen', id=id))

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy.exc import IntegrityError
from app import db
from app.models import (
    Mitarbeiter, Dienst, Dienstplan, DienstplanStatus,
    MitarbeiterWunsch, WunschTyp, Regel, Qualifikation
)
from app.services.planer import DienstPlaner
from app.services.konflikt import KonfliktErkennung
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
import calendar

bp = Blueprint('planung', __name__, url_prefix='/planung')


def validate_jahr_monat(jahr, monat):
    """Validiert Jahr und Monat Parameter. Gibt (jahr, monat, error) zurück."""
    if jahr is None or monat is None:
        return None, None, 'Jahr und Monat sind erforderlich'
    if not (1900 <= jahr <= 2100):
        return None, None, f'Ungültiges Jahr: {jahr} (muss zwischen 1900 und 2100 liegen)'
    if not (1 <= monat <= 12):
        return None, None, f'Ungültiger Monat: {monat} (muss zwischen 1 und 12 liegen)'
    return jahr, monat, None


@bp.route('/')
def dashboard():
    # Statistics
    stats = {
        'mitarbeiter_count': Mitarbeiter.query.count(),
        'mitarbeiter_aktiv': Mitarbeiter.query.filter_by(aktiv=True).count(),
        'dienste_count': Dienst.query.count(),
        'regeln_count': Regel.query.count(),
        'regeln_aktiv': Regel.query.filter_by(aktiv=True).count(),
        'konflikte_count': 0
    }

    # Current week data
    heute = date.today()
    montag = heute - timedelta(days=heute.weekday())
    wochentage = []
    for i in range(7):
        tag = montag + timedelta(days=i)
        wochentage.append({
            'name': ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'][i],
            'datum': tag.strftime('%d.%m.'),
            'date': tag,
            'ist_heute': tag == heute
        })

    # Get schedules for current week
    mitarbeiter = Mitarbeiter.query.filter_by(aktiv=True).order_by(Mitarbeiter.name).all()
    wochenplan = []

    for ma in mitarbeiter:
        ma_dienste = []
        for tag in wochentage:
            dp = Dienstplan.query.filter_by(
                mitarbeiter_id=ma.id,
                datum=tag['date']
            ).first()
            if dp:
                ma_dienste.append({
                    'kurzname': dp.dienst.kurzname,
                    'farbe': dp.dienst.farbe
                })
            else:
                ma_dienste.append(None)

        wochenplan.append({
            'name': ma.name,
            'dienste': ma_dienste
        })

    # Get conflicts
    konflikt_service = KonfliktErkennung()
    konflikte = konflikt_service.pruefe_monat(heute.year, heute.month)
    stats['konflikte_count'] = len(konflikte)

    return render_template('dashboard.html',
                           stats=stats,
                           wochentage=wochentage,
                           wochenplan=wochenplan,
                           konflikte=konflikte[:5])


@bp.route('/kalender')
def kalender():
    # Get year and month from query params
    jahr = request.args.get('jahr', date.today().year, type=int)
    monat = request.args.get('monat', date.today().month, type=int)

    # Validierung
    jahr, monat, error = validate_jahr_monat(jahr, monat)
    if error:
        flash(error, 'danger')
        return redirect(url_for('planung.dashboard'))

    # Calculate previous/next month
    aktuell = date(jahr, monat, 1)
    vorheriger = aktuell - relativedelta(months=1)
    naechster = aktuell + relativedelta(months=1)

    # Get calendar data
    cal = calendar.Calendar(firstweekday=0)
    monatstage = list(cal.itermonthdays2(jahr, monat))

    # Get all schedules for this month
    start_datum = date(jahr, monat, 1)
    if monat == 12:
        ende_datum = date(jahr + 1, 1, 1)
    else:
        ende_datum = date(jahr, monat + 1, 1)

    dienstplaene = Dienstplan.query.filter(
        Dienstplan.datum >= start_datum,
        Dienstplan.datum < ende_datum
    ).all()

    # Organize by date and employee
    plan_dict = {}
    for dp in dienstplaene:
        key = (dp.datum, dp.mitarbeiter_id)
        plan_dict[key] = dp

    # Get employees and shifts
    mitarbeiter = Mitarbeiter.query.filter_by(aktiv=True).order_by(Mitarbeiter.name).all()
    dienste = Dienst.query.order_by(Dienst.start_zeit).all()

    # Get wishes for this month
    wuensche = MitarbeiterWunsch.query.filter(
        MitarbeiterWunsch.datum >= start_datum,
        MitarbeiterWunsch.datum < ende_datum
    ).all()

    wunsch_dict = {}
    ausschluss_dict = {}
    for w in wuensche:
        key = (w.datum, w.mitarbeiter_id)
        if w.wunsch_typ == WunschTyp.DIENST_AUSSCHLUSS:
            if key not in ausschluss_dict:
                ausschluss_dict[key] = []
            ausschluss_dict[key].append(w)
        else:
            wunsch_dict[key] = w

    # Calculate hours per employee for this month
    stunden_dict = {}
    _, num_days = calendar.monthrange(jahr, monat)
    wochen_im_monat = num_days / 7.0

    for ma in mitarbeiter:
        # Get scheduled shifts for this employee
        ma_shifts = [dp for dp in dienstplaene if dp.mitarbeiter_id == ma.id]

        # Sum up hours
        geplante_stunden = 0.0
        for dp in ma_shifts:
            geplante_stunden += dp.dienst.get_dauer_stunden()

        # Calculate target hours for this month
        soll_stunden = ma.arbeitsstunden_woche * wochen_im_monat

        # Calculate percentage
        prozent = (geplante_stunden / soll_stunden * 100) if soll_stunden > 0 else 0

        stunden_dict[ma.id] = {
            'geplant': geplante_stunden,
            'soll': soll_stunden,
            'prozent': prozent
        }

    return render_template('planung/kalender.html',
                           jahr=jahr,
                           monat=monat,
                           monat_name=calendar.month_name[monat],
                           vorheriger=vorheriger,
                           naechster=naechster,
                           monatstage=monatstage,
                           mitarbeiter=mitarbeiter,
                           dienste=dienste,
                           plan_dict=plan_dict,
                           wunsch_dict=wunsch_dict,
                           ausschluss_dict=ausschluss_dict,
                           stunden_dict=stunden_dict,
                           heute=date.today())


@bp.route('/api/eintrag', methods=['POST'])
def api_eintrag():
    """Create or update a schedule entry"""
    data = request.get_json()

    mitarbeiter_id = data.get('mitarbeiter_id')
    datum_str = data.get('datum')
    dienst_id = data.get('dienst_id')

    if not mitarbeiter_id or not datum_str:
        return jsonify({'error': 'Mitarbeiter und Datum sind erforderlich'}), 400

    try:
        datum = datetime.strptime(datum_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Ungültiges Datumsformat'}), 400

    # Find existing entry
    existing = Dienstplan.query.filter_by(
        mitarbeiter_id=mitarbeiter_id,
        datum=datum
    ).first()

    try:
        if dienst_id:
            # Create or update
            if existing:
                existing.dienst_id = dienst_id
                existing.status = DienstplanStatus.GEPLANT
            else:
                dp = Dienstplan(
                    datum=datum,
                    mitarbeiter_id=mitarbeiter_id,
                    dienst_id=dienst_id,
                    status=DienstplanStatus.GEPLANT
                )
                db.session.add(dp)
        else:
            # Delete if exists
            if existing:
                db.session.delete(existing)

        db.session.commit()
        return jsonify({'success': True})

    except IntegrityError:
        db.session.rollback()
        # Race condition: Entry was created by another request
        # Retry with update
        existing = Dienstplan.query.filter_by(
            mitarbeiter_id=mitarbeiter_id,
            datum=datum
        ).first()
        if existing and dienst_id:
            existing.dienst_id = dienst_id
            existing.status = DienstplanStatus.GEPLANT
            db.session.commit()
            return jsonify({'success': True})
        return jsonify({'error': 'Konflikt bei gleichzeitiger Bearbeitung'}), 409


@bp.route('/api/wunsch', methods=['POST'])
def api_wunsch():
    """Create or update an employee wish"""
    data = request.get_json()

    mitarbeiter_id = data.get('mitarbeiter_id')
    datum_str = data.get('datum')
    wunsch_typ = data.get('wunsch_typ')
    dienst_id = data.get('dienst_id')

    if not mitarbeiter_id or not datum_str:
        return jsonify({'error': 'Mitarbeiter und Datum sind erforderlich'}), 400

    try:
        datum = datetime.strptime(datum_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Ungültiges Datumsformat'}), 400

    if wunsch_typ:
        try:
            wunsch_typ_enum = WunschTyp(wunsch_typ)
        except ValueError:
            return jsonify({'error': 'Ungültiger Wunschtyp'}), 400

        # Delete existing non-exclusion wish first
        existing = MitarbeiterWunsch.query.filter(
            MitarbeiterWunsch.mitarbeiter_id == mitarbeiter_id,
            MitarbeiterWunsch.datum == datum,
            MitarbeiterWunsch.wunsch_typ != WunschTyp.DIENST_AUSSCHLUSS
        ).first()

        if existing:
            existing.wunsch_typ = wunsch_typ_enum
            existing.dienst_id = dienst_id if wunsch_typ == 'dienst_wunsch' else None
        else:
            wunsch = MitarbeiterWunsch(
                mitarbeiter_id=mitarbeiter_id,
                datum=datum,
                wunsch_typ=wunsch_typ_enum,
                dienst_id=dienst_id if wunsch_typ == 'dienst_wunsch' else None
            )
            db.session.add(wunsch)
    else:
        # Delete all wishes for this day (including exclusions)
        MitarbeiterWunsch.query.filter_by(
            mitarbeiter_id=mitarbeiter_id,
            datum=datum
        ).delete()

    db.session.commit()

    return jsonify({'success': True})


@bp.route('/generieren', methods=['GET', 'POST'])
def generieren():
    if request.method == 'POST':
        jahr = request.form.get('jahr', type=int)
        monat = request.form.get('monat', type=int)
        ueberschreiben = request.form.get('ueberschreiben') == 'on'

        if not jahr or not monat:
            flash('Jahr und Monat sind erforderlich.', 'danger')
            return redirect(url_for('planung.generieren'))

        planer = DienstPlaner()
        try:
            result = planer.generiere_plan(jahr, monat, ueberschreiben=ueberschreiben)

            if result['erfolg']:
                if result.get('teilweise'):
                    flash(f'Teillösung für {monat}/{jahr}: {result["eintraege"]} Einträge erstellt. '
                          f'Vollständige Planung war nicht möglich.', 'warning')
                else:
                    flash(f'Dienstplan für {monat}/{jahr} wurde erfolgreich generiert. '
                          f'{result["eintraege"]} Einträge erstellt.', 'success')

                # Show warnings
                for warnung in result.get('warnungen', []):
                    flash(warnung, 'warning')

            else:
                flash(f'Planung fehlgeschlagen: {result["fehler"]}', 'danger')

            # Show diagnostics
            for diag in result.get('diagnose', []):
                if diag['schwere'] == 'kritisch':
                    flash(f'Problem: {diag["text"]}', 'danger')
                else:
                    flash(f'Hinweis: {diag["text"]}', 'warning')

        except Exception as e:
            flash(f'Fehler bei der Planung: {str(e)}', 'danger')

        return redirect(url_for('planung.kalender', jahr=jahr, monat=monat))

    # GET: Show generation form
    heute = date.today()
    regeln = Regel.query.filter_by(aktiv=True).order_by(Regel.prioritaet, Regel.name).all()
    mitarbeiter_count = Mitarbeiter.query.filter_by(aktiv=True).count()
    dienste_count = Dienst.query.count()

    return render_template('planung/generieren.html',
                           jahr=heute.year,
                           monat=heute.month,
                           regeln=regeln,
                           mitarbeiter_count=mitarbeiter_count,
                           dienste_count=dienste_count)


@bp.route('/konflikte')
def konflikte():
    jahr = request.args.get('jahr', date.today().year, type=int)
    monat = request.args.get('monat', date.today().month, type=int)

    # Validierung
    jahr, monat, error = validate_jahr_monat(jahr, monat)
    if error:
        flash(error, 'danger')
        return redirect(url_for('planung.dashboard'))

    konflikt_service = KonfliktErkennung()
    konflikte = konflikt_service.pruefe_monat(jahr, monat)

    return render_template('planung/konflikte.html',
                           konflikte=konflikte,
                           jahr=jahr,
                           monat=monat,
                           monat_name=calendar.month_name[monat])


@bp.route('/export')
def export():
    return render_template('planung/export.html')


@bp.route('/api/ausschluss', methods=['GET', 'POST'])
def api_ausschluss():
    """Get or set shift exclusions for an employee on a date"""
    if request.method == 'GET':
        mitarbeiter_id = request.args.get('mitarbeiter_id', type=int)
        datum_str = request.args.get('datum')

        if not mitarbeiter_id or not datum_str:
            return jsonify({'error': 'Parameter fehlen'}), 400

        try:
            datum = datetime.strptime(datum_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Ungültiges Datumsformat'}), 400

        # Find all exclusions for this employee/date
        ausschluesse = MitarbeiterWunsch.query.filter_by(
            mitarbeiter_id=mitarbeiter_id,
            datum=datum,
            wunsch_typ=WunschTyp.DIENST_AUSSCHLUSS
        ).all()

        return jsonify({
            'ausschluesse': [w.dienst_id for w in ausschluesse if w.dienst_id]
        })

    else:  # POST
        data = request.get_json()
        mitarbeiter_id = data.get('mitarbeiter_id')
        datum_str = data.get('datum')
        dienst_id = data.get('dienst_id')
        aktiv = data.get('aktiv', True)

        if not mitarbeiter_id or not datum_str or not dienst_id:
            return jsonify({'error': 'Parameter fehlen'}), 400

        try:
            datum = datetime.strptime(datum_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Ungültiges Datumsformat'}), 400

        # Find existing exclusion
        existing = MitarbeiterWunsch.query.filter_by(
            mitarbeiter_id=mitarbeiter_id,
            datum=datum,
            wunsch_typ=WunschTyp.DIENST_AUSSCHLUSS,
            dienst_id=dienst_id
        ).first()

        if aktiv:
            # Add exclusion if not exists
            if not existing:
                ausschluss = MitarbeiterWunsch(
                    mitarbeiter_id=mitarbeiter_id,
                    datum=datum,
                    wunsch_typ=WunschTyp.DIENST_AUSSCHLUSS,
                    dienst_id=dienst_id
                )
                db.session.add(ausschluss)
        else:
            # Remove exclusion if exists
            if existing:
                db.session.delete(existing)

        db.session.commit()
        return jsonify({'success': True})


@bp.route('/api/export/<format>')
def api_export(format):
    jahr = request.args.get('jahr', date.today().year, type=int)
    monat = request.args.get('monat', date.today().month, type=int)

    # Validierung
    jahr, monat, error = validate_jahr_monat(jahr, monat)
    if error:
        return jsonify({'error': error}), 400

    from app.services.export import ExportService
    export_service = ExportService()

    if format == 'pdf':
        return export_service.export_pdf(jahr, monat)
    elif format == 'excel':
        return export_service.export_excel(jahr, monat)
    else:
        return jsonify({'error': 'Unbekanntes Format'}), 400


@bp.route('/stundenübersicht')
def stundenuebersicht():
    """Soll/Ist Stundenübersicht pro Mitarbeiter"""
    jahr = request.args.get('jahr', date.today().year, type=int)
    monat = request.args.get('monat', date.today().month, type=int)

    # Validierung
    jahr, monat, error = validate_jahr_monat(jahr, monat)
    if error:
        flash(error, 'danger')
        return redirect(url_for('planung.dashboard'))

    # Vorheriger/Nächster Monat für Navigation
    aktuell = date(jahr, monat, 1)
    vorheriger = aktuell - relativedelta(months=1)
    naechster = aktuell + relativedelta(months=1)

    # Monatsinfos
    _, num_days = calendar.monthrange(jahr, monat)
    wochen_im_monat = num_days / 7.0

    # Alle Dienstplaneinträge für den Monat
    start_datum = date(jahr, monat, 1)
    ende_datum = date(jahr, monat, num_days)

    dienstplaene = Dienstplan.query.filter(
        Dienstplan.datum >= start_datum,
        Dienstplan.datum <= ende_datum
    ).all()

    # Gruppiere nach Mitarbeiter
    ma_stunden = {}
    ma_dienste_count = {}

    for dp in dienstplaene:
        mid = dp.mitarbeiter_id
        if mid not in ma_stunden:
            ma_stunden[mid] = 0.0
            ma_dienste_count[mid] = {}

        stunden = dp.dienst.get_dauer_stunden()
        ma_stunden[mid] += stunden

        # Zähle Dienste nach Typ
        dname = dp.dienst.kurzname
        if dname not in ma_dienste_count[mid]:
            ma_dienste_count[mid][dname] = 0
        ma_dienste_count[mid][dname] += 1

    # Mitarbeiter laden und Soll/Ist berechnen
    mitarbeiter = Mitarbeiter.query.filter_by(aktiv=True).order_by(Mitarbeiter.name).all()
    dienste = Dienst.query.order_by(Dienst.start_zeit).all()

    uebersicht = []
    gesamt_soll = 0
    gesamt_ist = 0

    for ma in mitarbeiter:
        soll = ma.arbeitsstunden_woche * wochen_im_monat
        ist = ma_stunden.get(ma.id, 0.0)
        differenz = ist - soll
        prozent = (ist / soll * 100) if soll > 0 else 0

        # Dienst-Aufschlüsselung
        dienste_detail = ma_dienste_count.get(ma.id, {})

        uebersicht.append({
            'mitarbeiter': ma,
            'soll': round(soll, 1),
            'ist': round(ist, 1),
            'differenz': round(differenz, 1),
            'prozent': round(prozent, 1),
            'dienste': dienste_detail,
            'arbeitstage': sum(dienste_detail.values())
        })

        gesamt_soll += soll
        gesamt_ist += ist

    # Nach Differenz sortieren (wer hat am meisten Überstunden/Unterstunden?)
    sortierung = request.args.get('sort', 'name')
    if sortierung == 'differenz':
        uebersicht.sort(key=lambda x: x['differenz'], reverse=True)
    elif sortierung == 'differenz_asc':
        uebersicht.sort(key=lambda x: x['differenz'])
    elif sortierung == 'prozent':
        uebersicht.sort(key=lambda x: x['prozent'], reverse=True)
    elif sortierung == 'ist':
        uebersicht.sort(key=lambda x: x['ist'], reverse=True)
    # Default: nach Name (bereits sortiert)

    return render_template('planung/stundenuebersicht.html',
                           jahr=jahr,
                           monat=monat,
                           monat_name=calendar.month_name[monat],
                           vorheriger=vorheriger,
                           naechster=naechster,
                           uebersicht=uebersicht,
                           dienste=dienste,
                           gesamt_soll=round(gesamt_soll, 1),
                           gesamt_ist=round(gesamt_ist, 1),
                           gesamt_differenz=round(gesamt_ist - gesamt_soll, 1),
                           sortierung=sortierung)


@bp.route('/api/diagnose')
def api_diagnose():
    """Diagnose-Endpoint: Prüft ob Planung möglich ist"""
    jahr = request.args.get('jahr', date.today().year, type=int)
    monat = request.args.get('monat', date.today().month, type=int)

    # Validierung
    jahr, monat, error = validate_jahr_monat(jahr, monat)
    if error:
        return jsonify({'error': error}), 400

    mitarbeiter = Mitarbeiter.query.filter_by(aktiv=True).all()
    dienste = Dienst.query.all()
    _, num_days = calendar.monthrange(jahr, monat)
    tage = list(range(1, num_days + 1))

    probleme = []

    # Check 1: Gibt es Mitarbeiter?
    if not mitarbeiter:
        probleme.append({
            'typ': 'KEINE_MITARBEITER',
            'text': 'Keine aktiven Mitarbeiter vorhanden.',
            'schwere': 'kritisch'
        })
        return jsonify({'probleme': probleme, 'jahr': jahr, 'monat': monat})

    # Check 2: Gibt es Dienste?
    if not dienste:
        probleme.append({
            'typ': 'KEINE_DIENSTE',
            'text': 'Keine Dienste konfiguriert.',
            'schwere': 'kritisch'
        })
        return jsonify({'probleme': probleme, 'jahr': jahr, 'monat': monat})

    # Check 3: Kapazität
    verfuegbare_schichten = len(mitarbeiter) * len(tage)
    benoetigte_schichten = sum(d.min_besetzung or 0 for d in dienste) * len(tage)

    if benoetigte_schichten > verfuegbare_schichten:
        probleme.append({
            'typ': 'KAPAZITAET',
            'text': f'Kapazitätsproblem: {len(mitarbeiter)} MA × {len(tage)} Tage = max. {verfuegbare_schichten} Schichten, '
                    f'aber Mindestbesetzung erfordert {benoetigte_schichten} Schichten.',
            'schwere': 'kritisch'
        })

    # Check 4: Qualifikationen pro Dienst
    for d in dienste:
        erforderliche = d.get_erforderliche_qualifikationen()
        if erforderliche:
            qualifizierte = [m for m in mitarbeiter if d.kann_mitarbeiter_arbeiten(m)]
            if len(qualifizierte) == 0:
                probleme.append({
                    'typ': 'KEINE_QUALIFIKATION',
                    'text': f'Dienst "{d.name}" ({d.kurzname}): Kein MA hat erforderliche Qualifikation '
                            f'({", ".join(q.name for q in erforderliche)}).',
                    'schwere': 'kritisch'
                })
            elif len(qualifizierte) < (d.min_besetzung or 1):
                probleme.append({
                    'typ': 'ZU_WENIG_QUALIFIZIERT',
                    'text': f'Dienst "{d.name}": Nur {len(qualifizierte)} qualifizierte MA, '
                            f'aber Mindestbesetzung ist {d.min_besetzung}.',
                    'schwere': 'warnung'
                })

    # Summary
    zusammenfassung = {
        'mitarbeiter_aktiv': len(mitarbeiter),
        'dienste': len(dienste),
        'tage_im_monat': len(tage),
        'max_schichten': verfuegbare_schichten,
        'min_benoetigte_schichten': benoetigte_schichten,
        'kritische_probleme': len([p for p in probleme if p['schwere'] == 'kritisch']),
        'warnungen': len([p for p in probleme if p['schwere'] == 'warnung'])
    }

    return jsonify({
        'probleme': probleme,
        'zusammenfassung': zusammenfassung,
        'jahr': jahr,
        'monat': monat,
        'planbar': len([p for p in probleme if p['schwere'] == 'kritisch']) == 0
    })

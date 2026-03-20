import pytest
from datetime import date, time
from app import create_app, db
from app.models import (
    Mitarbeiter, Qualifikation, MitarbeiterQualifikation,
    Dienst, DienstQualifikation, Regel, RegelTyp,
    Dienstplan, DienstplanStatus, MitarbeiterWunsch, WunschTyp,
    User
)


@pytest.fixture
def app():
    """Create application for testing"""
    app = create_app('testing')

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Create authenticated test client"""
    with app.app_context():
        User.create_admin('admin', 'admin123')
    client = app.test_client()
    client.post('/login', data={
        'username': 'admin',
        'password': 'admin123'
    })
    return client


@pytest.fixture
def runner(app):
    """Create CLI runner"""
    return app.test_cli_runner()


@pytest.fixture
def sample_qualifikationen(app):
    """Create sample qualifications"""
    with app.app_context():
        q1 = Qualifikation(name='Examinierte Pflegekraft', farbe='#28a745')
        q2 = Qualifikation(name='Pflegehelferin', farbe='#6c757d')
        q3 = Qualifikation(name='Praxisanleiterin', farbe='#007bff')

        db.session.add_all([q1, q2, q3])
        db.session.commit()

        return [q1.id, q2.id, q3.id]


@pytest.fixture
def sample_dienste(app):
    """Create sample shifts"""
    with app.app_context():
        d1 = Dienst(
            name='Frühdienst',
            kurzname='F',
            start_zeit=time(6, 0),
            ende_zeit=time(14, 0),
            farbe='#ffc107'
        )
        d2 = Dienst(
            name='Spätdienst',
            kurzname='S',
            start_zeit=time(14, 0),
            ende_zeit=time(22, 0),
            farbe='#17a2b8'
        )
        d3 = Dienst(
            name='Nachtdienst',
            kurzname='N',
            start_zeit=time(22, 0),
            ende_zeit=time(6, 0),
            farbe='#343a40'
        )

        db.session.add_all([d1, d2, d3])
        db.session.commit()

        return [d1.id, d2.id, d3.id]


@pytest.fixture
def sample_mitarbeiter(app, sample_qualifikationen):
    """Create sample employees"""
    with app.app_context():
        qual_ids = sample_qualifikationen

        m1 = Mitarbeiter(
            name='Anna Müller',
            personalnummer='P001',
            email='anna@example.com',
            stellenanteil=100.0,
            aktiv=True
        )
        m2 = Mitarbeiter(
            name='Bernd Schmidt',
            personalnummer='P002',
            stellenanteil=100.0,
            aktiv=True
        )
        m3 = Mitarbeiter(
            name='Clara Weber',
            personalnummer='P003',
            stellenanteil=75.0,
            aktiv=True
        )

        db.session.add_all([m1, m2, m3])
        db.session.flush()

        # Add qualifications
        mq1 = MitarbeiterQualifikation(
            mitarbeiter_id=m1.id,
            qualifikation_id=qual_ids[0],
            erworben_am=date(2020, 1, 1)
        )
        mq2 = MitarbeiterQualifikation(
            mitarbeiter_id=m2.id,
            qualifikation_id=qual_ids[0],
            erworben_am=date(2019, 6, 1)
        )
        mq3 = MitarbeiterQualifikation(
            mitarbeiter_id=m3.id,
            qualifikation_id=qual_ids[1],
            erworben_am=date(2021, 3, 1)
        )

        db.session.add_all([mq1, mq2, mq3])
        db.session.commit()

        return [m1.id, m2.id, m3.id]


@pytest.fixture
def sample_regeln(app, sample_dienste, sample_qualifikationen):
    """Create sample rules"""
    with app.app_context():
        r1 = Regel(
            name='Max 5 Tage hintereinander',
            typ=RegelTyp.MAX_TAGE_FOLGE,
            parameter={'max': 5},
            prioritaet=1,
            aktiv=True
        )
        r2 = Regel(
            name='Mindest-Ruhezeit 11h',
            typ=RegelTyp.MIN_RUHEZEIT,
            parameter={'stunden': 11},
            prioritaet=1,
            aktiv=True
        )
        r3 = Regel(
            name='Mind. 1 Person Frühdienst',
            typ=RegelTyp.MIN_PERSONAL_DIENST,
            parameter={'dienst_id': sample_dienste[0], 'min': 1},
            prioritaet=2,
            aktiv=True
        )

        db.session.add_all([r1, r2, r3])
        db.session.commit()

        return [r1.id, r2.id, r3.id]

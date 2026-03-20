"""
Tests für Datenmodelle
"""
import pytest
from datetime import date, time, timedelta
from app import db
from app.models import (
    Mitarbeiter, Qualifikation, MitarbeiterQualifikation,
    Dienst, DienstQualifikation, Regel, RegelTyp,
    Dienstplan, DienstplanStatus
)


class TestQualifikation:
    """Tests für Qualifikation Model"""

    def test_create_qualifikation(self, app):
        with app.app_context():
            q = Qualifikation(name='Testqualifikation', farbe='#ff0000')
            db.session.add(q)
            db.session.commit()

            assert q.id is not None
            assert q.name == 'Testqualifikation'
            assert q.farbe == '#ff0000'

    def test_to_dict(self, app):
        with app.app_context():
            q = Qualifikation(name='Test', beschreibung='Beschreibung', farbe='#00ff00')
            db.session.add(q)
            db.session.commit()

            d = q.to_dict()
            assert d['name'] == 'Test'
            assert d['beschreibung'] == 'Beschreibung'
            assert d['farbe'] == '#00ff00'


class TestMitarbeiter:
    """Tests für Mitarbeiter Model"""

    def test_create_mitarbeiter(self, app):
        with app.app_context():
            m = Mitarbeiter(
                name='Test Person',
                personalnummer='T001',
                email='test@example.com',
                stellenanteil=100.0
            )
            db.session.add(m)
            db.session.commit()

            assert m.id is not None
            assert m.name == 'Test Person'
            assert m.aktiv == True

    def test_hat_qualifikation(self, app, sample_mitarbeiter, sample_qualifikationen):
        with app.app_context():
            m = Mitarbeiter.query.get(sample_mitarbeiter[0])

            # Should have first qualification
            assert m.hat_qualifikation(sample_qualifikationen[0]) == True
            # Should not have third qualification
            assert m.hat_qualifikation(sample_qualifikationen[2]) == False

    def test_get_gueltige_qualifikationen(self, app, sample_mitarbeiter):
        with app.app_context():
            m = Mitarbeiter.query.get(sample_mitarbeiter[0])
            quals = m.get_gueltige_qualifikationen()

            assert len(quals) >= 1

    def test_to_dict(self, app, sample_mitarbeiter):
        with app.app_context():
            m = Mitarbeiter.query.get(sample_mitarbeiter[0])
            d = m.to_dict()

            assert d['name'] == 'Anna Müller'
            assert d['personalnummer'] == 'P001'
            assert 'qualifikationen' in d


class TestDienst:
    """Tests für Dienst Model"""

    def test_create_dienst(self, app):
        with app.app_context():
            d = Dienst(
                name='Testdienst',
                kurzname='T',
                start_zeit=time(8, 0),
                ende_zeit=time(16, 0),
                farbe='#0000ff'
            )
            db.session.add(d)
            db.session.commit()

            assert d.id is not None
            assert d.name == 'Testdienst'

    def test_get_dauer_stunden(self, app, sample_dienste):
        with app.app_context():
            # Frühdienst: 6:00 - 14:00 = 8 Stunden
            d = Dienst.query.get(sample_dienste[0])
            assert d.get_dauer_stunden() == 8.0

    def test_get_dauer_stunden_nachtdienst(self, app, sample_dienste):
        with app.app_context():
            # Nachtdienst: 22:00 - 06:00 = 8 Stunden
            d = Dienst.query.get(sample_dienste[2])
            assert d.get_dauer_stunden() == 8.0


class TestRegel:
    """Tests für Regel Model"""

    def test_create_regel(self, app):
        with app.app_context():
            r = Regel(
                name='Testregel',
                typ=RegelTyp.MAX_TAGE_FOLGE,
                parameter={'max': 5},
                prioritaet=1
            )
            db.session.add(r)
            db.session.commit()

            assert r.id is not None
            assert r.parameter == {'max': 5}

    def test_to_dict(self, app, sample_regeln):
        with app.app_context():
            r = Regel.query.get(sample_regeln[0])
            d = r.to_dict()

            assert d['name'] == 'Max 5 Tage hintereinander'
            assert d['typ'] == 'MAX_TAGE_FOLGE'
            assert d['prioritaet_text'] == 'Hart'


class TestDienstplan:
    """Tests für Dienstplan Model"""

    def test_create_dienstplan(self, app, sample_mitarbeiter, sample_dienste):
        with app.app_context():
            dp = Dienstplan(
                datum=date.today(),
                mitarbeiter_id=sample_mitarbeiter[0],
                dienst_id=sample_dienste[0],
                status=DienstplanStatus.GEPLANT
            )
            db.session.add(dp)
            db.session.commit()

            assert dp.id is not None
            assert dp.status == DienstplanStatus.GEPLANT

    def test_unique_constraint(self, app, sample_mitarbeiter, sample_dienste):
        with app.app_context():
            dp1 = Dienstplan(
                datum=date.today(),
                mitarbeiter_id=sample_mitarbeiter[0],
                dienst_id=sample_dienste[0]
            )
            db.session.add(dp1)
            db.session.commit()

            # Try to add another entry for same employee and day
            dp2 = Dienstplan(
                datum=date.today(),
                mitarbeiter_id=sample_mitarbeiter[0],
                dienst_id=sample_dienste[1]
            )
            db.session.add(dp2)

            with pytest.raises(Exception):
                db.session.commit()

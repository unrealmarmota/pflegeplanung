"""
Tests für API-Routen
"""
import pytest
import json
from datetime import date
from app import db
from app.models import Qualifikation, Mitarbeiter, Dienst, Regel


class TestQualifikationenRoutes:
    """Tests für Qualifikationen-Routen"""

    def test_index(self, client, app):
        response = client.get('/qualifikationen/')
        assert response.status_code == 200
        assert b'Qualifikationen' in response.data

    def test_create_get(self, client, app):
        response = client.get('/qualifikationen/neu')
        assert response.status_code == 200
        assert b'Neue Qualifikation' in response.data

    def test_create_post(self, client, app):
        response = client.post('/qualifikationen/neu', data={
            'name': 'Neue Qualifikation',
            'beschreibung': 'Eine Beschreibung',
            'farbe': '#ff0000'
        }, follow_redirects=True)

        assert response.status_code == 200

        with app.app_context():
            q = Qualifikation.query.filter_by(name='Neue Qualifikation').first()
            assert q is not None

    def test_api_list(self, client, app, sample_qualifikationen):
        response = client.get('/qualifikationen/api/list')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'qualifikationen' in data
        assert len(data['qualifikationen']) == 3


class TestMitarbeiterRoutes:
    """Tests für Mitarbeiter-Routen"""

    def test_index(self, client, app):
        response = client.get('/mitarbeiter/')
        assert response.status_code == 200
        assert b'Mitarbeiter' in response.data

    def test_create_get(self, client, app):
        response = client.get('/mitarbeiter/neu')
        assert response.status_code == 200
        assert b'Neuer Mitarbeiter' in response.data

    def test_create_post(self, client, app, sample_qualifikationen):
        response = client.post('/mitarbeiter/neu', data={
            'name': 'Test Mitarbeiter',
            'personalnummer': 'T999',
            'email': 'test@example.com',
            'stellenanteil': '100',
            'aktiv': 'on'
        }, follow_redirects=True)

        assert response.status_code == 200

        with app.app_context():
            m = Mitarbeiter.query.filter_by(personalnummer='T999').first()
            assert m is not None
            assert m.name == 'Test Mitarbeiter'

    def test_api_list(self, client, app, sample_mitarbeiter):
        response = client.get('/mitarbeiter/api/list')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'mitarbeiter' in data


class TestDiensteRoutes:
    """Tests für Dienste-Routen"""

    def test_index(self, client, app):
        response = client.get('/dienste/')
        assert response.status_code == 200
        assert b'Dienste' in response.data

    def test_create_post(self, client, app):
        response = client.post('/dienste/neu', data={
            'name': 'Testdienst',
            'kurzname': 'T',
            'start_zeit': '08:00',
            'ende_zeit': '16:00',
            'farbe': '#00ff00'
        }, follow_redirects=True)

        assert response.status_code == 200

        with app.app_context():
            d = Dienst.query.filter_by(name='Testdienst').first()
            assert d is not None

    def test_api_list(self, client, app, sample_dienste):
        response = client.get('/dienste/api/list')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'dienste' in data
        assert len(data['dienste']) == 3


class TestRegelnRoutes:
    """Tests für Regeln-Routen"""

    def test_index(self, client, app):
        response = client.get('/regeln/')
        assert response.status_code == 200
        assert b'Regeln' in response.data

    def test_api_typen(self, client, app):
        response = client.get('/regeln/api/typen')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert 'MAX_TAGE_FOLGE' in data
        assert 'MIN_RUHEZEIT' in data


class TestPlanungRoutes:
    """Tests für Planungs-Routen"""

    def test_dashboard(self, client, app):
        response = client.get('/planung/')
        assert response.status_code == 200
        assert b'Dashboard' in response.data

    def test_kalender(self, client, app):
        response = client.get('/planung/kalender')
        assert response.status_code == 200
        assert b'Dienstplan' in response.data

    def test_kalender_with_params(self, client, app):
        response = client.get('/planung/kalender?jahr=2024&monat=6')
        assert response.status_code == 200

    def test_generieren_get(self, client, app):
        response = client.get('/planung/generieren')
        assert response.status_code == 200
        assert b'generieren' in response.data

    def test_api_eintrag(self, client, app, sample_mitarbeiter, sample_dienste):
        response = client.post(
            '/planung/api/eintrag',
            data=json.dumps({
                'mitarbeiter_id': sample_mitarbeiter[0],
                'datum': '2024-01-15',
                'dienst_id': sample_dienste[0]
            }),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True

    def test_api_eintrag_delete(self, client, app, sample_mitarbeiter, sample_dienste):
        # First create
        client.post(
            '/planung/api/eintrag',
            data=json.dumps({
                'mitarbeiter_id': sample_mitarbeiter[0],
                'datum': '2024-01-15',
                'dienst_id': sample_dienste[0]
            }),
            content_type='application/json'
        )

        # Then delete
        response = client.post(
            '/planung/api/eintrag',
            data=json.dumps({
                'mitarbeiter_id': sample_mitarbeiter[0],
                'datum': '2024-01-15',
                'dienst_id': None
            }),
            content_type='application/json'
        )

        assert response.status_code == 200

    def test_konflikte(self, client, app):
        response = client.get('/planung/konflikte?jahr=2024&monat=1')
        assert response.status_code == 200
        assert b'Konflikte' in response.data

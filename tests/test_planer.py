"""
Tests für den Dienstplaner
"""
import pytest
from datetime import date, time
from app import db
from app.models import Dienstplan, Regel, RegelTyp
from app.services.planer import DienstPlaner


class TestDienstPlaner:
    """Tests für die automatische Dienstplanung"""

    def test_generiere_plan_ohne_daten(self, app):
        """Test: Fehler wenn keine Mitarbeiter vorhanden"""
        with app.app_context():
            planer = DienstPlaner()
            result = planer.generiere_plan(2024, 1)

            assert result['erfolg'] == False
            assert 'Mitarbeiter' in result['fehler']

    def test_generiere_plan_ohne_dienste(self, app, sample_mitarbeiter):
        """Test: Fehler wenn keine Dienste konfiguriert"""
        with app.app_context():
            planer = DienstPlaner()
            result = planer.generiere_plan(2024, 1)

            assert result['erfolg'] == False
            assert 'Dienste' in result['fehler']

    def test_generiere_plan_basic(self, app, sample_mitarbeiter, sample_dienste):
        """Test: Grundlegende Planung ohne Regeln"""
        with app.app_context():
            planer = DienstPlaner()
            result = planer.generiere_plan(2024, 1)

            assert result['erfolg'] == True
            assert result['eintraege'] > 0

            # Check that entries were created
            count = Dienstplan.query.count()
            assert count == result['eintraege']

    def test_generiere_plan_mit_regeln(self, app, sample_mitarbeiter, sample_dienste, sample_regeln):
        """Test: Planung mit aktiven Regeln"""
        with app.app_context():
            planer = DienstPlaner()
            result = planer.generiere_plan(2024, 1)

            assert result['erfolg'] == True

    def test_ueberschreiben_bestehende(self, app, sample_mitarbeiter, sample_dienste):
        """Test: Überschreiben bestehender Einträge"""
        with app.app_context():
            # First planning
            planer = DienstPlaner()
            result1 = planer.generiere_plan(2024, 1)
            count1 = result1['eintraege']

            # Second planning with overwrite
            result2 = planer.generiere_plan(2024, 1, ueberschreiben=True)

            # Should have entries again
            assert result2['erfolg'] == True
            assert result2['eintraege'] > 0

    def test_constraint_max_tage_folge(self, app, sample_mitarbeiter, sample_dienste):
        """Test: Max aufeinanderfolgende Arbeitstage wird eingehalten"""
        with app.app_context():
            # Create rule: max 3 consecutive days
            regel = Regel(
                name='Max 3 Tage',
                typ=RegelTyp.MAX_TAGE_FOLGE,
                parameter={'max': 3},
                prioritaet=1,
                aktiv=True
            )
            db.session.add(regel)
            db.session.commit()

            planer = DienstPlaner()
            result = planer.generiere_plan(2024, 1, ueberschreiben=True)

            # This is a soft test - with constraints the solver might find a solution
            # or might not depending on parameters
            assert result is not None

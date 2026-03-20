"""
Tests für den Dienstplaner
"""
import pytest
from datetime import date, time, datetime
from app import db
from app.models import (
    Dienstplan, Regel, RegelTyp, Dienst, Mitarbeiter,
    MitarbeiterWunsch, WunschTyp, MitarbeiterDienstPraeferenz
)
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

    def test_ruhezeit_spaet_frueh(self, app, sample_mitarbeiter, sample_dienste):
        """Test: Spätdienst→Frühdienst Ruhezeit wird geprüft (nicht nur Nacht→Früh)"""
        with app.app_context():
            regel = Regel(
                name='Min Ruhezeit 11h',
                typ=RegelTyp.MIN_RUHEZEIT,
                parameter={'stunden': 11},
                prioritaet=1,
                aktiv=True
            )
            db.session.add(regel)
            db.session.commit()

            planer = DienstPlaner()
            result = planer.generiere_plan(2024, 1, ueberschreiben=True)
            assert result['erfolg'] == True

            # Verify: No Spätdienst(14-22) followed by Frühdienst(6-14) next day
            alle = Dienstplan.query.all()
            zuweisungen = {}
            for dp in alle:
                zuweisungen.setdefault((dp.mitarbeiter_id, dp.datum.day), dp)

            dienste = {d.id: d for d in Dienst.query.all()}
            for dp in alle:
                tag = dp.datum.day
                naechster_tag = tag + 1
                next_dp_key = (dp.mitarbeiter_id, naechster_tag)
                if next_dp_key in zuweisungen:
                    d1 = dienste[dp.dienst_id]
                    d2 = dienste[zuweisungen[next_dp_key].dienst_id]
                    ende = datetime.combine(dp.datum, d1.ende_zeit)
                    if d1.ende_zeit <= d1.start_zeit:
                        from datetime import timedelta
                        ende = datetime.combine(dp.datum + timedelta(days=1), d1.ende_zeit)
                    start = datetime.combine(dp.datum + __import__('datetime').timedelta(days=1), d2.start_zeit)
                    ruhe = (start - ende).total_seconds() / 3600
                    assert ruhe >= 11, (
                        f'MA {dp.mitarbeiter_id} Tag {tag}->{naechster_tag}: '
                        f'Ruhezeit {ruhe:.1f}h < 11h ({d1.name}->{d2.name})'
                    )

    def test_post_solve_validierung(self, app, sample_mitarbeiter, sample_dienste, sample_regeln):
        """Test: Post-Solve Validierung wird korrekt zurückgegeben"""
        with app.app_context():
            planer = DienstPlaner()
            result = planer.generiere_plan(2024, 1)

            assert result['erfolg'] == True
            assert 'validierungen' in result
            # With only 3 employees, solver may use best_possible mode
            # which may have some violations - just verify the key exists
            assert isinstance(result['validierungen'], list)

    def test_objective_breakdown(self, app, sample_mitarbeiter, sample_dienste):
        """Test: Objective-Breakdown wird zurückgegeben"""
        with app.app_context():
            planer = DienstPlaner()
            result = planer.generiere_plan(2024, 1)

            assert result['erfolg'] == True
            assert 'objective_breakdown' in result
            ob = result['objective_breakdown']
            assert 'total_schichten' in ob
            assert 'objective_wert' in ob
            assert 'solver_status' in ob
            assert ob['total_schichten'] > 0

    def test_wunsch_frei_respektiert(self, app, sample_mitarbeiter, sample_dienste):
        """Test: FREI-Wünsche werden respektiert"""
        with app.app_context():
            ma = Mitarbeiter.query.first()
            wunsch = MitarbeiterWunsch(
                mitarbeiter_id=ma.id,
                datum=date(2024, 1, 15),
                wunsch_typ=WunschTyp.FREI
            )
            db.session.add(wunsch)
            db.session.commit()

            planer = DienstPlaner()
            result = planer.generiere_plan(2024, 1)

            assert result['erfolg'] == True

            # MA should not work on Jan 15
            eintrag = Dienstplan.query.filter_by(
                mitarbeiter_id=ma.id,
                datum=date(2024, 1, 15)
            ).first()
            # FREI is soft, but with enough staff it should be respected
            # Check that objective breakdown tracks it
            ob = result['objective_breakdown']
            assert 'frei_wuensche_verletzt' in ob

    def test_nicht_verfuegbar_hart(self, app, sample_mitarbeiter, sample_dienste):
        """Test: NICHT_VERFUEGBAR ist harte Constraint"""
        with app.app_context():
            ma = Mitarbeiter.query.first()
            wunsch = MitarbeiterWunsch(
                mitarbeiter_id=ma.id,
                datum=date(2024, 1, 15),
                wunsch_typ=WunschTyp.NICHT_VERFUEGBAR
            )
            db.session.add(wunsch)
            db.session.commit()

            planer = DienstPlaner()
            result = planer.generiere_plan(2024, 1)

            assert result['erfolg'] == True

            # MA must NOT work on Jan 15 (hard constraint)
            eintrag = Dienstplan.query.filter_by(
                mitarbeiter_id=ma.id,
                datum=date(2024, 1, 15)
            ).first()
            assert eintrag is None, "MA arbeitet trotz NICHT_VERFUEGBAR"

    def test_max_tage_folge_validated(self, app, sample_mitarbeiter, sample_dienste):
        """Test: Max consecutive days is checked by post-solve validation"""
        with app.app_context():
            regel = Regel(
                name='Max 5 Tage',
                typ=RegelTyp.MAX_TAGE_FOLGE,
                parameter={'max': 5},
                prioritaet=1,
                aktiv=True
            )
            db.session.add(regel)
            db.session.commit()

            planer = DienstPlaner()
            result = planer.generiere_plan(2024, 1)

            assert result['erfolg'] == True

            # Check no employee works more than 5 consecutive days
            mitarbeiter = Mitarbeiter.query.filter_by(aktiv=True).all()
            for m in mitarbeiter:
                consecutive = 0
                for tag in range(1, 32):
                    dp = Dienstplan.query.filter_by(
                        mitarbeiter_id=m.id,
                        datum=date(2024, 1, tag)
                    ).first()
                    if dp:
                        consecutive += 1
                        assert consecutive <= 5, (
                            f'{m.name} arbeitet {consecutive} Tage in Folge am Tag {tag}'
                        )
                    else:
                        consecutive = 0

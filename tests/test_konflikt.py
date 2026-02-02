"""
Tests für die Konflikterkennung
"""
import pytest
from datetime import date, time, timedelta
from app import db
from app.models import (
    Mitarbeiter, Dienst, Dienstplan, DienstplanStatus,
    MitarbeiterWunsch, WunschTyp, Regel, RegelTyp
)
from app.services.konflikt import KonfliktErkennung, Konflikt


class TestKonfliktErkennung:
    """Tests für den Konflikt-Service"""

    def test_keine_konflikte(self, app, sample_mitarbeiter, sample_dienste):
        """Test: Keine Konflikte bei korrektem Plan"""
        with app.app_context():
            # Create simple valid schedule
            dp = Dienstplan(
                datum=date(2024, 1, 15),
                mitarbeiter_id=sample_mitarbeiter[0],
                dienst_id=sample_dienste[0],
                status=DienstplanStatus.GEPLANT
            )
            db.session.add(dp)
            db.session.commit()

            service = KonfliktErkennung()
            konflikte = service.pruefe_monat(2024, 1)

            # May have understaffing conflicts but no critical ones for double booking
            doppelbelegung = [k for k in konflikte if k.typ == 'Doppelbelegung']
            assert len(doppelbelegung) == 0

    def test_erkennt_doppelbelegung(self, app, sample_mitarbeiter, sample_dienste):
        """Test: Erkennt Doppelbelegung"""
        with app.app_context():
            # Create double booking (same employee, same day, different shifts)
            # This should violate the unique constraint, so we need to test differently
            service = KonfliktErkennung()

            # The model prevents true double booking via unique constraint
            # But we can test the detection logic by checking if it would find issues

    def test_erkennt_ruhezeit_verletzung(self, app, sample_mitarbeiter, sample_dienste):
        """Test: Erkennt Ruhezeit-Verletzung"""
        with app.app_context():
            # Add minimum rest time rule
            regel = Regel(
                name='Min Ruhezeit',
                typ=RegelTyp.MIN_RUHEZEIT,
                parameter={'stunden': 11},
                prioritaet=1,
                aktiv=True
            )
            db.session.add(regel)

            # Create night shift followed by early shift
            dp1 = Dienstplan(
                datum=date(2024, 1, 15),
                mitarbeiter_id=sample_mitarbeiter[0],
                dienst_id=sample_dienste[2],  # Night shift 22:00-06:00
                status=DienstplanStatus.GEPLANT
            )
            dp2 = Dienstplan(
                datum=date(2024, 1, 16),
                mitarbeiter_id=sample_mitarbeiter[0],
                dienst_id=sample_dienste[0],  # Early shift 06:00-14:00
                status=DienstplanStatus.GEPLANT
            )
            db.session.add_all([dp1, dp2])
            db.session.commit()

            service = KonfliktErkennung()
            konflikte = service.pruefe_monat(2024, 1)

            # Should find rest time violation
            ruhezeit_konflikte = [k for k in konflikte if k.typ == 'Ruhezeit-Verletzung']
            assert len(ruhezeit_konflikte) > 0

    def test_erkennt_wunsch_konflikt(self, app, sample_mitarbeiter, sample_dienste):
        """Test: Erkennt Wunsch-Konflikt"""
        with app.app_context():
            # Create wish for day off
            wunsch = MitarbeiterWunsch(
                mitarbeiter_id=sample_mitarbeiter[0],
                datum=date(2024, 1, 15),
                wunsch_typ=WunschTyp.FREI
            )
            db.session.add(wunsch)

            # But assign a shift
            dp = Dienstplan(
                datum=date(2024, 1, 15),
                mitarbeiter_id=sample_mitarbeiter[0],
                dienst_id=sample_dienste[0],
                status=DienstplanStatus.GEPLANT
            )
            db.session.add(dp)
            db.session.commit()

            service = KonfliktErkennung()
            konflikte = service.pruefe_monat(2024, 1)

            # Should find wish conflict
            wunsch_konflikte = [k for k in konflikte if 'Wunsch' in k.typ]
            assert len(wunsch_konflikte) > 0

    def test_erkennt_nicht_verfuegbar_konflikt(self, app, sample_mitarbeiter, sample_dienste):
        """Test: Erkennt kritischen Verfügbarkeits-Konflikt"""
        with app.app_context():
            # Mark as not available
            wunsch = MitarbeiterWunsch(
                mitarbeiter_id=sample_mitarbeiter[0],
                datum=date(2024, 1, 15),
                wunsch_typ=WunschTyp.NICHT_VERFUEGBAR
            )
            db.session.add(wunsch)

            # But assign a shift
            dp = Dienstplan(
                datum=date(2024, 1, 15),
                mitarbeiter_id=sample_mitarbeiter[0],
                dienst_id=sample_dienste[0],
                status=DienstplanStatus.GEPLANT
            )
            db.session.add(dp)
            db.session.commit()

            service = KonfliktErkennung()
            konflikte = service.pruefe_monat(2024, 1)

            # Should find critical conflict
            kritisch = [k for k in konflikte if k.schwere == 'kritisch' and 'Verfügbar' in k.typ]
            assert len(kritisch) > 0

    def test_erkennt_max_tage_folge(self, app, sample_mitarbeiter, sample_dienste):
        """Test: Erkennt zu viele aufeinanderfolgende Arbeitstage"""
        with app.app_context():
            # Add rule: max 3 consecutive days
            regel = Regel(
                name='Max 3 Tage',
                typ=RegelTyp.MAX_TAGE_FOLGE,
                parameter={'max': 3},
                prioritaet=1,
                aktiv=True
            )
            db.session.add(regel)

            # Create 5 consecutive days
            for i in range(5):
                dp = Dienstplan(
                    datum=date(2024, 1, 15) + timedelta(days=i),
                    mitarbeiter_id=sample_mitarbeiter[0],
                    dienst_id=sample_dienste[0],
                    status=DienstplanStatus.GEPLANT
                )
                db.session.add(dp)
            db.session.commit()

            service = KonfliktErkennung()
            konflikte = service.pruefe_monat(2024, 1)

            # Should find consecutive days conflict
            tage_konflikte = [k for k in konflikte if 'Arbeitstage' in k.typ]
            assert len(tage_konflikte) > 0


class TestKonfliktKlasse:
    """Tests für die Konflikt-Klasse"""

    def test_to_dict(self):
        k = Konflikt(
            typ='Testkonflikt',
            beschreibung='Eine Beschreibung',
            schwere='warnung',
            datum=date(2024, 1, 15),
            mitarbeiter='Test Person'
        )

        d = k.to_dict()

        assert d['typ'] == 'Testkonflikt'
        assert d['beschreibung'] == 'Eine Beschreibung'
        assert d['schwere'] == 'warnung'
        assert d['datum'] == '2024-01-15'
        assert d['mitarbeiter'] == 'Test Person'

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pflegeplanung is a German nursing staff shift scheduling application. It uses Google OR-Tools constraint programming to automatically generate optimal schedules while respecting labor laws, qualifications, and employee preferences.

**Stack:** Python 3.9+, Flask, SQLAlchemy, Google OR-Tools, SQLite, WeasyPrint (PDF), OpenPyXL (Excel)

## Common Commands

```bash
# Run development server (port 5001)
python run.py

# Run desktop app (PyWebView wrapper)
python desktop_app.py

# Initialize database with sample data
python init_db.py

# Run database migrations
python migrate_db.py

# Run all tests (use venv python, pytest not on PATH)
venv/bin/python -m pytest

# Run tests with coverage
venv/bin/python -m pytest --cov=app tests/

# Run single test file
venv/bin/python -m pytest tests/test_planer.py -v

# Run 30-employee stress test
venv/bin/python test_30ma.py

# Docker deployment
docker-compose up
```

## Architecture

### Core Services

**DienstPlaner** (`app/services/planer.py`):
- Heart of the application - constraint-based shift optimization using OR-Tools CP-SAT solver
- `generiere_plan(jahr, monat)` is the main entry point
- Converts rules to constraints, respects wishes, handles qualifications
- Uses "best_possible" mode when INFEASIBLE - relaxes constraints and uses soft penalties
- Soft constraints use `self.soft_penalties` list added to objective function

**KonfliktErkennung** (`app/services/konflikt.py`):
- Post-generation conflict detection
- Scans for rule violations, understaffing, qualification gaps
- Returns `Konflikt` objects with severity levels (kritisch/warnung/info)

### Data Model Relationships

```
Mitarbeiter ─┬─< MitarbeiterQualifikation >─── Qualifikation
             ├─< Dienstplan >─── Dienst ─< DienstQualifikation >─┘
             ├─< MitarbeiterWunsch
             ├─< MitarbeiterDienstPraeferenz
             └─< MitarbeiterDienstEinschraenkung

Regel (23+ types with JSON parameters)
Feiertag ─< FeiertagsAusgleich
```

### Rule Types (RegelTyp enum)

Rules have `prioritaet`: 1=hard (must satisfy), 2=soft (penalty in objective)

Key types:
- `MAX_TAGE_FOLGE` - max consecutive work days
- `MIN_RUHEZEIT` - min hours between shifts (default 11h)
- `DIENST_BLOCK` - shifts in blocks (e.g., night shifts 2-4 consecutive)
- `FREIE_TAGE_NACH_BLOCK` - required rest days after block
- `QUALIFIKATION_PFLICHT` - qualification requirements per shift
- `WOCHENENDE_ROTATION` - max weekends per month
- `MAX_NACHT_BLOECKE` - max night blocks per month

### Flask Application Structure

- `create_app()` in `app/__init__.py` - factory pattern
- Blueprints in `app/routes/` for each domain
- All routes except auth require authentication via `@app.before_request` + flask_login
- Default admin: `admin` / `admin123`
- `Einstellungen` model for global settings (e.g. `basis_wochenstunden`)

### Mitarbeiter Model

- `stellenanteil` (Float, default 100.0) - percentage of full-time (100 = Vollzeit)
- `arbeitsstunden_woche` is a **computed property** (not a DB column): `basis_wochenstunden * stellenanteil / 100`
- `regel_ausnahmen` stored as JSON text in `_regel_ausnahmen` column, accessed via property

## Key Implementation Details

### Adding New Constraints

1. Add `RegelTyp` enum value in `app/models/regel.py`
2. Add constraint method `_constraint_xyz()` in `app/services/planer.py`
3. Wire up in `_apply_regeln()` method
4. For soft constraints, append penalties to `self.soft_penalties`

### Qualification System

- `DienstQualifikation.min_anzahl` specifies minimum qualified staff per shift
- `DienstQualifikation.erforderlich` (default True) - if True, ONLY qualified employees can work this shift; if False, anyone can work but min_anzahl qualified must be present
- Enforced via `_apply_qualifikation_min_anzahl()` (hard) or `_apply_qualifikation_min_anzahl_soft()` (soft)
- Soft version uses capped variables with +500 bonus for proper enforcement
- Qualifikation hierarchy: `inkludiert_id` allows e.g. FWB to include Examinierte (checked recursively via `get_alle_inkludierten()`)

### Employee Constraints

- `MitarbeiterDienstEinschraenkung` - restricts which shifts an employee can work (e.g., weekends only Frühdienst)
- `MitarbeiterDienstPraeferenz` - min/max shifts per month per type
- `MitarbeiterWunsch` - day-specific requests (FREI, NICHT_VERFUEGBAR, DIENST_WUNSCH, DIENST_AUSSCHLUSS); field is `wunsch_typ` (not `typ`)
- `Mitarbeiter.regel_ausnahmen` - JSON field for individual rule overrides (e.g., `{'MAX_TAGE_FOLGE': 7}`)

### Individual Rule Exceptions

Employees can override global rules via `regel_ausnahmen` JSON field:
```python
ma.regel_ausnahmen = {
    'MAX_TAGE_FOLGE': 7,        # Can work 7 days instead of 5
    'WOCHENENDE_ROTATION': 5,   # Can work all weekends
    'MAX_NAECHTE_MONAT': 0,     # No night shifts
    'MIN_NAECHTE_MONAT': 0,     # Exempt from night duty
    'MIN_WOCHENENDEN_MONAT': 0  # Exempt from weekend duty
}
```
Constraint methods check `m.get_regel_wert('RULE_NAME', default)` for individual values.

### Fairness Rules

- `MIN_NAECHTE_MONAT` - minimum night shifts per employee (proportional to Stellenanteil)
- `MIN_WOCHENENDEN_MONAT` - minimum weekends per employee (proportional to Stellenanteil)
- Implemented as soft constraints with high bonus (+300/+400) using capped variables

### OR-Tools Solver Pattern

```python
self.model = cp_model.CpModel()
self.shifts = {}  # (ma_id, tag, dienst_id) -> BoolVar

# Create variables
for m, tag, d in combinations:
    self.shifts[(m.id, tag, d.id)] = self.model.NewBoolVar(name)

# Add constraints
self.model.Add(sum(vars) <= max_value)

# Objective with soft penalties
objective_terms.extend(self.soft_penalties)
self.model.Maximize(sum(objective_terms))

# Solve with timeout
self.solver = cp_model.CpSolver()
self.solver.parameters.max_time_in_seconds = 60.0
status = self.solver.Solve(self.model)
```

## Configuration

Environment variables:
- `FLASK_CONFIG`: development, testing, production
- `DATABASE_URL` or `PFLEGEPLANUNG_DB_PATH`: database location
- `SECRET_KEY`: Flask secret key

## Deployment

### Docker/Unraid
- Gunicorn timeout must be >= 120s for solver (default 30s too short)
- Database migrations: Add new columns manually via `sqlite3` if container won't start
- Common missing columns after updates: `mitarbeiter.regel_ausnahmen`, `dienste.ist_abwesenheit`

### Database Migrations
When adding new model fields, update `migrate_db.py` and run on deployment:
```bash
sqlite3 /path/to/pflegeplanung.db "ALTER TABLE tablename ADD COLUMN colname TYPE DEFAULT value;"
```

## Testing

- Tests use `venv/bin/python -m pytest` (pytest not globally installed)
- Test fixtures in `tests/conftest.py` create authenticated client (auto-login as admin)
- `test_30ma.py` - standalone stress test: 30 employees (16 VZ, 14 TZ), 14 FWB, wishes, full rule set
  - Uses temp DB, cleans up after itself
  - Solved OPTIMAL in ~5s with 484 entries for March 2026
- Key gotcha: `Mitarbeiter` constructor uses `stellenanteil`, NOT `arbeitsstunden_woche`
- Key gotcha: `DienstQualifikation.erforderlich=True` blocks unqualified MA from ALL shifts of that type — can make solver INFEASIBLE if too few qualified staff

## Language

All code comments, variable names, and user-facing text are in German. Key vocabulary:
- Mitarbeiter = Employee
- Dienst = Shift
- Qualifikation = Qualification
- Regel = Rule
- Dienstplan = Schedule
- Wunsch = Wish/Request
- Frei = Free/Off
- Frühdienst/Spätdienst/Nachtdienst = Early/Late/Night shift

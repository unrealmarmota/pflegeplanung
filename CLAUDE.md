# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pflegeplanung is a German nursing staff shift scheduling application. It uses Google OR-Tools constraint programming to automatically generate optimal schedules while respecting labor laws, qualifications, and employee preferences.

**Stack:** Python 3.11+, Flask, SQLAlchemy, Google OR-Tools, SQLite, WeasyPrint (PDF), OpenPyXL (Excel)

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

# Run all tests
pytest

# Run tests with coverage
pytest --cov=app tests/

# Run single test file
pytest tests/test_planer.py -v

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
- All routes except auth require authentication via `@app.before_request`
- Default admin: `admin` / `admin123`

## Key Implementation Details

### Adding New Constraints

1. Add `RegelTyp` enum value in `app/models/regel.py`
2. Add constraint method `_constraint_xyz()` in `app/services/planer.py`
3. Wire up in `_apply_regeln()` method
4. For soft constraints, append penalties to `self.soft_penalties`

### Qualification System

- `DienstQualifikation.min_anzahl` specifies minimum qualified staff per shift
- Enforced via `_apply_qualifikation_min_anzahl()` (hard) or `_apply_qualifikation_min_anzahl_soft()` (soft)
- Soft version uses capped variables with +500 bonus for proper enforcement

### Employee Constraints

- `MitarbeiterDienstEinschraenkung` - restricts which shifts an employee can work (e.g., weekends only Frühdienst)
- `MitarbeiterDienstPraeferenz` - min/max shifts per month per type
- `MitarbeiterWunsch` - day-specific requests (FREI, NICHT_VERFUEGBAR, DIENST_WUNSCH)

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

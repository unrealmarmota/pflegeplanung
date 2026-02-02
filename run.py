#!/usr/bin/env python3
import os
from app import create_app, db
from app.models import (
    Mitarbeiter, Qualifikation, Dienst, Regel,
    Dienstplan, MitarbeiterWunsch
)

app = create_app(os.getenv('FLASK_CONFIG') or 'default')


@app.shell_context_processor
def make_shell_context():
    return {
        'db': db,
        'Mitarbeiter': Mitarbeiter,
        'Qualifikation': Qualifikation,
        'Dienst': Dienst,
        'Regel': Regel,
        'Dienstplan': Dienstplan,
        'MitarbeiterWunsch': MitarbeiterWunsch
    }


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)

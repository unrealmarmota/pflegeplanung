from app import db
import enum
import json


class RegelTyp(enum.Enum):
    MAX_TAGE_FOLGE = 'MAX_TAGE_FOLGE'
    MIN_RUHEZEIT = 'MIN_RUHEZEIT'
    MAX_WOCHENSTUNDEN = 'MAX_WOCHENSTUNDEN'
    MIN_PERSONAL_DIENST = 'MIN_PERSONAL_DIENST'
    WOCHENENDE_ROTATION = 'WOCHENENDE_ROTATION'
    KEIN_NACHT_VOR_FRUEH = 'KEIN_NACHT_VOR_FRUEH'
    QUALIFIKATION_PFLICHT = 'QUALIFIKATION_PFLICHT'
    URLAUB_SPERRE = 'URLAUB_SPERRE'
    # Neue flexible Regeln
    DIENST_BLOCK = 'DIENST_BLOCK'
    KEIN_WECHSEL_VON_NACH = 'KEIN_WECHSEL_VON_NACH'
    MAX_DIENST_PRO_WOCHE = 'MAX_DIENST_PRO_WOCHE'
    FREIE_TAGE_NACH_BLOCK = 'FREIE_TAGE_NACH_BLOCK'
    KEIN_WOCHENENDE = 'KEIN_WOCHENENDE'
    MAX_NACHT_BLOECKE = 'MAX_NACHT_BLOECKE'
    MAX_NAECHTE_MONAT = 'MAX_NAECHTE_MONAT'


REGEL_TYP_BESCHREIBUNGEN = {
    RegelTyp.MAX_TAGE_FOLGE: {
        'name': 'Maximale aufeinanderfolgende Arbeitstage',
        'beschreibung': 'Begrenzt die Anzahl der Tage, die ein Mitarbeiter hintereinander arbeiten darf.',
        'parameter': {'max': {'typ': 'integer', 'label': 'Maximale Tage', 'default': 5}}
    },
    RegelTyp.MIN_RUHEZEIT: {
        'name': 'Mindest-Ruhezeit',
        'beschreibung': 'Minimale Pause zwischen zwei Diensten in Stunden.',
        'parameter': {'stunden': {'typ': 'integer', 'label': 'Stunden', 'default': 11}}
    },
    RegelTyp.MAX_WOCHENSTUNDEN: {
        'name': 'Maximale Wochenstunden',
        'beschreibung': 'Maximale Arbeitsstunden pro Woche.',
        'parameter': {'stunden': {'typ': 'integer', 'label': 'Stunden', 'default': 48}}
    },
    RegelTyp.MIN_PERSONAL_DIENST: {
        'name': 'Mindestbesetzung pro Dienst',
        'beschreibung': 'Mindestanzahl an Personal für einen bestimmten Dienst.',
        'parameter': {
            'dienst_id': {'typ': 'dienst', 'label': 'Dienst'},
            'min': {'typ': 'integer', 'label': 'Mindestanzahl', 'default': 3}
        }
    },
    RegelTyp.WOCHENENDE_ROTATION: {
        'name': 'Wochenend-Rotation',
        'beschreibung': 'Maximale Anzahl an Wochenenden pro Monat.',
        'parameter': {'max': {'typ': 'integer', 'label': 'Max. Wochenenden', 'default': 2}}
    },
    RegelTyp.KEIN_NACHT_VOR_FRUEH: {
        'name': 'Kein Frühdienst nach Nachtdienst',
        'beschreibung': 'Verhindert, dass ein Frühdienst direkt nach einem Nachtdienst geplant wird.',
        'parameter': {}
    },
    RegelTyp.QUALIFIKATION_PFLICHT: {
        'name': 'Qualifikations-Pflicht',
        'beschreibung': 'Erfordert eine bestimmte Anzahl qualifizierter Mitarbeiter pro Dienst.',
        'parameter': {
            'dienst_id': {'typ': 'dienst', 'label': 'Dienst'},
            'qualifikation_id': {'typ': 'qualifikation', 'label': 'Qualifikation'},
            'min': {'typ': 'integer', 'label': 'Mindestanzahl', 'default': 1}
        }
    },
    RegelTyp.URLAUB_SPERRE: {
        'name': 'Urlaubs-Sperre',
        'beschreibung': 'Sperrt einen Zeitraum für Urlaub/Freizeit.',
        'parameter': {
            'von': {'typ': 'date', 'label': 'Von'},
            'bis': {'typ': 'date', 'label': 'Bis'}
        }
    },
    RegelTyp.DIENST_BLOCK: {
        'name': 'Dienst nur als Block',
        'beschreibung': 'Ein Dienst muss in einer Mindestanzahl aufeinanderfolgender Tage geplant werden (z.B. Nächte nur als 2-4er Block).',
        'parameter': {
            'dienst_id': {'typ': 'dienst', 'label': 'Dienst'},
            'min_folge': {'typ': 'integer', 'label': 'Min. Tage am Stück', 'default': 2},
            'max_folge': {'typ': 'integer', 'label': 'Max. Tage am Stück', 'default': 4}
        }
    },
    RegelTyp.KEIN_WECHSEL_VON_NACH: {
        'name': 'Kein direkter Dienstwechsel',
        'beschreibung': 'Verhindert den Wechsel von einem Dienst zu einem anderen am Folgetag.',
        'parameter': {
            'von_dienst_id': {'typ': 'dienst', 'label': 'Von Dienst'},
            'nach_dienst_id': {'typ': 'dienst', 'label': 'Nach Dienst'}
        }
    },
    RegelTyp.MAX_DIENST_PRO_WOCHE: {
        'name': 'Max. Dienst pro Woche',
        'beschreibung': 'Begrenzt die Anzahl eines bestimmten Dienstes pro Woche.',
        'parameter': {
            'dienst_id': {'typ': 'dienst', 'label': 'Dienst'},
            'max': {'typ': 'integer', 'label': 'Maximum pro Woche', 'default': 3}
        }
    },
    RegelTyp.FREIE_TAGE_NACH_BLOCK: {
        'name': 'Freie Tage nach Blockdienst',
        'beschreibung': 'Erfordert eine Mindestanzahl freier Tage nach einem Blockdienst.',
        'parameter': {
            'dienst_id': {'typ': 'dienst', 'label': 'Dienst'},
            'min_frei': {'typ': 'integer', 'label': 'Min. freie Tage danach', 'default': 2}
        }
    },
    RegelTyp.KEIN_WOCHENENDE: {
        'name': 'Kein Wochenende',
        'beschreibung': 'Verhindert, dass ein bestimmter Dienst am Wochenende geplant wird.',
        'parameter': {
            'dienst_id': {'typ': 'dienst', 'label': 'Dienst'}
        }
    },
    RegelTyp.MAX_NACHT_BLOECKE: {
        'name': 'Nacht-Blöcke pro Monat',
        'beschreibung': 'Begrenzt die Anzahl der Nachtdienst-Blöcke pro Mitarbeiter pro Monat. Mit min>1 werden die Nächte auf mehrere Blöcke verteilt.',
        'parameter': {
            'min': {'typ': 'integer', 'label': 'Min. Blöcke', 'default': 2},
            'max': {'typ': 'integer', 'label': 'Max. Blöcke', 'default': 3}
        }
    },
    RegelTyp.MAX_NAECHTE_MONAT: {
        'name': 'Max. Nächte pro Monat',
        'beschreibung': 'Begrenzt die absolute Anzahl an Nachtdiensten pro Mitarbeiter pro Monat.',
        'parameter': {
            'max': {'typ': 'integer', 'label': 'Max. Nächte', 'default': 8}
        }
    }
}


class Regel(db.Model):
    __tablename__ = 'regeln'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    typ = db.Column(db.Enum(RegelTyp), nullable=False)
    _parameter = db.Column('parameter', db.Text, default='{}')
    prioritaet = db.Column(db.Integer, default=1)  # 1=hart, 2=weich
    aktiv = db.Column(db.Boolean, default=True)

    @property
    def parameter(self):
        return json.loads(self._parameter) if self._parameter else {}

    @parameter.setter
    def parameter(self, value):
        self._parameter = json.dumps(value) if value else '{}'

    def __repr__(self):
        return f'<Regel {self.name} ({self.typ.value})>'

    def get_typ_info(self):
        return REGEL_TYP_BESCHREIBUNGEN.get(self.typ, {})

    PRIORITAET_TEXTE = {
        1: 'Hart',
        2: 'Weich',
        3: 'Optional'
    }

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'typ': self.typ.value,
            'typ_name': self.get_typ_info().get('name', self.typ.value),
            'parameter': self.parameter,
            'prioritaet': self.prioritaet,
            'prioritaet_text': self.PRIORITAET_TEXTE.get(self.prioritaet, 'Unbekannt'),
            'aktiv': self.aktiv
        }

from app import db
from datetime import time, datetime, timedelta


class DienstQualifikation(db.Model):
    __tablename__ = 'dienst_qualifikationen'

    dienst_id = db.Column(
        db.Integer,
        db.ForeignKey('dienste.id'),
        primary_key=True
    )
    qualifikation_id = db.Column(
        db.Integer,
        db.ForeignKey('qualifikationen.id'),
        primary_key=True
    )
    min_anzahl = db.Column(db.Integer, default=1)
    erforderlich = db.Column(db.Boolean, default=True)  # Nur MA mit dieser Quali dürfen den Dienst machen

    dienst = db.relationship('Dienst', back_populates='qualifikation_anforderungen')
    qualifikation = db.relationship('Qualifikation', back_populates='dienst_anforderungen')


class Dienst(db.Model):
    __tablename__ = 'dienste'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    kurzname = db.Column(db.String(5), nullable=False)
    start_zeit = db.Column(db.Time, nullable=False)
    ende_zeit = db.Column(db.Time, nullable=False)
    farbe = db.Column(db.String(7), default='#0d6efd')  # Hex-Farbcode
    min_besetzung = db.Column(db.Integer, default=1)  # Mindestbesetzung
    max_besetzung = db.Column(db.Integer, nullable=True)  # Maximalbesetzung (optional)
    ist_abwesenheit = db.Column(db.Boolean, default=False)  # Urlaub, Krank, etc. - nicht auto-planbar

    # Beziehungen
    qualifikation_anforderungen = db.relationship(
        'DienstQualifikation',
        back_populates='dienst',
        cascade='all, delete-orphan'
    )
    dienstplaene = db.relationship(
        'Dienstplan',
        back_populates='dienst',
        cascade='all, delete-orphan'
    )
    wuensche = db.relationship(
        'MitarbeiterWunsch',
        back_populates='dienst'
    )

    def __repr__(self):
        return f'<Dienst {self.name} ({self.kurzname})>'

    def get_dauer_stunden(self):
        """Berechnet die Dienstdauer in Stunden"""
        start = datetime.combine(datetime.today(), self.start_zeit)
        ende = datetime.combine(datetime.today(), self.ende_zeit)

        # Falls der Dienst über Mitternacht geht
        if ende < start:
            ende = ende + timedelta(days=1)

        delta = ende - start
        return delta.total_seconds() / 3600

    def get_erforderliche_qualifikationen(self):
        """Gibt alle erforderlichen Qualifikationen für diesen Dienst zurück"""
        return [dq.qualifikation for dq in self.qualifikation_anforderungen if dq.erforderlich]

    def kann_mitarbeiter_arbeiten(self, mitarbeiter):
        """Prüft ob ein Mitarbeiter die erforderlichen Qualifikationen hat"""
        erforderliche = self.get_erforderliche_qualifikationen()
        if not erforderliche:
            return True  # Keine Einschränkung

        # Mitarbeiter braucht mindestens eine der erforderlichen Qualifikationen
        ma_quali_ids = set()
        for mq in mitarbeiter.qualifikationen:
            if mq.ist_gueltig():
                ma_quali_ids.add(mq.qualifikation_id)
                # Inkludierte Qualifikationen auch berücksichtigen
                for inkl in mq.qualifikation.get_alle_inkludierten():
                    ma_quali_ids.add(inkl.id)

        for quali in erforderliche:
            if quali.id in ma_quali_ids:
                return True

        return False

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'kurzname': self.kurzname,
            'start_zeit': self.start_zeit.strftime('%H:%M') if self.start_zeit else None,
            'ende_zeit': self.ende_zeit.strftime('%H:%M') if self.ende_zeit else None,
            'farbe': self.farbe,
            'dauer_stunden': self.get_dauer_stunden(),
            'min_besetzung': self.min_besetzung,
            'max_besetzung': self.max_besetzung,
            'ist_abwesenheit': self.ist_abwesenheit,
            'qualifikation_anforderungen': [
                {
                    'qualifikation_id': dq.qualifikation_id,
                    'qualifikation_name': dq.qualifikation.name,
                    'min_anzahl': dq.min_anzahl
                }
                for dq in self.qualifikation_anforderungen
            ]
        }

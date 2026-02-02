from app import db


class Qualifikation(db.Model):
    __tablename__ = 'qualifikationen'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    beschreibung = db.Column(db.Text)
    farbe = db.Column(db.String(7), default='#6c757d')  # Hex-Farbcode

    # Hierarchie: Diese Qualifikation inkludiert eine andere
    # z.B. "Fachweiterbildung" inkludiert "Examinierte Pflegekraft"
    inkludiert_id = db.Column(db.Integer, db.ForeignKey('qualifikationen.id'), nullable=True)

    # Beziehungen
    inkludiert = db.relationship(
        'Qualifikation',
        remote_side=[id],
        backref='inkludiert_von',
        foreign_keys=[inkludiert_id]
    )
    mitarbeiter = db.relationship(
        'MitarbeiterQualifikation',
        back_populates='qualifikation',
        cascade='all, delete-orphan'
    )
    dienst_anforderungen = db.relationship(
        'DienstQualifikation',
        back_populates='qualifikation',
        cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f'<Qualifikation {self.name}>'

    def get_alle_inkludierten(self):
        """Gibt alle inkludierten Qualifikationen zurück (rekursiv)"""
        result = []
        if self.inkludiert:
            result.append(self.inkludiert)
            result.extend(self.inkludiert.get_alle_inkludierten())
        return result

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'beschreibung': self.beschreibung,
            'farbe': self.farbe,
            'inkludiert_id': self.inkludiert_id,
            'inkludiert_name': self.inkludiert.name if self.inkludiert else None
        }

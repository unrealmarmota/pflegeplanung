from app import db
import enum
from datetime import date


class DienstplanStatus(enum.Enum):
    GEPLANT = 'geplant'
    BESTAETIGT = 'bestaetigt'
    GETAUSCHT = 'getauscht'


class WunschTyp(enum.Enum):
    FREI = 'frei'
    DIENST_WUNSCH = 'dienst_wunsch'
    NICHT_VERFUEGBAR = 'nicht_verfuegbar'
    DIENST_AUSSCHLUSS = 'dienst_ausschluss'  # Bestimmter Dienst ausgeschlossen


class Dienstplan(db.Model):
    __tablename__ = 'dienstplaene'

    id = db.Column(db.Integer, primary_key=True)
    datum = db.Column(db.Date, nullable=False)
    mitarbeiter_id = db.Column(
        db.Integer,
        db.ForeignKey('mitarbeiter.id'),
        nullable=False
    )
    dienst_id = db.Column(
        db.Integer,
        db.ForeignKey('dienste.id'),
        nullable=False
    )
    status = db.Column(
        db.Enum(DienstplanStatus),
        default=DienstplanStatus.GEPLANT
    )
    notizen = db.Column(db.Text)

    # Beziehungen
    mitarbeiter = db.relationship('Mitarbeiter', back_populates='dienstplaene')
    dienst = db.relationship('Dienst', back_populates='dienstplaene')

    # Unique constraint: Ein Mitarbeiter kann nur einen Dienst pro Tag haben
    __table_args__ = (
        db.UniqueConstraint('datum', 'mitarbeiter_id', name='unique_mitarbeiter_tag'),
    )

    def __repr__(self):
        return f'<Dienstplan {self.datum} - {self.mitarbeiter.name} - {self.dienst.kurzname}>'

    def to_dict(self):
        return {
            'id': self.id,
            'datum': self.datum.isoformat(),
            'mitarbeiter_id': self.mitarbeiter_id,
            'mitarbeiter_name': self.mitarbeiter.name,
            'dienst_id': self.dienst_id,
            'dienst_kurzname': self.dienst.kurzname,
            'dienst_name': self.dienst.name,
            'dienst_farbe': self.dienst.farbe,
            'status': self.status.value,
            'notizen': self.notizen
        }


class MitarbeiterWunsch(db.Model):
    __tablename__ = 'mitarbeiter_wuensche'

    id = db.Column(db.Integer, primary_key=True)
    mitarbeiter_id = db.Column(
        db.Integer,
        db.ForeignKey('mitarbeiter.id'),
        nullable=False
    )
    datum = db.Column(db.Date, nullable=False)
    wunsch_typ = db.Column(db.Enum(WunschTyp), nullable=False)
    dienst_id = db.Column(
        db.Integer,
        db.ForeignKey('dienste.id'),
        nullable=True
    )
    prioritaet = db.Column(db.Integer, default=1)  # 1=hoch, 2=mittel, 3=niedrig

    # Beziehungen
    mitarbeiter = db.relationship('Mitarbeiter', back_populates='wuensche')
    dienst = db.relationship('Dienst', back_populates='wuensche')

    def __repr__(self):
        return f'<Wunsch {self.datum} - {self.mitarbeiter.name} - {self.wunsch_typ.value}>'

    def to_dict(self):
        return {
            'id': self.id,
            'mitarbeiter_id': self.mitarbeiter_id,
            'mitarbeiter_name': self.mitarbeiter.name,
            'datum': self.datum.isoformat(),
            'wunsch_typ': self.wunsch_typ.value,
            'dienst_id': self.dienst_id,
            'dienst_name': self.dienst.name if self.dienst else None,
            'prioritaet': self.prioritaet
        }

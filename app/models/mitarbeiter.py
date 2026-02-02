from app import db
from datetime import date
import enum


class TagTyp(enum.Enum):
    """Wann gilt die Einschränkung"""
    WOCHENENDE = 'WOCHENENDE'      # Samstag + Sonntag
    WOCHENTAG = 'WOCHENTAG'        # Montag - Freitag
    MONTAG = 'MONTAG'
    DIENSTAG = 'DIENSTAG'
    MITTWOCH = 'MITTWOCH'
    DONNERSTAG = 'DONNERSTAG'
    FREITAG = 'FREITAG'
    SAMSTAG = 'SAMSTAG'
    SONNTAG = 'SONNTAG'


TAG_TYP_NAMEN = {
    TagTyp.WOCHENENDE: 'Wochenende (Sa+So)',
    TagTyp.WOCHENTAG: 'Wochentag (Mo-Fr)',
    TagTyp.MONTAG: 'Montag',
    TagTyp.DIENSTAG: 'Dienstag',
    TagTyp.MITTWOCH: 'Mittwoch',
    TagTyp.DONNERSTAG: 'Donnerstag',
    TagTyp.FREITAG: 'Freitag',
    TagTyp.SAMSTAG: 'Samstag',
    TagTyp.SONNTAG: 'Sonntag',
}


class MitarbeiterDienstEinschraenkung(db.Model):
    """Einschränkung: An bestimmten Tagen nur bestimmte Dienste erlauben

    Beispiel: Johannes darf am Wochenende NUR Frühdienst machen
    -> mitarbeiter=Johannes, tag_typ=WOCHENENDE, nur_dienst=Frühdienst
    """
    __tablename__ = 'mitarbeiter_dienst_einschraenkungen'

    id = db.Column(db.Integer, primary_key=True)
    mitarbeiter_id = db.Column(
        db.Integer,
        db.ForeignKey('mitarbeiter.id'),
        nullable=False
    )
    tag_typ = db.Column(db.Enum(TagTyp), nullable=False)
    nur_dienst_id = db.Column(
        db.Integer,
        db.ForeignKey('dienste.id'),
        nullable=False
    )
    aktiv = db.Column(db.Boolean, default=True)
    notiz = db.Column(db.String(200))

    mitarbeiter = db.relationship('Mitarbeiter', back_populates='dienst_einschraenkungen')
    nur_dienst = db.relationship('Dienst')

    def matches_date(self, datum):
        """Prüft ob diese Einschränkung für ein Datum gilt"""
        weekday = datum.weekday()  # 0=Montag, 6=Sonntag

        if self.tag_typ == TagTyp.WOCHENENDE:
            return weekday >= 5
        elif self.tag_typ == TagTyp.WOCHENTAG:
            return weekday < 5
        elif self.tag_typ == TagTyp.MONTAG:
            return weekday == 0
        elif self.tag_typ == TagTyp.DIENSTAG:
            return weekday == 1
        elif self.tag_typ == TagTyp.MITTWOCH:
            return weekday == 2
        elif self.tag_typ == TagTyp.DONNERSTAG:
            return weekday == 3
        elif self.tag_typ == TagTyp.FREITAG:
            return weekday == 4
        elif self.tag_typ == TagTyp.SAMSTAG:
            return weekday == 5
        elif self.tag_typ == TagTyp.SONNTAG:
            return weekday == 6
        return False

    def to_dict(self):
        return {
            'id': self.id,
            'mitarbeiter_id': self.mitarbeiter_id,
            'mitarbeiter_name': self.mitarbeiter.name if self.mitarbeiter else None,
            'tag_typ': self.tag_typ.value,
            'tag_typ_name': TAG_TYP_NAMEN.get(self.tag_typ, self.tag_typ.value),
            'nur_dienst_id': self.nur_dienst_id,
            'nur_dienst_name': self.nur_dienst.name if self.nur_dienst else None,
            'aktiv': self.aktiv,
            'notiz': self.notiz
        }


class MitarbeiterDienstPraeferenz(db.Model):
    """Mindestanzahl bestimmter Dienste pro Mitarbeiter pro Monat (Soft-Regel)"""
    __tablename__ = 'mitarbeiter_dienst_praeferenzen'

    id = db.Column(db.Integer, primary_key=True)
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
    min_pro_monat = db.Column(db.Integer, default=0)  # Mindestanzahl pro Monat
    max_pro_monat = db.Column(db.Integer, nullable=True)  # Maximalanzahl pro Monat (optional)

    mitarbeiter = db.relationship('Mitarbeiter', back_populates='dienst_praeferenzen')
    dienst = db.relationship('Dienst', backref='mitarbeiter_praeferenzen')

    __table_args__ = (
        db.UniqueConstraint('mitarbeiter_id', 'dienst_id', name='unique_ma_dienst_praeferenz'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'mitarbeiter_id': self.mitarbeiter_id,
            'dienst_id': self.dienst_id,
            'dienst_name': self.dienst.name if self.dienst else None,
            'min_pro_monat': self.min_pro_monat,
            'max_pro_monat': self.max_pro_monat
        }


class MitarbeiterQualifikation(db.Model):
    __tablename__ = 'mitarbeiter_qualifikationen'

    mitarbeiter_id = db.Column(
        db.Integer,
        db.ForeignKey('mitarbeiter.id'),
        primary_key=True
    )
    qualifikation_id = db.Column(
        db.Integer,
        db.ForeignKey('qualifikationen.id'),
        primary_key=True
    )
    erworben_am = db.Column(db.Date, default=date.today)
    gueltig_bis = db.Column(db.Date, nullable=True)

    mitarbeiter = db.relationship('Mitarbeiter', back_populates='qualifikationen')
    qualifikation = db.relationship('Qualifikation', back_populates='mitarbeiter')

    def ist_gueltig(self):
        if self.gueltig_bis is None:
            return True
        return self.gueltig_bis >= date.today()


class Mitarbeiter(db.Model):
    __tablename__ = 'mitarbeiter'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    personalnummer = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120))
    telefon = db.Column(db.String(30))
    eintrittsdatum = db.Column(db.Date, default=date.today)
    stellenanteil = db.Column(db.Float, default=100.0)  # Prozent (100 = Vollzeit)
    aktiv = db.Column(db.Boolean, default=True)

    @property
    def arbeitsstunden_woche(self):
        """Berechnet Wochenstunden aus Basis-Arbeitszeit und Stellenanteil"""
        from app.models.einstellungen import Einstellungen
        basis = Einstellungen.get_float('basis_wochenstunden', 38.5)
        return round(basis * self.stellenanteil / 100, 2)

    # Beziehungen
    qualifikationen = db.relationship(
        'MitarbeiterQualifikation',
        back_populates='mitarbeiter',
        cascade='all, delete-orphan'
    )
    dienstplaene = db.relationship(
        'Dienstplan',
        back_populates='mitarbeiter',
        cascade='all, delete-orphan'
    )
    wuensche = db.relationship(
        'MitarbeiterWunsch',
        back_populates='mitarbeiter',
        cascade='all, delete-orphan'
    )
    dienst_praeferenzen = db.relationship(
        'MitarbeiterDienstPraeferenz',
        back_populates='mitarbeiter',
        cascade='all, delete-orphan'
    )
    dienst_einschraenkungen = db.relationship(
        'MitarbeiterDienstEinschraenkung',
        back_populates='mitarbeiter',
        cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f'<Mitarbeiter {self.name} ({self.personalnummer})>'

    def hat_qualifikation(self, qualifikation_id):
        """
        Prüft ob Mitarbeiter eine Qualifikation hat.
        Berücksichtigt auch Qualifikations-Hierarchie (z.B. FWB inkludiert Exam)
        """
        for mq in self.qualifikationen:
            if not mq.ist_gueltig():
                continue

            # Direkte Qualifikation
            if mq.qualifikation_id == qualifikation_id:
                return True

            # Prüfe ob eine der Qualifikationen die gesuchte inkludiert
            for inkl in mq.qualifikation.get_alle_inkludierten():
                if inkl.id == qualifikation_id:
                    return True

        return False

    def get_gueltige_qualifikationen(self):
        return [mq.qualifikation for mq in self.qualifikationen if mq.ist_gueltig()]

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'personalnummer': self.personalnummer,
            'email': self.email,
            'telefon': self.telefon,
            'eintrittsdatum': self.eintrittsdatum.isoformat() if self.eintrittsdatum else None,
            'stellenanteil': self.stellenanteil,
            'arbeitsstunden_woche': self.arbeitsstunden_woche,
            'aktiv': self.aktiv,
            'qualifikationen': [
                {
                    'id': mq.qualifikation.id,
                    'name': mq.qualifikation.name,
                    'farbe': mq.qualifikation.farbe,
                    'gueltig': mq.ist_gueltig()
                }
                for mq in self.qualifikationen
            ]
        }

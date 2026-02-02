from app import db
from datetime import date


class Feiertag(db.Model):
    """Feiertage für die Dienstplanung"""
    __tablename__ = 'feiertage'

    id = db.Column(db.Integer, primary_key=True)
    datum = db.Column(db.Date, nullable=False, unique=True)
    name = db.Column(db.String(100), nullable=False)
    bundesland = db.Column(db.String(50), default='alle')  # 'alle' oder spezifisches Bundesland

    def __repr__(self):
        return f'<Feiertag {self.datum} - {self.name}>'

    @classmethod
    def ist_feiertag(cls, datum):
        """Prüft ob ein Datum ein Feiertag ist"""
        return cls.query.filter_by(datum=datum).first() is not None

    @classmethod
    def get_feiertage_im_monat(cls, jahr, monat):
        """Gibt alle Feiertage eines Monats zurück"""
        from calendar import monthrange
        start = date(jahr, monat, 1)
        _, last_day = monthrange(jahr, monat)
        ende = date(jahr, monat, last_day)
        return cls.query.filter(cls.datum >= start, cls.datum <= ende).all()

    @classmethod
    def init_deutsche_feiertage(cls, jahr):
        """Initialisiert deutsche Feiertage für ein Jahr"""
        from datetime import timedelta

        # Berechne Ostersonntag (Gaußsche Osterformel)
        a = jahr % 19
        b = jahr // 100
        c = jahr % 100
        d = b // 4
        e = b % 4
        f = (b + 8) // 25
        g = (b - f + 1) // 3
        h = (19 * a + b - d - g + 15) % 30
        i = c // 4
        k = c % 4
        l = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * l) // 451
        monat = (h + l - 7 * m + 114) // 31
        tag = ((h + l - 7 * m + 114) % 31) + 1
        ostersonntag = date(jahr, monat, tag)

        feiertage = [
            (date(jahr, 1, 1), "Neujahr", "alle"),
            (date(jahr, 5, 1), "Tag der Arbeit", "alle"),
            (date(jahr, 10, 3), "Tag der Deutschen Einheit", "alle"),
            (date(jahr, 12, 25), "1. Weihnachtstag", "alle"),
            (date(jahr, 12, 26), "2. Weihnachtstag", "alle"),
            # Bewegliche Feiertage (abhängig von Ostern)
            (ostersonntag - timedelta(days=2), "Karfreitag", "alle"),
            (ostersonntag + timedelta(days=1), "Ostermontag", "alle"),
            (ostersonntag + timedelta(days=39), "Christi Himmelfahrt", "alle"),
            (ostersonntag + timedelta(days=50), "Pfingstmontag", "alle"),
        ]

        added = 0
        for datum, name, bundesland in feiertage:
            if not cls.query.filter_by(datum=datum).first():
                db.session.add(cls(datum=datum, name=name, bundesland=bundesland))
                added += 1

        db.session.commit()
        return added


class FeiertagsAusgleich(db.Model):
    """Freizeitausgleich für Feiertagsarbeit"""
    __tablename__ = 'feiertags_ausgleich'

    id = db.Column(db.Integer, primary_key=True)
    mitarbeiter_id = db.Column(
        db.Integer,
        db.ForeignKey('mitarbeiter.id'),
        nullable=False
    )
    feiertag_id = db.Column(
        db.Integer,
        db.ForeignKey('feiertage.id'),
        nullable=False
    )
    gearbeitet_am = db.Column(db.Date, nullable=False)  # Datum des Feiertagsdienstes
    ausgleich_am = db.Column(db.Date, nullable=True)  # Datum des Ausgleichstages (wenn genommen)
    ausgleich_stunden = db.Column(db.Float, default=0)  # Stunden Ausgleich (z.B. 8h)
    status = db.Column(db.String(20), default='offen')  # offen, geplant, genommen

    # Beziehungen
    mitarbeiter = db.relationship('Mitarbeiter', backref='feiertags_ausgleiche')
    feiertag = db.relationship('Feiertag', backref='ausgleiche')

    def __repr__(self):
        return f'<Ausgleich {self.mitarbeiter.name} - {self.feiertag.name}>'

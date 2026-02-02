from app import db


class Einstellungen(db.Model):
    """Globale Einstellungen der Anwendung"""
    __tablename__ = 'einstellungen'

    id = db.Column(db.Integer, primary_key=True)
    schluessel = db.Column(db.String(50), unique=True, nullable=False)
    wert = db.Column(db.String(200), nullable=False)
    beschreibung = db.Column(db.String(200))

    # Standardwerte
    DEFAULTS = {
        'basis_wochenstunden': ('38.5', 'Basis-Wochenarbeitszeit in Stunden'),
    }

    @classmethod
    def get(cls, schluessel, default=None):
        """Holt einen Einstellungswert"""
        setting = cls.query.filter_by(schluessel=schluessel).first()
        if setting:
            return setting.wert
        # Fallback auf Default
        if schluessel in cls.DEFAULTS:
            return cls.DEFAULTS[schluessel][0]
        return default

    @classmethod
    def get_float(cls, schluessel, default=0.0):
        """Holt einen Einstellungswert als Float"""
        val = cls.get(schluessel)
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    @classmethod
    def set(cls, schluessel, wert, beschreibung=None):
        """Setzt einen Einstellungswert"""
        setting = cls.query.filter_by(schluessel=schluessel).first()
        if setting:
            setting.wert = str(wert)
            if beschreibung:
                setting.beschreibung = beschreibung
        else:
            setting = cls(
                schluessel=schluessel,
                wert=str(wert),
                beschreibung=beschreibung or cls.DEFAULTS.get(schluessel, ('', ''))[1]
            )
            db.session.add(setting)
        db.session.commit()
        return setting

    @classmethod
    def init_defaults(cls):
        """Initialisiert Standardwerte falls nicht vorhanden"""
        for schluessel, (wert, beschreibung) in cls.DEFAULTS.items():
            if not cls.query.filter_by(schluessel=schluessel).first():
                setting = cls(schluessel=schluessel, wert=wert, beschreibung=beschreibung)
                db.session.add(setting)
        db.session.commit()

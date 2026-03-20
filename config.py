import os

basedir = os.path.abspath(os.path.dirname(__file__))


def get_database_uri():
    """Ermittelt den Datenbank-Pfad (Desktop-App oder Entwicklung)"""
    # Zuerst: Expliziter Pfad von Desktop-App
    db_path = os.environ.get('PFLEGEPLANUNG_DB_PATH')
    if db_path:
        return 'sqlite:///' + db_path

    # Dann: DATABASE_URL Umgebungsvariable
    db_url = os.environ.get('DATABASE_URL')
    if db_url:
        return db_url

    # Fallback: Lokale Datei im Projektverzeichnis
    return 'sqlite:///' + os.path.join(basedir, 'pflegeplanung.db')


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'pflegeplanung-geheim-key-2024'
    SQLALCHEMY_DATABASE_URI = get_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CLAUDE_API_KEY = os.environ.get('CLAUDE_API_KEY')


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


class ProductionConfig(Config):
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

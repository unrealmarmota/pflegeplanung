from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user
from config import config

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()


def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)
    migrate.init_app(app, db)

    # Flask-Login Setup
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Bitte melde dich an, um diese Seite zu sehen.'
    login_manager.login_message_category = 'info'

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return User.query.get(int(user_id))

    # Auth Blueprint (vor anderen, da Login-Seite öffentlich)
    from app.routes.auth import auth
    app.register_blueprint(auth)

    # Geschützte Blueprints
    from app.routes import mitarbeiter, qualifikationen, dienste, regeln, planung, einstellungen, feiertage
    app.register_blueprint(mitarbeiter.bp)
    app.register_blueprint(qualifikationen.bp)
    app.register_blueprint(dienste.bp)
    app.register_blueprint(regeln.bp)
    app.register_blueprint(planung.bp)
    app.register_blueprint(einstellungen.bp)
    app.register_blueprint(feiertage.bp)

    # Login für alle Routen erzwingen (außer auth und static)
    @app.before_request
    def require_login():
        from flask import request
        # Öffentliche Endpunkte
        public_endpoints = ['auth.login', 'auth.logout', 'static']
        if request.endpoint and any(request.endpoint.startswith(p) for p in public_endpoints):
            return None
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login', next=request.url))

    # Einstellungen und Admin-User initialisieren
    with app.app_context():
        from app.models import Einstellungen, User
        db.create_all()  # Erstellt User-Tabelle falls nicht vorhanden
        Einstellungen.init_defaults()

        # Standard-Admin erstellen falls kein User existiert
        if User.query.count() == 0:
            User.create_admin('admin', 'admin123')
            print('>>> Standard-Admin erstellt: admin / admin123')
            print('>>> BITTE PASSWORT NACH ERSTEM LOGIN ÄNDERN!')

    @app.route('/')
    def index():
        return redirect(url_for('planung.dashboard'))

    # Current user für Templates verfügbar machen
    @app.context_processor
    def inject_user():
        return dict(current_user=current_user)

    return app

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User
from app import db
from datetime import datetime

auth = Blueprint('auth', __name__)


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user, remember=True)
            user.last_login = datetime.utcnow()
            db.session.commit()

            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('main.index'))

        flash('Ungültiger Benutzername oder Passwort', 'danger')

    return render_template('auth/login.html')


@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Erfolgreich abgemeldet', 'success')
    return redirect(url_for('auth.login'))


@auth.route('/passwort-aendern', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not current_user.check_password(current_password):
            flash('Aktuelles Passwort ist falsch', 'danger')
        elif new_password != confirm_password:
            flash('Neue Passwörter stimmen nicht überein', 'danger')
        elif len(new_password) < 6:
            flash('Neues Passwort muss mindestens 6 Zeichen haben', 'danger')
        else:
            current_user.set_password(new_password)
            db.session.commit()
            flash('Passwort erfolgreich geändert', 'success')
            return redirect(url_for('main.index'))

    return render_template('auth/change_password.html')

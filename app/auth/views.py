from flask import render_template, redirect, url_for, flash, request, session
from flask_login import login_required, current_user, login_user, logout_user
from . import auth
from .email import send_email
from .forms import *
from .security import Security, User
from ..db.database_queries import query_select, query_change
from datetime import datetime
from .. import login_manager


# Adapted from Flask Web Development: Developing Web Applications with Python 2nd Edition,  978-1491991732
@auth.route('/login', methods=["GET", "POST"])
def login():
    """Login user if they are registered"""
    login_form = LoginForm()

    if login_form.validate_on_submit():
        email = login_form.email.data.lower()
        password = login_form.password.data

        # Retrieve user object to verify if email and password are correct
        registered_user = query_select(
            query="SELECT * FROM user WHERE email = (?)",
            key=email
        )

        if registered_user:
            user = load_user(registered_user[0][0])
            if user.email == email and Security().verify_password(user.password_hash, password):
                login_user(user)
                session['user_id'] = user.get_id()
                print(query_select(
                    query="SELECT patient_id FROM patient WHERE user_id = (?)",
                    key=session['user_id']
                ))
                session['patient_id'] = query_select(
                    query="SELECT patient_id FROM patient WHERE user_id = (?)",
                    key=session['user_id']
                )[0][0]

                next = request.args.get('next')

                if next is None or not next.startswith('/'):
                    next = url_for('profile.profile_main')
                return redirect(next)
            else:
                flash('Invalid password')
        else:
            flash('Invalid email')

    return render_template('login.html', form=login_form)


@auth.route('/register', methods=["GET", "POST"])
def register():
    registration_form = RegistrationForm()

    if registration_form.validate_on_submit():
        email = registration_form.email.data.lower()

        # Check for duplicate email
        duplicate_email = query_select(
            query="SELECT * FROM user WHERE email = (?)",
            key=email
        )

        if duplicate_email:
            flash("Email already registered")
        else:
            # Generate password hash
            password_hash = Security().generate_password_hash(registration_form.password.data)

            # Insert new user into the user table
            query_change(
                query="INSERT INTO user (email, password) VALUES (?, ?)",
                key=[email, password_hash]
            )

            # Select user_id of the new user
            user_id = query_select(
                query="SELECT user_id FROM user WHERE email = (?)",
                key=email
            )[0][0]

            # Process date of birth and allergies
            dob = datetime.strptime(request.form['dob'], '%Y-%m-%d').date()
            dob = datetime.strftime(dob, "%m-%d-%Y")

            # Insert new patient into the patient_table
            query_change(
                query="INSERT INTO patient (fname, lname, mname, dob, weight, user_id) VALUES (?, ?, ?, ?, ?, ?)",
                key=[request.form['fname'],
                     request.form['lname'],
                     request.form['minitial'],
                     dob,
                     request.form['weight'],
                     user_id]
            )

            # Select patient_id of the new user
            patient_id = query_select(
                query="SELECT patient_id FROM patient WHERE user_id = (?)",
                key=user_id)[0][0]

            # Add allergy to patient_allergy table
            allergies = request.form['allergies']
            if allergies != "":
                allergies = allergies.split(",")
                for allergy in allergies:
                    query_change(
                        query="INSERT OR IGNORE INTO  patient_allergy (patient_id, allergy) VALUES (?, ?)",
                        key=[patient_id, allergy]
                    )

            # Add user and patient ids to the session
            session['user_id'] = user_id
            session['patient_id'] = patient_id

            # Generate token, used to verify email address
            token = Security().generate_configuration_token(user_id)
            send_email(email,
                       "Confirm Your Account",
                       "email/confirm_registration.html",
                       token=token)
            flash("A confirmation email has been sent")
        return redirect(url_for("auth.register"))

    return render_template("register.html", form=registration_form)


@auth.route('/confirm/<token>')
@login_required
def confirm_registration(token):
    """Confirm token in confirmation email"""

    if Security().confirm(current_user.id, token):
        query_change(
            query="UPDATE user SET confirmed = (?) WHERE user_id = (?)",
            key=[1, current_user.id]
        )
        flash('You have confirmed your account.')
        return redirect(url_for('profile.profile_main'))
    else:
        flash('The confirmation link is invalid or has expired.')
        return redirect(url_for('main.index'))

    # return redirect(url_for('profile.profile_main'))


@auth.route('/logout')
@login_required
def logout():
    """Log user out of the session"""
    logout_user()
    flash('You have been logged out')
    return redirect(url_for('main.index'))


@auth.route('/forgot_password', methods=["GET", "POST"])
def forgot_password():
    """Allow users to receive an email to verify password reset request"""
    forgot_password_form = ForgotPasswordForm()

    if forgot_password_form.validate_on_submit():
        email = forgot_password_form.email.data.lower()

        # Retrieve user object to determine if user is registered
        registered_user = query_select(
            query="SELECT * FROM user WHERE email = (?)",
            key=email
        )

        if not registered_user:
            flash('Email is not registered')
        else:
            # Generate token to to reset password
            token = Security().generate_configuration_token(registered_user[0][0])
            send_email(registered_user[0][1],
                       "Reset Password",
                       "email/forgot_password.html",
                       email=email,
                       token=token)
            flash("An email was sent to reset your password.")
            return redirect(url_for('auth.forgot_password'))

    return render_template('forgot_password.html', form=forgot_password_form)


@auth.route('/confirm_reset_password/<email>/<token>', methods=["GET", "POST"])
def confirm_reset_password(email, token):
    """Confirm the email token to reset password"""
    registered_user = query_select(
        query="SELECT * FROM user WHERE email = (?)",
        key=email
    )

    if Security().confirm(registered_user[0][0], token):
        return redirect(url_for('auth.reset_password', email=email))
    else:
        flash('The link is invalid or has expired.')
    return redirect(url_for('auth.login'))


@auth.route('/reset_password/<email>', methods=["GET", "POST"])
def reset_password(email):
    """Allow user to type a new password"""
    reset_password_form = ResetPasswordForm()

    if reset_password_form.validate_on_submit():
        registered_user = query_select(
            query="SELECT * FROM user WHERE email = (?)",
            key=email
        )
        password_hash = Security().generate_password_hash(reset_password_form.password.data)

        query_change(
            query="UPDATE user SET password = (?) WHERE user_id = (?)",
            key=[password_hash, registered_user[0][0]]
        )
        flash("Password successfully changed. Please login with the new password.")
        return redirect(url_for('auth.login'))

    return render_template('reset_password.html', form=reset_password_form)


@login_manager.user_loader
def load_user(user_id):
    """Reload the user object from the user ID stored in the session"""

    result = query_select(
        query="SELECT * FROM user WHERE user_id = (?)",
        key=user_id
    )

    if result is None:
        return False
    else:
        return User(int(result[0][0]), result[0][1], result[0][2], int(result[0][3]))

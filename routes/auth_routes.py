"""Authentication routes for login/logout"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, current_user
from models.user import User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Login page"""
    # Redirect if already logged in
    if current_user.is_authenticated:
        return redirect(url_for('status.list_recordings'))
    
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        remember = request.form.get("remember", False)
        
        # Validation
        if not email or not password:
            flash("Please enter both email and password.", "danger")
            return render_template("login.html")
        
        # Get user
        user = User.get_by_email(email)
        
        # Check credentials
        if user and user.check_password(password):
            login_user(user, remember=bool(remember))
            
            # Redirect to next page or status
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('status.list_recordings'))
        else:
            flash("Invalid email or password.", "danger")
    
    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    """Logout current user"""
    logout_user()
    return redirect(url_for('auth.login'))

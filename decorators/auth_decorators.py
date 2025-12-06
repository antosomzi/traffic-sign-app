"""Authentication decorators for route protection"""

from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user


def login_required(f):
    """Decorator to require login for a route"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator to require admin privileges for a route"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('auth.login'))
        
        if not current_user.is_admin:
            flash("You need admin privileges to access this page.", "danger")
            return redirect(url_for('status.list_recordings'))
        
        return f(*args, **kwargs)
    return decorated_function

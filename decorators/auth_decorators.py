"""Authentication decorators for route protection"""

from functools import wraps
from flask import redirect, url_for, flash, request, jsonify
from flask_login import current_user, login_user
from models.auth_token import AuthToken
from models.api_key import APIKey
from models.user import User


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


def org_owner_required(f):
    """Decorator to require organization owner privileges for a route"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('auth.login'))
        
        if not current_user.is_org_owner and not current_user.is_admin:
            flash("You need organization owner privileges to access this page.", "danger")
            return redirect(url_for('status.list_recordings'))
        
        return f(*args, **kwargs)
    return decorated_function


def token_required(f):
    """Decorator to require valid API token for mobile routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')

        if not auth_header:
            return jsonify({"error": "Authorization header missing"}), 401

        # Extract token (format: "Bearer <token>")
        try:
            token = auth_header.split(' ')[1] if ' ' in auth_header else auth_header
        except IndexError:
            return jsonify({"error": "Invalid authorization header format"}), 401

        # Verify token and get user
        user_id = AuthToken.get_by_token(token)
        if not user_id:
            return jsonify({"error": "Invalid or expired token"}), 401

        user = User.get_by_id(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 401

        # Pass user to the route function
        return f(user, *args, **kwargs)

    return decorated_function


def api_key_required(f):
    """Decorator to require valid API key for B2B API routes

    Expects API key in X-API-Key header.
    Returns 401 if API key is missing or invalid.

    Usage:
        @download_bp.route("/download/csv-only-range", methods=["GET"])
        @api_key_required
        def download_csv_only_range():
            # current_user is available after authentication
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get API key from X-API-Key header
        api_key = request.headers.get('X-API-Key')

        if not api_key:
            return jsonify({"error": "X-API-Key header missing"}), 401

        # Verify API key and get user
        user_id = APIKey.get_by_key(api_key)
        if not user_id:
            return jsonify({"error": "Invalid or revoked API key"}), 401

        user = User.get_by_id(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 401

        # Log in user for this request so current_user is available
        login_user(user)

        return f(*args, **kwargs)

    return decorated_function


def auth_required(f):
    """Decorator that accepts EITHER Flask-Login session OR API token
    
    For web requests: Uses Flask-Login session (current_user)
    For API requests: Uses Authorization header token
    
    This allows the same route to work for both web and mobile
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if there's an Authorization header (API request)
        auth_header = request.headers.get('Authorization')
        
        if auth_header:
            # Mobile API request with token
            try:
                token = auth_header.split(' ')[1] if ' ' in auth_header else auth_header
                user_id = AuthToken.get_by_token(token)
                
                if not user_id:
                    return jsonify({"error": "Invalid or expired token"}), 401
                
                user = User.get_by_id(user_id)
                if not user:
                    return jsonify({"error": "User not found"}), 401
                
                # Temporarily set current_user for this request
                from flask_login import login_user
                login_user(user)
                
            except Exception as e:
                return jsonify({"error": "Invalid authorization header"}), 401
        
        # Check Flask-Login session (web request or already logged in from token)
        if not current_user.is_authenticated:
            # Web request without login
            if request.is_json or auth_header:
                return jsonify({"error": "Authentication required"}), 401
            else:
                flash("Please log in to access this page.", "warning")
                return redirect(url_for('auth.login'))
        
        return f(*args, **kwargs)
    
    return decorated_function

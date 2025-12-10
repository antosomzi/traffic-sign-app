"""
Traffic Sign ML Pipeline - Flask Application

Refactored modular architecture with:
- Application factory pattern
- Blueprint-based routing
- Service layer separation
- Centralized configuration
- Authentication with Flask-Login
"""

import os
from flask import Flask, redirect, url_for
from flask_login import LoginManager
from config import Config
from routes import upload_bp, status_bp, download_bp, delete_bp, rerun_bp
from routes.test_routes import test_bp
from routes.auth_routes import auth_bp
from models.user import User


def create_app(config_class=Config):
    """
    Application factory for creating Flask app instance
    
    Args:
        config_class: Configuration class to use (defaults to Config)
    
    Returns:
        Configured Flask application instance
    """
    app = Flask(__name__)
    
    # Flask configuration
    app.config["MAX_CONTENT_LENGTH"] = config_class.MAX_CONTENT_LENGTH
    app.config["SECRET_KEY"] = config_class.SECRET_KEY
    
    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "warning"
    
    @login_manager.user_loader
    def load_user(user_id):
        """Load user by ID for Flask-Login"""
        return User.get_by_id(int(user_id))
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(status_bp)
    app.register_blueprint(download_bp)
    app.register_blueprint(delete_bp)
    app.register_blueprint(rerun_bp)
    
    # Import and register admin blueprint
    from routes.admin_routes import admin_bp
    app.register_blueprint(admin_bp)
    
    # Import and register organization owner blueprint
    from routes.org_owner_routes import org_owner_bp
    app.register_blueprint(org_owner_bp)
    
    # Import and register mobile auth blueprint
    from routes.mobile_auth_routes import api_bp
    app.register_blueprint(api_bp)
    
    # Register test routes (only active in local mode)
    if os.getenv("USE_GPU_INSTANCE", "false").lower() != "true":
        app.register_blueprint(test_bp)
    
    # Root route redirect to status
    @app.route("/")
    def index():
        return redirect(url_for('status.list_recordings'))
    
    # Add security headers
    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        return response
    
    return app


# Create application instance
app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)

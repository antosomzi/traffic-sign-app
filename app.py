"""
Traffic Sign ML Pipeline - Flask Application

Refactored modular architecture with:
- Application factory pattern
- Blueprint-based routing
- Service layer separation
- Centralized configuration
"""

from flask import Flask
from config import Config
from routes import upload_bp, status_bp, download_bp


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
    # MAX_CONTENT_LENGTH is used by Flask to automatically reject large uploads
    app.config["MAX_CONTENT_LENGTH"] = config_class.MAX_CONTENT_LENGTH
    
    # Register blueprints
    app.register_blueprint(upload_bp)
    app.register_blueprint(status_bp)
    app.register_blueprint(download_bp)
    
    return app


# Create application instance
app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)

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
    
    # Load configuration
    app.config["UPLOAD_FOLDER"] = config_class.UPLOAD_FOLDER
    app.config["EXTRACT_FOLDER"] = config_class.EXTRACT_FOLDER
    app.config["TEMP_EXTRACT_FOLDER"] = config_class.TEMP_EXTRACT_FOLDER
    app.config["MAX_CONTENT_LENGTH"] = config_class.MAX_CONTENT_LENGTH
    
    # Register blueprints
    app.register_blueprint(upload_bp)
    app.register_blueprint(status_bp)
    app.register_blueprint(download_bp)
    
    return app


# Create application instance
app = create_app()


# Backwards compatibility wrappers for tasks.py
# These delegate to the service layer
from services.redis_service import RedisProgressService


def get_extraction_progress(job_id):
    """Backwards compatibility wrapper for RedisProgressService"""
    return RedisProgressService.get_extraction_progress(job_id)

def set_extraction_progress(job_id, progress_dict):
    """Backwards compatibility wrapper for RedisProgressService"""
    return RedisProgressService.set_extraction_progress(job_id, progress_dict)

def update_extraction_progress(job_id, **kwargs):
    """Backwards compatibility wrapper for RedisProgressService"""
    return RedisProgressService.update_extraction_progress(job_id, **kwargs)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)

"""Routes package"""

from routes.upload_routes import upload_bp
from routes.status_routes import status_bp
from routes.download_routes import download_bp

__all__ = ["upload_bp", "status_bp", "download_bp"]

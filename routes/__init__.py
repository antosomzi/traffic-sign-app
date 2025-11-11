"""Routes package"""

from routes.upload_routes import upload_bp
from routes.status_routes import status_bp
from routes.download_routes import download_bp
from routes.delete_routes import delete_bp
from routes.rerun_routes import rerun_bp

__all__ = ["upload_bp", "status_bp", "download_bp", "delete_bp", "rerun_bp"]

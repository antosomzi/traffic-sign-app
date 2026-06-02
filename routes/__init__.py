"""Routes package"""

from routes.auth_routes import auth_bp
from routes.sign_app import (
    upload_bp, 
    status_bp, 
    download_bp, 
    delete_bp, 
    rerun_bp,
    admin_bp,
    org_owner_bp,
    map_bp,
    api_bp,
    test_bp
)

__all__ = [
    "auth_bp",
    "upload_bp", 
    "status_bp", 
    "download_bp", 
    "delete_bp", 
    "rerun_bp",
    "admin_bp",
    "org_owner_bp",
    "map_bp",
    "api_bp",
    "test_bp"
]

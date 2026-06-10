"""Models subpackage for sign_app"""
from models.sign_app.database import Base, engine, get_session

# Import curve_analytic models to ensure they are registered for relationships
import models.curve_analytic

from models.sign_app.user import User
from models.sign_app.organization import Organization
from models.sign_app.recording import Recording
from models.sign_app.sign import Sign
from models.sign_app.api_key import APIKey
from models.sign_app.auth_token import AuthToken
from models.sign_app.model_history import ModelHistory

# Import curve_analytic models to ensure they are registered for relationships
import models.curve_analytic

__all__ = [
    "Base",
    "engine",
    "get_session",
    "User",
    "Organization",
    "Recording",
    "Sign",
    "APIKey",
    "AuthToken",
    "ModelHistory"
]

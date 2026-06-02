"""API Key model for B2B API authentication"""

import secrets
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, func, Index

from models.sign_app.database import Base, get_session


class APIKey(Base):
    """Model for API keys used in B2B authentication"""

    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String)
    key_hash = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    expires_at = Column(DateTime)
    revoked = Column(Boolean, default=False)

    __table_args__ = (
        Index("idx_api_keys_user_id", "user_id"),
    )

    @staticmethod
    def create(user_id, name=None, expires_days=None):
        """Create a new API key for a user

        Args:
            user_id: User ID to create API key for
            name: Optional name/description for the API key
            expires_days: Number of days until API key expires (None for never expires)

        Returns:
            tuple: (api_key_id, plain_key) - The plain key is only returned once
        """
        # Generate a long random API key (like Stripe: sk_live_xxx)
        prefix = "sk_live_"
        plain_key = prefix + secrets.token_urlsafe(32)
        
        # Hash the key before storing (like passwords)
        key_hash = generate_password_hash(plain_key)
        
        # Calculate expiration date if provided
        expires_at = None
        if expires_days:
            from datetime import timedelta
            expires_at = datetime.now() + timedelta(days=expires_days)

        with get_session() as session:
            api_key = APIKey(user_id=user_id, name=name, key_hash=key_hash, expires_at=expires_at)
            session.add(api_key)
            session.flush()
            session.refresh(api_key)
            return api_key.id, plain_key

    @staticmethod
    def get_by_key(plain_key):
        """Get user_id by API key if valid

        Args:
            plain_key: Full API key string (e.g., sk_live_xxx)

        Returns:
            user_id if API key is valid, None otherwise
        """
        with get_session() as session:
            keys = session.query(APIKey).filter(APIKey.revoked.is_(False)).all()

            if not keys:
                return None

            for key in keys:
                expires_at = key.expires_at
                if isinstance(expires_at, str):
                    expires_at = datetime.fromisoformat(expires_at)

                if expires_at and datetime.now() > expires_at:
                    continue

                if check_password_hash(key.key_hash, plain_key):
                    return key.user_id

            return None

    @staticmethod
    def get_all_for_user(user_id):
        """Get all API keys for a user (without the actual key values)

        Args:
            user_id: User ID to get keys for

        Returns:
            list: List of API key metadata (id, name, created_at, expires_at, revoked)
        """
        with get_session() as session:
            rows = (
                session.query(APIKey)
                .filter(APIKey.user_id == user_id)
                .order_by(APIKey.created_at.desc())
                .all()
            )

            return [
                {
                    "id": row.id,
                    "name": row.name,
                    "created_at": row.created_at,
                    "expires_at": row.expires_at,
                    "revoked": bool(row.revoked)
                }
                for row in rows
            ]

    @staticmethod
    def delete_by_id(api_key_id):
        """Delete an API key by ID

        Args:
            api_key_id: API key ID to delete
        """
        with get_session() as session:
            session.query(APIKey).filter(APIKey.id == api_key_id).delete(synchronize_session=False)

    @staticmethod
    def revoke(api_key_id):
        """Revoke an API key (soft delete)

        Args:
            api_key_id: API key ID to revoke
        """
        with get_session() as session:
            session.query(APIKey).filter(APIKey.id == api_key_id).update({"revoked": True})

    @staticmethod
    def delete_all_for_user(user_id):
        """Delete all API keys for a user

        Args:
            user_id: User ID to delete all keys for
        """
        with get_session() as session:
            session.query(APIKey).filter(APIKey.user_id == user_id).delete(synchronize_session=False)

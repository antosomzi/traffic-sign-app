"""Authentication token model for mobile API"""

import secrets
from datetime import datetime, timedelta
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func, Index

from models.sign_app.database import Base, get_session


class AuthToken(Base):
    """Model for mobile authentication tokens"""

    __tablename__ = "auth_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    expires_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index("idx_auth_tokens_token", "token"),
        Index("idx_auth_tokens_user_id", "user_id"),
    )
    
    @staticmethod
    def create(user_id, expires_days=365):
        """Create a new authentication token for a user
        
        Args:
            user_id: User ID to create token for
            expires_days: Number of days until token expires (default: 365)
            
        Returns:
            token: The generated token string
        """
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now() + timedelta(days=expires_days)
        
        with get_session() as session:
            auth_token = AuthToken(user_id=user_id, token=token, expires_at=expires_at)
            session.add(auth_token)
            session.flush()
            return token
    
    @staticmethod
    def get_by_token(token):
        """Get user_id by token if valid
        
        Args:
            token: Token string to verify
            
        Returns:
            user_id if token is valid, None otherwise
        """
        with get_session() as session:
            result = session.query(AuthToken).filter(AuthToken.token == token).first()

            if not result:
                return None

            expires_at = result.expires_at
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at)

            if datetime.now() > expires_at:
                AuthToken.delete(token)
                return None

            return result.user_id
    
    @staticmethod
    def delete(token):
        """Delete a token (logout)
        
        Args:
            token: Token string to delete
        """
        with get_session() as session:
            session.query(AuthToken).filter(AuthToken.token == token).delete(synchronize_session=False)
    
    @staticmethod
    def delete_all_for_user(user_id):
        """Delete all tokens for a user (logout from all devices)
        
        Args:
            user_id: User ID to delete all tokens for
        """
        with get_session() as session:
            session.query(AuthToken).filter(AuthToken.user_id == user_id).delete(synchronize_session=False)

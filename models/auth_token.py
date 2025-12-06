"""Authentication token model for mobile API"""

import secrets
from datetime import datetime, timedelta
from models.database import get_db


class AuthToken:
    """Model for mobile authentication tokens"""
    
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
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO auth_tokens (user_id, token, expires_at)
                VALUES (?, ?, ?)
            """, (user_id, token, expires_at))
            conn.commit()
        
        return token
    
    @staticmethod
    def get_by_token(token):
        """Get user_id by token if valid
        
        Args:
            token: Token string to verify
            
        Returns:
            user_id if token is valid, None otherwise
        """
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id, expires_at
                FROM auth_tokens
                WHERE token = ?
            """, (token,))
            
            result = cursor.fetchone()
            if not result:
                return None
            
            user_id, expires_at = result
            
            # Check if token is expired
            if datetime.now() > datetime.fromisoformat(expires_at):
                # Delete expired token
                AuthToken.delete(token)
                return None
            
            return user_id
    
    @staticmethod
    def delete(token):
        """Delete a token (logout)
        
        Args:
            token: Token string to delete
        """
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM auth_tokens WHERE token = ?", (token,))
            conn.commit()
    
    @staticmethod
    def delete_all_for_user(user_id):
        """Delete all tokens for a user (logout from all devices)
        
        Args:
            user_id: User ID to delete all tokens for
        """
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM auth_tokens WHERE user_id = ?", (user_id,))
            conn.commit()

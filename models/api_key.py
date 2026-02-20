"""API Key model for B2B API authentication"""

import secrets
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from models.database import get_db


class APIKey:
    """Model for API keys used in B2B authentication"""

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

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO api_keys (user_id, name, key_hash, expires_at)
                VALUES (?, ?, ?, ?)
            """, (user_id, name, key_hash, expires_at))
            api_key_id = cursor.lastrowid

        return api_key_id, plain_key

    @staticmethod
    def get_by_key(plain_key):
        """Get user_id by API key if valid

        Args:
            plain_key: Full API key string (e.g., sk_live_xxx)

        Returns:
            user_id if API key is valid, None otherwise
        """
        with get_db() as conn:
            cursor = conn.cursor()
            # Get all API keys (we need to check each one since we can't query by hashed value)
            cursor.execute("""
                SELECT id, user_id, key_hash, expires_at, revoked
                FROM api_keys
            """)

            rows = cursor.fetchall()
            if not rows:
                return None

            # Check each key
            for row in rows:
                key_id, user_id, key_hash, expires_at, revoked = row

                # Check if revoked (convert to int for safety)
                if int(revoked) == 1:
                    continue

                # Check if expired
                if expires_at and datetime.now() > datetime.fromisoformat(expires_at):
                    continue

                # Verify the hash
                if check_password_hash(key_hash, plain_key):
                    return user_id

            return None

    @staticmethod
    def get_all_for_user(user_id):
        """Get all API keys for a user (without the actual key values)

        Args:
            user_id: User ID to get keys for

        Returns:
            list: List of API key metadata (id, name, created_at, expires_at, revoked)
        """
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, created_at, expires_at, revoked
                FROM api_keys
                WHERE user_id = ?
                ORDER BY created_at DESC
            """, (user_id,))

            rows = cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "created_at": row["created_at"],
                    "expires_at": row["expires_at"],
                    "revoked": bool(row["revoked"])
                }
                for row in rows
            ]

    @staticmethod
    def delete_by_id(api_key_id):
        """Delete an API key by ID

        Args:
            api_key_id: API key ID to delete
        """
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM api_keys WHERE id = ?", (api_key_id,))
            conn.commit()

    @staticmethod
    def revoke(api_key_id):
        """Revoke an API key (soft delete)

        Args:
            api_key_id: API key ID to revoke
        """
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE api_keys SET revoked = 1 WHERE id = ?", (api_key_id,))
            conn.commit()

    @staticmethod
    def delete_all_for_user(user_id):
        """Delete all API keys for a user

        Args:
            user_id: User ID to delete all keys for
        """
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM api_keys WHERE user_id = ?", (user_id,))
            conn.commit()

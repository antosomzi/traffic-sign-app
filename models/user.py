"""User model with Flask-Login integration"""

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from .database import get_db
from .organization import Organization


class User(UserMixin):
    """User entity with Flask-Login support"""
    
    def __init__(self, id, email, password_hash, name, organization_id, is_admin, is_org_owner=False, created_at=None):
        self.id = id
        self.email = email
        self.password_hash = password_hash
        self.name = name
        self.organization_id = organization_id
        self.is_admin = bool(is_admin)
        self.is_org_owner = bool(is_org_owner)
        self.created_at = created_at
        self._organization = None
    
    @property
    def organization(self):
        """Lazy load organization"""
        if self._organization is None:
            self._organization = Organization.get_by_id(self.organization_id)
        return self._organization
    
    def check_password(self, password):
        """Verify password"""
        return check_password_hash(self.password_hash, password)
    
    @staticmethod
    def create(email, password, name, organization_id, is_admin=False, is_org_owner=False):
        """Create a new user"""
        password_hash = generate_password_hash(password)
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO users (email, password_hash, name, organization_id, is_admin, is_org_owner)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (email, password_hash, name, organization_id, 1 if is_admin else 0, 1 if is_org_owner else 0)
            )
            user_id = cursor.lastrowid
        
        return User.get_by_id(user_id)
    
    @staticmethod
    def get_by_id(user_id):
        """Get user by ID (required by Flask-Login)"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, email, password_hash, name, organization_id, is_admin, is_org_owner, created_at
                   FROM users WHERE id = ?""",
                (user_id,)
            )
            row = cursor.fetchone()
        
        if row:
            return User(
                id=row['id'],
                email=row['email'],
                password_hash=row['password_hash'],
                name=row['name'],
                organization_id=row['organization_id'],
                is_admin=row['is_admin'],
                is_org_owner=row['is_org_owner'],
                created_at=row['created_at']
            )
        return None
    
    @staticmethod
    def get_by_email(email):
        """Get user by email"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, email, password_hash, name, organization_id, is_admin, is_org_owner, created_at
                   FROM users WHERE email = ?""",
                (email,)
            )
            row = cursor.fetchone()
        
        if row:
            return User(
                id=row['id'],
                email=row['email'],
                password_hash=row['password_hash'],
                name=row['name'],
                organization_id=row['organization_id'],
                is_admin=row['is_admin'],
                is_org_owner=row['is_org_owner'],
                created_at=row['created_at']
            )
        return None
    
    @staticmethod
    def get_all():
        """Get all users"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, email, password_hash, name, organization_id, is_admin, is_org_owner, created_at
                   FROM users ORDER BY created_at DESC"""
            )
            rows = cursor.fetchall()
        
        return [
            User(
                id=row['id'],
                email=row['email'],
                password_hash=row['password_hash'],
                name=row['name'],
                organization_id=row['organization_id'],
                is_admin=row['is_admin'],
                is_org_owner=row['is_org_owner'],
                created_at=row['created_at']
            )
            for row in rows
        ]
    
    @staticmethod
    def get_by_organization(organization_id):
        """Get all users in an organization"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, email, password_hash, name, organization_id, is_admin, is_org_owner, created_at
                   FROM users WHERE organization_id = ? ORDER BY name""",
                (organization_id,)
            )
            rows = cursor.fetchall()
        
        return [
            User(
                id=row['id'],
                email=row['email'],
                password_hash=row['password_hash'],
                name=row['name'],
                organization_id=row['organization_id'],
                is_admin=row['is_admin'],
                is_org_owner=row['is_org_owner'],
                created_at=row['created_at']
            )
            for row in rows
        ]
    
    def update_password(self, new_password):
        """Update user password"""
        password_hash = generate_password_hash(new_password)
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (password_hash, self.id)
            )
        self.password_hash = password_hash
    
    def update_admin_status(self, is_admin):
        """Update admin status"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET is_admin = ? WHERE id = ?",
                (1 if is_admin else 0, self.id)
            )
        self.is_admin = bool(is_admin)
    
    def update_org_owner_status(self, is_org_owner):
        """Update organization owner status"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET is_org_owner = ? WHERE id = ?",
                (1 if is_org_owner else 0, self.id)
            )
        self.is_org_owner = bool(is_org_owner)
    
    def update_fields(self, email, name, organization_id):
        """Update user fields (email, name, organization)"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET email = ?, name = ?, organization_id = ? WHERE id = ?",
                (email, name, organization_id, self.id)
            )
        self.email = email
        self.name = name
        self.organization_id = organization_id
        self._organization = None  # Reset cached organization
    
    def delete(self):
        """Delete user from database"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE id = ?", (self.id,))

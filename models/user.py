"""User model with Flask-Login integration"""

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, func

from .database import Base, get_session
from .organization import Organization


class User(Base, UserMixin):
    """User entity with Flask-Login support"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    name = Column(String, nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    is_admin = Column(Boolean, default=False)
    is_org_owner = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    
    @property
    def organization(self):
        """Lazy load organization"""
        if getattr(self, "_organization", None) is None:
            self._organization = Organization.get_by_id(self.organization_id)
        return self._organization
    
    def check_password(self, password):
        """Verify password"""
        return check_password_hash(self.password_hash, password)
    
    @staticmethod
    def create(email, password, name, organization_id, is_admin=False, is_org_owner=False):
        """Create a new user"""
        password_hash = generate_password_hash(password)

        with get_session() as session:
            user = User(
                email=email,
                password_hash=password_hash,
                name=name,
                organization_id=organization_id,
                is_admin=bool(is_admin),
                is_org_owner=bool(is_org_owner)
            )
            session.add(user)
            session.flush()
            session.refresh(user)
            return user
    
    @staticmethod
    def get_by_id(user_id):
        """Get user by ID (required by Flask-Login)"""
        with get_session() as session:
            return session.get(User, user_id)
    
    @staticmethod
    def get_by_email(email):
        """Get user by email"""
        with get_session() as session:
            return session.query(User).filter(User.email == email).first()
    
    @staticmethod
    def get_all():
        """Get all users"""
        with get_session() as session:
            return session.query(User).order_by(User.created_at.desc()).all()
    
    @staticmethod
    def get_by_organization(organization_id):
        """Get all users in an organization"""
        with get_session() as session:
            return session.query(User).filter(User.organization_id == organization_id).order_by(User.name).all()
    
    def update_password(self, new_password):
        """Update user password"""
        password_hash = generate_password_hash(new_password)
        with get_session() as session:
            session.query(User).filter(User.id == self.id).update({"password_hash": password_hash})
        self.password_hash = password_hash
    
    def update_admin_status(self, is_admin):
        """Update admin status"""
        with get_session() as session:
            session.query(User).filter(User.id == self.id).update({"is_admin": bool(is_admin)})
        self.is_admin = bool(is_admin)
    
    def update_org_owner_status(self, is_org_owner):
        """Update organization owner status"""
        with get_session() as session:
            session.query(User).filter(User.id == self.id).update({"is_org_owner": bool(is_org_owner)})
        self.is_org_owner = bool(is_org_owner)
    
    def update_fields(self, email, name, organization_id):
        """Update user fields (email, name, organization)"""
        with get_session() as session:
            session.query(User).filter(User.id == self.id).update(
                {"email": email, "name": name, "organization_id": organization_id}
            )
        self.email = email
        self.name = name
        self.organization_id = organization_id
        self._organization = None  # Reset cached organization
    
    def delete(self):
        """Delete user from database"""
        with get_session() as session:
            session.query(User).filter(User.id == self.id).delete()

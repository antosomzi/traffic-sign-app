"""Organization model"""

import os
from sqlalchemy import Column, Integer, String, DateTime, func

from .database import Base, get_session


def _get_org_routes_dir(org_id):
    """Return the directory for an organization's routes GeoJSON file."""
    from config import Config
    return os.path.join(Config.ORG_ROUTES_FOLDER, str(org_id))


class Organization(Base):
    """Organization entity"""

    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    
    @staticmethod
    def create(name):
        """Create a new organization"""
        with get_session() as session:
            organization = Organization(name=name)
            session.add(organization)
            session.flush()
            session.refresh(organization)
            return organization
    
    @staticmethod
    def get_by_id(org_id):
        """Get organization by ID"""
        with get_session() as session:
            return session.get(Organization, org_id)
    
    @staticmethod
    def get_by_name(name):
        """Get organization by name"""
        with get_session() as session:
            return session.query(Organization).filter(Organization.name == name).first()
    
    @staticmethod
    def get_all():
        """Get all organizations"""
        with get_session() as session:
            return session.query(Organization).order_by(Organization.name).all()
    
    def count_recordings(self):
        """Count recordings for this organization"""
        from .recording import Recording

        with get_session() as session:
            return session.query(func.count(Recording.id)).filter(Recording.organization_id == self.id).scalar() or 0
    
    def count_users(self):
        """Count users in this organization"""
        from .user import User

        with get_session() as session:
            return session.query(func.count(User.id)).filter(User.organization_id == self.id).scalar() or 0
    
    def update_name(self, name):
        """Update organization name"""
        with get_session() as session:
            session.query(Organization).filter(Organization.id == self.id).update({"name": name})
        self.name = name
    
    def delete(self):
        """Delete organization and all its users"""
        from .user import User

        with get_session() as session:
            session.query(User).filter(User.organization_id == self.id).delete(synchronize_session=False)
            session.query(Organization).filter(Organization.id == self.id).delete(synchronize_session=False)

    # -----------------------------------------------------------------
    # Organization Routes GeoJSON
    # -----------------------------------------------------------------

    def get_routes_geojson_path(self):
        """Return the path to this org's routes GeoJSON file (may not exist)."""
        return os.path.join(_get_org_routes_dir(self.id), "routes.geojson")

    def has_routes(self):
        """Check if the organisation has a routes GeoJSON file uploaded."""
        return os.path.isfile(self.get_routes_geojson_path())

    def save_routes_geojson(self, geojson_content: str):
        """Save a GeoJSON string to the org's routes file.

        Creates the directory if it doesn't exist. Overwrites any existing file.

        Args:
            geojson_content: Raw GeoJSON string (already validated by caller).
        """
        routes_dir = _get_org_routes_dir(self.id)
        os.makedirs(routes_dir, exist_ok=True)
        path = os.path.join(routes_dir, "routes.geojson")
        with open(path, "w", encoding="utf-8") as f:
            f.write(geojson_content)

    def load_routes_geojson(self):
        """Load and return the routes GeoJSON as a Python dict, or None."""
        import json
        path = self.get_routes_geojson_path()
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def delete_routes_geojson(self):
        """Delete the organisation's routes GeoJSON file if it exists."""
        path = self.get_routes_geojson_path()
        if os.path.isfile(path):
            os.remove(path)

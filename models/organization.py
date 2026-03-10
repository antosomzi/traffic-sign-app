"""Organization model"""

import os
from .database import get_db


def _get_org_routes_dir(org_id):
    """Return the directory for an organization's routes GeoJSON file."""
    from config import Config
    return os.path.join(Config.ORG_ROUTES_FOLDER, str(org_id))


class Organization:
    """Organization entity"""
    
    def __init__(self, id, name, created_at=None):
        self.id = id
        self.name = name
        self.created_at = created_at
    
    @staticmethod
    def create(name):
        """Create a new organization"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO organizations (name) VALUES (?)",
                (name,)
            )
            org_id = cursor.lastrowid
        return Organization.get_by_id(org_id)
    
    @staticmethod
    def get_by_id(org_id):
        """Get organization by ID"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, name, created_at FROM organizations WHERE id = ?",
                (org_id,)
            )
            row = cursor.fetchone()
        
        if row:
            return Organization(
                id=row['id'],
                name=row['name'],
                created_at=row['created_at']
            )
        return None
    
    @staticmethod
    def get_by_name(name):
        """Get organization by name"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, name, created_at FROM organizations WHERE name = ?",
                (name,)
            )
            row = cursor.fetchone()
        
        if row:
            return Organization(
                id=row['id'],
                name=row['name'],
                created_at=row['created_at']
            )
        return None
    
    @staticmethod
    def get_all():
        """Get all organizations"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, name, created_at FROM organizations ORDER BY name"
            )
            rows = cursor.fetchall()
        
        return [
            Organization(
                id=row['id'],
                name=row['name'],
                created_at=row['created_at']
            )
            for row in rows
        ]
    
    def count_recordings(self):
        """Count recordings for this organization"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) as count FROM recordings WHERE organization_id = ?",
                (self.id,)
            )
            row = cursor.fetchone()
        return row['count'] if row else 0
    
    def count_users(self):
        """Count users in this organization"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) as count FROM users WHERE organization_id = ?",
                (self.id,)
            )
            row = cursor.fetchone()
        return row['count'] if row else 0
    
    def update_name(self, name):
        """Update organization name"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE organizations SET name = ? WHERE id = ?",
                (name, self.id)
            )
        self.name = name
    
    def delete(self):
        """Delete organization and all its users"""
        with get_db() as conn:
            cursor = conn.cursor()
            # Delete all users in this organization first
            cursor.execute("DELETE FROM users WHERE organization_id = ?", (self.id,))
            # Then delete the organization
            cursor.execute("DELETE FROM organizations WHERE id = ?", (self.id,))

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

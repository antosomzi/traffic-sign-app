"""Organization model"""

from .database import get_db


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

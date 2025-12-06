"""Recording model for multi-tenancy"""

from .database import get_db


class Recording:
    """Recording entity linking recording_id to organization"""
    
    def __init__(self, id, organization_id, upload_date=None):
        self.id = id  # recording_id (e.g., "2024_05_20_23_32_53_415")
        self.organization_id = organization_id
        self.upload_date = upload_date
    
    @staticmethod
    def create(recording_id, organization_id):
        """Create a new recording entry"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO recordings (id, organization_id) VALUES (?, ?)",
                (recording_id, organization_id)
            )
        return Recording.get_by_id(recording_id)
    
    @staticmethod
    def get_by_id(recording_id):
        """Get recording by ID"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, organization_id, upload_date FROM recordings WHERE id = ?",
                (recording_id,)
            )
            row = cursor.fetchone()
        
        if row:
            return Recording(
                id=row['id'],
                organization_id=row['organization_id'],
                upload_date=row['upload_date']
            )
        return None
    
    @staticmethod
    def get_by_organization(organization_id):
        """Get all recording IDs for an organization"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, organization_id, upload_date FROM recordings WHERE organization_id = ? ORDER BY upload_date DESC",
                (organization_id,)
            )
            rows = cursor.fetchall()
        
        return [
            Recording(
                id=row['id'],
                organization_id=row['organization_id'],
                upload_date=row['upload_date']
            )
            for row in rows
        ]
    
    @staticmethod
    def delete(recording_id):
        """Delete a recording entry"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM recordings WHERE id = ?",
                (recording_id,)
            )
    
    @staticmethod
    def exists(recording_id):
        """Check if recording exists"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) as count FROM recordings WHERE id = ?",
                (recording_id,)
            )
            row = cursor.fetchone()
        return row['count'] > 0 if row else False
    
    def belongs_to_organization(self, organization_id):
        """Check if recording belongs to specific organization"""
        return self.organization_id == organization_id

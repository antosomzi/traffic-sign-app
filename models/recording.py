"""Recording model for multi-tenancy"""

from datetime import datetime
from .database import get_db


def parse_recording_date(recording_id):
    """
    Parse recording_id to extract recording date
    Format: '2024_05_20_23_32_53_415' → datetime(2024, 5, 20, 23, 32, 53)
    """
    parts = recording_id.split('_')
    if len(parts) >= 6:
        try:
            return datetime(
                int(parts[0]), int(parts[1]), int(parts[2]),
                int(parts[3]), int(parts[4]), int(parts[5])
            )
        except (ValueError, IndexError):
            return None
    return None


def parse_db_datetime(value):
    """
    Parse datetime from SQLite database.
    SQLite stores datetimes as strings, so we need to convert them.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            # Try ISO format first (2024-05-20 23:32:53)
            return datetime.fromisoformat(value)
        except ValueError:
            try:
                # Try common SQLite format
                return datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                try:
                    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    return None
    return None


class Recording:
    """Recording entity linking recording_id to organization and user"""
    
    def __init__(self, id, organization_id, user_id=None, upload_date=None, recording_date=None):
        self.id = id  # recording_id (e.g., "2024_05_20_23_32_53_415")
        self.organization_id = organization_id
        self.user_id = user_id
        # Parse dates from strings if needed
        self.upload_date = parse_db_datetime(upload_date)
        self.recording_date = parse_db_datetime(recording_date)
        self._user = None
    
    @property
    def user(self):
        """Lazy load user"""
        if self._user is None and self.user_id:
            from .user import User
            self._user = User.get_by_id(self.user_id)
        return self._user
    
    @property
    def uploader_name(self):
        """Get uploader's name"""
        return self.user.name if self.user else "Unknown"
    
    @staticmethod
    def create(recording_id, organization_id, user_id=None):
        """Create a new recording entry"""
        recording_date = parse_recording_date(recording_id)
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO recordings (id, organization_id, user_id, recording_date) 
                   VALUES (?, ?, ?, ?)""",
                (recording_id, organization_id, user_id, recording_date)
            )
        return Recording.get_by_id(recording_id)
    
    @staticmethod
    def get_by_id(recording_id):
        """Get recording by ID"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, organization_id, user_id, upload_date, recording_date 
                   FROM recordings WHERE id = ?""",
                (recording_id,)
            )
            row = cursor.fetchone()
        
        if row:
            return Recording(
                id=row['id'],
                organization_id=row['organization_id'],
                user_id=row['user_id'],
                upload_date=row['upload_date'],
                recording_date=row['recording_date']
            )
        return None
    
    @staticmethod
    def get_by_organization(organization_id, user_ids=None, sort_by='upload_date', sort_order='desc'):
        """
        Get all recordings for an organization with optional filtering and sorting.
        
        Args:
            organization_id: Filter by organization
            user_ids: Optional list of user IDs to filter by
            sort_by: 'upload_date' or 'recording_date'
            sort_order: 'asc' or 'desc'
        
        Returns:
            List of Recording objects
        """
        # Validate sort parameters
        valid_sort_columns = ['upload_date', 'recording_date']
        if sort_by not in valid_sort_columns:
            sort_by = 'upload_date'
        
        sort_order = 'DESC' if sort_order.lower() == 'desc' else 'ASC'
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Build query
            query = f"""
                SELECT id, organization_id, user_id, upload_date, recording_date 
                FROM recordings 
                WHERE organization_id = ?
            """
            params = [organization_id]
            
            # Add user filter if provided
            if user_ids:
                placeholders = ','.join(['?' for _ in user_ids])
                query += f" AND user_id IN ({placeholders})"
                params.extend(user_ids)
            
            # Add sorting
            query += f" ORDER BY {sort_by} {sort_order}"
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
        
        return [
            Recording(
                id=row['id'],
                organization_id=row['organization_id'],
                user_id=row['user_id'],
                upload_date=row['upload_date'],
                recording_date=row['recording_date']
            )
            for row in rows
        ]
    
    @staticmethod
    def get_users_with_recordings(organization_id):
        """
        Get list of users who have uploaded recordings in an organization.
        Useful for populating filter dropdowns.
        
        Returns:
            List of dicts with user_id and user_name
        """
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT r.user_id, u.name as user_name
                FROM recordings r
                LEFT JOIN users u ON r.user_id = u.id
                WHERE r.organization_id = ? AND r.user_id IS NOT NULL
                ORDER BY u.name
            """, (organization_id,))
            rows = cursor.fetchall()
        
        return [{'id': row['user_id'], 'name': row['user_name'] or 'Unknown'} for row in rows]
    
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

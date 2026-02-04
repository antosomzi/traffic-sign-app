"""Sign model for storing detected traffic signs from pipeline results"""

from .database import get_db


class Sign:
    """Sign entity representing a detected traffic sign with GPS coordinates"""
    
    def __init__(self, id, recording_id, mutcd_code, latitude, longitude):
        self.id = id
        self.recording_id = recording_id
        self.mutcd_code = mutcd_code
        self.latitude = latitude
        self.longitude = longitude
    
    @staticmethod
    def create(recording_id, mutcd_code, latitude, longitude):
        """Create a new sign entry"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO signs (recording_id, mutcd_code, latitude, longitude) 
                   VALUES (?, ?, ?, ?)""",
                (recording_id, mutcd_code, latitude, longitude)
            )
            sign_id = cursor.lastrowid
        return Sign(sign_id, recording_id, mutcd_code, latitude, longitude)
    
    @staticmethod
    def bulk_create(signs_data):
        """
        Bulk create signs for better performance.
        
        Args:
            signs_data: List of tuples (recording_id, mutcd_code, latitude, longitude)
        
        Returns:
            Number of signs created
        """
        if not signs_data:
            return 0
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.executemany(
                """INSERT INTO signs (recording_id, mutcd_code, latitude, longitude) 
                   VALUES (?, ?, ?, ?)""",
                signs_data
            )
        return len(signs_data)
    
    @staticmethod
    def get_by_id(sign_id):
        """Get sign by ID"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, recording_id, mutcd_code, latitude, longitude 
                   FROM signs WHERE id = ?""",
                (sign_id,)
            )
            row = cursor.fetchone()
        
        if row:
            return Sign(
                id=row['id'],
                recording_id=row['recording_id'],
                mutcd_code=row['mutcd_code'],
                latitude=row['latitude'],
                longitude=row['longitude']
            )
        return None
    
    @staticmethod
    def get_by_recording(recording_id):
        """Get all signs for a recording"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, recording_id, mutcd_code, latitude, longitude 
                   FROM signs WHERE recording_id = ?""",
                (recording_id,)
            )
            rows = cursor.fetchall()
        
        return [
            Sign(
                id=row['id'],
                recording_id=row['recording_id'],
                mutcd_code=row['mutcd_code'],
                latitude=row['latitude'],
                longitude=row['longitude']
            )
            for row in rows
        ]
    
    @staticmethod
    def get_by_organization(organization_id, recording_ids=None, mutcd_codes=None):
        """
        Get all signs for an organization's validated recordings.
        
        Args:
            organization_id: Filter by organization
            recording_ids: Optional list of recording IDs to filter by
            mutcd_codes: Optional list of MUTCD codes to filter by
        
        Returns:
            List of Sign objects with recording info
        """
        with get_db() as conn:
            cursor = conn.cursor()
            
            query = """
                SELECT s.id, s.recording_id, s.mutcd_code, s.latitude, s.longitude
                FROM signs s
                INNER JOIN recordings r ON s.recording_id = r.id
                WHERE r.organization_id = ?
            """
            params = [organization_id]
            
            # Add recording filter if provided
            if recording_ids:
                placeholders = ','.join(['?' for _ in recording_ids])
                query += f" AND s.recording_id IN ({placeholders})"
                params.extend(recording_ids)
            
            # Add MUTCD code filter if provided
            if mutcd_codes:
                placeholders = ','.join(['?' for _ in mutcd_codes])
                query += f" AND s.mutcd_code IN ({placeholders})"
                params.extend(mutcd_codes)
            
            query += " ORDER BY s.recording_id, s.id"
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
        
        return [
            Sign(
                id=row['id'],
                recording_id=row['recording_id'],
                mutcd_code=row['mutcd_code'],
                latitude=row['latitude'],
                longitude=row['longitude']
            )
            for row in rows
        ]
    
    @staticmethod
    def get_unique_mutcd_codes(organization_id):
        """
        Get all unique MUTCD codes for an organization's signs.
        Useful for filter dropdowns.
        
        Returns:
            List of unique MUTCD codes sorted alphabetically
        """
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT s.mutcd_code
                FROM signs s
                INNER JOIN recordings r ON s.recording_id = r.id
                WHERE r.organization_id = ?
                ORDER BY s.mutcd_code
            """, (organization_id,))
            rows = cursor.fetchall()
        
        return [row['mutcd_code'] for row in rows]
    
    @staticmethod
    def get_recordings_with_signs(organization_id):
        """
        Get list of recordings that have signs.
        Useful for filter dropdowns.
        
        Returns:
            List of recording IDs that have signs
        """
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT s.recording_id
                FROM signs s
                INNER JOIN recordings r ON s.recording_id = r.id
                WHERE r.organization_id = ?
                ORDER BY s.recording_id
            """, (organization_id,))
            rows = cursor.fetchall()
        
        return [row['recording_id'] for row in rows]
    
    @staticmethod
    def delete_by_recording(recording_id):
        """Delete all signs for a recording"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM signs WHERE recording_id = ?",
                (recording_id,)
            )
            return cursor.rowcount
    
    @staticmethod
    def count_by_recording(recording_id):
        """Count signs for a recording"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) as count FROM signs WHERE recording_id = ?",
                (recording_id,)
            )
            row = cursor.fetchone()
        return row['count'] if row else 0
    
    @staticmethod
    def count_by_organization(organization_id):
        """Count total signs for an organization"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM signs s
                INNER JOIN recordings r ON s.recording_id = r.id
                WHERE r.organization_id = ?
            """, (organization_id,))
            row = cursor.fetchone()
        return row['count'] if row else 0
    
    def to_geojson_feature(self):
        """Convert sign to GeoJSON Feature"""
        return {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [self.longitude, self.latitude]
            },
            "properties": {
                "id": self.id,
                "recording_id": self.recording_id,
                "mutcd_code": self.mutcd_code
            }
        }
    
    @staticmethod
    def to_geojson_collection(signs):
        """Convert list of signs to GeoJSON FeatureCollection"""
        return {
            "type": "FeatureCollection",
            "features": [sign.to_geojson_feature() for sign in signs]
        }

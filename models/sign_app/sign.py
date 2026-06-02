"""Sign model for storing detected traffic signs from pipeline results"""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, func, Index

from .database import Base, get_session


class Sign(Base):
    """Sign entity representing a detected traffic sign with GPS coordinates"""

    __tablename__ = "signs"

    id = Column(Integer, primary_key=True)
    recording_id = Column(String, ForeignKey("recordings.id", ondelete="CASCADE"), nullable=False)
    mutcd_code = Column(String, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    created_at = Column(DateTime, server_default=func.current_timestamp())

    __table_args__ = (
        Index("idx_signs_recording_id", "recording_id"),
        Index("idx_signs_mutcd_code", "mutcd_code"),
    )
    
    @staticmethod
    def create(recording_id, mutcd_code, latitude, longitude):
        """Create a new sign entry"""
        with get_session() as session:
            sign = Sign(
                recording_id=recording_id,
                mutcd_code=mutcd_code,
                latitude=latitude,
                longitude=longitude
            )
            session.add(sign)
            session.flush()
            session.refresh(sign)
            return sign
    
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
        
        with get_session() as session:
            sign_objects = [
                Sign(
                    recording_id=recording_id,
                    mutcd_code=mutcd_code,
                    latitude=latitude,
                    longitude=longitude
                )
                for recording_id, mutcd_code, latitude, longitude in signs_data
            ]
            session.bulk_save_objects(sign_objects)
            return len(sign_objects)
    
    @staticmethod
    def get_by_id(sign_id):
        """Get sign by ID"""
        with get_session() as session:
            return session.get(Sign, sign_id)
    
    @staticmethod
    def get_by_recording(recording_id):
        """Get all signs for a recording"""
        with get_session() as session:
            return session.query(Sign).filter(Sign.recording_id == recording_id).all()
    
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
        from .recording import Recording

        with get_session() as session:
            query = (
                session.query(Sign)
                .join(Recording, Sign.recording_id == Recording.id)
                .filter(Recording.organization_id == organization_id)
            )

            if recording_ids:
                query = query.filter(Sign.recording_id.in_(recording_ids))

            if mutcd_codes:
                query = query.filter(Sign.mutcd_code.in_(mutcd_codes))

            return query.order_by(Sign.recording_id, Sign.id).all()
    
    @staticmethod
    def get_unique_mutcd_codes(organization_id):
        """
        Get all unique MUTCD codes for an organization's signs.
        Useful for filter dropdowns.
        
        Returns:
            List of unique MUTCD codes sorted alphabetically
        """
        from .recording import Recording

        with get_session() as session:
            rows = (
                session.query(Sign.mutcd_code)
                .join(Recording, Sign.recording_id == Recording.id)
                .filter(Recording.organization_id == organization_id)
                .distinct()
                .order_by(Sign.mutcd_code)
                .all()
            )

        return [row.mutcd_code for row in rows]
    
    @staticmethod
    def get_recordings_with_signs(organization_id):
        """
        Get list of recordings that have signs.
        Useful for filter dropdowns.
        
        Returns:
            List of recording IDs that have signs
        """
        from .recording import Recording

        with get_session() as session:
            rows = (
                session.query(Sign.recording_id)
                .join(Recording, Sign.recording_id == Recording.id)
                .filter(Recording.organization_id == organization_id)
                .distinct()
                .order_by(Sign.recording_id)
                .all()
            )

        return [row.recording_id for row in rows]
    
    @staticmethod
    def delete_by_recording(recording_id):
        """Delete all signs for a recording"""
        with get_session() as session:
            return session.query(Sign).filter(Sign.recording_id == recording_id).delete(synchronize_session=False)
    
    @staticmethod
    def count_by_recording(recording_id):
        """Count signs for a recording"""
        with get_session() as session:
            return session.query(func.count(Sign.id)).filter(Sign.recording_id == recording_id).scalar() or 0
    
    @staticmethod
    def count_by_organization(organization_id):
        """Count total signs for an organization"""
        from .recording import Recording

        with get_session() as session:
            return (
                session.query(func.count(Sign.id))
                .join(Recording, Sign.recording_id == Recording.id)
                .filter(Recording.organization_id == organization_id)
                .scalar()
                or 0
            )
    
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

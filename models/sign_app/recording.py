"""Recording model for multi-tenancy"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import joinedload, relationship, reconstructor
from models.sign_app.model_history import ModelHistory

from .database import Base, get_session


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


class Recording(Base):
    """Recording entity linking recording_id to organization and user"""

    __tablename__ = "recordings"

    id = Column(String, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    model_history_id = Column(Integer, ForeignKey("model_history.id"), nullable=True)
    upload_date = Column(DateTime, server_default=func.current_timestamp())
    recording_date = Column(DateTime)
    note = Column(Text)
    video_s3_key = Column(String)
    status = Column(String, default="processing")
    status_message = Column(Text)
    status_timestamp = Column(DateTime, server_default=func.current_timestamp())

    error_details = Column(Text)  # Stores JSON string
    validation_status = Column(String, default="to_be_validated")
    validated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    validated_at = Column(DateTime)


    user_rel = relationship("User", foreign_keys=[user_id], viewonly=True)
    model_history_rel = relationship("ModelHistory", foreign_keys=[model_history_id], viewonly=True)
    curve_recording = relationship(
        "CurveRecording", 
        primaryjoin="Recording.id == foreign(CurveRecording.recording_id)", 
        viewonly=True,
        uselist=False
    )
    
    @reconstructor
    def init_on_load(self):
        """Initialize transient fields after loading from DB."""
        self._user = None
        self.uploader_name = None
        self.model_history_name = None

    @property
    def user(self):
        """Lazy load user"""
        if self._user is None and self.user_id:
            from .user import User
            self._user = User.get_by_id(self.user_id)
        return self._user
    

    @staticmethod
    def create(recording_id, organization_id, user_id=None, model_history_id=None):
        """Create a new recording entry"""
        recording_date = parse_recording_date(recording_id)

        with get_session() as session:
            recording = Recording(
                id=recording_id,
                organization_id=organization_id,
                user_id=user_id,
                model_history_id=model_history_id,
                recording_date=recording_date,
                status="processing",
                validation_status="to_be_validated"
            )
            session.add(recording)
            session.flush()
            session.refresh(recording)
            return recording
    
    @staticmethod
    def get_by_id(recording_id):
        """Get recording by ID"""
        with get_session() as session:
            return session.get(Recording, recording_id)
        
    @staticmethod
    def update_status(recording_id, status=None, message=None, error_details=None, video_s3_key=None, validation_status=None, validated_by=None, validated_at=None):
        """Update recording status and metadata in DB"""
        import json
        updates = {}
        if status:
            updates["status"] = status
        if message is not None:
            updates["status_message"] = message
        if error_details is not None:
            updates["error_details"] = json.dumps(error_details) if isinstance(error_details, (dict, list)) else error_details

        if video_s3_key:
            updates["video_s3_key"] = video_s3_key
        if validation_status:
            updates["validation_status"] = validation_status
        if validated_by is not None:
            updates["validated_by"] = validated_by
        if validated_at:
            updates["validated_at"] = validated_at
        
        updates["status_timestamp"] = datetime.now()

        with get_session() as session:
            session.query(Recording).filter(Recording.id == recording_id).update(updates)
            session.commit()

    @staticmethod
    def update_model(recording_id):
        with get_session() as session:
            current_model = ModelHistory.get_current_active()
            
            if not current_model:
                raise ValueError("Aucun modèle actif trouvé.")
                
            session.query(Recording).filter(Recording.id == recording_id).update({
                "model_history_id": current_model.id  
            })
            session.commit()

    
    @staticmethod
    def get_by_organization(organization_id, user_ids=None, model_history_ids=None, sort_by='upload_date', sort_order='desc'):
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
        
        sort_column = Recording.upload_date if sort_by == 'upload_date' else Recording.recording_date
        sort_column = sort_column.desc() if sort_order == 'DESC' else sort_column.asc()

        with get_session() as session:
            query = (
                session.query(Recording)
                .options(joinedload(Recording.user_rel), joinedload(Recording.model_history_rel))
                .filter(Recording.organization_id == organization_id)
            )

            if user_ids:
                query = query.filter(Recording.user_id.in_(user_ids))

            if model_history_ids:
                query = query.filter(Recording.model_history_id.in_(model_history_ids))

            recordings = query.order_by(sort_column).all()

            for recording in recordings:
                recording.uploader_name = recording.user_rel.name if recording.user_rel else None
                recording.model_history_name = (
                    recording.model_history_rel.version_name if recording.model_history_rel else None
                )

            return recordings
    
    @staticmethod
    def get_users_with_recordings(organization_id):
        """
        Get list of users who have uploaded recordings in an organization.
        Useful for populating filter dropdowns.
        
        Returns:
            List of dicts with user_id and user_name
        """
        from .user import User

        with get_session() as session:
            rows = (
                session.query(User.id, User.name)
                .join(Recording, Recording.user_id == User.id)
                .filter(Recording.organization_id == organization_id)
                .filter(Recording.user_id.isnot(None))
                .distinct()
                .order_by(User.name)
                .all()
            )

        return [{'id': row.id, 'name': row.name or 'Unknown'} for row in rows]
    
    @staticmethod
    def delete(recording_id):
        """Delete a recording entry"""
        with get_session() as session:
            session.query(Recording).filter(Recording.id == recording_id).delete(synchronize_session=False)
    
    @staticmethod
    def exists(recording_id):
        """Check if recording exists"""
        with get_session() as session:
            return session.query(Recording.id).filter(Recording.id == recording_id).first() is not None
    
    def belongs_to_organization(self, organization_id):
        """Check if recording belongs to specific organization"""
        return self.organization_id == organization_id
    

    def update_note(self, new_note):
        """Update the note for this recording"""
        with get_session() as session:
            session.query(Recording).filter(Recording.id == self.id).update({"note": new_note})
        self.note = new_note

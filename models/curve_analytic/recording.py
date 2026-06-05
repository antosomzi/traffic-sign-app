"""Recording model for curve analytics"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from models.sign_app.database import Base, get_session

class CurveRecording(Base):
    """Recording entity for curve analytics data collection"""
    __tablename__ = "curve_recordings"

    id = Column(Integer, primary_key=True)
    recording_id = Column(String(255), nullable=False, unique=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    device_id = Column(String(255), nullable=False)
    imei_folder = Column(String(255), nullable=False)
    uploaded_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    organization = relationship("Organization", back_populates="curves_recordings")
    recording_curves = relationship(
        "RecordingCurve",
        back_populates="recording",
        cascade="all, delete-orphan",
    )

    @staticmethod
    def get_by_recording_id(rec_id):
        with get_session() as session:
            return session.query(CurveRecording).filter(CurveRecording.recording_id == rec_id).first()

    @staticmethod
    def create(data):
        with get_session() as session:
            recording = CurveRecording(**data)
            session.add(recording)
            session.commit()
            return recording

    def to_dict(self):
        return {
            "id": self.id,
            "recordingId": self.recording_id,
            "organizationId": self.organization_id,
            "deviceId": self.device_id,
            "imeiFolder": self.imei_folder,
            "uploadedAt": self.uploaded_at.isoformat() if self.uploaded_at else None
        }

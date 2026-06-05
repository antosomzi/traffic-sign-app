"""Curve and RecordingCurve models for curve analytics"""

from sqlalchemy import Column, Integer, String, Float, ForeignKey, JSON, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from models.sign_app.database import Base, get_session

class Curve(Base):
    """Curve entity representing a physical road curve"""
    __tablename__ = "curves"

    id = Column(Integer, primary_key=True)
    curve_id = Column(String(255), nullable=False, unique=True, index=True)
    centerline_geojson = Column(JSON, nullable=False)
    midpoint_lat = Column(Float, nullable=False)
    midpoint_lon = Column(Float, nullable=False)
    curve_radius_ft = Column(Float, nullable=True)
    deviation_angle_deg = Column(Float, nullable=True)

    # Relationships
    recording_curves = relationship(
        "RecordingCurve",
        back_populates="curve",
        cascade="all, delete-orphan",
    )

    @staticmethod
    def get_all():
        with get_session() as session:
            return session.query(Curve).all()

    @staticmethod
    def get_all_for_org(organization_id):
        """Get all curves that have at least one recording from this organization"""
        from models.curve_analytic.recording import CurveRecording
        from sqlalchemy.orm import joinedload
        with get_session() as session:
            return session.query(Curve)\
                .join(Curve.recording_curves)\
                .join(RecordingCurve.recording)\
                .options(joinedload(Curve.recording_curves).joinedload(RecordingCurve.recording))\
                .filter(CurveRecording.organization_id == organization_id)\
                .distinct().all()

    @staticmethod
    def get_by_id(curve_id):
        with get_session() as session:
            return session.get(Curve, curve_id)

    @staticmethod
    def get_by_curve_id_str(curve_id_str):
        with get_session() as session:
            return session.query(Curve).filter(Curve.curve_id == curve_id_str).first()

    def to_list_item(self):
        return {
            "id": self.id,
            "curveId": self.curve_id,
            "centerlineGeojson": self.centerline_geojson,
            "midpointLat": self.midpoint_lat,
            "midpointLon": self.midpoint_lon,
        }

    def to_detail(self):
        return {
            "id": self.id,
            "curveId": self.curve_id,
            "curveRadiusFt": self.curve_radius_ft,
            "deviationAngleDeg": self.deviation_angle_deg,
            "midpointLat": self.midpoint_lat,
            "midpointLon": self.midpoint_lon,
            "centerlineGeojson": self.centerline_geojson,
            "googleMapsUrl": (
                "https://www.google.com/maps/search/?api=1"
                f"&query={self.midpoint_lat},{self.midpoint_lon}"
            ),
            "recordings": [
                rc.to_detail()
                for rc in sorted(
                    self.recording_curves,
                    key=lambda item: item.recording.recording_id if item.recording else "",
                    reverse=True,
                )
            ],
        }


class RecordingCurve(Base):
    """Specific data for a recording on a curve"""
    __tablename__ = "recording_curves"

    id = Column(Integer, primary_key=True)
    recording_id = Column(Integer, ForeignKey("curve_recordings.id", ondelete="CASCADE"), nullable=False)
    curve_id = Column(Integer, ForeignKey("curves.id", ondelete="CASCADE"), nullable=False)
    advisory_speed_mph = Column(Float, nullable=True)
    max_superelevation = Column(Float, nullable=True)
    midpoint_superelevation = Column(Float, nullable=True)
    gps_points = Column(JSON, nullable=False)
    bbi_series = Column(JSON, nullable=False)
    speed_series = Column(JSON, nullable=False)
    superelevation_series = Column(JSON, nullable=False)
    advisory_speed_series = Column(JSON, nullable=False)

    __table_args__ = (
        UniqueConstraint("recording_id", "curve_id", name="uq_recording_curve"),
    )

    # Relationships
    recording = relationship("CurveRecording", back_populates="recording_curves")
    curve = relationship("Curve", back_populates="recording_curves")

    def to_detail(self):
        advisory_display = None
        if self.advisory_speed_mph is not None:
            advisory_display = "50+" if self.advisory_speed_mph > 50 else str(
                int(self.advisory_speed_mph)
                if float(self.advisory_speed_mph).is_integer()
                else round(float(self.advisory_speed_mph), 1)
            )

        return {
            "id": self.id,
            "recordingId": self.recording.recording_id if self.recording else None,
            "advisorySpeedMph": self.advisory_speed_mph,
            "advisorySpeedDisplay": advisory_display,
            "maxSuperelevation": self.max_superelevation,
            "midpointSuperelevation": self.midpoint_superelevation,
            "gpsPoints": self.gps_points,
            "bbiSeries": self.bbi_series,
            "speedSeries": self.speed_series,
            "superelevationSeries": self.superelevation_series,
            "advisorySpeedSeries": self.advisory_speed_series,
        }

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Integer, String, DateTime, Boolean, func, Index

from models.database import Base, get_session


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

class ModelHistory(Base):
    __tablename__ = "model_history"

    id = Column(Integer, primary_key=True)
    version_name = Column(String, nullable=False)
    updated_date = Column(DateTime, server_default=func.current_timestamp())
    is_active = Column(Boolean, default=False)

    __table_args__ = (
        Index("idx_model_history_is_active", "is_active"),
    )

    @staticmethod
    def create(version_name: str, is_active: bool = False) -> 'ModelHistory':
        """Crée une nouvelle entrée de modèle."""
        with get_session() as session:
            model_history = ModelHistory(
                version_name=version_name,
                updated_date=datetime.now(),
                is_active=bool(is_active)
            )
            session.add(model_history)
            session.flush()
            session.refresh(model_history)
            model_id = model_history.id

        if is_active and model_id:
            ModelHistory.set_active_model(model_id)

        return ModelHistory.get_model_history(model_id)

    @staticmethod
    def get_model_history(model_id: int) -> Optional['ModelHistory']:
        """Récupère un modèle spécifique par son ID."""
        with get_session() as session:
            result = session.get(ModelHistory, model_id)

            if result and isinstance(result.updated_date, str):
                result.updated_date = parse_db_datetime(result.updated_date)

            return result

    @staticmethod
    def get_current_active() -> Optional['ModelHistory']:
        with get_session() as session:
            result = session.query(ModelHistory).filter(ModelHistory.is_active.is_(True)).first()
            if result and isinstance(result.updated_date, str):
                result.updated_date = parse_db_datetime(result.updated_date)
            return result

    @staticmethod
    def set_active_model(model_id: int) -> bool:
        with get_session() as session:
            try:
                session.query(ModelHistory).update({"is_active": False})
                session.query(ModelHistory).filter(ModelHistory.id == model_id).update({"is_active": True})
                return True
            except Exception as e:
                session.rollback()
                print(f"Erreur lors de la mise à jour du modèle actif : {e}")
                return False
            
    @staticmethod
    def get_all_model_history() -> list['ModelHistory']:
        """Récupère tous les modèles de l'historique."""
        with get_session() as session:
            rows = session.query(ModelHistory).order_by(ModelHistory.updated_date.desc()).all()

            for row in rows:
                if isinstance(row.updated_date, str):
                    row.updated_date = parse_db_datetime(row.updated_date)

            return rows
        

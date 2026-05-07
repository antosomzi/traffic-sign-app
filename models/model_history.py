from datetime import datetime
from typing import Optional
from models.database import get_db
from models.recording import parse_db_datetime

class ModelHistory:
    def __init__(self, id: int, version_name: str, updated_date: datetime, is_active: bool = False):
        self.id = id
        self.version_name = version_name
        self.updated_date = updated_date
        self.is_active = is_active

    @staticmethod
    def create(version_name: str, is_active: bool = False) -> 'ModelHistory':
        """Crée une nouvelle entrée de modèle."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO model_history (version_name, is_active)
                VALUES (?, ?)
                """,
                (version_name, int(is_active))
            )
            model_id = cursor.lastrowid

        if is_active and model_id:
            ModelHistory.set_active_model(model_id)

        return ModelHistory.get_model_history(model_id)

    @staticmethod
    def get_model_history(model_id: int) -> Optional['ModelHistory']:
        """Récupère un modèle spécifique par son ID."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, version_name, updated_date, is_active FROM model_history WHERE id = ?",
                (model_id,)
            )
            row = cursor.fetchone()
        
        if row:
            return ModelHistory(
                id=row['id'],
                version_name=row['version_name'],
                updated_date=parse_db_datetime(row['updated_date']),
                is_active=bool(row['is_active']) # Correction de l'erreur de syntaxe
            )
        return None

    @staticmethod
    def get_current_active() -> Optional['ModelHistory']:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, version_name, updated_date, is_active FROM model_history WHERE is_active = TRUE"
            )
            row = cursor.fetchone()
        
        if row:
            return ModelHistory(
                id=row['id'],
                version_name=row['version_name'],
                updated_date=parse_db_datetime(row['updated_date']),
                is_active=bool(row['is_active'])
            )
        return None

    @staticmethod
    def set_active_model(model_id: int) -> bool:
        with get_db() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("UPDATE model_history SET is_active = FALSE")
                
                cursor.execute("UPDATE model_history SET is_active = TRUE WHERE id = ?", (model_id,))
                
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                print(f"Erreur lors de la mise à jour du modèle actif : {e}")
                return False
            
    @staticmethod
    def get_all_model_history() -> list['ModelHistory']:
        """Récupère tous les modèles de l'historique."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, version_name, updated_date, is_active FROM model_history ORDER BY updated_date DESC"
            )
            rows = cursor.fetchall()

        return [
            ModelHistory(
                id=row['id'],
                version_name=row['version_name'],
                updated_date=parse_db_datetime(row['updated_date']),
                is_active=bool(row['is_active'])
            )
            for row in rows
        ]
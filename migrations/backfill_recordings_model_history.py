"""Migration: Backfill recordings.model_history_id with default model (id=1)"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.sign_app.database import get_db


def migrate(default_model_id: int = 1):
    """Backfill recordings without model_history_id using default model ID."""
    print("🔄 Starting migration: backfill_recordings_model_history")

    with get_db() as conn:
        cursor = conn.cursor()

        # Ensure model exists
        cursor.execute("SELECT id FROM model_history WHERE id = ?", (default_model_id,))
        if not cursor.fetchone():
            raise ValueError(f"ModelHistory id={default_model_id} not found")

        # Backfill recordings
        cursor.execute(
            """
            UPDATE recordings
            SET model_history_id = ?
            WHERE model_history_id IS NULL
            """,
            (default_model_id,)
        )

        updated_count = cursor.rowcount
        conn.commit()

    print(f"✅ Backfilled {updated_count} recordings with model_history_id={default_model_id}")


if __name__ == "__main__":
    migrate()
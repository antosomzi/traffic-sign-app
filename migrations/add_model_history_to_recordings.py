"""Migration: Add model_history_id to recordings table"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.sign_app.database import get_db


def migrate():
    """Add model_history_id column to recordings table"""
    print("🔄 Starting migration: add_model_history_to_recordings")

    with get_db() as conn:
        cursor = conn.cursor()

        # Check existing columns
        cursor.execute("PRAGMA table_info(recordings)")
        columns = [col['name'] for col in cursor.fetchall()]

        if 'model_history_id' not in columns:
            print("  Adding model_history_id column...")
            cursor.execute(
                """
                ALTER TABLE recordings
                ADD COLUMN model_history_id INTEGER
                """
            )
        else:
            print("  model_history_id column already exists")

        conn.commit()

    # Create index for model_history_id
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_recordings_model_history_id
            ON recordings(model_history_id)
            """
        )
        conn.commit()

    print("✅ Migration completed: add_model_history_to_recordings")


if __name__ == "__main__":
    migrate()
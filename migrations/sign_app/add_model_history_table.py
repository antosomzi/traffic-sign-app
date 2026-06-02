"""
Migration: Add model_history table for ML model version tracking

Usage:
    python migrations/add_model_history_table.py
"""

import os
import sys

# Add parent directory to path to import models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.sign_app.database import get_db


def migrate():
    """Run the migration to add model_history table"""
    print("🔄 Adding model_history table...")

    with get_db() as conn:
        cursor = conn.cursor()

        # Check if table already exists
        cursor.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='model_history'
            """
        )

        if cursor.fetchone():
            print("✅ Table 'model_history' already exists")
            return

        # Create model_history table
        cursor.execute(
            """
            CREATE TABLE model_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version_name TEXT NOT NULL,
                updated_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 0
            )
            """
        )

        # Index for active model lookup
        cursor.execute(
            """
            CREATE INDEX idx_model_history_is_active
            ON model_history(is_active)
            """
        )

        conn.commit()

        print("✅ Table 'model_history' created successfully")
        print("✅ Index created for active model lookup")


if __name__ == "__main__":
    print("=" * 60)
    print("Model History Migration")
    print("=" * 60)

    try:
        migrate()
        print("\n✅ Migration completed successfully!")
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        sys.exit(1)
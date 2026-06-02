"""
Migration: Add api_keys table for B2B API authentication

This migration adds the api_keys table to support API key authentication
for the /download/csv-only-range endpoint.

Usage:
    python migrations/add_api_keys_table.py
"""

import sqlite3
import os


def get_db_path():
    """Get database path based on environment (EC2 vs local)"""
    if os.path.exists("/home/ec2-user"):
        return "/home/ec2-user/app.db"
    else:
        # Go up one level from migrations folder
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_path, "app.db")


def migrate():
    """Run the migration to add api_keys table"""
    db_path = get_db_path()
    print(f"📍 Database path: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("🔧 Creating api_keys table...")

    # Create api_keys table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT,
            key_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            revoked INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    print("✅ Table created")

    print("🔧 Creating indexes...")

    # Create indexes for better query performance
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_api_keys_user_id
        ON api_keys(user_id)
    """)

    print("✅ Indexes created")

    conn.commit()
    conn.close()

    print("✅ Migration completed successfully!")


if __name__ == "__main__":
    migrate()

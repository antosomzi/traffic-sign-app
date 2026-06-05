"""
Migration: Add curves table for trajectory analytics

This migration adds the curves table to store road curve analytics data,
including GPS points, speeds, and advisory speed information.

Usage:
    python migrations/sign_app/add_curves_table.py
"""

import sqlite3
import os


def get_db_path():
    """Get database path based on environment (EC2 vs local)"""
    if os.path.exists("/home/ec2-user"):
        return "/home/ec2-user/app.db"
    else:
        # We are in migrations/sign_app/add_curves_table.py
        # Go up 3 levels to reach the project root
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(base_path, "app.db")


def migrate():
    """Run the migration to add curves table"""
    db_path = get_db_path()
    print(f"📍 Database path: {db_path}")

    if not os.path.exists(db_path):
        print(f"❌ Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("🔧 Creating curves table...")

    # Create curves table
    # Note: JSON fields are stored as TEXT in SQLite
    # Boolean is stored as INTEGER (0 or 1)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS curves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            curve_id_str TEXT NOT NULL,
            organization_id INTEGER,
            center_lat REAL NOT NULL,
            center_lon REAL NOT NULL,
            gps_points TEXT NOT NULL,
            speeds TEXT NOT NULL,
            accelerations TEXT,
            bbis TEXT,
            superelevations TEXT NOT NULL,
            timestamps TEXT NOT NULL,
            min_advisory_speed REAL,
            historical_advisory_speed REAL,
            discrepancy_detected INTEGER DEFAULT 0,
            advisory_speed_profile TEXT,
            radius TEXT,
            FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
        )
    """)

    print("✅ Table created")

    print("🔧 Creating indexes...")

    # Create indexes for better query performance
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_curves_curve_id_str
        ON curves(curve_id_str)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_curves_organization_id
        ON curves(organization_id)
    """)

    print("✅ Indexes created")

    conn.commit()
    conn.close()

    print("✅ Migration completed successfully!")


if __name__ == "__main__":
    migrate()

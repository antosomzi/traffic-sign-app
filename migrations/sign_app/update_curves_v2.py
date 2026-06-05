"""
Migration: Update curves table and add recording_curves (v2)

This migration:
1. Drops the old curves table.
2. Creates the new curves table with updated schema.
3. Creates the recording_curves table for linking recordings to curves.

Usage:
    python migrations/sign_app/update_curves_v2.py
"""

import sqlite3
import os


def get_db_path():
    """Get database path based on environment (EC2 vs local)"""
    if os.path.exists("/home/ec2-user"):
        return "/home/ec2-user/app.db"
    else:
        # Go up 3 levels to reach the project root
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(base_path, "app.db")


def migrate():
    """Run the migration"""
    db_path = get_db_path()
    print(f"📍 Database path: {db_path}")

    if not os.path.exists(db_path):
        print(f"❌ Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("🗑️ Dropping old curves table...")
    cursor.execute("DROP TABLE IF EXISTS curves")

    print("🔧 Creating new curves table...")
    # New curves table: physical road elements
    cursor.execute("""
        CREATE TABLE curves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            curve_id TEXT NOT NULL UNIQUE,
            centerline_geojson TEXT NOT NULL,
            midpoint_lat REAL NOT NULL,
            midpoint_lon REAL NOT NULL,
            curve_radius_ft REAL,
            deviation_angle_deg REAL
        )
    """)

    print("🔧 Creating recording_curves table...")
    # Specific data for a recording on a curve
    cursor.execute("""
        CREATE TABLE recording_curves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recording_id TEXT NOT NULL,
            curve_id INTEGER NOT NULL,
            advisory_speed_mph REAL,
            max_superelevation REAL,
            midpoint_superelevation REAL,
            gps_points TEXT NOT NULL,
            bbi_series TEXT NOT NULL,
            speed_series TEXT NOT NULL,
            superelevation_series TEXT NOT NULL,
            advisory_speed_series TEXT NOT NULL,
            FOREIGN KEY (recording_id) REFERENCES recordings(id) ON DELETE CASCADE,
            FOREIGN KEY (curve_id) REFERENCES curves(id) ON DELETE CASCADE,
            UNIQUE(recording_id, curve_id)
        )
    """)

    print("🔧 Creating indexes...")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_curves_curve_id ON curves(curve_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_recording_curves_recording_id ON recording_curves(recording_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_recording_curves_curve_id ON recording_curves(curve_id)")

    conn.commit()
    conn.close()

    print("✅ Migration completed successfully!")


if __name__ == "__main__":
    migrate()

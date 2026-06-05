"""
Migration: Add curve_recordings table and update recording_curves link (v3.1)

This migration:
1. Drops existing curve-related tables.
2. Creates curve_recordings table (WITH organization_id).
3. Creates curves table.
4. Creates recording_curves table linking both.

Usage:
    python migrations/sign_app/update_curves_v3.py
"""

import sqlite3
import os


def get_db_path():
    """Get database path based on environment (EC2 vs local)"""
    if os.path.exists("/home/ec2-user"):
        return "/home/ec2-user/app.db"
    else:
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(base_path, "app.db")


def migrate():
    """Run the migration"""
    db_path = get_db_path()
    print(f"📍 Database path: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("🗑️ Dropping old curve tables...")
    cursor.execute("DROP TABLE IF EXISTS recording_curves")
    cursor.execute("DROP TABLE IF EXISTS curves")
    cursor.execute("DROP TABLE IF EXISTS curve_recordings")

    print("🔧 Creating curve_recordings table...")
    cursor.execute("""
        CREATE TABLE curve_recordings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recording_id TEXT NOT NULL UNIQUE,
            organization_id INTEGER NOT NULL,
            device_id TEXT NOT NULL,
            imei_folder TEXT NOT NULL,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
        )
    """)

    print("🔧 Creating curves table...")
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
    cursor.execute("""
        CREATE TABLE recording_curves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recording_id INTEGER NOT NULL,
            curve_id INTEGER NOT NULL,
            advisory_speed_mph REAL,
            max_superelevation REAL,
            midpoint_superelevation REAL,
            gps_points TEXT NOT NULL,
            bbi_series TEXT NOT NULL,
            speed_series TEXT NOT NULL,
            superelevation_series TEXT NOT NULL,
            advisory_speed_series TEXT NOT NULL,
            FOREIGN KEY (recording_id) REFERENCES curve_recordings(id) ON DELETE CASCADE,
            FOREIGN KEY (curve_id) REFERENCES curves(id) ON DELETE CASCADE,
            UNIQUE(recording_id, curve_id)
        )
    """)

    print("🔧 Creating indexes...")
    cursor.execute("CREATE INDEX idx_cr_recording_id ON curve_recordings(recording_id)")
    cursor.execute("CREATE INDEX idx_cr_org_id ON curve_recordings(organization_id)")
    cursor.execute("CREATE INDEX idx_curves_cid ON curves(curve_id)")

    conn.commit()
    conn.close()

    print("✅ Migration completed successfully!")


if __name__ == "__main__":
    migrate()

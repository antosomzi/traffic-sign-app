"""Migration: Add user_id to recordings table for user-recording association"""

import os
import sys
import json
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.database import get_db, get_db_path
from config import Config


def parse_recording_date(recording_id):
    """
    Parse recording_id to extract recording date
    Format: '2024_05_20_23_32_53_415' → datetime(2024, 5, 20, 23, 32, 53)
    """
    parts = recording_id.split('_')
    if len(parts) >= 6:
        try:
            return datetime(
                int(parts[0]), int(parts[1]), int(parts[2]),
                int(parts[3]), int(parts[4]), int(parts[5])
            )
        except (ValueError, IndexError):
            return None
    return None


def get_admin_user_id():
    """Get the admin user ID for backfilling existing recordings"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM users WHERE email = ?",
            ("arevel3@gatech.edu",)
        )
        row = cursor.fetchone()
        if row:
            return row['id']
    return None


def upgrade():
    """
    Add user_id and recording_date columns to recordings table.
    Backfill existing recordings to admin user.
    """
    print("🔄 Starting migration: add_user_to_recordings")
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(recordings)")
        columns = [col['name'] for col in cursor.fetchall()]
        
        # Add user_id column if not exists
        if 'user_id' not in columns:
            print("  Adding user_id column...")
            cursor.execute("""
                ALTER TABLE recordings ADD COLUMN user_id INTEGER REFERENCES users(id)
            """)
        else:
            print("  user_id column already exists")
        
        # Add recording_date column if not exists
        if 'recording_date' not in columns:
            print("  Adding recording_date column...")
            cursor.execute("""
                ALTER TABLE recordings ADD COLUMN recording_date TIMESTAMP
            """)
        else:
            print("  recording_date column already exists")
        
        conn.commit()
    
    # Create index for user_id
    with get_db() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_recordings_user_id 
                ON recordings(user_id)
            """)
            print("  Created index on user_id")
        except Exception as e:
            print(f"  Index creation skipped: {e}")
        conn.commit()
    
    # Backfill existing recordings
    backfill_existing_recordings()
    
    print("✅ Migration completed: add_user_to_recordings")


def backfill_existing_recordings():
    """Backfill existing recordings with user_id and recording_date"""
    print("\n🔄 Backfilling existing recordings...")
    
    # Get admin user ID
    admin_user_id = get_admin_user_id()
    if not admin_user_id:
        print("  ⚠️ Admin user (arevel3@gatech.edu) not found. Skipping backfill.")
        return
    
    print(f"  Found admin user ID: {admin_user_id}")
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get all recordings without user_id
        cursor.execute("""
            SELECT id, organization_id FROM recordings WHERE user_id IS NULL
        """)
        recordings = cursor.fetchall()
        
        if not recordings:
            print("  No recordings need backfilling")
            return
        
        print(f"  Found {len(recordings)} recordings to backfill")
        
        for rec in recordings:
            recording_id = rec['id']
            
            # Parse recording date from ID
            recording_date = parse_recording_date(recording_id)
            
            # Update with admin user and parsed date
            cursor.execute("""
                UPDATE recordings 
                SET user_id = ?, recording_date = ?
                WHERE id = ?
            """, (admin_user_id, recording_date, recording_id))
            
            print(f"    ✓ {recording_id} → user_id={admin_user_id}, date={recording_date}")
        
        conn.commit()
    
    print(f"  ✅ Backfilled {len(recordings)} recordings to admin user")


def scan_and_sync_filesystem():
    """
    Scan the recordings folder and ensure all recordings are in the database.
    Useful for syncing filesystem with database after migration.
    """
    print("\n🔍 Scanning filesystem for untracked recordings...")
    
    recordings_root = Config.EXTRACT_FOLDER
    if not os.path.isdir(recordings_root):
        print(f"  Recordings folder not found: {recordings_root}")
        return
    
    admin_user_id = get_admin_user_id()
    if not admin_user_id:
        print("  ⚠️ Admin user not found. Cannot sync untracked recordings.")
        return
    
    # Get admin's organization
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT organization_id FROM users WHERE id = ?", (admin_user_id,))
        row = cursor.fetchone()
        admin_org_id = row['organization_id'] if row else None
    
    if not admin_org_id:
        print("  ⚠️ Could not determine admin's organization")
        return
    
    added_count = 0
    
    for folder_name in os.listdir(recordings_root):
        folder_path = os.path.join(recordings_root, folder_name)
        if not os.path.isdir(folder_path):
            continue
        
        # Check if recording exists in database
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM recordings WHERE id = ?", (folder_name,))
            exists = cursor.fetchone() is not None
        
        if not exists:
            # Read status.json for upload timestamp
            status_file = os.path.join(folder_path, "status.json")
            upload_date = None
            
            if os.path.isfile(status_file):
                try:
                    with open(status_file, 'r') as f:
                        status_data = json.load(f)
                        timestamp = status_data.get('timestamp')
                        if timestamp:
                            upload_date = datetime.fromisoformat(timestamp)
                except Exception:
                    pass
            
            if not upload_date:
                # Fallback to file modification time
                upload_date = datetime.fromtimestamp(os.path.getmtime(folder_path))
            
            # Parse recording date
            recording_date = parse_recording_date(folder_name)
            
            # Insert into database
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO recordings (id, organization_id, user_id, upload_date, recording_date)
                    VALUES (?, ?, ?, ?, ?)
                """, (folder_name, admin_org_id, admin_user_id, upload_date, recording_date))
                conn.commit()
            
            print(f"    + Added: {folder_name}")
            added_count += 1
    
    if added_count > 0:
        print(f"  ✅ Added {added_count} untracked recordings to database")
    else:
        print("  All recordings are already tracked in database")


def downgrade():
    """Remove user_id and recording_date columns (for rollback)"""
    print("🔄 Rolling back migration: add_user_to_recordings")
    print("  ⚠️ SQLite does not support DROP COLUMN directly.")
    print("  To rollback, you would need to recreate the table.")
    print("  This is a no-op for safety.")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Migration: Add user_id to recordings")
    parser.add_argument("--sync-filesystem", action="store_true", 
                       help="Also scan filesystem and add untracked recordings")
    parser.add_argument("--downgrade", action="store_true",
                       help="Rollback migration (limited in SQLite)")
    
    args = parser.parse_args()
    
    if args.downgrade:
        downgrade()
    else:
        upgrade()
        if args.sync_filesystem:
            scan_and_sync_filesystem()

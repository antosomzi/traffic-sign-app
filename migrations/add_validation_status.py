"""
Migration script to add validation_status to existing recordings' status.json files.
Also initializes the signs table if it doesn't exist.

Run this script after updating the codebase to add the validation feature:
    python migrations/add_validation_status.py
"""

import os
import sys
import json
import sqlite3

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from models.database import get_db_path, init_db


def migrate_status_files():
    """
    Add validation_status field to all existing status.json files.
    Sets default value to 'to_be_validated'.
    """
    recordings_root = Config.EXTRACT_FOLDER
    
    if not os.path.isdir(recordings_root):
        print(f"Recordings folder not found: {recordings_root}")
        return 0
    
    updated_count = 0
    skipped_count = 0
    error_count = 0
    
    for rec_id in os.listdir(recordings_root):
        rec_folder = os.path.join(recordings_root, rec_id)
        
        if not os.path.isdir(rec_folder):
            continue
        
        status_file = os.path.join(rec_folder, "status.json")
        
        if not os.path.isfile(status_file):
            print(f"  ⚠️ No status.json found for {rec_id}")
            continue
        
        try:
            with open(status_file, 'r') as f:
                status_data = json.load(f)
            
            # Check if validation_status already exists
            if 'validation_status' in status_data:
                print(f"  ⏭️ {rec_id}: Already has validation_status = {status_data['validation_status']}")
                skipped_count += 1
                continue
            
            # Add validation_status
            status_data['validation_status'] = 'to_be_validated'
            status_data['validated_by'] = None
            status_data['validated_at'] = None
            
            with open(status_file, 'w') as f:
                json.dump(status_data, f, indent=2)
            
            print(f"  ✅ {rec_id}: Added validation_status = to_be_validated")
            updated_count += 1
            
        except json.JSONDecodeError as e:
            print(f"  ❌ {rec_id}: Invalid JSON - {e}")
            error_count += 1
        except Exception as e:
            print(f"  ❌ {rec_id}: Error - {e}")
            error_count += 1
    
    return updated_count, skipped_count, error_count


def create_signs_table():
    """
    Create the signs table if it doesn't exist.
    """
    db_path = get_db_path()
    
    print(f"Creating signs table in: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create signs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recording_id TEXT NOT NULL,
            mutcd_code TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (recording_id) REFERENCES recordings(id) ON DELETE CASCADE
        )
    """)
    
    # Create indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_signs_recording_id 
        ON signs(recording_id)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_signs_mutcd_code 
        ON signs(mutcd_code)
    """)
    
    conn.commit()
    conn.close()
    
    print("✅ Signs table created/verified")


def main():
    print("=" * 60)
    print("Migration: Add Validation Status to Recordings")
    print("=" * 60)
    print()
    
    # Step 1: Create/verify signs table
    print("Step 1: Creating signs table...")
    create_signs_table()
    print()
    
    # Step 2: Migrate status.json files
    print("Step 2: Migrating status.json files...")
    updated, skipped, errors = migrate_status_files()
    print()
    
    # Summary
    print("=" * 60)
    print("Migration Summary:")
    print(f"  ✅ Updated: {updated}")
    print(f"  ⏭️ Skipped (already migrated): {skipped}")
    print(f"  ❌ Errors: {errors}")
    print("=" * 60)
    
    if errors > 0:
        print("\n⚠️ Some recordings had errors. Please check the logs above.")
        return 1
    
    print("\n✅ Migration completed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
Migration script to move recording status from status.json to the database.
Adds new columns to the recordings table and backfills data.
Removes status.json files after successful migration.

Usage:
    python migrations/sign_app/move_status_to_db.py           # Real migration
    python migrations/sign_app/move_status_to_db.py --dry-run # Simulation
"""

import os
import sys
import json
import sqlite3
import argparse
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config import Config
from models.sign_app.database import get_db_path

def migrate(dry_run=False):
    db_path = get_db_path()
    if dry_run:
        print("🔍 [DRY RUN] Simulation of status migration to database")
    else:
        print(f"🚀 [REAL RUN] Migrating database at: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 1. Check/Add new columns
    columns_to_add = [
        ("video_s3_key", "TEXT"),
        ("status", "TEXT DEFAULT 'processing'"),
        ("status_message", "TEXT"),
        ("status_timestamp", "TIMESTAMP"),
        ("camera_folder", "TEXT"),
        ("error_details", "TEXT"),
        ("validation_status", "TEXT DEFAULT 'to_be_validated'"),
        ("validated_by", "INTEGER"),
        ("validated_at", "TIMESTAMP")
    ]
    
    # Get existing columns
    cursor.execute("PRAGMA table_info(recordings)")
    existing_columns = [col[1] for col in cursor.fetchall()]
    
    for col_name, col_type in columns_to_add:
        if col_name in existing_columns:
            print(f"⏭️ Column {col_name} already exists")
        else:
            if dry_run:
                print(f"➕ [DRY RUN] Would add column: {col_name} ({col_type})")
            else:
                try:
                    cursor.execute(f"ALTER TABLE recordings ADD COLUMN {col_name} {col_type}")
                    print(f"✅ Added column: {col_name}")
                except sqlite3.OperationalError as e:
                    print(f"❌ Error adding column {col_name}: {e}")

    if not dry_run:
        conn.commit()
    
    # 2. Backfill from status.json
    recordings_root = Config.EXTRACT_FOLDER
    cursor.execute("SELECT id FROM recordings")
    rows = cursor.fetchall()
    db_recording_ids = [row[0] for row in rows]
    
    updated_count = 0
    deleted_json_count = 0
    
    print(f"\nFound {len(db_recording_ids)} recordings in database.")
    
    for rec_id in db_recording_ids:
        rec_folder = os.path.join(recordings_root, rec_id)
        if not os.path.isdir(rec_folder):
            continue
            
        status_file = os.path.join(rec_folder, "status.json")
        if os.path.exists(status_file):
            try:
                with open(status_file, 'r') as f:
                    data = json.load(f)
                
                status = data.get("status", "completed")
                message = data.get("message", "")
                timestamp_str = data.get("timestamp")
                video_s3_key = data.get("video_s3_key")
                camera_folder = data.get("camera_folder")
                error_details = data.get("error_details")
                validation_status = data.get("validation_status", "to_be_validated")
                validated_by = data.get("validated_by")
                validated_at_str = data.get("validated_at")
                
                # Convert timestamps if possible
                timestamp = None
                if timestamp_str:
                    try:
                        timestamp = datetime.fromisoformat(timestamp_str)
                    except ValueError:
                        timestamp = datetime.now()
                else:
                    timestamp = datetime.now()

                validated_at = None
                if validated_at_str:
                    try:
                        validated_at = datetime.fromisoformat(validated_at_str)
                    except ValueError:
                        pass
                
                if dry_run:
                    print(f"📝 [DRY RUN] Would update DB for {rec_id} (status: {status})")
                    print(f"🗑️ [DRY RUN] Would delete {status_file}")
                else:
                    # Update DB
                    cursor.execute("""
                        UPDATE recordings 
                        SET status = ?, 
                            status_message = ?, 
                            status_timestamp = ?, 
                            video_s3_key = COALESCE(?, video_s3_key), 
                            camera_folder = ?, 
                            error_details = ?, 
                            validation_status = ?, 
                            validated_by = ?, 
                            validated_at = ?
                        WHERE id = ?
                    """, (
                        status, message, timestamp, video_s3_key, camera_folder,
                        json.dumps(error_details) if error_details else None,
                        validation_status, validated_by, validated_at,
                        rec_id
                    ))
                    
                    # Delete status.json
                    os.remove(status_file)
                    print(f"  ✅ Migrated and removed status.json for {rec_id}")
                
                updated_count += 1
                deleted_json_count += 1
                
            except Exception as e:
                print(f"  ❌ Error migrating {rec_id}: {e}")
        else:
            # Fallback for completed recordings without status.json
            supports_csv = os.path.join(rec_folder, "result_pipeline_stable", "s7_export_csv", "supports.csv")
            if os.path.exists(supports_csv):
                 if dry_run:
                     print(f"ℹ️ [DRY RUN] Would mark {rec_id} as completed (found supports.csv)")
                 else:
                     cursor.execute("UPDATE recordings SET status = 'completed' WHERE id = ?", (rec_id,))
                     print(f"  ℹ️ Marked {rec_id} as completed (found supports.csv)")
                 updated_count += 1

    if not dry_run:
        conn.commit()
    conn.close()
    
    print("\n" + "="*40)
    if dry_run:
        print(f"Simulation Summary (DRY RUN):")
        print(f"  Total recordings that would be updated: {updated_count}")
        print(f"  status.json files that would be deleted: {deleted_json_count}")
    else:
        print(f"Migration Summary (REAL RUN):")
        print(f"  Total recordings updated: {updated_count}")
        print(f"  status.json files deleted: {deleted_json_count}")
    print("="*40)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate status.json data to recordings table")
    parser.add_argument("--dry-run", action="store_true", help="Simulate the migration without applying changes")
    args = parser.parse_args()
    
    migrate(dry_run=args.dry_run)

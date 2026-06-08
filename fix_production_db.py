"""
Diagnostic and repair script for recording statuses in the database.
Logs the current state and synchronizes it with the physical files on disk.
"""

import os
import sqlite3
import sys

# Auto-detect environment
if os.path.exists("/home/ec2-user"):
    RECORDINGS_ROOT = "/home/ec2-user/recordings"
    DB_PATH = "/home/ec2-user/app.db"
else:
    # Local development paths
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    RECORDINGS_ROOT = os.path.join(BASE_DIR, "recordings")
    DB_PATH = os.path.join(BASE_DIR, "app.db")

def run_diagnostic_and_fix():
    print("="*60)
    print(f"🔍 DATABASE STATUS DIAGNOSTIC & REPAIR")
    print(f"📂 Recordings Root: {RECORDINGS_ROOT}")
    print(f"🗄️  Database Path: {DB_PATH}")
    print("="*60)

    if not os.path.exists(DB_PATH):
        print(f"❌ Error: Database not found at {DB_PATH}")
        return

    if not os.path.exists(RECORDINGS_ROOT):
        print(f"❌ Error: Recordings folder not found at {RECORDINGS_ROOT}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get all recordings from disk
    folders = [f for f in os.listdir(RECORDINGS_ROOT) if os.path.isdir(os.path.join(RECORDINGS_ROOT, f))]
    print(f"📋 Found {len(folders)} recording folders on disk.\n")

    updated_count = 0
    missing_in_db = 0

    for rec_id in folders:
        rec_folder = os.path.join(RECORDINGS_ROOT, rec_id)
        final_file = os.path.join(rec_folder, "result_pipeline_stable", "s7_export_csv", "supports.csv")
        is_physically_done = os.path.isfile(final_file)

        # Query current DB state
        cursor.execute("SELECT status, validation_status, video_s3_key FROM recordings WHERE id = ?", (rec_id,))
        row = cursor.fetchone()

        if not row:
            print(f"⚠️  {rec_id:30} | NOT IN DATABASE | Disk Done: {is_physically_done}")
            missing_in_db += 1
            continue

        current_status = row['status']
        
        # Log comparison
        status_icon = "✅" if current_status == "completed" else "⏳"
        disk_icon = "✅" if is_physically_done else "❌"
        
        print(f"🔎 {rec_id:30} | DB: {current_status:12} {status_icon} | Disk Done: {str(is_physically_done):5} {disk_icon}")

        # Fix if needed
        if is_physically_done and current_status != "completed":
            print(f"   ⬆️  Repairing: Switching status to 'completed' in DB...")
            cursor.execute(
                "UPDATE recordings SET status = 'completed', status_message = '' WHERE id = ?",
                (rec_id,)
            )
            updated_count += 1
        elif not is_physically_done and current_status == "completed":
            print(f"   ❓ Warning: DB says completed but files are missing on disk!")

    conn.commit()
    
    # Final summary of DB content
    print("\n" + "="*60)
    print("📊 FINAL SUMMARY")
    cursor.execute("SELECT status, count(*) as count FROM recordings GROUP BY status")
    stats = cursor.fetchall()
    for s in stats:
        print(f"   {s['status']:15}: {s['count']} records")
    
    print("-" * 30)
    print(f"✨ Repaired {updated_count} records.")
    print(f"⚠️  {missing_in_db} folders on disk are missing from DB.")
    print("="*60)

    conn.close()

if __name__ == "__main__":
    run_diagnostic_and_fix()

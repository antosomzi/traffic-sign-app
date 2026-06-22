#!/usr/bin/env python3
"""
Migration script to upload existing GPS files from EFS to S3, preserving filenames.
"""

import os
import sys

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config import Config
from services.sign_app.s3_service import S3VideoService
from services.sign_app.download_service import find_gps_files


def migrate_gps_files(dry_run=True):
    """Scan local recordings and upload GPS files to S3, preserving original names."""
    extract_folder = Config.EXTRACT_FOLDER
    s3_service = S3VideoService()
    
    if dry_run:
        print("🧪 MODE DRY RUN ACTIVÉ : Rien ne sera réellement envoyé sur S3.")
    print(f"🚀 Starting GPS migration from {extract_folder}")
    
    if not os.path.exists(extract_folder):
        print(f"❌ Extract folder {extract_folder} does not exist.")
        return

    recording_ids = [d for d in os.listdir(extract_folder) if os.path.isdir(os.path.join(extract_folder, d))]
    print(f"📂 Found {len(recording_ids)} recordings to check.")

    count = 0
    for recording_id in recording_ids:
        recording_path = os.path.join(extract_folder, recording_id)
        
        # Use existing utility to find GPS files correctly nested in the 'location' folder
        gps_files = find_gps_files(recording_path)
        
        if not gps_files:
            continue
            
        prefix = s3_service.get_recording_prefix(recording_id)
        
        # Check if the S3 folder (prefix) exists before uploading
        try:
            response = s3_service.s3_client.list_objects_v2(
                Bucket=s3_service.bucket,
                Prefix=prefix,
                MaxKeys=1
            )
            prefix_exists = 'Contents' in response
        except Exception as e:
            print(f"❌ Error checking S3 for {recording_id}: {e}")
            continue

        if not prefix_exists:
            print(f"⏭️  [SKIPPED] No S3 folder found for {recording_id} (Prefix: {prefix}).")
            continue
        else:
            print(f"📁 [FOUND] S3 folder exists for {recording_id} (Prefix: {prefix}). Proceeding to upload.")
        
        for local_path in gps_files:
            filename = os.path.basename(local_path)
                
            # We preserve the original filename in S3 (flat structure)
            s3_key = f"{prefix}{filename}"
            
            if dry_run:
                print(f"🔍 [DRY RUN] Would upload: {local_path}")
                print(f"             -> S3 Path: s3://{s3_service.bucket}/{s3_key}")
                count += 1
            else:
                print(f"📤 Uploading {filename} from {local_path}")
                print(f"             -> S3 Path: s3://{s3_service.bucket}/{s3_key}")
                try:
                    s3_service.s3_client.upload_file(local_path, s3_service.bucket, s3_key)
                    count += 1
                except Exception as e:
                    print(f"❌ Failed to upload {filename} for {recording_id}: {e}")

    print(f"✅ Migration complete! {count} files uploaded.")


if __name__ == "__main__":
    migrate_gps_files(dry_run=False)

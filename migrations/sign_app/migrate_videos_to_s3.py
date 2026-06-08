#!/usr/bin/env python3
"""
Migration script to upload existing videos from EFS to S3.

This script:
1. Scans all recordings in the EXTRACT_FOLDER
2. For each recording with a local video file:
   - Uploads the video to S3
   - Updates status.json with the S3 key
   - Optionally deletes the local video file

Usage:
    # Dry run (see what would be migrated):
    python migrate_videos_to_s3.py --dry-run

    # Actually migrate (upload to S3, keep local files):
    python migrate_videos_to_s3.py

    # Migrate and delete local videos after upload:
    python migrate_videos_to_s3.py --delete-local
"""

import argparse
import json
import os
import sys

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from models.sign_app.recording import Recording
from services.sign_app.s3_service import S3VideoService, find_video_in_recording


def get_s3_key_from_status(recording_id: str) -> str | None:
    """Check if recording already has an S3 key in the database."""
    recording = Recording.get_by_id(recording_id)
    return recording.video_s3_key if recording else None


def update_status_with_s3_key(recording_id: str, s3_key: str, video_path: str = None, recording_path: str = None) -> bool:
    """Update recording metadata in the database."""
    try:
        camera_folder_relative = None
        if video_path and recording_path:
            camera_folder = os.path.dirname(video_path)
            camera_folder_relative = os.path.relpath(camera_folder, recording_path)
        
        Recording.update_status(
            recording_id,
            video_s3_key=s3_key,
            camera_folder=camera_folder_relative
        )
        return True
    except Exception as e:
        print(f"  ❌ Failed to update database: {e}")
        return False


def migrate_recording(
    s3_service: S3VideoService,
    recording_id: str,
    recording_path: str,
    dry_run: bool = False,
    delete_local: bool = False
) -> dict:
    """
    Migrate a single recording's video to S3.
    
    Returns:
        dict with keys: status ('skipped', 'migrated', 'error'), message, size_mb
    """
    result = {"status": "skipped", "message": "", "size_mb": 0}
    
    # Find local video first
    video_path = find_video_in_recording(recording_path)
    
    # Check if already migrated
    existing_s3_key = get_s3_key_from_status(recording_id)
    if existing_s3_key:
        # Already on S3 - check if camera_folder is missing in the database
        recording = Recording.get_by_id(recording_id)
        needs_camera_folder = recording and not recording.camera_folder
        
        if needs_camera_folder:
            print(f"  🔍 Missing camera_folder for {recording_id}, will add it")
            # Try to find camera folder structure even if video is gone
            camera_folder_path = None
            
            if video_path:
                # Video still exists locally
                camera_folder_path = os.path.dirname(video_path)
                print(f"  📁 Found camera folder from video path: {camera_folder_path}")
            else:
                # Video gone, search for camera folder in structure
                print(f"  🔍 Searching for camera folder in directory structure...")
                for root, dirs, files in os.walk(recording_path):
                    if os.path.basename(root) == "camera":
                        camera_folder_path = root
                        print(f"  ✅ Found camera folder: {camera_folder_path}")
                        break
            
            if camera_folder_path:
                camera_folder_relative = os.path.relpath(camera_folder_path, recording_path)
                
                # Update DB directly
                if update_status_with_s3_key(recording_id, existing_s3_key, video_path, recording_path):
                    result["status"] = "updated"
                    result["message"] = f"Added camera_folder: {camera_folder_relative}"
                    
                    # Delete local file if it exists and requested
                    if video_path and delete_local:
                        size_bytes = os.path.getsize(video_path)
                        result["size_mb"] = size_bytes / (1024 * 1024)
                        os.remove(video_path)
                        result["message"] += f" (deleted local {result['size_mb']:.1f} MB)"
                    
                    return result
                else:
                    result["status"] = "error"
                    result["message"] = f"Failed to update database"
                    return result
            else:
                result["status"] = "error"
                result["message"] = "Could not find camera folder structure"
                return result
        
        # Already on S3 with camera_folder - maybe delete local file?
        if video_path and delete_local:
            size_bytes = os.path.getsize(video_path)
            result["size_mb"] = size_bytes / (1024 * 1024)
            os.remove(video_path)
            result["status"] = "cleaned"
            result["message"] = f"Already on S3, deleted local file ({result['size_mb']:.1f} MB)"
        else:
            result["message"] = f"Already on S3: {existing_s3_key}"
        return result
    
    # No S3 key - check if local video exists
    if not video_path:
        result["message"] = "No video file found"
        return result
    
    # Get file size
    size_bytes = os.path.getsize(video_path)
    size_mb = size_bytes / (1024 * 1024)
    result["size_mb"] = size_mb
    
    if dry_run:
        result["status"] = "would_migrate"
        result["message"] = f"Would upload: {video_path} ({size_mb:.1f} MB)"
        return result
    
    try:
        # Upload to S3
        s3_key = s3_service.upload_video(video_path, recording_id)
        
        # Update DB with S3 key and camera folder
        if update_status_with_s3_key(recording_id, s3_key, video_path, recording_path):
            result["status"] = "migrated"
            result["message"] = f"Uploaded to S3: {s3_key}"
            
            # Delete local if requested
            if delete_local:
                os.remove(video_path)
                result["message"] += " (local deleted)"
        else:
            result["status"] = "error"
            result["message"] = "Upload succeeded but failed to update database"
            
    except Exception as e:
        result["status"] = "error"
        result["message"] = f"Upload failed: {e}"
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Migrate existing videos from EFS to S3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without actually uploading"
    )
    parser.add_argument(
        "--delete-local",
        action="store_true",
        help="Delete local video files after successful S3 upload"
    )
    parser.add_argument(
        "--recording",
        type=str,
        help="Migrate only a specific recording ID"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Video Migration: EFS → S3")
    print("=" * 60)
    print(f"Recordings folder: {Config.EXTRACT_FOLDER}")
    print(f"S3 Bucket: {Config.S3_BUCKET_NAME}")
    print(f"S3 Region: {Config.S3_REGION}")
    print(f"Dry run: {args.dry_run}")
    print(f"Delete local: {args.delete_local}")
    print("=" * 60)
    
    if not os.path.exists(Config.EXTRACT_FOLDER):
        print(f"❌ Recordings folder not found: {Config.EXTRACT_FOLDER}")
        sys.exit(1)
    
    # Get list of recordings
    if args.recording:
        recordings = [args.recording]
        if not os.path.isdir(os.path.join(Config.EXTRACT_FOLDER, args.recording)):
            print(f"❌ Recording not found: {args.recording}")
            sys.exit(1)
    else:
        recordings = [
            d for d in os.listdir(Config.EXTRACT_FOLDER)
            if os.path.isdir(os.path.join(Config.EXTRACT_FOLDER, d))
        ]
    
    print(f"\nFound {len(recordings)} recording(s) to process\n")
    
    # Initialize S3 service (only if not dry run, to avoid boto3 errors locally)
    s3_service = None
    if not args.dry_run:
        try:
            s3_service = S3VideoService()
        except Exception as e:
            print(f"❌ Failed to initialize S3 service: {e}")
            print("   Make sure you're running on EC2 with proper IAM role or have AWS credentials configured")
            sys.exit(1)
    
    # Stats
    stats = {
        "skipped": 0,
        "migrated": 0,
        "would_migrate": 0,
        "error": 0,
        "total_size_mb": 0
    }
    
    for recording_id in sorted(recordings):
        recording_path = os.path.join(Config.EXTRACT_FOLDER, recording_id)
        print(f"📁 {recording_id}")
        
        result = migrate_recording(
            s3_service=s3_service,
            recording_id=recording_id,
            recording_path=recording_path,
            dry_run=args.dry_run,
            delete_local=args.delete_local
        )
        
        status_emoji = {
            "skipped": "⏭️",
            "migrated": "✅",
            "would_migrate": "🔄",
            "cleaned": "🗑️",
            "updated": "📝",
            "error": "❌"
        }.get(result["status"], "❓")
        
        print(f"   {status_emoji} {result['message']}")
        
        stats[result["status"]] = stats.get(result["status"], 0) + 1
        if result["status"] in ["migrated", "would_migrate", "cleaned", "updated"]:
            stats["total_size_mb"] += result["size_mb"]
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    if args.dry_run:
        print(f"Would migrate: {stats['would_migrate']} recording(s)")
        print(f"Total size: {stats['total_size_mb']:.1f} MB ({stats['total_size_mb']/1024:.2f} GB)")
        print(f"Skipped (already on S3 or no video): {stats['skipped']}")
        print("\n💡 Run without --dry-run to actually migrate")
    else:
        print(f"Migrated: {stats['migrated']} recording(s)")
        print(f"Updated (added camera_folder): {stats.get('updated', 0)}")
        print(f"Cleaned (local deleted): {stats.get('cleaned', 0)}")
        print(f"Errors: {stats['error']}")
        print(f"Skipped: {stats['skipped']}")
        print(f"Total size processed: {stats['total_size_mb']:.1f} MB ({stats['total_size_mb']/1024:.2f} GB)")
    
    print("=" * 60)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Test S3 video download manually
"""
import json
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.s3_service import S3VideoService


def test_download(recording_id):
    """Test downloading video from S3 for a recording"""
    
    # Auto-detect environment
    if os.path.exists("/home/ec2-user"):
        base_path = "/home/ec2-user"
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    recording_path = os.path.join(base_path, "recordings", recording_id)
    
    print(f"Testing S3 download for: {recording_id}")
    print(f"Recording path: {recording_path}")
    print("=" * 60)
    
    if not os.path.isdir(recording_path):
        print(f"❌ Recording not found: {recording_path}")
        return
    
    # Read status.json
    status_file = os.path.join(recording_path, "status.json")
    if not os.path.exists(status_file):
        print(f"❌ No status.json found")
        return
    
    with open(status_file, 'r') as f:
        status_data = json.load(f)
    
    print("Current status.json:")
    print(json.dumps(status_data, indent=2))
    print()
    
    s3_key = status_data.get('video_s3_key')
    camera_folder_relative = status_data.get('camera_folder')
    
    if not s3_key:
        print("❌ No video_s3_key in status.json")
        return
    
    if not camera_folder_relative:
        print("❌ No camera_folder in status.json")
        return
    
    print(f"✅ S3 key: {s3_key}")
    print(f"✅ Camera folder: {camera_folder_relative}")
    print()
    
    # Build paths
    camera_folder = os.path.join(recording_path, camera_folder_relative)
    local_video_path = os.path.join(camera_folder, os.path.basename(s3_key))
    
    print(f"Camera folder path: {camera_folder}")
    print(f"Target video path: {local_video_path}")
    print()
    
    # Create folder
    os.makedirs(camera_folder, exist_ok=True)
    print(f"✅ Camera folder created/exists")
    print()
    
    # Download
    print("Starting download...")
    s3_service = S3VideoService()
    success = s3_service.download_video(s3_key, local_video_path)
    
    if success:
        print()
        print("=" * 60)
        print("✅ SUCCESS!")
        print(f"Video downloaded to: {local_video_path}")
        
        if os.path.exists(local_video_path):
            size_mb = os.path.getsize(local_video_path) / (1024 * 1024)
            print(f"File size: {size_mb:.2f} MB")
        
        # List files in camera folder
        print()
        print("Files in camera folder:")
        for f in os.listdir(camera_folder):
            file_path = os.path.join(camera_folder, f)
            if os.path.isfile(file_path):
                size = os.path.getsize(file_path) / (1024 * 1024)
                print(f"  - {f} ({size:.2f} MB)")
    else:
        print()
        print("=" * 60)
        print("❌ FAILED to download video")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_s3_download.py <recording_id>")
        print("Example: python test_s3_download.py 2025_11_19_16_02_58_052")
        sys.exit(1)
    
    recording_id = sys.argv[1]
    test_download(recording_id)

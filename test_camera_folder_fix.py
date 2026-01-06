#!/usr/bin/env python3
"""
Quick test to check if camera_folder detection works for a specific recording
"""
import json
import os
import sys

def test_recording(recording_path):
    """Test if we can find camera folder for a recording"""
    print(f"Testing: {recording_path}")
    print("=" * 60)
    
    # Check status.json
    status_file = os.path.join(recording_path, "status.json")
    if not os.path.exists(status_file):
        print("❌ No status.json found")
        return
    
    with open(status_file, 'r') as f:
        status_data = json.load(f)
    
    print(f"Current status.json content:")
    print(json.dumps(status_data, indent=2))
    print()
    
    has_video_s3_key = 'video_s3_key' in status_data
    has_camera_folder = 'camera_folder' in status_data
    
    print(f"Has video_s3_key: {has_video_s3_key}")
    print(f"Has camera_folder: {has_camera_folder}")
    print()
    
    if has_video_s3_key and not has_camera_folder:
        print("🔍 Need to add camera_folder - searching directory structure...")
        
        # Search for camera folder
        camera_folder_path = None
        for root, dirs, files in os.walk(recording_path):
            if os.path.basename(root) == "camera":
                camera_folder_path = root
                print(f"✅ Found camera folder: {camera_folder_path}")
                break
        
        if camera_folder_path:
            camera_folder_relative = os.path.relpath(camera_folder_path, recording_path)
            print(f"📁 Relative path: {camera_folder_relative}")
            print()
            print("Would update status.json with:")
            status_data['camera_folder'] = camera_folder_relative
            print(json.dumps(status_data, indent=2))
        else:
            print("❌ Could not find camera folder in directory structure")
    else:
        print("✅ Already has camera_folder or doesn't need it")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_camera_folder_fix.py <recording_path>")
        print("Example: python test_camera_folder_fix.py /home/ec2-user/recordings/2024_05_20_23_32_53_415_v2")
        sys.exit(1)
    
    recording_path = sys.argv[1]
    if not os.path.isdir(recording_path):
        print(f"❌ Directory not found: {recording_path}")
        sys.exit(1)
    
    test_recording(recording_path)

"""Service for handling download operations"""

import os
import io
import zipfile
from typing import List, Optional
from flask import abort
from config import Config
from pipeline.post_processing import get_merged_signs_csv_path
from services.route_filtering_service import get_best_signs_csv_path


def get_recording_folder(recording_id: str) -> str:
    """Get and validate the recording folder path."""
    base = Config.EXTRACT_FOLDER
    rec_folder = os.path.join(base, recording_id)
    
    if not os.path.isdir(rec_folder):
        abort(404, description="Recording not found")
    
    return rec_folder


def get_merged_signs_content(rec_folder: str) -> str:
    """Return the best available signs CSV content for a recording.

    Prefers ``signs_merged_filtered.csv`` (route-filtered) when it exists,
    and falls back to ``signs_merged.csv``.
    """
    best_path = get_best_signs_csv_path(rec_folder)
    if not best_path:
        abort(404, description="signs_merged.csv not found. Run: python migrations/generate_merged_signs.py")

    with open(best_path, "r", encoding="utf-8") as f:
        return f.read()


def get_json_file(rec_folder: str) -> str:
    """Get path to JSON result file and validate it exists."""
    json_folder = os.path.join(rec_folder, "result_pipeline_stable", "s6_localization")
    json_file = os.path.join(json_folder, "output.json")
    
    if not os.path.isfile(json_file):
        abort(404, description="Missing output.json (in s6_localization)")
    
    return json_file


def find_gps_files(rec_folder: str) -> List[str]:
    """Find all GPS CSV files in the location folder."""
    gps_files = []
    
    for root, dirs, files in os.walk(rec_folder):
        if "location" in root:
            for f in files:
                if f.endswith(".csv"):
                    gps_files.append(os.path.join(root, f))
    
    return gps_files


def find_video_file(rec_folder: str) -> tuple[Optional[str], bool]:
    """Find the MP4 video file - check local EFS first, then download from S3.
    Returns: (path_to_video, is_temporary)
    """
    # Check local EFS first
    for root, dirs, files in os.walk(rec_folder):
        if "camera" in root:
            for f in files:
                if f.endswith(".mp4"):
                    return os.path.join(root, f), False
    
    # No local video found - check if it's on S3
    status_file = os.path.join(rec_folder, "status.json")
    if os.path.exists(status_file):
        try:
            import json
            with open(status_file, 'r') as f:
                status_data = json.load(f)
            
            s3_key = status_data.get('video_s3_key')
            if s3_key:
                from services.s3_service import S3VideoService, get_camera_folder
                s3_service = S3VideoService()
                
                # Find camera folder for download destination
                camera_folder = get_camera_folder(rec_folder)
                if not camera_folder:
                    # Try to find IMEI folder and create camera subfolder
                    for root, dirs, files in os.walk(rec_folder):
                        if "IMEINotAvailable" in root or root.count(os.sep) - rec_folder.count(os.sep) == 2:
                            camera_folder = os.path.join(root, "camera")
                            os.makedirs(camera_folder, exist_ok=True)
                            break
                
                if camera_folder:
                    local_path = os.path.join(camera_folder, os.path.basename(s3_key))
                    print(f"📥 Downloading video from S3 for download...")
                    if s3_service.download_video(s3_key, local_path):
                        return local_path, True
        except ValueError as ve:
            # Re-raise the ValueError so the route can handle it
            raise ve
        except Exception as e:
            print(f"⚠️ Error downloading video from S3: {e}")
    
    return None, False


def create_csv_only_zip(recording_id: str, rec_folder: str) -> io.BytesIO:
    """Create a ZIP file containing a single merged signs CSV."""
    merged = get_merged_signs_content(rec_folder)

    mem_zip = io.BytesIO()
    with zipfile.ZipFile(mem_zip, "w") as zipf:
        zipf.writestr("signs.csv", merged)

    mem_zip.seek(0)
    return mem_zip


def create_full_results_zip(
    recording_id: str,
    rec_folder: str,
    json_file: str,
    gps_files: List[str],
    video_file_info: tuple[Optional[str], bool]
) -> io.BytesIO:
    """Create a ZIP file containing merged CSV, JSON, GPS data, and video.
    video_file_info is a tuple of (path, is_temporary). If temporary, it will be deleted after zipping.
    """
    merged = get_merged_signs_content(rec_folder)

    mem_zip = io.BytesIO()
    
    with zipfile.ZipFile(mem_zip, "w") as zipf:
        # Add merged signs CSV
        zipf.writestr("signs.csv", merged)
        zipf.write(json_file, arcname=os.path.basename(json_file))
        
        # Add GPS files
        for gps_file in gps_files:
            zipf.write(gps_file, arcname=f"location/{os.path.basename(gps_file)}")
        
        # Add video
        video_file, is_temp = video_file_info
        if video_file and os.path.isfile(video_file):
            zipf.write(video_file, arcname=f"camera/{os.path.basename(video_file)}")
            
            # Auto-cleanup temporary video downloaded from S3
            if is_temp:
                try:
                    os.remove(video_file)
                    print(f"🧹 Cleaned up temporary video file: {video_file}")
                except Exception as e:
                    print(f"⚠️ Failed to clean up temp video: {e}")
    
    mem_zip.seek(0)
    return mem_zip


def create_multi_recordings_csv_zip(recordings_folders: List[tuple]) -> io.BytesIO:
    """Create a ZIP file containing a single merged signs CSV per recording.

    recordings_folders: list of tuples (recording_id, rec_folder_path)
    Each recording will be placed in its own folder inside the ZIP.
    """
    mem_zip = io.BytesIO()

    with zipfile.ZipFile(mem_zip, "w") as zipf:
        for rec_id, rec_folder in recordings_folders:
            merged = get_merged_signs_content(rec_folder)
            zipf.writestr(f"{rec_id}/signs.csv", merged)

    mem_zip.seek(0)
    return mem_zip

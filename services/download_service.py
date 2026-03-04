"""Service for handling download operations"""

import os
import io
import csv
import zipfile
from typing import Tuple, List, Optional
from flask import abort
from config import Config


def get_recording_folder(recording_id: str) -> str:
    """Get and validate the recording folder path."""
    base = Config.EXTRACT_FOLDER
    rec_folder = os.path.join(base, recording_id)
    
    if not os.path.isdir(rec_folder):
        abort(404, description="Recording not found")
    
    return rec_folder


def get_csv_files(rec_folder: str) -> Tuple[str, str]:
    """Get paths to CSV result files and validate they exist."""
    result_folder = os.path.join(rec_folder, "result_pipeline_stable", "s7_export_csv")
    
    if not os.path.isdir(result_folder):
        abort(404, description="Results folder not found")
    
    supports_csv = os.path.join(result_folder, "supports.csv")
    signs_csv = os.path.join(result_folder, "signs.csv")
    
    missing = []
    if not os.path.isfile(supports_csv):
        missing.append("supports.csv")
    if not os.path.isfile(signs_csv):
        missing.append("signs.csv")
    
    if missing:
        abort(404, description=f"Missing CSV files: {', '.join(missing)}")
    
    return supports_csv, signs_csv


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


def find_video_file(rec_folder: str) -> Optional[str]:
    """Find the MP4 video file - check local EFS first, then download from S3."""
    # Check local EFS first
    for root, dirs, files in os.walk(rec_folder):
        if "camera" in root:
            for f in files:
                if f.endswith(".mp4"):
                    return os.path.join(root, f)
    
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
                        return local_path
        except Exception as e:
            print(f"⚠️ Error downloading video from S3: {e}")
    
    return None


def merge_signs_supports_csv(signs_csv: str, supports_csv: str) -> str:
    """Merge signs.csv and supports.csv into a single CSV string.

    Joins signs to supports via Foreign Key → support ID to resolve Longitude/Latitude.

    Output format:
        ID,MUTCD Code,Position on the Support,Height (in),Width (in),Longitude,Latitude
    """
    # Load support coordinates keyed by ID
    support_coords = {}
    if os.path.isfile(supports_csv):
        with open(supports_csv, "r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                sid = row.get("ID", "").strip()
                lon = row.get("Longitude", "").strip()
                lat = row.get("Latitude", "").strip()
                if sid and lon and lat:
                    support_coords[sid] = (lon, lat)

    # Build merged rows
    header = "ID,MUTCD Code,Position on the Support,Height (in),Width (in),Longitude,Latitude"
    rows = [header]

    if os.path.isfile(signs_csv):
        with open(signs_csv, "r", newline="", encoding="utf-8") as f:
            for idx, row in enumerate(csv.DictReader(f)):
                foreign_key = row.get("Foreign Key", "").strip()
                mutcd = row.get("MUTCD Code", "").strip()
                position = row.get("Position on the Support", "1").strip()
                height = row.get("Height (in)", "0").strip()
                width = row.get("Width (in)", "0").strip()

                lon, lat = support_coords.get(foreign_key, ("", ""))
                rows.append(f"{idx},{mutcd},{position},{height},{width},{lon},{lat}")

    return "\n".join(rows)


def create_csv_only_zip(recording_id: str, supports_csv: str, signs_csv: str) -> io.BytesIO:
    """Create a ZIP file containing a single merged signs CSV."""
    merged = merge_signs_supports_csv(signs_csv, supports_csv)

    mem_zip = io.BytesIO()
    with zipfile.ZipFile(mem_zip, "w") as zipf:
        zipf.writestr("signs.csv", merged)

    mem_zip.seek(0)
    return mem_zip


def create_full_results_zip(
    recording_id: str,
    supports_csv: str,
    signs_csv: str,
    json_file: str,
    gps_files: List[str],
    video_file: Optional[str]
) -> io.BytesIO:
    """Create a ZIP file containing merged CSV, JSON, GPS data, and video."""
    merged = merge_signs_supports_csv(signs_csv, supports_csv)

    mem_zip = io.BytesIO()
    
    with zipfile.ZipFile(mem_zip, "w") as zipf:
        # Add merged signs CSV
        zipf.writestr("signs.csv", merged)
        zipf.write(json_file, arcname=os.path.basename(json_file))
        
        # Add GPS files
        for gps_file in gps_files:
            zipf.write(gps_file, arcname=f"location/{os.path.basename(gps_file)}")
        
        # Add video
        if video_file and os.path.isfile(video_file):
            zipf.write(video_file, arcname=f"camera/{os.path.basename(video_file)}")
    
    mem_zip.seek(0)
    return mem_zip


def create_multi_recordings_csv_zip(recordings_csv_pairs: List[tuple]) -> io.BytesIO:
    """Create a ZIP file containing a single merged signs CSV per recording.

    recordings_csv_pairs: list of tuples (recording_id, supports_csv_path, signs_csv_path)
    Each recording will be placed in its own folder inside the ZIP.
    """
    mem_zip = io.BytesIO()

    with zipfile.ZipFile(mem_zip, "w") as zipf:
        for rec_id, supports_csv, signs_csv in recordings_csv_pairs:
            merged = merge_signs_supports_csv(signs_csv, supports_csv)
            zipf.writestr(f"{rec_id}/signs.csv", merged)

    mem_zip.seek(0)
    return mem_zip

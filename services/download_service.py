"""Service for handling download operations"""

import os
import io
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
    """Find the MP4 video file in the camera folder."""
    for root, dirs, files in os.walk(rec_folder):
        if "camera" in root:
            for f in files:
                if f.endswith(".mp4"):
                    return os.path.join(root, f)
    
    return None


def create_csv_only_zip(recording_id: str, supports_csv: str, signs_csv: str) -> io.BytesIO:
    """Create a ZIP file containing only CSV results."""
    mem_zip = io.BytesIO()
    
    with zipfile.ZipFile(mem_zip, "w") as zipf:
        zipf.write(supports_csv, arcname=os.path.basename(supports_csv))
        zipf.write(signs_csv, arcname=os.path.basename(signs_csv))
    
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
    """Create a ZIP file containing CSV results, JSON, GPS data, and video."""
    mem_zip = io.BytesIO()
    
    with zipfile.ZipFile(mem_zip, "w") as zipf:
        # Add result CSVs and JSON
        zipf.write(supports_csv, arcname=os.path.basename(supports_csv))
        zipf.write(signs_csv, arcname=os.path.basename(signs_csv))
        zipf.write(json_file, arcname=os.path.basename(json_file))
        
        # Add GPS files
        for gps_file in gps_files:
            zipf.write(gps_file, arcname=f"location/{os.path.basename(gps_file)}")
        
        # Add video
        if video_file and os.path.isfile(video_file):
            zipf.write(video_file, arcname=f"camera/{os.path.basename(video_file)}")
    
    mem_zip.seek(0)
    return mem_zip

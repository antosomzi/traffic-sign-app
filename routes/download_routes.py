"""Download routes for retrieving processing results"""

from flask import Blueprint, send_file, abort
from flask_login import login_required, current_user
from services.download_service import (
    get_recording_folder,
    get_csv_files,
    get_json_file,
    find_gps_files,
    find_video_file,
    create_csv_only_zip,
    create_full_results_zip
)
from services.organization_service import OrganizationService

download_bp = Blueprint("download", __name__)


@download_bp.route("/download/<recording_id>", methods=["GET"])
@login_required
def download_zip(recording_id):
    """Downloads full results: CSV, JSON, GPS data, and video in a ZIP file."""
    # Check if user can access this recording
    if not OrganizationService.can_access_recording(current_user, recording_id):
        abort(403)
    # Get and validate recording folder
    rec_folder = get_recording_folder(recording_id)
    
    # Get CSV files
    supports_csv, signs_csv = get_csv_files(rec_folder)
    
    # Get JSON file
    json_file = get_json_file(rec_folder)
    
    # Find GPS and video files
    gps_files = find_gps_files(rec_folder)
    video_file = find_video_file(rec_folder)
    
    # Create ZIP file
    zip_filename = f"{recording_id}_results.zip"
    mem_zip = create_full_results_zip(
        recording_id,
        supports_csv,
        signs_csv,
        json_file,
        gps_files,
        video_file
    )
    
    return send_file(mem_zip, as_attachment=True, download_name=zip_filename, mimetype="application/zip")


@download_bp.route("/download/<recording_id>/csv-only", methods=["GET"])
@login_required
def download_csv_only(recording_id):
    """Downloads only the CSV results (supports.csv and signs.csv) in a ZIP file."""
    # Check if user can access this recording
    if not OrganizationService.can_access_recording(current_user, recording_id):
        abort(403)
    # Get and validate recording folder
    rec_folder = get_recording_folder(recording_id)
    
    # Get CSV files
    supports_csv, signs_csv = get_csv_files(rec_folder)
    
    # Create ZIP file with only CSVs
    zip_filename = f"{recording_id}_results_csv_only.zip"
    mem_zip = create_csv_only_zip(recording_id, supports_csv, signs_csv)
    
    return send_file(mem_zip, as_attachment=True, download_name=zip_filename, mimetype="application/zip")

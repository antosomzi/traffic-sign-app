"""Download routes for retrieving processing results"""

from flask import Blueprint, send_file, abort, request
from flask_login import login_required, current_user
from services.download_service import (
    get_recording_folder,
    get_csv_files,
    get_json_file,
    find_gps_files,
    find_video_file,
    create_csv_only_zip,
    create_full_results_zip,
    create_multi_recordings_csv_zip
)
from services.organization_service import OrganizationService
from datetime import datetime

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


@download_bp.route("/download/csv-only-range", methods=["GET"])
@login_required
def download_csv_only_range():
    """Download CSVs for all recordings in the current user's organization
    whose recording_date is between `start` and `end` query parameters.

    Query parameters:
        start: ISO date or datetime string (e.g. 2024-01-01 or 2024-01-01T00:00:00)
        end: ISO date or datetime string
    """
    # Parse query parameters
    start = request.args.get("start")
    end = request.args.get("end")

    if not start or not end:
        abort(400, description="Missing 'start' or 'end' query parameter (ISO date)" )

    # Parse into datetime objects (be permissive: accept date-only or full ISO)
    def _parse_dt(s):
        try:
            return datetime.fromisoformat(s)
        except Exception:
            try:
                return datetime.strptime(s, "%Y-%m-%d")
            except Exception:
                return None

    start_dt = _parse_dt(start)
    end_dt = _parse_dt(end)

    if not start_dt or not end_dt:
        abort(400, description="Invalid date format for 'start' or 'end'. Use YYYY-MM-DD or ISO format.")

    # Ensure start <= end
    if start_dt > end_dt:
        abort(400, description="'start' must be before or equal to 'end'")

    # Get recordings for organization and filter by recording_date
    recordings = OrganizationService.get_recordings_for_organization(current_user.organization_id)

    matched = []
    for rec in recordings:
        if not rec.recording_date:
            continue
        if start_dt <= rec.recording_date <= end_dt:
            # Ensure folder and CSVs exist; get_recording_folder/get_csv_files will abort with 404 if missing
            try:
                rec_folder = get_recording_folder(rec.id)
                supports_csv, signs_csv = get_csv_files(rec_folder)
                matched.append((rec.id, supports_csv, signs_csv))
            except Exception:
                # Skip recordings that lack results instead of failing the whole batch
                continue

    if not matched:
        abort(404, description="No completed recordings with CSV results found in the provided date range.")

    mem_zip = create_multi_recordings_csv_zip(matched)
    zip_filename = f"recordings_csv_{start}_{end}.zip"
    return send_file(mem_zip, as_attachment=True, download_name=zip_filename, mimetype="application/zip")

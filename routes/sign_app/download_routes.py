"""Download routes for retrieving processing results"""

import os
from flask import Blueprint, send_file, abort, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from decorators.auth_decorators import api_key_required
from services.sign_app.download_service import (
    get_recording_folder,
    get_json_file,
    find_gps_files,
    find_video_file,
    get_merged_signs_content,
    create_full_results_zip,
    create_multi_recordings_csv_zip
)
from services.sign_app.organization_service import OrganizationService
from services.sign_app.s3_service import S3VideoService
from models.sign_app.recording import Recording
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
    
    # Get JSON file
    json_file = get_json_file(rec_folder)
    
    # Find GPS and video files (skipped for ZIP to avoid server OOM)
    # The frontend downloads these directly from S3 using presigned URLs
    gps_files = []
    video_file_info = (None, False)
    
    # Create ZIP file (uses pre-merged signs_merged.csv or falls back to runtime merge)
    zip_filename = f"{recording_id}_results.zip"
    mem_zip = create_full_results_zip(
        recording_id,
        rec_folder,
        json_file,
        gps_files,
        video_file_info
    )
    
    return send_file(mem_zip, as_attachment=True, download_name=zip_filename, mimetype="application/zip")


@download_bp.route("/download/<recording_id>/urls", methods=["GET"])
@login_required
def download_presigned_urls(recording_id):
    """Return presigned S3 URLs for video and GPS files.
    
    CSV and JSON are handled by the main download_zip endpoint to avoid memory issues with large files.
    """
    if not OrganizationService.can_access_recording(current_user, recording_id):
        abort(403)

    files = {"video": None, "gps": []}

    recording = Recording.get_by_id(recording_id)
    if recording:
        s3_service = S3VideoService()
        
        # 1. Fetch video URL explicitly from the database field
        # (This is more robust than relying on list_objects_v2 prefix matching)
        if recording.video_s3_key:
            filename = os.path.basename(recording.video_s3_key)
            url = s3_service.generate_presigned_get(recording.video_s3_key, filename=filename)
            if url:
                files["video"] = {"url": url, "filename": filename}
        
        # 2. Fetch GPS CSV files dynamically using list_objects_v2
        prefix = s3_service.get_recording_prefix(recording_id)
        response = s3_service.s3_client.list_objects_v2(Bucket=s3_service.bucket, Prefix=prefix)
        
        for obj in response.get('Contents', []):
            s3_key = obj['Key']
            filename = os.path.basename(s3_key)
            if not filename:
                continue
            
            if filename.lower().endswith(".csv"):
                url = s3_service.generate_presigned_get(s3_key, filename=filename)
                if url:
                    files["gps"].append({"url": url, "filename": filename})

    return jsonify({
        "recording_id": recording_id,
        "files": files
    })


@download_bp.route("/download/<recording_id>/csv-only", methods=["GET"])
@login_required
def download_csv_only(recording_id):
    """Downloads the merged signs CSV (signs + supports joined) as a single file."""
    # Check if user can access this recording
    if not OrganizationService.can_access_recording(current_user, recording_id):
        abort(403)
    # Get and validate recording folder
    rec_folder = get_recording_folder(recording_id)
    
    # Read pre-merged CSV (or merge at runtime for legacy recordings)
    merged = get_merged_signs_content(rec_folder)
    
    from flask import Response
    return Response(
        merged,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="signs_{recording_id}.csv"'}
    )


@download_bp.route("/download/csv-only-range", methods=["GET"])
@api_key_required
def download_csv_only_range():
    """Download CSVs for all recordings in the current user's organization
    whose recording_date is between `start` and `end` query parameters.

    Query parameters:
        start: ISO date or datetime string (e.g. 2024-01-01 or 2024-01-01T00:00:00)
        end: ISO date or datetime string

    Authentication:
        Requires X-API-Key header.
        Example: curl -H "X-API-Key: sk_live_xxx" "https://api.com/download/csv-only-range?start=2024-01-01&end=2024-01-31"
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
            # Ensure folder exists; get_recording_folder will abort with 404 if missing
            try:
                rec_folder = get_recording_folder(rec.id)
                matched.append((rec.id, rec_folder))
            except Exception:
                # Skip recordings that lack results instead of failing the whole batch
                continue

    if not matched:
        abort(404, description="No completed recordings with CSV results found in the provided date range.")

    mem_zip = create_multi_recordings_csv_zip(matched)
    zip_filename = f"recordings_csv_{start}_{end}.zip"
    return send_file(mem_zip, as_attachment=True, download_name=zip_filename, mimetype="application/zip")

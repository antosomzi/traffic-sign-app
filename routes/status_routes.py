"""Status routes for displaying recording processing status"""

import os
import json
from datetime import datetime
from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from decorators.auth_decorators import auth_required
from config import Config
from services.organization_service import OrganizationService
from models.user import User

status_bp = Blueprint("status", __name__)

# Check if we're in local mode (for test features)
IS_LOCAL_MODE = os.getenv("USE_GPU_INSTANCE", "false").lower() != "true"

STEP_NAMES = [
    "s0_detection",
    "s1_small_sign_filter",
    "s2_tracking",
    "s3_small_track_filter",
    "s4_classification",
    "s5_frames_gps_coordinates_extraction",
    "s6_localization",
    "s7_export_csv"
]


def _collect_recordings(organization_id, user_ids=None, sort_by='upload_date', sort_order='desc'):
    """
    Collect recordings for a specific organization with optional filtering and sorting.
    
    Args:
        organization_id: Filter by organization
        user_ids: Optional list of user IDs to filter by
        sort_by: 'upload_date' or 'recording_date'
        sort_order: 'asc' or 'desc'
    """
    recordings_root = Config.EXTRACT_FOLDER

    all_records = []

    if not os.path.isdir(recordings_root):
        return all_records

    # Get recordings from database with filtering and sorting
    recordings = OrganizationService.get_recordings_for_organization(
        organization_id,
        user_ids=user_ids,
        sort_by=sort_by,
        sort_order=sort_order
    )

    for rec in recordings:
        rec_id = rec.id
        rec_folder = os.path.join(recordings_root, rec_id)
        if not os.path.isdir(rec_folder):
            continue

        # Read status.json file
        status_file = os.path.join(rec_folder, "status.json")
        current_status = "validated"
        status_message = ""
        timestamp = None
        error_details = None

        if os.path.isfile(status_file):
            try:
                with open(status_file, "r") as f:
                    status_data = json.load(f)
                    current_status = status_data.get("status", "validated")
                    status_message = status_data.get("message", "")
                    timestamp = status_data.get("timestamp", None)
                    error_details = status_data.get("error_details", None)
            except Exception:
                # Ignore malformed JSON and fall back to defaults
                pass

        # Check if processing outputs exist
        result_root = os.path.join(rec_folder, "result_pipeline_stable")
        has_results = os.path.isdir(result_root)
        step_status = []
        is_completed = False
        show_steps = False

        if has_results:
            final_output = os.path.join(result_root, "s7_export_csv", "supports.csv")
            is_completed = os.path.isfile(final_output)

        # Determine when the current processing run started (status timestamp)
        run_started_at = None
        if current_status == "processing" and timestamp:
            try:
                run_started_at = datetime.fromisoformat(timestamp).timestamp()
            except ValueError:
                run_started_at = None

        # Build step progress when processing
        if current_status == "processing" and has_results:
            show_steps = True
            for step in STEP_NAMES:
                step_folder = os.path.join(result_root, step)

                if step == "s7_export_csv":
                    output_file = os.path.join(step_folder, "supports.csv")
                else:
                    output_file = os.path.join(step_folder, "output.json")

                done_flag = False
                if os.path.isfile(output_file):
                    if run_started_at is None:
                        done_flag = True
                    else:
                        try:
                            done_flag = os.path.getmtime(output_file) >= run_started_at
                        except OSError:
                            done_flag = False

                step_status.append({
                    "name": step,
                    "done": done_flag
                })

        # Determine display status prioritizing the explicit status.json value
        if current_status == "processing":
            display_status = "processing"
            # Only show message if result folder doesn't exist yet
            if has_results:
                display_message = ""
            else:
                display_message = status_message or "Processing in progress..."
        elif current_status == "error":
            display_status = "error"
            display_message = status_message or "Error during processing"
        elif current_status == "completed":
            display_status = "completed"
            display_message = ""
        elif current_status == "validated":
            display_status = "validated"
            display_message = status_message or "Awaiting processing"
        else:
            # Fallback to inferred completion when status.json is missing or unexpected
            if is_completed:
                display_status = "completed"
                display_message = ""
            else:
                display_status = current_status or "validated"
                display_message = status_message or "Awaiting processing"

        all_records.append({
            "id": rec_id,
            "status": display_status,
            "message": display_message,
            "timestamp": timestamp,
            "show_steps": show_steps,
            "steps": step_status if show_steps else None,
            "error_details": error_details,
            "user_id": rec.user_id,
            "uploader_name": rec.uploader_name,
            "upload_date": rec.upload_date.isoformat() if rec.upload_date else None,
            "recording_date": rec.recording_date.isoformat() if rec.recording_date else None
        })

    # Sorting is already handled by database query, no need to sort here

    return all_records


@status_bp.route("/status", methods=["GET"])
@login_required
def list_recordings():
    """Lists all recordings and their processing status for current user's organization."""
    # Parse query params for filtering/sorting (support both user_id and user_ids)
    user_ids = request.args.getlist('user_ids', type=int) or request.args.getlist('user_id', type=int) or None
    sort_by = request.args.get('sort_by', 'upload_date')
    sort_order = request.args.get('sort_order', 'desc')
    
    records = _collect_recordings(
        current_user.organization_id,
        user_ids=user_ids,
        sort_by=sort_by,
        sort_order=sort_order
    )
    
    # Get users in organization for filter dropdown
    org_users = User.get_by_organization(current_user.organization_id)
    
    return render_template(
        "status.html",
        recordings=records,
        step_names=STEP_NAMES,
        is_local_mode=IS_LOCAL_MODE,
        org_users=org_users,
        current_filters={
            'user_ids': user_ids or [],
            'sort_by': sort_by,
            'sort_order': sort_order
        }
    )


@status_bp.route("/status/data", methods=["GET"])
@login_required
def status_data():
    """Returns the recording status data as JSON for AJAX polling."""
    # Parse query params for filtering/sorting (support both user_id and user_ids)
    user_ids = request.args.getlist('user_ids', type=int) or request.args.getlist('user_id', type=int) or None
    sort_by = request.args.get('sort_by', 'upload_date')
    sort_order = request.args.get('sort_order', 'desc')
    
    records = _collect_recordings(
        current_user.organization_id,
        user_ids=user_ids,
        sort_by=sort_by,
        sort_order=sort_order
    )
    return jsonify({"recordings": records})


@status_bp.route("/status/users", methods=["GET"])
@login_required
def get_organization_users():
    """Returns users in current user's organization for filter dropdown."""
    org_users = User.get_by_organization(current_user.organization_id)
    return jsonify({
        "users": [{"id": u.id, "name": u.name} for u in org_users]
    })

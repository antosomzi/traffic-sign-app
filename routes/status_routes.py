"""Status routes for displaying recording processing status"""

import os
import json
from datetime import datetime
from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from decorators.auth_decorators import auth_required
from config import Config
from services.organization_service import OrganizationService
from services.signs_service import import_signs_for_recording, delete_signs_for_recording
from models.user import User
from models.model_history import ModelHistory
from models.recording import Recording

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


def _collect_recordings(organization_id, user_ids=None, model_history_ids=None, sort_by='upload_date', sort_order='desc'):
    """
    Collect recordings for a specific organization with optional filtering and sorting.
    """
    recordings_root = Config.EXTRACT_FOLDER
    all_records = []

    if not os.path.isdir(recordings_root):
        return all_records

    # Get recordings from database with filtering and sorting
    recordings = OrganizationService.get_recordings_for_organization(
        organization_id,
        user_ids=user_ids,
        model_history_ids=model_history_ids,
        sort_by=sort_by,
        sort_order=sort_order
    )

    for rec in recordings:
        rec_id = rec.id
        rec_folder = os.path.join(recordings_root, rec_id)
        
        if not os.path.isdir(rec_folder):
            continue

        # 1. Read status.json file 
        status_file = os.path.join(rec_folder, "status.json")
        current_status = "validated"
        status_message = ""
        timestamp = None
        error_details = None
        validation_status = "to_be_validated"

        if os.path.isfile(status_file):
            try:
                with open(status_file, "r") as f:
                    status_data = json.load(f)
                    current_status = status_data.get("status", "validated")
                    status_message = status_data.get("message", "")
                    timestamp = status_data.get("timestamp", None)
                    error_details = status_data.get("error_details", None)
                    validation_status = status_data.get("validation_status", "to_be_validated")
            except Exception:
                pass
        display_status = current_status
        display_message = status_message
        show_steps = False
        step_status = []

        if current_status == "processing":
            result_root = os.path.join(rec_folder, "result_pipeline_stable")
            
            if not os.path.isdir(result_root):
                display_message = status_message or "Processing in progress..."
            else:
                display_message = ""
                show_steps = True
                
                for step in STEP_NAMES:
                    filename = "supports.csv" if step == "s7_export_csv" else "output.json"
                    output_file = os.path.join(result_root, step, filename)
                    
                    step_status.append({
                        "name": step,
                        "done": os.path.isfile(output_file)
                    })

        elif current_status == "error":
            display_message = status_message or "Error during processing"
            
        elif current_status == "completed":
            display_message = ""
            
        elif current_status == "validated":
            display_message = status_message or "Awaiting processing"
            
        else:
            # Fallback de secours (Seulement si le statut est bizarre)
            result_root = os.path.join(rec_folder, "result_pipeline_stable")
            final_output = os.path.join(result_root, "s7_export_csv", "supports.csv")
            
            if os.path.isfile(final_output):
                display_status = "completed"
                display_message = ""
            else:
                display_status = current_status or "validated"
                display_message = status_message or "Awaiting processing"

        # 3. Ajout à la liste
        all_records.append({
            "id": rec_id,
            "status": display_status,
            "message": display_message,
            "timestamp": timestamp,
            "show_steps": show_steps,
            "steps": step_status if show_steps else None,
            "error_details": error_details,
            "validation_status": validation_status,
            "model_history_name": rec.model_history_name,
            "user_id": rec.user_id,
            "uploader_name": rec.uploader_name,
            "upload_date": rec.upload_date.isoformat() if rec.upload_date else None,
            "recording_date": rec.recording_date.isoformat() if rec.recording_date else None,
            "note": rec.note,
            "model_history_id": rec.model_history_id
        })

    # Sorting is already handled by database query, no need to sort here

    return all_records

@status_bp.route("/status", methods=["GET"])
@login_required
def list_recordings():
    """Lists all recordings and their processing status for current user's organization."""
    # Parse query params for filtering/sorting (support both user_id and user_ids)
    user_ids = request.args.getlist('user_ids', type=int) or request.args.getlist('user_id', type=int) or None
    model_ids = request.args.getlist('model_ids', type=int) or None
    sort_by = request.args.get('sort_by', 'upload_date')
    sort_order = request.args.get('sort_order', 'desc')
    
    records = _collect_recordings(
        current_user.organization_id,
        user_ids=user_ids,
        model_history_ids=model_ids,
        sort_by=sort_by,
        sort_order=sort_order
    )
    
    # Get users in organization for filter dropdown
    org_users = User.get_by_organization(current_user.organization_id)
    model_histories=ModelHistory.get_all_model_history()
    return render_template(
        "status.html",
        recordings=records,
        step_names=STEP_NAMES,
        is_local_mode=IS_LOCAL_MODE,
        org_users=org_users,
        model_histories=model_histories,
        current_filters={
            'user_ids': user_ids or [],
            'model_ids': model_ids or [],
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
    model_ids = request.args.getlist('model_ids', type=int) or None
    sort_by = request.args.get('sort_by', 'upload_date')
    sort_order = request.args.get('sort_order', 'desc')
    
    records = _collect_recordings(
        current_user.organization_id,
        user_ids=user_ids,
        model_history_ids=model_ids,
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


@status_bp.route("/api/recording/<recording_id>/validate", methods=["POST"])
@login_required
def toggle_validation(recording_id):
    """
    Toggle the validation status of a recording.
    
    Request body (JSON):
        - validated: boolean (true to validate, false to unvalidate)
    
    Returns:
        JSON with validation_status and signs_count
    """
    # Check recording exists and belongs to user's organization
    recording = Recording.get_by_id(recording_id)
    if not recording:
        return jsonify({"error": "Recording not found"}), 404
    
    if recording.organization_id != current_user.organization_id:
        return jsonify({"error": "Access denied"}), 403
    
    # Parse request body
    data = request.get_json() or {}
    validated = data.get('validated', True)
    
    # Check that recording is completed before allowing validation
    rec_folder = os.path.join(Config.EXTRACT_FOLDER, recording_id)
    status_file = os.path.join(rec_folder, "status.json")
    
    if not os.path.isfile(status_file):
        return jsonify({"error": "Recording status not found"}), 404
    
    try:
        with open(status_file, "r") as f:
            status_data = json.load(f)
    except Exception as e:
        return jsonify({"error": f"Failed to read status: {str(e)}"}), 500
    
    # Check if pipeline is completed
    current_status = status_data.get("status", "")
    if current_status != "completed":
        return jsonify({
            "error": "Only completed recordings can be validated",
            "current_status": current_status
        }), 400
    
    # Update validation status
    new_validation_status = "validated" if validated else "to_be_validated"
    status_data["validation_status"] = new_validation_status
    status_data["validated_by"] = current_user.id if validated else None
    status_data["validated_at"] = datetime.now().isoformat() if validated else None
    
    try:
        with open(status_file, "w") as f:
            json.dump(status_data, f, indent=2)
    except Exception as e:
        return jsonify({"error": f"Failed to save status: {str(e)}"}), 500
    
    # Import or delete signs based on validation status
    signs_count = 0
    if validated:
        # Import signs from CSV to database
        signs_count = import_signs_for_recording(recording_id)
    else:
        # Delete signs from database when unvalidating
        delete_signs_for_recording(recording_id)
    
    return jsonify({
        "success": True,
        "validation_status": new_validation_status,
        "signs_count": signs_count,
        "recording_id": recording_id
    })

@status_bp.route("/api/recording/<recording_id>/note", methods=["POST"])
@login_required
def update_note(recording_id):
    """
    Update the note for a recording.
    
    Request body (JSON):
        - note: string (the note content)
    Returns:
        JSON with success status and updated note   
    """
    recording= Recording.get_by_id(recording_id)
    if not recording:
        return jsonify({"error": "Recording not found"}), 404
    if recording.organization_id != current_user.organization_id:
        return jsonify({"error": "Access denied"}), 403
    data = request.get_json() or {}
    note = data.get("note", "")
    try:
        recording.update_note(note)
        return jsonify({
            "success": True, 
            "note": note,
            "recording_id": recording_id
        }), 200
    except Exception as e:
        return jsonify({"error": f"Failed to update note: {str(e)}"}), 500


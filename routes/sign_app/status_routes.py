"""Status routes for displaying recording processing status"""

import os
import json
from datetime import datetime
from urllib.parse import urljoin
from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash, abort
import requests
from flask_login import login_required, current_user
from decorators.auth_decorators import auth_required
from config import Config
from services.sign_app.organization_service import OrganizationService
from services.sign_app.signs_service import import_signs_for_recording, delete_signs_for_recording
from models.sign_app.user import User
from models.sign_app.model_history import ModelHistory
from models.sign_app.recording import Recording

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

        # 1. Base DB Status (Default source of truth)
        display_status = rec.status or "validated"
        display_message = rec.status_message or ""
        
        # 2. Systematic step construction (Physical progress)
        step_status = []
        result_root = os.path.join(rec_folder, "result_pipeline_stable")
        
        if os.path.isdir(result_root):
            for step in STEP_NAMES:
                filename = "supports.csv" if step == "s7_export_csv" else "output.json"
                is_done = os.path.isfile(os.path.join(result_root, step, filename))
                step_status.append({"name": step, "done": is_done})
        else:
            # If the results folder doesn't exist yet, all steps are set to False
            step_status = [{"name": step, "done": False} for step in STEP_NAMES]

        # 3. Final status adjustment if DB is not yet updated
        # If DB already says 'completed' or 'error', we trust it and skip disk adjustment
        if display_status in ["validated", "processing"]:
            all_done = all(s["done"] for s in step_status)
            any_done = any(s["done"] for s in step_status)

            if all_done:
                display_status = "completed"
                display_message = "" 
            elif any_done:
                display_status = "processing"
                display_message = display_message or "Processing in progress..."
            else:
                # If DB says processing but no files are found, keep DB status but clarify message
                if display_status == "processing":
                    display_message = display_message or "Pipeline starting..."
                else:
                    display_message = display_message or "Awaiting processing"

        elif display_status == "completed":
            display_message = ""
        
        elif display_status == "error":
            display_message = display_message or "Error during processing"

        # 4. Safe JSON error handling
        error_details = None
        if rec.error_details:
            try:
                error_details = json.loads(rec.error_details)
            except Exception:
                error_details = rec.error_details

        # 5. Build response object
        all_records.append({
            "id": rec_id,
            "status": display_status,
            "message": display_message,
            "timestamp": rec.status_timestamp.isoformat() if rec.status_timestamp else None,
            "show_steps": display_status in ["processing", "error"], # UI decides whether to display
            "steps": step_status,
            "error_details": error_details,
            "validation_status": rec.validation_status or "to_be_validated",
            "model_history_name": rec.model_history_name,
            "user_id": rec.user_id,
            "uploader_name": rec.uploader_name,
            "upload_date": rec.upload_date.isoformat() if rec.upload_date else None,
            "recording_date": rec.recording_date.isoformat() if rec.recording_date else None,
            "note": rec.note,
            "model_history_id": rec.model_history_id
        })

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
    if recording.status != "completed":
        return jsonify({
            "error": "Only completed recordings can be validated",
            "current_status": recording.status
        }), 400
    
    # Update validation status
    new_validation_status = "validated" if validated else "to_be_validated"
    
    Recording.update_status(
        recording_id,
        validation_status=new_validation_status,
        validated_by=current_user.id if validated else None,
        validated_at=datetime.now() if validated else None
    )
    
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

@status_bp.route("/status/qaqc/<recording_id>", methods=["GET"])
@login_required
def qaqc_redirect(recording_id):
    """
    Redirects to the QA/QC external site with the recording data.
    """
    # 1. Check recording exists and belongs to user's organization
    recording = Recording.get_by_id(recording_id)
    if not recording:
        abort(404, description="Recording not found")
    
    if recording.organization_id != current_user.organization_id:
        abort(403, description="Access denied")
        
    # 2. Get output.json path
    rec_folder = os.path.join(Config.EXTRACT_FOLDER, recording_id)

    # Path: result_pipeline_stable/s6_localization/output.json
    output_json_path = os.path.join(
        rec_folder,
        "result_pipeline_stable",
        "s6_localization",
        "output.json",
    )

    if not os.path.exists(output_json_path):
        flash("Results (output.json) not found for this recording. Processing might not be complete.", "warning")
        return redirect(url_for("status.list_recordings"))

    # 3. Read data
    try:
        print(f"[QA/QC] Starting export for recording: {recording_id}")

        with open(output_json_path, "r") as f:
            output_data = json.load(f)

        print(f"[QA/QC] output.json loaded. Type: {type(output_data)}, Keys: {list(output_data.keys()) if isinstance(output_data, dict) else 'Not a dict'}")
        if isinstance(output_data, dict) and "output" in output_data:
            print(f"[QA/QC] 'output' key found. Inner keys: {list(output_data['output'].keys()) if isinstance(output_data['output'], dict) else 'Not a dict'}")
        elif isinstance(output_data, dict):
            print(f"[QA/QC] WARNING: 'output' key NOT found in output_data. Actual keys: {list(output_data.keys())}")

        s3_key = recording.video_s3_key
        print(f"[QA/QC] s3_key: {s3_key}")
        
        # 4. Prepare payload (Match exact QA/QC API format)
        filename = os.path.basename(s3_key) if s3_key else f"{recording_id}_cam.mp4"
        payload = {
            "filename": filename,
            "s3Key": s3_key,
            "outputJson": output_data
        }
        
        print(f"[QA/QC] Payload prepared. Filename: {filename}, s3Key: {s3_key}")
        print(f"[QA/QC] Payload size in bytes (approx): {len(json.dumps(payload))}")
        
        # 5. Call external API
        qaqc_url = "https://qaqc.sci.ce.gatech.edu/api/external/sign-web-app-upload"
        qaqc_base_domain = "https://qaqc.sci.ce.gatech.edu"
        print(f"[QA/QC] Sending POST request to: {qaqc_url}")
        
        # We use a timeout to avoid hanging the app if the external service is down
        response = requests.post(qaqc_url, json=payload, allow_redirects=False, timeout=30)
        
        print(f"[QA/QC] Received response. Status code: {response.status_code}")
        
        # If it returns a redirect (301, 302, 303, 307, 308)
        if response.status_code in [301, 302, 303, 307, 308]:
            redirect_url = response.headers.get("Location")
            if redirect_url:
                # Force absolute URL if relative path is returned
                if not redirect_url.startswith("http"):
                    redirect_url = urljoin(qaqc_base_domain, redirect_url)
                print(f"[QA/QC] Redirecting to: {redirect_url}")
                return redirect(redirect_url)
            else:
                print("[QA/QC] ERROR: Redirect status but no Location header.")
                flash("QA/QC API returned a redirect but no Location header was found.", "danger")
                return redirect(url_for("status.list_recordings"))
        
        # If it returns 200, check if there's a redirect URL in the JSON body
        elif response.status_code == 200:
            print(f"[QA/QC] Response body: {response.text[:200]}")
            try:
                res_data = response.json()
                if isinstance(res_data, dict) and "redirect_url" in res_data:
                    redirect_url = res_data["redirect_url"]
                    # Force absolute URL if relative path is returned
                    if not redirect_url.startswith("http"):
                        redirect_url = urljoin(qaqc_base_domain, redirect_url)
                    print(f"[QA/QC] Redirecting to URL from JSON: {redirect_url}")
                    return redirect(redirect_url)
            except:
                print("[QA/QC] Failed to parse JSON response or 'redirect_url' not found.")
                pass
            flash("Data sent to QA/QC successfully, but no redirect was provided.", "info")
            return redirect(url_for("status.list_recordings"))
            
        else:
            print(f"[QA/QC] ERROR Response body: {response.text[:500]}")
            flash(f"Error from QA/QC API (Status {response.status_code}): {response.text[:100]}", "danger")
            return redirect(url_for("status.list_recordings"))
            
    except requests.exceptions.Timeout:
        print(f"[QA/QC] ERROR: Timeout after 30 seconds.")
        flash("The QA/QC service took too long to respond. Please try again later.", "danger")
        return redirect(url_for("status.list_recordings"))
    except Exception as e:
        print(f"[QA/QC] ERROR exception: {str(e)}")
        flash(f"Error preparing QA/QC request: {str(e)}", "danger")
        return redirect(url_for("status.list_recordings"))


"""Routes for re-running the ML pipeline on an existing recording"""

import json
import os
import shutil
import subprocess
from flask import Blueprint, jsonify, abort
from flask_login import login_required, current_user
from config import Config
from utils.file_utils import create_status_file
from services.organization_service import OrganizationService

try:
    from pipeline.celery_tasks import run_pipeline_task
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False

rerun_bp = Blueprint("rerun", __name__)


@rerun_bp.route("/rerun/<recording_id>", methods=["POST"])
@login_required
def rerun_recording(recording_id: str):
    """Queue the ML pipeline to run again for an existing recording."""
    # Check if user can access this recording
    if not OrganizationService.can_access_recording(current_user, recording_id):
        abort(403)
    recording_path = os.path.join(Config.EXTRACT_FOLDER, recording_id)

    if not os.path.isdir(recording_path):
        return jsonify({
            "success": False,
            "message": "Recording not found."
        }), 404

    # Read current status to tailor response messaging (rerun is allowed even while processing)
    status_file = os.path.join(recording_path, "status.json")
    was_processing = False
    if os.path.exists(status_file):
        try:
            with open(status_file, "r") as handle:
                status_data = json.load(handle)
                was_processing = status_data.get("status") == "processing"
        except Exception:
            pass

    if not CELERY_AVAILABLE:
        return jsonify({
            "success": False,
            "message": "Pipeline queue is unavailable."
        }), 503

    # Delete the existing result_pipeline_stable folder if it exists
    result_folder = os.path.join(recording_path, "result_pipeline_stable")
    if os.path.exists(result_folder):
        try:
            shutil.rmtree(result_folder)
        except PermissionError:
            print(f"[RERUN] Permission denied, attempting sudo chown")
            try:
                subprocess.run(
                    ['/usr/bin/sudo', 'chown', '-R', 'ec2-user:ec2-user', result_folder],
                    check=True,
                    capture_output=True,
                    text=True
                )
                shutil.rmtree(result_folder)
            except Exception as e:
                return jsonify({
                    "success": False,
                    "message": f"Failed to delete old results: {str(e)}"
                }), 500

    # Update status.json to show the recording is queued again
    create_status_file(
        recording_path,
        "processing",
        "Pipeline restart requested. Re-running from step 0..."
    )

    try:
        run_pipeline_task.delay(recording_id)
    except Exception as exc:
        return jsonify({
            "success": False,
            "message": f"Failed to queue pipeline: {exc}"
        }), 500

    return jsonify({
        "success": True,
        "message": "Pipeline re-run has been queued successfully." if not was_processing else "Pipeline restart requested. A fresh run from step 0 has been queued."
    }), 200

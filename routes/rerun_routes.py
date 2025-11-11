"""Routes for re-running the ML pipeline on an existing recording"""

import json
import os
from flask import Blueprint, jsonify
from config import Config
from utils.file_utils import create_status_file

try:
    from tasks import run_pipeline_task
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False

rerun_bp = Blueprint("rerun", __name__)


@rerun_bp.route("/rerun/<recording_id>", methods=["POST"])
def rerun_recording(recording_id: str):
    """Queue the ML pipeline to run again for an existing recording."""
    recording_path = os.path.join(Config.EXTRACT_FOLDER, recording_id)

    if not os.path.isdir(recording_path):
        return jsonify({
            "success": False,
            "message": "Recording not found."
        }), 404

    status_file = os.path.join(recording_path, "status.json")
    previous_status = None
    previous_message = ""

    if os.path.exists(status_file):
        try:
            with open(status_file, "r") as handle:
                status_data = json.load(handle)
                previous_status = status_data.get("status")
                previous_message = status_data.get("message", "")
        except Exception:
            previous_status = None
            previous_message = ""

    if previous_status == "processing":
        return jsonify({
            "success": False,
            "message": "Recording is currently processing."
        }), 400

    if not CELERY_AVAILABLE:
        return jsonify({
            "success": False,
            "message": "Pipeline queue is unavailable."
        }), 503

    # Update status.json to show the recording is queued again
    create_status_file(
        recording_path,
        "validated",
        "Recording re-queued for processing."
    )

    try:
        run_pipeline_task.delay(recording_id)
    except Exception as exc:
        # Restore previous status if queuing fails so the UI stays accurate
        if previous_status:
            create_status_file(recording_path, previous_status, previous_message)
        return jsonify({
            "success": False,
            "message": f"Failed to queue pipeline: {exc}"
        }), 500

    return jsonify({
        "success": True,
        "message": "Pipeline re-run has been queued successfully."
    }), 200

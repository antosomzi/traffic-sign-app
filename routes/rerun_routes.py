"""Routes for re-running the ML pipeline on an existing recording"""

import json
import os
import shutil
import subprocess
from flask import Blueprint, jsonify
from config import Config
from utils.file_utils import create_status_file

try:
    from pipeline.celery_tasks import run_pipeline_task
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

    # Check if currently processing
    status_file = os.path.join(recording_path, "status.json")
    if os.path.exists(status_file):
        try:
            with open(status_file, "r") as handle:
                status_data = json.load(handle)
                if status_data.get("status") == "processing":
                    return jsonify({
                        "success": False,
                        "message": "Recording is currently processing."
                    }), 400
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
        "validated",
        "Recording re-queued for processing."
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
        "message": "Pipeline re-run has been queued successfully."
    }), 200

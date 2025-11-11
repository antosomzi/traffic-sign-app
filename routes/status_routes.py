"""Status routes for displaying recording processing status"""

import os
import json
from datetime import datetime
from flask import Blueprint, render_template, current_app
from config import Config

status_bp = Blueprint("status", __name__)

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


@status_bp.route("/status", methods=["GET"])
def status():
    """Lists all recordings and their processing status."""
    recordings_root = Config.EXTRACT_FOLDER

    all_records = []
    
    if not os.path.isdir(recordings_root):
        return render_template("status.html", recordings=[], step_names=STEP_NAMES)
    
    for rec_id in os.listdir(recordings_root):
        rec_folder = os.path.join(recordings_root, rec_id)
        if not os.path.isdir(rec_folder):
            continue

        # Read status.json file
        status_file = os.path.join(rec_folder, "status.json")
        current_status = "validated"
        status_message = ""
        timestamp = None
        
        if os.path.isfile(status_file):
            try:
                with open(status_file, "r") as f:
                    status_data = json.load(f)
                    current_status = status_data.get("status", "validated")
                    status_message = status_data.get("message", "")
                    timestamp = status_data.get("timestamp", None)
            except:
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
            "steps": step_status if show_steps else None
        })

    # Sort by timestamp (most recent first)
    all_records.sort(key=lambda x: x["timestamp"] or "", reverse=True)

    return render_template(
        "status.html",
        recordings=all_records,
        step_names=STEP_NAMES
    )

"""Testing routes for simulating pipeline errors (local development only)."""

import json
import os
from datetime import datetime
from flask import Blueprint, jsonify

from config import Config

test_bp = Blueprint("test", __name__)

# Only enable test routes in local mode
USE_GPU_INSTANCE = os.getenv("USE_GPU_INSTANCE", "false").lower() == "true"


@test_bp.route("/test/simulate-error/<recording_id>", methods=["POST"])
def simulate_error(recording_id):
    """Simulate a pipeline error for testing (local mode only)."""
    
    # Block if GPU mode is enabled
    if USE_GPU_INSTANCE:
        return jsonify({
            "success": False,
            "message": "Test routes are disabled in GPU mode"
        }), 403
    
    recording_path = os.path.join(Config.EXTRACT_FOLDER, recording_id)
    
    if not os.path.isdir(recording_path):
        return jsonify({
            "success": False,
            "message": f"Recording not found: {recording_id}"
        }), 404
    
    # Simulate a realistic pipeline error with error_details
    status_file = os.path.join(recording_path, "status.json")
    
    error_details = {
        "error_type": "pipeline_execution_failed",
        "exit_code": 1,
        "docker_stderr": "Error: CUDA out of memory. Tried to allocate 2.00 GiB",
        "pipeline_log_tail": """
[2024-11-19 15:30:45] INFO: Starting traffic sign detection...
[2024-11-19 15:30:47] INFO: Loading YOLOv8 model...
[2024-11-19 15:30:52] INFO: Processing video frames...
[2024-11-19 15:31:23] ERROR: RuntimeError: CUDA out of memory
[2024-11-19 15:31:23] ERROR: Tried to allocate 2.00 GiB (GPU 0; 15.75 GiB total capacity)
[2024-11-19 15:31:23] ERROR: Current memory usage: 14.23 GiB
[2024-11-19 15:31:23] ERROR: Stack trace:
[2024-11-19 15:31:23] ERROR:   File "pipeline.py", line 142, in process_video
[2024-11-19 15:31:23] ERROR:   File "detector.py", line 87, in detect_batch
[2024-11-19 15:31:23] FATAL: Pipeline aborted due to CUDA error
        """.strip(),
        "elapsed_seconds": 98,
        "docker_command": "sudo docker run --rm --gpus all -v /data traffic-pipeline:gpu",
        "timestamp": datetime.now().isoformat(),
    }
    
    status_data = {
        "status": "error",
        "message": "Pipeline failed (exit 1)",
        "timestamp": datetime.now().isoformat(),
        "error_details": error_details
    }
    
    try:
        with open(status_file, "w") as f:
            json.dump(status_data, f, indent=2)
        
        return jsonify({
            "success": True,
            "message": f"Simulated error for recording {recording_id}",
            "error_details": error_details
        })
    
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Failed to write error status: {str(e)}"
        }), 500

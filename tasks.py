from celery_app import celery
import subprocess
import os
import time
import json
from gpu_pipeline_runner import start_and_run_pipeline_ssh

# Configuration - Auto-detect environment (EC2 vs local)
if os.path.exists("/home/ec2-user"):
    BASE_PATH = "/home/ec2-user"
else:
    BASE_PATH = os.path.dirname(os.path.abspath(__file__))

RECORDINGS_PATH = os.path.join(BASE_PATH, "recordings")

# Toggle between local execution and GPU instance execution
USE_GPU_INSTANCE = os.getenv("USE_GPU_INSTANCE", "false").lower() == "true"


def update_status(recording_path, status, message=""):
    """Updates the status.json file for a recording."""
    status_file = os.path.join(recording_path, "status.json")
    
    status_data = {
        "status": status,
        "message": message,
        "timestamp": __import__("datetime").datetime.now().isoformat()
    }
    
    with open(status_file, "w") as f:
        json.dump(status_data, f, indent=2)


def run_pipeline_local(recording_id, recording_path):
    """Run pipeline locally on the same instance (original behavior)."""
    result_folder = os.path.join(recording_path, "result_pipeline_stable")
    
    print(f"[LOCAL] Running pipeline locally for: {recording_id}")
    update_status(recording_path, "processing", "ML pipeline in progress (local)...")

    # Script is in the BASE_PATH directory
    pipeline_script = os.path.join(BASE_PATH, "simulate_pipeline.sh")
    cmd = f"bash {pipeline_script} {recording_path}"

    subprocess.run(cmd, shell=True, check=True)

    export_csv = os.path.join(result_folder, "s7_export_csv", "supports.csv")
    
    max_wait = 3600  # 1 hour max
    elapsed = 0
    while not os.path.isfile(export_csv) and elapsed < max_wait:
        time.sleep(10)
        elapsed += 10

    if not os.path.isfile(export_csv):
        # Friendly message for no signs detected (instead of timeout error)
        user_friendly_message = "No traffic signs detected in this recording. The video may not contain any recognizable traffic signs or the recording quality may be insufficient."
        update_status(recording_path, "error", user_friendly_message)
        
        # Raise with technical details for logging
        raise TimeoutError(f"Pipeline timeout - expected output file not found: {export_csv}")

    update_status(recording_path, "completed", "Processing completed successfully.")
    
    return f"Pipeline completed for {recording_id}"


def run_pipeline_gpu(recording_id, recording_path):
    """Run pipeline on a dedicated GPU instance via SSH."""
    # Only handles the GPU/SSH/Docker workflow
    print(f"[GPU-SSH] Launching GPU instance for: {recording_id}")
    update_status(recording_path, "processing", "GPU instance is not ready yet, please wait...")

    success, instance_id, message = start_and_run_pipeline_ssh(recording_id)

    if not success:
        update_status(recording_path, "error", f"GPU pipeline failed: {message}")
        raise Exception(f"GPU pipeline failed: {message}")

    # Wait for NFS cache sync and verify output
    print(f"[VALIDATION] Waiting 60s for NFS cache synchronization (acregmin=3s)...")
    time.sleep(60)

    export_csv = os.path.join(recording_path, "result_pipeline_stable", "s7_export_csv", "supports.csv")
    print(f"[VALIDATION] Checking for output file: {export_csv}")
    
    if not os.path.isfile(export_csv):
        # Friendly message for no signs detected (instead of technical error path)
        user_friendly_message = "No traffic signs detected in this recording. The video may not contain any recognizable traffic signs or the recording quality may be insufficient."
        update_status(recording_path, "error", user_friendly_message)
        
        # Raise with technical details for logging, but user sees friendly message
        raise FileNotFoundError(f"Expected output file not found: {export_csv}")

    print(f"✅ Output file validated")
    update_status(recording_path, "completed", f"Pipeline completed on GPU instance {instance_id}")

    return f"Pipeline completed for {recording_id} on GPU instance {instance_id}"


@celery.task
def run_pipeline_task(recording_id):
    """Runs the ML pipeline on a given recording folder."""
    recording_path = os.path.join(RECORDINGS_PATH, recording_id)

    print(f"[INFO] Starting pipeline for recording: {recording_id}")
    print(f"[INFO] Recording path: {recording_path}")
    print(f"[INFO] GPU mode: {USE_GPU_INSTANCE}")
    
    if not os.path.isdir(recording_path):
        if os.path.isdir(RECORDINGS_PATH):
            available = os.listdir(RECORDINGS_PATH)
            print(f"[DEBUG] Available recordings: {available}")
        raise FileNotFoundError(f"Recording not found: {recording_id}")

    try:
        # Choose execution mode
        if USE_GPU_INSTANCE:
            return run_pipeline_gpu(recording_id, recording_path)
        else:
            return run_pipeline_local(recording_id, recording_path)

    except subprocess.CalledProcessError as e:
        update_status(recording_path, "error", f"Pipeline execution error: {str(e)}")
        raise

    except (FileNotFoundError, TimeoutError) as e:
        # These exceptions already have user-friendly messages written to status.json
        # Don't overwrite them - just log and re-raise
        print(f"[INFO] Expected error handled with user-friendly message: {type(e).__name__}")
        raise

    except Exception as e:
        # Only update status for truly unexpected errors
        update_status(recording_path, "error", f"Unexpected error: {str(e)}")
        raise


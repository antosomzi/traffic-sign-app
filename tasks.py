from celery_app import celery
import subprocess
import os
import time
import json
from ec2_gpu_manager import launch_and_run_pipeline_ssh

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

    # Script is in the app directory
    pipeline_script = os.path.join(BASE_PATH, "app", "simulate_pipeline.sh")
    cmd = f"bash {pipeline_script} {recording_path}"

    subprocess.run(cmd, shell=True, check=True)

    export_csv = os.path.join(result_folder, "s7_export_csv", "supports.csv")
    
    max_wait = 3600  # 1 hour max
    elapsed = 0
    while not os.path.isfile(export_csv) and elapsed < max_wait:
        time.sleep(10)
        elapsed += 10

    if not os.path.isfile(export_csv):
        update_status(recording_path, "error", "Timeout: processing took too long.")
        raise TimeoutError(f"Pipeline timeout for {recording_id}")

    update_status(recording_path, "completed", "Processing completed successfully.")
    
    return f"Pipeline completed for {recording_id}"


def run_pipeline_gpu(recording_id, recording_path):
    """Run pipeline on a dedicated GPU instance via SSH."""
    print(f"[GPU-SSH] Launching GPU instance for: {recording_id}")
    update_status(recording_path, "processing", "Launching GPU instance via SSH...")
    
    # Launch GPU instance and execute pipeline via SSH
    success, instance_id, message = launch_and_run_pipeline_ssh(recording_id)
    
    if not success:
        update_status(recording_path, "error", f"GPU pipeline failed: {message}")
        raise Exception(f"GPU pipeline failed: {message}")
    
    # Verify results
    export_csv = os.path.join(recording_path, "result_pipeline_stable", "s7_export_csv", "supports.csv")
    
    if not os.path.isfile(export_csv):
        update_status(recording_path, "error", "Pipeline completed but output file not found.")
        raise FileNotFoundError(f"Expected output file not found: {export_csv}")
    
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

    except Exception as e:
        update_status(recording_path, "error", f"Unexpected error: {str(e)}")
        raise


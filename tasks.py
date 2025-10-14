from celery_app import celery
import subprocess
import os
import time
import json

# Configuration - Auto-detect environment (EC2 vs local)
if os.path.exists("/home/ec2-user"):
    BASE_PATH = "/home/ec2-user"
else:
    BASE_PATH = os.path.dirname(os.path.abspath(__file__))

RECORDINGS_PATH = os.path.join(BASE_PATH, "recordings")


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


@celery.task
def run_pipeline_task(recording_id):
    """Runs the ML pipeline on a given recording folder."""
    recording_path = os.path.join(RECORDINGS_PATH, recording_id)
    result_folder = os.path.join(recording_path, "result_pipeline_stable")

    print(f"[DEBUG] Looking for recording at: {recording_path}")
    print(f"[DEBUG] RECORDINGS_PATH: {RECORDINGS_PATH}")
    print(f"[DEBUG] Recording ID: {recording_id}")
    
    if not os.path.isdir(recording_path):
        if os.path.isdir(RECORDINGS_PATH):
            available = os.listdir(RECORDINGS_PATH)
            print(f"[DEBUG] Available recordings: {available}")
        raise FileNotFoundError(f"Recording not found: {recording_id}")

    try:
        update_status(recording_path, "processing", "ML pipeline in progress...")

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

    except subprocess.CalledProcessError as e:
        update_status(recording_path, "error", f"Pipeline execution error: {str(e)}")
        raise

    except Exception as e:
        update_status(recording_path, "error", f"Unexpected error: {str(e)}")
        raise


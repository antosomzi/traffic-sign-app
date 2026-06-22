"""Celery tasks for orchestrating the ML pipeline execution."""

import json
import os
import subprocess
import sys
import time

# Ensure app directory is in Python path for imports
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from celery_app import celery
from pipeline.gpu.runner import start_and_run_pipeline_ssh
from pipeline.post_processing import generate_merged_signs_csv
from services.sign_app.confidence import add_confidence_to_merged_signs_csv
from services.sign_app.filtered_output_json import filter_output_json
from services.sign_app.route_filtering_service import filter_signs_by_org_routes
from services.sign_app.s3_service import S3VideoService, get_camera_folder
from models.sign_app.recording import Recording
from utils.file_utils import update_recording_status


# Configuration - Auto-detect environment (EC2 vs local)
if os.path.exists("/home/ec2-user"):
    BASE_PATH = "/home/ec2-user"
else:
    BASE_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RECORDINGS_PATH = os.path.join(BASE_PATH, "recordings")

# Toggle between local execution and GPU instance execution
USE_GPU_INSTANCE = os.getenv("USE_GPU_INSTANCE", "false").lower() == "true"


def prepare_recording_from_s3(recording_id):
    """
    Download all necessary files (video, GPS) from S3 to EFS.
    Preserves original filenames and updates status in DB.
    """
    recording_path = os.path.join(RECORDINGS_PATH, recording_id)
    os.makedirs(recording_path, exist_ok=True)

    update_recording_status(recording_id, "processing", "Downloading files from S3...")

    s3_service = S3VideoService()
    prefix = s3_service.get_recording_prefix(recording_id)

    # Fetch recording from DB to get the saved camera_folder (e.g. device_id/imei/camera)
    recording = Recording.get_by_id(recording_id)
    base_folder_structure = ""
    if recording and recording.camera_folder:
        # Normalize separators just in case
        camera_folder_clean = recording.camera_folder.replace('\\', '/')
        camera_path_parts = camera_folder_clean.split('/')
        if camera_path_parts and camera_path_parts[-1] == "camera":
            base_folder_structure = os.sep.join(camera_path_parts[:-1])
        else:
            base_folder_structure = os.sep.join(camera_path_parts)

    # List objects to find original filenames
    response = s3_service.s3_client.list_objects_v2(Bucket=s3_service.bucket, Prefix=prefix)

    video_path = None
    for obj in response.get('Contents', []):
        s3_key = obj['Key']
        filename = os.path.basename(s3_key)
        if not filename: continue

        # Since files on S3 are flat, we recreate the correct structure based on DB metadata
        if filename.lower().endswith(".mp4"):
            subfolder = "camera"
        else:
            subfolder = "location"

        if base_folder_structure:
            relative_path = os.path.join(base_folder_structure, subfolder, filename)
        else:
            relative_path = os.path.join(subfolder, filename)

        local_path = os.path.join(recording_path, relative_path)
        local_dir = os.path.dirname(local_path)
        os.makedirs(local_dir, exist_ok=True)

        if s3_service.download_file(s3_key, local_path):
            print(f"[S3] Downloaded {filename} to {local_path}")
            if subfolder == "camera":
                video_path = local_path
                # Update DB with the actual S3 key used
                camera_folder_relative = os.path.relpath(local_dir, recording_path)
                Recording.update_status(recording_id, video_s3_key=s3_key, camera_folder=camera_folder_relative)

    return video_path

def cleanup_local_video(video_path):
    """Remove local video after pipeline completes to save EFS space."""
    if video_path and os.path.exists(video_path):
        try:
            os.remove(video_path)
        except Exception:
            pass


def run_pipeline_local(recording_id, recording_path):
    """Run pipeline locally on the same instance (original behavior)."""
    result_folder = os.path.join(recording_path, "result_pipeline_stable")
    local_video_path = None

    def _safe_stream(stream):
        if stream is None:
            return None
        return stream if hasattr(stream, "fileno") else None

    try:
        # Check if recording still exists before starting
        if not os.path.exists(recording_path):
            os.makedirs(recording_path, exist_ok=True)
        
        # Download files from S3
        local_video_path = prepare_recording_from_s3(recording_id)
        
        # Check again after download
        if not os.path.exists(recording_path):
            cleanup_local_video(local_video_path)
            return f"Recording {recording_id} was deleted during video download"
        
        update_recording_status(recording_id, "processing", "ML pipeline in progress (local)...")

        # Script is in the BASE_PATH directory
        pipeline_script = os.path.join(BASE_PATH, "simulate_pipeline.sh")
        subprocess.run(
            ["bash", pipeline_script, recording_path],
            check=True,
            stdout=_safe_stream(getattr(sys, "__stdout__", sys.stdout)),
            stderr=_safe_stream(getattr(sys, "__stderr__", sys.stderr)),
        )

        export_csv = os.path.join(result_folder, "s7_export_csv", "supports.csv")

        max_wait = 3600  # 1 hour max
        elapsed = 0
        while not os.path.isfile(export_csv) and elapsed < max_wait:
            # Check if recording still exists during wait
            if not os.path.exists(recording_path):
                cleanup_local_video(local_video_path)
                return f"Recording {recording_id} was deleted during pipeline execution"
            
            time.sleep(10)
            elapsed += 10

        if not os.path.isfile(export_csv):
            # Cleanup video before raising error
            cleanup_local_video(local_video_path)
            
            # Friendly message for no signs detected (instead of timeout error)
            user_friendly_message = (
                "No traffic signs detected in this recording. The video may not contain any "
                "recognizable traffic signs or the recording quality may be insufficient."
            )
            if os.path.exists(recording_path):
                update_recording_status(recording_id, "error", user_friendly_message)

            # Raise with technical details for logging
            raise TimeoutError(f"Pipeline timeout - expected output file not found: {export_csv}")

        # Post-processing: merge signs.csv + supports.csv into a single file
        generate_merged_signs_csv(recording_path)

        # Route filtering: keep only signs near the org's routes (if routes exist)
        filter_signs_by_org_routes(recording_path, recording_id)

        # Enrich output.json with root-level filtered cluster IDs (if filtered CSV exists)
        filter_output_json(recording_path, recording_id)

        # Cleanup local video after successful pipeline (save EFS space)
        cleanup_local_video(local_video_path)

        if os.path.exists(recording_path):
            update_recording_status(recording_id, "completed", "Processing completed successfully.")

        return f"Pipeline completed for {recording_id}"
    
    except Exception as e:
        # Always cleanup video on any exception
        cleanup_local_video(local_video_path)
        raise


def run_pipeline_gpu(recording_id, recording_path):
    """Run pipeline on a dedicated GPU instance via SSH."""
    local_video_path = None

    try:
        # Check if recording still exists before starting
        if not os.path.exists(recording_path):
            os.makedirs(recording_path, exist_ok=True)
        
        # Download files from S3 to EFS before launching GPU (GPU mounts EFS)
        local_video_path = prepare_recording_from_s3(recording_id)
        
        # Check again after download (user might have deleted during download)
        if not os.path.exists(recording_path):
            cleanup_local_video(local_video_path)
            return f"Recording {recording_id} was deleted during video download"
        
        update_recording_status(recording_id, "processing", "GPU instance is not ready yet, please wait...")

        # start_and_run_pipeline_ssh now returns 4 values: success, instance_id, message, error_details
        result = start_and_run_pipeline_ssh(recording_id)
        success, instance_id, message, error_details = result if len(result) == 4 else (*result, {})

        # Check if recording still exists after pipeline execution
        if not os.path.exists(recording_path):
            cleanup_local_video(local_video_path)
            return f"Recording {recording_id} was deleted during pipeline execution"

        if not success:
            # Cleanup video even on error
            cleanup_local_video(local_video_path)
            
            # Store both user-friendly message and technical error details
            update_recording_status(
                recording_id, 
                "error", 
                f"GPU pipeline failed: {message}",
                error_details=error_details
            )
            return f"GPU pipeline failed: {message}"

        # Wait for NFS cache sync and verify output
        print("[VALIDATION] Waiting 60s for NFS cache synchronization (acregmin=3s)...")
        time.sleep(60)

        # Check if recording still exists after wait
        if not os.path.exists(recording_path):
            cleanup_local_video(local_video_path)
            return f"Recording {recording_id} was deleted during validation wait"

        export_csv = os.path.join(
            recording_path, "result_pipeline_stable", "s7_export_csv", "supports.csv"
        )
        print(f"[VALIDATION] Checking for output file: {export_csv}")

        if not os.path.isfile(export_csv):
            # Cleanup video before raising error
            cleanup_local_video(local_video_path)
            
            # Friendly message for no signs detected (instead of technical error path)
            user_friendly_message = (
                "No traffic signs detected in this recording. The video may not contain any "
                "recognizable traffic signs or the recording quality may be insufficient."
            )
            update_recording_status(recording_id, "error", user_friendly_message)

            # Raise with technical details for logging, but user sees friendly message
            raise FileNotFoundError(f"Expected output file not found: {export_csv}")

        print("✅ Output file validated")
        
        # Post-processing: merge signs.csv + supports.csv into a single file
        generate_merged_signs_csv(recording_path)

        # Route filtering: keep only signs near the org's routes (if routes exist)
        filter_signs_by_org_routes(recording_path, recording_id)

        add_confidence_to_merged_signs_csv(recording_path)

        # Enrich output.json with root-level filtered cluster IDs (if filtered CSV exists)
        filter_output_json(recording_path, recording_id)
        
        # Cleanup local video after successful pipeline (save EFS space)
        cleanup_local_video(local_video_path)
        
        update_recording_status(
            recording_id, "completed", f"Pipeline completed on GPU instance {instance_id}"
        )

        return f"Pipeline completed for {recording_id} on GPU instance {instance_id}"
    
    except Exception as e:
        # Always cleanup video on any exception
        cleanup_local_video(local_video_path)
        raise


@celery.task
def run_pipeline_task(recording_id, job_id=None):
    """Runs the ML pipeline on a given recording folder."""
    recording_path = os.path.join(RECORDINGS_PATH, recording_id)

    print(f"[INFO] Starting pipeline for recording: {recording_id}")

    try:
        # Choose execution mode
        if USE_GPU_INSTANCE:
            return run_pipeline_gpu(recording_id, recording_path)
        else:
            return run_pipeline_local(recording_id, recording_path)

    except subprocess.CalledProcessError as e:
        update_recording_status(recording_id, "error", f"Pipeline execution error: {str(e)}")
        raise

    except (FileNotFoundError, TimeoutError) as e:
        # These exceptions already have user-friendly messages written to the database
        print(f"[INFO] Expected error handled with user-friendly message: {type(e).__name__}")
        raise

    except Exception as e:
        # Only update status for truly unexpected errors
        update_recording_status(recording_id, "error", f"Unexpected error: {str(e)}")
        raise

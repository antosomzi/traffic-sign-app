"""Celery tasks for orchestrating the ML pipeline execution."""

import json
import os
import subprocess
import time

from celery_app import celery
from pipeline.gpu.runner import start_and_run_pipeline_ssh


# Configuration - Auto-detect environment (EC2 vs local)
if os.path.exists("/home/ec2-user"):
    BASE_PATH = "/home/ec2-user"
else:
    BASE_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RECORDINGS_PATH = os.path.join(BASE_PATH, "recordings")

# Toggle between local execution and GPU instance execution
USE_GPU_INSTANCE = os.getenv("USE_GPU_INSTANCE", "false").lower() == "true"


def update_status(recording_path, status, message="", error_details=None):
    """Updates the status.json file for a recording.
    
    Args:
        recording_path: Path to the recording directory
        status: Status string (processing, completed, error)
        message: User-friendly status message
        error_details: Optional dict with technical error details (diagnostics, logs, etc.)
    """
    status_file = os.path.join(recording_path, "status.json")

    # Load existing status to preserve video_s3_key
    existing_data = {}
    if os.path.exists(status_file):
        try:
            with open(status_file, "r") as f:
                existing_data = json.load(f)
        except Exception:
            pass
    
    status_data = {
        "status": status,
        "message": message,
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    }
    
    # Preserve video_s3_key and camera_folder if they exist
    if existing_data.get("video_s3_key"):
        status_data["video_s3_key"] = existing_data["video_s3_key"]
    if existing_data.get("camera_folder"):
        status_data["camera_folder"] = existing_data["camera_folder"]
    
    # Add error_details if provided (for technical debugging)
    if error_details:
        status_data["error_details"] = error_details

    with open(status_file, "w") as f:
        json.dump(status_data, f, indent=2)


def download_video_from_s3(recording_path):
    """Download video from S3 if it was uploaded there.
    
    Args:
        recording_path: Path to the recording directory
        
    Returns:
        Path to local video file or None if no S3 video
    """
    status_file = os.path.join(recording_path, "status.json")
    
    print(f"[S3] 🔍 Checking for S3 video in: {recording_path}", flush=True)
    
    if not os.path.exists(status_file):
        print(f"[S3] ⚠️ Status file not found: {status_file}", flush=True)
        return None
    
    try:
        with open(status_file, 'r') as f:
            status_data = json.load(f)
        
        print(f"[S3] 📄 Status data keys: {list(status_data.keys())}", flush=True)
        
        s3_key = status_data.get('video_s3_key')
        if not s3_key:
            print("[S3] No video_s3_key in status.json, video is on EFS", flush=True)
            return None
        
        print(f"[S3] 🔑 Found S3 key: {s3_key}", flush=True)
        
        # Get camera folder path from status.json
        camera_folder_relative = status_data.get('camera_folder')
        if not camera_folder_relative:
            print("[S3] ⚠️ No camera_folder in status.json, trying to find it...", flush=True)
            # Fallback: try to find camera folder
            from services.s3_service import get_camera_folder
            camera_folder = get_camera_folder(recording_path)
            if not camera_folder:
                print("[S3] ❌ Could not find camera folder", flush=True)
                return None
        else:
            # Use stored path
            camera_folder = os.path.join(recording_path, camera_folder_relative)
            print(f"[S3] 📁 Camera folder: {camera_folder}", flush=True)
        
        # Create camera folder if it doesn't exist
        os.makedirs(camera_folder, exist_ok=True)
        print(f"[S3] ✅ Camera folder created/verified: {camera_folder}", flush=True)
        
        # Import here to avoid circular imports
        from services.s3_service import S3VideoService
        s3_service = S3VideoService()
        
        local_video_path = os.path.join(camera_folder, os.path.basename(s3_key))
        print(f"[S3] 🎯 Target video path: {local_video_path}", flush=True)
        
        # Download from S3
        print(f"[S3] 📥 Downloading video from S3 for pipeline...", flush=True)
        success = s3_service.download_video(s3_key, local_video_path)
        
        if success:
            print(f"[S3] ✅ Video downloaded to {local_video_path}", flush=True)
            # Verify file exists and has size
            if os.path.exists(local_video_path):
                size_mb = os.path.getsize(local_video_path) / (1024 * 1024)
                print(f"[S3] ✅ File verified: {size_mb:.2f} MB", flush=True)
            else:
                print(f"[S3] ❌ File not found after download!", flush=True)
                return None
            return local_video_path
        else:
            print(f"[S3] ❌ Failed to download video", flush=True)
            return None
            
    except Exception as e:
        print(f"[S3] ❌ Error downloading video: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return None


def cleanup_local_video(video_path):
    """Remove local video after pipeline completes to save EFS space.
    
    Args:
        video_path: Path to local video file
    """
    if video_path and os.path.exists(video_path):
        try:
            os.remove(video_path)
            print(f"[S3] 🗑️ Cleaned up temporary video file: {video_path}")
        except Exception as e:
            print(f"[S3] ⚠️ Could not cleanup video file: {e}")


def run_pipeline_local(recording_id, recording_path):
    """Run pipeline locally on the same instance (original behavior)."""
    result_folder = os.path.join(recording_path, "result_pipeline_stable")
    local_video_path = None

    print(f"[LOCAL] Running pipeline locally for: {recording_id}")
    
    # Download video from S3 if needed
    local_video_path = download_video_from_s3(recording_path)
    
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
        # Cleanup video before raising error
        cleanup_local_video(local_video_path)
        
        # Friendly message for no signs detected (instead of timeout error)
        user_friendly_message = (
            "No traffic signs detected in this recording. The video may not contain any "
            "recognizable traffic signs or the recording quality may be insufficient."
        )
        update_status(recording_path, "error", user_friendly_message)

        # Raise with technical details for logging
        raise TimeoutError(f"Pipeline timeout - expected output file not found: {export_csv}")

    # Cleanup local video after successful pipeline (save EFS space)
    cleanup_local_video(local_video_path)

    update_status(recording_path, "completed", "Processing completed successfully.")

    return f"Pipeline completed for {recording_id}"


def run_pipeline_gpu(recording_id, recording_path):
    """Run pipeline on a dedicated GPU instance via SSH."""
    local_video_path = None
    
    # Only handles the GPU/SSH/Docker workflow
    print(f"[GPU-SSH] Launching GPU instance for: {recording_id}", flush=True)
    
    # Download video from S3 to EFS before launching GPU (GPU mounts EFS)
    print(f"[GPU-SSH] Checking for S3 video to download...", flush=True)
    local_video_path = download_video_from_s3(recording_path)
    if local_video_path:
        print(f"[GPU-SSH] ✅ Video downloaded to EFS: {local_video_path}", flush=True)
    else:
        print(f"[GPU-SSH] ℹ️ No S3 video to download (video on EFS or no video_s3_key)", flush=True)
    
    update_status(recording_path, "processing", "GPU instance is not ready yet, please wait...")

    # start_and_run_pipeline_ssh now returns 4 values: success, instance_id, message, error_details
    result = start_and_run_pipeline_ssh(recording_id)
    success, instance_id, message, error_details = result if len(result) == 4 else (*result, {})

    if not success:
        # Cleanup video even on error
        cleanup_local_video(local_video_path)
        
        # Store both user-friendly message and technical error details
        update_status(
            recording_path, 
            "error", 
            f"GPU pipeline failed: {message}",
            error_details=error_details
        )
        # Don't raise - just return to avoid overwriting error_details in exception handler
        return f"GPU pipeline failed: {message}"

    # Wait for NFS cache sync and verify output
    print("[VALIDATION] Waiting 60s for NFS cache synchronization (acregmin=3s)...")
    time.sleep(60)

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
        update_status(recording_path, "error", user_friendly_message)

        # Raise with technical details for logging, but user sees friendly message
        raise FileNotFoundError(f"Expected output file not found: {export_csv}")

    print("✅ Output file validated")
    
    # Cleanup local video after successful pipeline (save EFS space)
    cleanup_local_video(local_video_path)
    
    update_status(
        recording_path, "completed", f"Pipeline completed on GPU instance {instance_id}"
    )

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
        # Don't overwrite them - just re-raise
        print(f"[INFO] Expected error handled with user-friendly message: {type(e).__name__}")
        raise

    except Exception as e:
        # Only update status for truly unexpected errors
        update_status(recording_path, "error", f"Unexpected error: {str(e)}")
        raise

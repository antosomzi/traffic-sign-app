"""Upload routes for handling file uploads and extraction status"""

import os
import time
import uuid
import threading
from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from decorators.auth_decorators import auth_required
from config import Config
from services.sign_app.redis_service import RedisProgressService
from services.sign_app.extraction_service import ExtractionService
from services.sign_app.organization_service import OrganizationService
from services.sign_app.s3_service import S3VideoService
from models.sign_app.recording import Recording
from utils.file_utils import allowed_file, update_recording_status

# Check if Celery is available
try:
    from pipeline.celery_tasks import run_pipeline_task
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    print("⚠️ Celery not available. Pipeline tasks will not be queued.")

upload_bp = Blueprint("upload", __name__)

# Initialize services
extraction_service = ExtractionService()


@upload_bp.route("/upload", methods=["GET"])
@login_required
def index():
    """Render the upload page"""
    return render_template("upload.html")


@upload_bp.route("/upload/init", methods=["POST"])
@auth_required
def init_upload():
    """Initialize S3 upload and return presigned URLs."""
    data = request.json
    recording_id = data.get("recording_id")
    files = data.get("files", [])  # List of filenames like ["video.mp4", "gps.json"]

    if not recording_id:
        return jsonify({"error": "recording_id is required"}), 400
    
    # Check if recording already exists
    if Recording.exists(recording_id):
        return jsonify({"error": f"Recording {recording_id} already exists"}), 400

    s3_service = S3VideoService()
    prefix = s3_service.get_recording_prefix(recording_id)
    
    presigned_urls = {}
    for filename in files:
        s3_key = f"{prefix}{filename}"
        # Determine content type based on extension
        content_type = "application/octet-stream"
        if filename.lower().endswith(".mp4"):
            content_type = "video/mp4"
        elif filename.lower().endswith((".json", ".csv", ".txt")):
            content_type = "application/json" if filename.endswith(".json") else "text/plain"
        
        presigned_data = s3_service.generate_presigned_post(s3_key, content_type=content_type)
        if presigned_data:
            presigned_urls[filename] = presigned_data

    return jsonify({
        "recording_id": recording_id,
        "presigned_urls": presigned_urls
    })


@upload_bp.route("/upload/complete", methods=["POST"])
@auth_required
def complete_upload():
    """Notify server that S3 upload is complete and trigger processing."""
    data = request.json
    recording_id = data.get("recording_id")
    camera_folder = data.get("camera_folder")
    
    if not recording_id:
        return jsonify({"error": "recording_id is required"}), 400

    # Capture organization_id AND user_id
    user_organization_id = current_user.organization_id
    user_id = current_user.id

    # Create recording entry in DB if it doesn't exist
    if not Recording.exists(recording_id):
        Recording.create(
            recording_id=recording_id,
            organization_id=user_organization_id,
            user_id=user_id,
            camera_folder=camera_folder
        )
    else:
        # If the recording already exists, ensure we update its camera_folder
        if camera_folder:
            Recording.update_status(recording_id, camera_folder=camera_folder)
    
    # Initialize Redis progress
    job_id = uuid.uuid4().hex
    initial_progress = {
        "status": "pending",
        "phase": "downloading",
        "progress_percent": 5,
        "recording_id": recording_id
    }
    RedisProgressService.set_extraction_progress(job_id, initial_progress)

    # Trigger Celery task
    if CELERY_AVAILABLE:
        run_pipeline_task.delay(recording_id)
        return jsonify({
            "status": "success",
            "message": "Processing triggered",
            "job_id": job_id,
            "recording_id": recording_id
        })
    else:
        return jsonify({"error": "Celery not available for processing"}), 503


@upload_bp.route("/upload", methods=["POST"])
@auth_required  # Accepts both web session and API token
def upload_recording():
    """Handle file upload and queue extraction"""
    if "file" not in request.files:
        return jsonify({"error": "No file in request"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "Invalid file type. Only ZIP/TAR allowed."}), 400


    job_id = uuid.uuid4().hex
    filename = f"{job_id}_{file.filename}"
    save_path = os.path.join(Config.UPLOAD_FOLDER, filename)



    # Read file content into memory ONCE
    try:
        file_content = file.read()
        print(f"📥 File received: {file.filename}, size: {len(file_content)} bytes")
    except Exception as e:
        return jsonify({"error": f"Failed to read file: {str(e)}"}), 500

    # Check existence du recording through ExtractionService (with bytes)
    exists, zip_top = extraction_service.check_recording_exists(file_content)
    print(f"🔍 ZIP validation - exists: {exists}, zip_top: {zip_top}")
    if exists is None:
        return jsonify({"error": "Uploaded file is not a valid ZIP archive or cannot be inspected."}), 400
    if exists:
        return jsonify({"error": f"Recording with ID '{zip_top}' has already been uploaded."}), 400

    # --- Fin du check existence ---

    # Initialize extraction progress in Redis
    initial_progress = {
        "status": "reading",
        "phase": "reading",
        "progress_percent": 0,
        "total_files": 0,
        "extracted_files": 0,
        "extract_size": None,
        "recording_id": None,
        "error_msg": None,
        "error_details": None
    }
    RedisProgressService.set_extraction_progress(job_id, initial_progress)
    print(f"✅ Redis progress initialized for job_id: {job_id}")

    # Update progress after reading (15%)
    RedisProgressService.update_extraction_progress(job_id, phase="writing", progress_percent=15)

    # Capture organization_id AND user_id BEFORE background thread (current_user won't exist in thread)
    user_organization_id = current_user.organization_id
    user_id = current_user.id
    print(f"👤 Upload by user {user_id} in organization: {user_organization_id}")

    def save_and_extract():
        """Saves file, extracts ZIP, then adds pipeline task to Celery queue"""
        print(f"🧵 Background thread started for job_id: {job_id}")
        prog = RedisProgressService.get_extraction_progress(job_id)
        if not prog:
            print(f"❌ No progress found in Redis for job_id: {job_id}")
            return
            
        try:
            # Write file content to disk
            print(f"💾 Writing file to: {save_path}")
            with open(save_path, 'wb') as f:
                f.write(file_content)
            print(f"✅ File written successfully: {save_path}")
            # Update progress after writing (30% total)
            RedisProgressService.update_extraction_progress(job_id, phase="extracting", progress_percent=30)
        except Exception as e:
            print(f"❌ Save failed for job_id {job_id}: {str(e)}")
            prog["status"] = "error"
            prog["error_msg"] = f"Save failed: {str(e)}"
            RedisProgressService.set_extraction_progress(job_id, prog)
            return
        
        # Extract archive
        print(f"📦 Starting extraction for job_id: {job_id}")
        try:
            recording_id = extraction_service.extract_archive(
                job_id,
                save_path,
                Config.TEMP_EXTRACT_FOLDER,
                Config.EXTRACT_FOLDER
            )
            print(f"📦 Extraction completed. recording_id: {recording_id}")

            # Safety net: if extraction returns None without a final explicit status,
            # force an error to avoid leaving frontend stuck in "preparing".
            if not recording_id:
                print("❌ Extraction returned no recording_id. Ensuring Redis status is error.")
                latest_prog = RedisProgressService.get_extraction_progress(job_id) or {}
                if latest_prog.get("status") != "error":
                    latest_prog["status"] = "error"
                    latest_prog["phase"] = "failed"
                    latest_prog["error_msg"] = (
                        "Invalid archive: please check the folder structure "
                        "(e.g., missing device/IMEI folder)."
                    )
                    RedisProgressService.set_extraction_progress(job_id, latest_prog)
                return
        except Exception as e:
            print(f"❌ Extraction process crashed for job_id {job_id}: {e}")
            latest_prog = RedisProgressService.get_extraction_progress(job_id) or {}
            latest_prog["status"] = "error"
            latest_prog["phase"] = "failed"
            latest_prog["error_msg"] = f"Critical error during extraction: {str(e)}"
            RedisProgressService.set_extraction_progress(job_id, latest_prog)
            return

        # Register recording to organization with user_id
        try:
            OrganizationService.register_recording(recording_id, user_organization_id, user_id=user_id)
            print(f"✅ Recording {recording_id} registered to org {user_organization_id} by user {user_id}")
        except Exception as e:
            print(f"⚠️ Failed to register recording to organization: {e}")
        
        # Queue pipeline task if extraction succeeded
        if CELERY_AVAILABLE:
            time.sleep(0.5)
            try:
                run_pipeline_task.delay(recording_id)
                print(f"✅ Pipeline task queued for: {recording_id}")
            except Exception as e:
                print(f"⚠️ Could not queue pipeline task: {e}")
        else:
            print(f"⚠️ Pipeline not queued. CELERY_AVAILABLE: {CELERY_AVAILABLE}")

    # Start save + extraction in background thread
    thread = threading.Thread(target=save_and_extract, daemon=True)
    thread.start()
    print(f"🚀 Background thread launched for job_id: {job_id}")

    return jsonify({"job_id": job_id}), 200


@upload_bp.route("/extract_status/<job_id>", methods=["GET"])
@login_required
def extract_status(job_id):
    """Get extraction status for a job"""
    prog = RedisProgressService.get_extraction_progress(job_id)
    
    if not prog:
        return jsonify({"error": "Unknown job_id"}), 404

    status = prog["status"]
    phase = prog.get("phase", "")
    progress_percent = prog.get("progress_percent", 0)

    # Error must always win over phase-based UI states to avoid sticky "preparing".
    if status == "error":
        response = {
            "status": "error",
            "message": prog.get("error_msg", "Unknown error")
        }
        if prog.get("error_details"):
            response["details"] = prog["error_details"]
        return jsonify(response), 200

    # Handle reading and writing phases
    if status == "reading":
        return jsonify({
            "status": "preparing",
            "phase": "reading",
            "percent": progress_percent,
            "message": "Reading uploaded file..."
        }), 200
    
    if phase == "writing":
        return jsonify({
            "status": "preparing",
            "phase": "writing",
            "percent": progress_percent,
            "message": "Writing file to disk..."
        }), 200
    
    if phase == "extracting":
        return jsonify({
            "status": "preparing",
            "phase": "extracting",
            "percent": progress_percent,
            "message": "Preparing extraction..."
        }), 200

    if phase == "encoding":
        return jsonify({
            "status": "preparing",
            "phase": "encoding",
            "percent": progress_percent,
            "message": "Encoding video (CFR / semi All-Intra)..."
        }), 200

    if phase == "uploading":
        return jsonify({
            "status": "preparing",
            "phase": "uploading",
            "percent": progress_percent,
            "message": "Uploading encoded video to S3..."
        }), 200

    if status == "running":
        total = prog["total_files"]
        done = prog["extracted_files"]
        # Calculate progress: 30% (reading+writing) + 60% (extraction)
        # Remaining 10% reserved for encoding/uploading/finalization phases
        extraction_percent = (done / total) * 60 if total > 0 else 0
        percent = min(89, 30 + extraction_percent)
        
        return jsonify({
            "status": "running",
            "total_files": total,
            "extracted_files": done,
            "percent": percent
        }), 200

    if status == "done":
        size_bytes = prog.get("extract_size", 0)
        def human_readable(num):
            for unit in ["B", "KB", "MB", "GB", "TB"]:
                if num < 1024:
                    return f"{num:.2f} {unit}"
                num /= 1024
            return f"{num:.2f} PB"

        return jsonify({
            "status": "done",
            "percent": 100,
            "extract_size": human_readable(size_bytes),
            "recording_id": prog.get("recording_id"),
            "message": "Upload validated, pipeline awaiting execution."
        }), 200

    return jsonify({
        "status": "error",
        "message": "Unexpected extraction state",
        "details": {
            "job_id": job_id,
            "raw_status": status,
            "raw_phase": phase
        }
    }), 200

"""Upload routes for handling file uploads and extraction status"""

import os
import time
import uuid
import threading
from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from decorators.auth_decorators import auth_required
from config import Config
from services.redis_service import RedisProgressService
from services.extraction_service import ExtractionService
from services.organization_service import OrganizationService
from utils.file_utils import allowed_file

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

    # Check existence du recording via ExtractionService (with bytes)
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
        recording_id = extraction_service.extract_archive(
            job_id, 
            save_path, 
            Config.TEMP_EXTRACT_FOLDER, 
            Config.EXTRACT_FOLDER
        )
        print(f"📦 Extraction completed. recording_id: {recording_id}")
        
        # Register recording to organization
        if recording_id:
            try:
                OrganizationService.register_recording(recording_id, current_user.organization_id)
                print(f"✅ Recording {recording_id} registered to org {current_user.organization_id}")
            except Exception as e:
                print(f"⚠️ Failed to register recording to organization: {e}")
        
        # Queue pipeline task if extraction succeeded
        if recording_id and CELERY_AVAILABLE:
            time.sleep(0.5)
            try:
                run_pipeline_task.delay(recording_id)
                print(f"✅ Pipeline task queued for: {recording_id}")
            except Exception as e:
                print(f"⚠️ Could not queue pipeline task: {e}")
        else:
            print(f"⚠️ Pipeline not queued. recording_id: {recording_id}, CELERY_AVAILABLE: {CELERY_AVAILABLE}")

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

    if status == "running":
        total = prog["total_files"]
        done = prog["extracted_files"]
        # Calculate progress: 30% (reading+writing) + 70% (extraction)
        extraction_percent = (done / total) * 70 if total > 0 else 0
        percent = 30 + extraction_percent
        
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

    if status == "error":
        response = {
            "status": "error",
            "message": prog.get("error_msg", "Unknown error")
        }
        if prog.get("error_details"):
            response["details"] = prog["error_details"]
        return jsonify(response), 200

    return jsonify({"status": "queued"}), 200

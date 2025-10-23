"""Upload routes for handling file uploads and extraction status"""

import os
import time
import uuid
import threading
from flask import Blueprint, render_template, request, jsonify, current_app
from config import Config
from services.redis_service import RedisProgressService
from services.extraction_service import ExtractionService
from utils.file_utils import allowed_file

# Check if Celery is available
try:
    from tasks import run_pipeline_task
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    print("⚠️ Celery not available. Pipeline tasks will not be queued.")

upload_bp = Blueprint("upload", __name__)

# Initialize services
extraction_service = ExtractionService()


@upload_bp.route("/", methods=["GET"])
def index():
    """Render the upload page"""
    return render_template("upload.html")


@upload_bp.route("/upload", methods=["POST"])
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
    except Exception as e:
        return jsonify({"error": f"Failed to read file: {str(e)}"}), 500

    # Check existence du recording via ExtractionService (with bytes)
    exists, zip_top = extraction_service.check_recording_exists(file_content)
    if exists is None:
        return jsonify({"error": "Uploaded file is not a valid ZIP archive or cannot be inspected."}), 400
    if exists:
        return jsonify({"error": f"Recording with ID '{zip_top}' already exists."}), 400

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

    # Update progress after reading (15%)
    RedisProgressService.update_extraction_progress(job_id, phase="writing", progress_percent=15)

    def save_and_extract():
        """Saves file, extracts ZIP, then adds pipeline task to Celery queue"""
        prog = RedisProgressService.get_extraction_progress(job_id)
        if not prog:
            return
            
        try:
            # Write file content to disk
            with open(save_path, 'wb') as f:
                f.write(file_content)
            # Update progress after writing (30% total)
            RedisProgressService.update_extraction_progress(job_id, phase="extracting", progress_percent=30)
        except Exception as e:
            prog["status"] = "error"
            prog["error_msg"] = f"Save failed: {str(e)}"
            RedisProgressService.set_extraction_progress(job_id, prog)
            return
        
        # Extract archive
        recording_id = extraction_service.extract_archive(
            job_id, 
            save_path, 
            Config.TEMP_EXTRACT_FOLDER, 
            Config.EXTRACT_FOLDER
        )
        
        # Queue pipeline task if extraction succeeded
        if recording_id and CELERY_AVAILABLE:
            time.sleep(0.5)
            try:
                run_pipeline_task.delay(recording_id)
                print(f"✅ Pipeline task queued for: {recording_id}")
            except Exception as e:
                print(f"⚠️ Could not queue pipeline task: {e}")

    # Start save + extraction in background thread
    thread = threading.Thread(target=save_and_extract, daemon=True)
    thread.start()

    return jsonify({"job_id": job_id}), 200


@upload_bp.route("/extract_status/<job_id>", methods=["GET"])
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

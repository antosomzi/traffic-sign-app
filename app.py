import os
import zipfile
import threading
import uuid
import shutil
import time
import json
import redis
from flask import Flask, request, render_template, jsonify, send_file, abort
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

try:
    from tasks import run_pipeline_task
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    print("Warning: Celery not available. Pipeline tasks will not be queued.")

# Redis connection for shared state across Gunicorn workers
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
if REDIS_PASSWORD:
    redis_client = redis.Redis(host='localhost', port=6379, db=0, password=REDIS_PASSWORD, decode_responses=True)
else:
    redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Configuration - Auto-detect environment (EC2 vs local)
if os.path.exists("/home/ec2-user"):
    BASE_PATH = "/home/ec2-user"
else:
    BASE_PATH = os.path.dirname(os.path.abspath(__file__))

UPLOAD_FOLDER      = os.path.join(BASE_PATH, "uploads")
EXTRACT_FOLDER     = os.path.join(BASE_PATH, "recordings")
TEMP_EXTRACT_FOLDER = os.path.join(BASE_PATH, "temp_extracts")
ALLOWED_EXTENSIONS = {"zip", "tar", "tar.gz", "tgz"}
MAX_CONTENT_LENGTH = 8 * 1024 * 1024 * 1024  # 8 GiB

app = Flask(__name__)
app.config["UPLOAD_FOLDER"]       = UPLOAD_FOLDER
app.config["EXTRACT_FOLDER"]      = EXTRACT_FOLDER
app.config["TEMP_EXTRACT_FOLDER"] = TEMP_EXTRACT_FOLDER
app.config["MAX_CONTENT_LENGTH"]  = MAX_CONTENT_LENGTH

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(EXTRACT_FOLDER, exist_ok=True)
os.makedirs(TEMP_EXTRACT_FOLDER, exist_ok=True)

# Helper functions for Redis-backed extraction progress
def get_extraction_progress(job_id):
    """Get extraction progress from Redis"""
    data = redis_client.get(f"extraction:{job_id}")
    if data:
        return json.loads(data)
    return None

def set_extraction_progress(job_id, progress_dict):
    """Set extraction progress in Redis with 1 hour expiry"""
    redis_client.setex(f"extraction:{job_id}", 3600, json.dumps(progress_dict))

def update_extraction_progress(job_id, **kwargs):
    """Update specific fields in extraction progress"""
    prog = get_extraction_progress(job_id)
    if prog:
        prog.update(kwargs)
        set_extraction_progress(job_id, prog)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def compute_folder_size(path):
    total = 0
    for root, _, files in os.walk(path):
        for fname in files:
            fp = os.path.join(root, fname)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total


def validate_structure(root_path, recording_id):
    """
    Validates the complete folder structure and returns detailed errors.
    
    Expected structure:
    root_path/
    └── <device_id>/
        └── <imei_folder>/
            ├─ acceleration/
            │    └ <recording_id>_acc.csv
            ├─ calibration/
            │    └ <timestamp>_calibration.csv (at least 1 file)
            ├─ camera/
            │    └ <recording_id>_cam_<recording_id>.mp4
            │    └ camera_params.csv
            ├─ location/
            │    └ <recording_id>_loc.csv
            │    └ <recording_id>_loc_cleaned.csv
            └─ processed/
                 └ <recording_id>_processed_acc.csv
                 └ <recording_id>_processed_loc.csv
    
    Args:
        root_path: Path to the folder to validate
        recording_id: Root folder name from ZIP (used to validate file names)
    
    Returns: (is_valid: bool, errors: dict)
    """
    errors = {}
    
    entries = os.listdir(root_path)
    devices = [d for d in entries if os.path.isdir(os.path.join(root_path, d))]
    
    if len(devices) == 0:
        errors["device_folder"] = "No device folder found"
        return False, errors
    elif len(devices) > 1:
        errors["device_folder"] = f"Multiple device folders found: {', '.join(devices)}. Only one expected."
        return False, errors
    
    device_folder = devices[0]
    device_path = os.path.join(root_path, device_folder)
    
    subentries = os.listdir(device_path)
    imei_folders = [d for d in subentries if os.path.isdir(os.path.join(device_path, d))]
    
    if len(imei_folders) == 0:
        errors["imei_folder"] = "No IMEI folder found"
        return False, errors
    elif len(imei_folders) > 1:
        errors["imei_folder"] = f"Multiple IMEI folders found: {', '.join(imei_folders)}. Only one expected."
        return False, errors
    
    imei_folder = imei_folders[0]
    imei_path = os.path.join(device_path, imei_folder)
    
    required_subfolders = ["acceleration", "calibration", "camera", "location", "processed"]
    missing_folders = []
    
    for sub in required_subfolders:
        full_sub = os.path.join(imei_path, sub)
        if not os.path.isdir(full_sub):
            missing_folders.append(sub)
    
    if missing_folders:
        errors["missing_folders"] = f"Missing folders: {', '.join(missing_folders)}"
        return False, errors
    
    missing_files = {}
    
    acc_file = f"{recording_id}_acc.csv"
    acc_path = os.path.join(imei_path, "acceleration", acc_file)
    if not os.path.isfile(acc_path):
        missing_files["acceleration"] = [acc_file]
    
    calib_dir = os.path.join(imei_path, "calibration")
    calib_files = [f for f in os.listdir(calib_dir) if f.endswith("_calibration.csv")]
    if not calib_files:
        missing_files["calibration"] = ["At least one *_calibration.csv file required"]
    
    cam_dir = os.path.join(imei_path, "camera")
    video_name = f"{recording_id}_cam_{recording_id}.mp4"
    cam_missing = []
    if video_name not in os.listdir(cam_dir):
        cam_missing.append(video_name)
    if "camera_params.csv" not in os.listdir(cam_dir):
        cam_missing.append("camera_params.csv")
    if cam_missing:
        missing_files["camera"] = cam_missing
    
    loc_dir = os.path.join(imei_path, "location")
    loc_files_needed = [f"{recording_id}_loc.csv", f"{recording_id}_loc_cleaned.csv"]
    loc_missing = [f for f in loc_files_needed if f not in os.listdir(loc_dir)]
    if loc_missing:
        missing_files["location"] = loc_missing
    
    proc_dir = os.path.join(imei_path, "processed")
    proc_files_needed = [f"{recording_id}_processed_acc.csv", f"{recording_id}_processed_loc.csv"]
    proc_missing = [f for f in proc_files_needed if f not in os.listdir(proc_dir)]
    if proc_missing:
        missing_files["processed"] = proc_missing
    
    if missing_files:
        errors["missing_files"] = missing_files
        return False, errors
    
    return True, {}


def create_status_file(recording_path, status, message=""):
    """Creates or updates the status.json file for a recording."""
    import json
    status_file = os.path.join(recording_path, "status.json")
    
    status_data = {
        "status": status,
        "message": message,
        "timestamp": __import__("datetime").datetime.now().isoformat()
    }
    
    with open(status_file, "w") as f:
        json.dump(status_data, f, indent=2)


def clean_macos_files(root_path):
    """Removes macOS system files from extracted folder."""
    for root, dirs, files in os.walk(root_path, topdown=False):
        for fname in files:
            if fname in [".DS_Store", "._.DS_Store"] or fname.startswith("._"):
                file_path = os.path.join(root, fname)
                try:
                    os.remove(file_path)
                except OSError:
                    pass
        
        for dirname in dirs:
            if dirname == "__MACOSX":
                dir_path = os.path.join(root, dirname)
                try:
                    shutil.rmtree(dir_path)
                except OSError:
                    pass


def extract_archive(job_id, zip_path, temp_root, final_root):
    """
    Atomic extraction process:
    1) Extract to temp_root/<job_id>/
    2) Collapse duplicate folders
    3) Validate structure
    4) If valid: move atomically to final_root/<recording_id>/
    5) On error: cleanup everything (ZIP + temp)
    """
    prog = get_extraction_progress(job_id)
    if not prog:
        prog = {
            "status": "error",
            "error_msg": "Job not found"
        }
        set_extraction_progress(job_id, prog)
        return None
        
    temp_extract_path = os.path.join(temp_root, job_id)
    zip_top = None
    final_path = None

    try:
        # Open ZIP and start extraction
        prog["status"] = "running"
        prog["phase"] = "running"  # Clear the "extracting" phase
        set_extraction_progress(job_id, prog)
        
        with zipfile.ZipFile(zip_path, "r") as z:
            members = z.infolist()
            
            # Filter out macOS system files
            members = [m for m in members if not (
                m.filename.startswith("__MACOSX/") or
                "/.DS_Store" in m.filename or
                m.filename == ".DS_Store" or
                m.filename.startswith("._")
            )]
            
            total_files = len(members)
            prog["total_files"] = total_files
            prog["extracted_files"] = 0
            set_extraction_progress(job_id, prog)

            # Identify root folder in ZIP
            top_levels = set()
            for member in members:
                if member.filename.strip("/"):
                    top = member.filename.rstrip("/").split("/")[0]
                    top_levels.add(top)

            if len(top_levels) != 1:
                prog["status"] = "error"
                prog["error_msg"] = "Archive must contain exactly one root folder."
                prog["error_details"] = {"zip_structure": f"Multiple root folders: {', '.join(top_levels)}"}
                set_extraction_progress(job_id, prog)
                return

            zip_top = top_levels.pop()
            os.makedirs(temp_extract_path, exist_ok=True)

            # Extract all files
            for member in members:
                dest_path = os.path.join(temp_extract_path, member.filename)
                
                # ZipSlip protection
                if not os.path.realpath(dest_path).startswith(os.path.realpath(temp_extract_path) + os.sep):
                    prog["status"] = "error"
                    prog["error_msg"] = "Unsafe file path detected in archive."
                    set_extraction_progress(job_id, prog)
                    return

                z.extract(member, temp_extract_path)
                prog["extracted_files"] += 1
                # Update Redis every 10 files for better performance
                if prog["extracted_files"] % 10 == 0 or prog["extracted_files"] == total_files:
                    set_extraction_progress(job_id, prog)

        # Collapse duplicate folders
        inner_candidate = os.path.join(temp_extract_path, zip_top)
        if os.path.isdir(inner_candidate):
            temp_flat = temp_extract_path + "__flat"
            os.rename(inner_candidate, temp_flat)
            shutil.rmtree(temp_extract_path)
            os.rename(temp_flat, temp_extract_path)

        # Clean macOS system files
        clean_macos_files(temp_extract_path)

        # Validate structure
        is_valid, validation_errors = validate_structure(temp_extract_path, zip_top)
        
        if not is_valid:
            prog["status"] = "error"
            prog["error_msg"] = "Invalid archive structure."
            prog["error_details"] = validation_errors
            set_extraction_progress(job_id, prog)
            return

        # Atomic move to final location
        final_path = os.path.join(final_root, zip_top)
        
        if os.path.exists(final_path):
            prog["status"] = "error"
            prog["error_msg"] = f"Recording with ID '{zip_top}' already exists."
            set_extraction_progress(job_id, prog)
            return

        shutil.move(temp_extract_path, final_path)

        # Create initial status file
        create_status_file(final_path, "validated", "Upload and validation successful, awaiting processing.")

        # Calculate size and mark as done
        size_bytes = compute_folder_size(final_path)
        prog["extract_size"] = size_bytes
        prog["recording_id"] = zip_top
        prog["status"] = "done"
        set_extraction_progress(job_id, prog)
        
        return zip_top

    except zipfile.BadZipFile:
        prog["status"] = "error"
        prog["error_msg"] = "Uploaded file is not a valid ZIP archive."
        set_extraction_progress(job_id, prog)

    except Exception as e:
        prog["status"] = "error"
        prog["error_msg"] = f"Error during extraction: {str(e)}"
        set_extraction_progress(job_id, prog)

    finally:
        # Cleanup on error
        if prog.get("status") != "done":
            try:
                if zip_path and os.path.isfile(zip_path):
                    os.remove(zip_path)
            except OSError:
                pass

            try:
                if temp_extract_path and os.path.isdir(temp_extract_path):
                    shutil.rmtree(temp_extract_path)
            except OSError:
                pass


@app.route("/", methods=["GET"])
def index():
    return render_template("upload.html")


@app.route("/upload", methods=["POST"])
def upload_recording():
    if "file" not in request.files:
        return jsonify({"error": "No file in request"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "Invalid file type. Only ZIP/TAR allowed."}), 400

    job_id = uuid.uuid4().hex
    filename = f"{job_id}_{file.filename}"
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)

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
    set_extraction_progress(job_id, initial_progress)

    # Read file content into memory before thread starts (Flask closes file after request)
    try:
        file_content = file.read()
        # Update progress after reading (15%)
        update_extraction_progress(job_id, phase="writing", progress_percent=15)
    except Exception as e:
        return jsonify({"error": f"Failed to read file: {str(e)}"}), 500

    def save_and_extract():
        """Saves file, extracts ZIP, then adds pipeline task to Celery queue"""
        prog = get_extraction_progress(job_id)
        if not prog:
            return
            
        try:
            # Write file content to disk
            with open(save_path, 'wb') as f:
                f.write(file_content)
            # Update progress after writing (30% total)
            update_extraction_progress(job_id, phase="extracting", progress_percent=30)
        except Exception as e:
            prog["status"] = "error"
            prog["error_msg"] = f"Save failed: {str(e)}"
            set_extraction_progress(job_id, prog)
            return
        
        # Extract archive
        recording_id = extract_archive(
            job_id, 
            save_path, 
            app.config["TEMP_EXTRACT_FOLDER"], 
            app.config["EXTRACT_FOLDER"]
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


@app.route("/extract_status/<job_id>", methods=["GET"])
def extract_status(job_id):
    prog = get_extraction_progress(job_id)
    
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


@app.route("/status", methods=["GET"])
def status():
    """Lists all recordings and their processing status."""
    import json
    from datetime import datetime
    
    recordings_root = app.config["EXTRACT_FOLDER"]
    step_names = [
        "s0_detection",
        "s1_small_sign_filter",
        "s2_tracking",
        "s3_small_track_filter",
        "s4_classification",
        "s5_frames_gps_coordinates_extraction",
        "s6_localization",
        "s7_export_csv"
    ]

    all_records = []
    
    if not os.path.isdir(recordings_root):
        return render_template("status.html", recordings=[], step_names=step_names)
    
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

        # Check if processing is complete
        result_root = os.path.join(rec_folder, "result_pipeline_stable")
        is_completed = False
        show_steps = False
        step_status = []
        
        if os.path.isdir(result_root):
            final_output = os.path.join(result_root, "s7_export_csv", "supports.csv")
            is_completed = os.path.isfile(final_output)
            
            # If processing, show steps
            if current_status == "processing" and not is_completed:
                show_steps = True
                for step in step_names:
                    step_folder = os.path.join(result_root, step)
                    
                    if step == "s7_export_csv":
                        output_file = os.path.join(step_folder, "supports.csv")
                    else:
                        output_file = os.path.join(step_folder, "output.json")

                    done_flag = os.path.isfile(output_file)
                    step_status.append({
                        "name": step,
                        "done": done_flag
                    })

        # Determine display status
        if is_completed:
            display_status = "completed"
            display_message = "Processing completed successfully"
        elif current_status == "processing":
            display_status = "processing"
            display_message = status_message or "Processing in progress..."
        elif current_status == "error":
            display_status = "error"
            display_message = status_message or "Error during processing"
        else:  # validated
            display_status = "validated"
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
        step_names=step_names
    )


@app.route("/download/<recording_id>", methods=["GET"])
def download_zip(recording_id):
    """Downloads the CSV results in a ZIP file."""
    base = app.config["EXTRACT_FOLDER"]
    rec_folder = os.path.join(base, recording_id)
    
    if not os.path.isdir(rec_folder):
        return abort(404, description="Recording not found")
    
    result_folder = os.path.join(rec_folder, "result_pipeline_stable", "s7_export_csv")
    if not os.path.isdir(result_folder):
        return abort(404, description="Results folder not found")
    
    output_file1 = os.path.join(result_folder, "supports.csv")
    output_file2 = os.path.join(result_folder, "signs.csv")
    
    if not os.path.isfile(output_file1) or not os.path.isfile(output_file2):
        return abort(404, description="Output files not found")
    
    zip_filename = f"{recording_id}_results.zip"
    zip_path = os.path.join(base, zip_filename)
    
    with zipfile.ZipFile(zip_path, "w") as zipf:
        zipf.write(output_file1, arcname=os.path.basename(output_file1))
        zipf.write(output_file2, arcname=os.path.basename(output_file2))
    
    if os.path.isfile(zip_path):
        return send_file(zip_path, as_attachment=True, download_name=zip_filename)
    else:
        return abort(404, description="Failed to create ZIP file")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)

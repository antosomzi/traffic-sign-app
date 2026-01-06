"""Extraction service for handling ZIP file processing"""

import os
import shutil
import zipfile
from services.redis_service import RedisProgressService
from services.validation_service import ValidationService
from utils.file_utils import compute_folder_size, create_status_file
from utils.cleanup_utils import clean_macos_files
import zipfile
import io

class ExtractionService:
    """Service for extracting and validating uploaded recordings"""
    
    def __init__(self, redis_service=None, validation_service=None):
        """
        Initialize extraction service with dependencies
        
        Args:
            redis_service: RedisProgressService instance (defaults to RedisProgressService)
            validation_service: ValidationService instance (defaults to ValidationService)
        """
        self.redis_service = redis_service or RedisProgressService
        self.validation_service = validation_service or ValidationService
    
    def check_recording_exists(self, file_bytes):
        """
        Inspect the zip (from bytes) to determine the recording_id and check if it already exists in final_root.
        Returns (True, recording_id) if it exists, (False, recording_id) if not, or (None, None) on error.
        """
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes), "r") as z:
                members = z.infolist()
                # Ignore macOS system files
                members = [m for m in members if not (
                    m.filename.startswith("__MACOSX/") or
                    "/.DS_Store" in m.filename or
                    m.filename == ".DS_Store" or
                    m.filename.startswith("._")
                )]
                top_levels = set()
                for member in members:
                    if member.filename.strip("/"):
                        top = member.filename.rstrip("/").split("/")[0]
                        top_levels.add(top)
                # There must be exactly one root folder
                if len(top_levels) != 1:
                    return None, None
                zip_top = top_levels.pop()
                from config import Config
                final_path = os.path.join(Config.EXTRACT_FOLDER, zip_top)
                if os.path.exists(final_path):
                    return True, zip_top
                return False, zip_top
        except Exception:
            return None, None

    def extract_archive(self, job_id, zip_path, temp_root, final_root):
        """
        Atomic extraction process:
        1) Extract to temp_root/<job_id>/
        2) Collapse duplicate folders
        3) Validate structure
        4) If valid: move atomically to final_root/<recording_id>/
        5) On error: cleanup everything (ZIP + temp)
        
        Args:
            job_id: Unique job identifier
            zip_path: Path to uploaded ZIP file
            temp_root: Temporary extraction directory
            final_root: Final destination for validated recordings
        
        Returns:
            recording_id (str) if successful, None otherwise
        """
        print(f"🔧 Starting extraction - job_id: {job_id}")
        prog = self.redis_service.get_extraction_progress(job_id)
        if not prog:
            print(f"❌ No progress found for job_id: {job_id}")
            prog = {
                "status": "error",
                "error_msg": "Job not found"
            }
            self.redis_service.set_extraction_progress(job_id, prog)
            return None
            
        temp_extract_path = os.path.join(temp_root, job_id)
        zip_top = None
        final_path = None

        try:
            # Open ZIP and start extraction
            prog["status"] = "running"
            prog["phase"] = "running"  # Clear the "extracting" phase
            self.redis_service.set_extraction_progress(job_id, prog)
            
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
                self.redis_service.set_extraction_progress(job_id, prog)

                # Identify root folder in ZIP
                top_levels = set()
                for member in members:
                    if member.filename.strip("/"):
                        top = member.filename.rstrip("/").split("/")[0]
                        top_levels.add(top)

                if len(top_levels) != 1:
                    print(f"❌ Multiple root folders detected: {top_levels}")
                    prog["status"] = "error"
                    prog["error_msg"] = "Archive must contain exactly one root folder."
                    prog["error_details"] = {"zip_structure": f"Multiple root folders: {', '.join(top_levels)}"}
                    self.redis_service.set_extraction_progress(job_id, prog)
                    return

                zip_top = top_levels.pop()
                print(f"✅ Single root folder found: {zip_top}")
                os.makedirs(temp_extract_path, exist_ok=True)

                # Extract all files
                for member in members:
                    dest_path = os.path.join(temp_extract_path, member.filename)
                    
                    # ZipSlip protection
                    if not os.path.realpath(dest_path).startswith(os.path.realpath(temp_extract_path) + os.sep):
                        prog["status"] = "error"
                        prog["error_msg"] = "Unsafe file path detected in archive."
                        self.redis_service.set_extraction_progress(job_id, prog)
                        return

                    z.extract(member, temp_extract_path)
                    prog["extracted_files"] += 1
                    # Update Redis every 10 files for better performance
                    if prog["extracted_files"] % 10 == 0 or prog["extracted_files"] == total_files:
                        self.redis_service.set_extraction_progress(job_id, prog)

            # Collapse duplicate folders
            inner_candidate = os.path.join(temp_extract_path, zip_top)
            if os.path.isdir(inner_candidate):
                print(f"🔄 Collapsing duplicate folder structure")
                temp_flat = temp_extract_path + "__flat"
                os.rename(inner_candidate, temp_flat)
                shutil.rmtree(temp_extract_path)
                os.rename(temp_flat, temp_extract_path)

            # Clean macOS system files
            clean_macos_files(temp_extract_path)

            # Validate structure
            print(f"🔍 Validating structure for: {zip_top}")
            is_valid, validation_errors = self.validation_service.validate_structure(temp_extract_path, zip_top)
            
            if not is_valid:
                print(f"❌ Validation failed: {validation_errors}")
                prog["status"] = "error"
                prog["error_msg"] = "Invalid archive structure."
                prog["error_details"] = validation_errors
                self.redis_service.set_extraction_progress(job_id, prog)
                return

            # Atomic move to final location
            final_path = os.path.join(final_root, zip_top)
            
            if os.path.exists(final_path):
                print(f"❌ Recording already exists: {zip_top}")
                prog["status"] = "error"
                prog["error_msg"] = f"Recording with ID '{zip_top}' already exists."
                self.redis_service.set_extraction_progress(job_id, prog)
                return

            shutil.move(temp_extract_path, final_path)

            # Create initial status file
            create_status_file(final_path, "validated", "Upload and validation successful, awaiting processing.")
            
            # Upload video to S3 and remove local copy to save EFS space
            try:
                from services.s3_service import S3VideoService, find_video_in_recording
                s3_service = S3VideoService()
                video_path = find_video_in_recording(final_path)
                
                if video_path:
                    print(f"📤 Uploading video to S3: {video_path}")
                    s3_key = s3_service.upload_video(video_path, zip_top)
                    
                    # Store camera folder path relative to recording root
                    camera_folder = os.path.dirname(video_path)
                    camera_folder_relative = os.path.relpath(camera_folder, final_path)
                    
                    # Update status.json with S3 reference and camera folder path
                    status_file = os.path.join(final_path, "status.json")
                    import json
                    with open(status_file, 'r') as f:
                        status_data = json.load(f)
                    status_data['video_s3_key'] = s3_key
                    status_data['camera_folder'] = camera_folder_relative
                    with open(status_file, 'w') as f:
                        json.dump(status_data, f, indent=2)
                    
                    # Delete local video to save EFS space
                    os.remove(video_path)
                    print(f"✅ Video uploaded to S3, local copy deleted")
                else:
                    print(f"⚠️ No video file found in recording")
            except Exception as s3_error:
                # Log but don't fail - video stays on EFS if S3 fails
                print(f"⚠️ S3 upload failed, video remains on EFS: {s3_error}")

            # Calculate size and mark as done
            size_bytes = compute_folder_size(final_path)
            prog["extract_size"] = size_bytes
            prog["recording_id"] = zip_top
            prog["status"] = "done"
            self.redis_service.set_extraction_progress(job_id, prog)
            
            # Delete ZIP file after successful extraction (no sudo needed - created by ec2-user)
            try:
                if zip_path and os.path.isfile(zip_path):
                    os.remove(zip_path)
                    print(f"🗑️ ZIP file deleted: {zip_path}")
            except OSError as e:
                # Not critical if deletion fails - log and continue
                print(f"⚠️ Could not delete ZIP file: {e}")
            
            print(f"✅ Extraction complete: {zip_top}")
            return zip_top

        except zipfile.BadZipFile:
            print(f"❌ Invalid ZIP file")
            prog["status"] = "error"
            prog["error_msg"] = "Uploaded file is not a valid ZIP archive."
            self.redis_service.set_extraction_progress(job_id, prog)

        except Exception as e:
            print(f"❌ Extraction error: {type(e).__name__}: {str(e)}")
            prog["status"] = "error"
            prog["error_msg"] = f"Error during extraction: {str(e)}"
            self.redis_service.set_extraction_progress(job_id, prog)

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
        
        return None

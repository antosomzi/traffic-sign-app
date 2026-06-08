"""Extraction service for handling ZIP file processing"""

import io
import json
import os
import shutil
import zipfile
from config import Config
from services.sign_app.s3_service import S3VideoService, find_video_in_recording
from services.sign_app.video_encoding_service import VideoEncodingError, encode_video_cfr_semi_all_intra
from services.sign_app.redis_service import RedisProgressService
from services.sign_app.validation_service import ValidationService
from models.sign_app.recording import Recording
from utils.file_utils import compute_folder_size, update_recording_status
from utils.cleanup_utils import clean_macos_files

USE_GPU_INSTANCE = os.getenv("USE_GPU_INSTANCE", "false").lower() == "true"

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
                recording_id = top_levels.pop()
                final_path = os.path.join(Config.EXTRACT_FOLDER, recording_id)
                if os.path.exists(final_path):
                    return True, recording_id
                return False, recording_id
        except Exception:
            return None, None

    def _get_upload_source_path(self, video_path, job_id):
        """Return the video path to upload (raw in GPU mode, encoded otherwise)."""
        if USE_GPU_INSTANCE:
            print("⚡ USE_GPU_INSTANCE=true: skipping local encoding at upload time")
            return video_path

        self.redis_service.update_extraction_progress(
            job_id,
            phase="encoding",
            progress_percent=90,
        )
        print(f"🎬 Encoding video for CFR/semi All-Intra upload: {video_path}")
        return encode_video_cfr_semi_all_intra(video_path)

    def _update_status_with_s3_metadata(self, final_path, video_path, s3_key):
        """Persist S3 metadata (key + camera folder) in the database."""
        camera_folder = os.path.dirname(video_path)
        camera_folder_relative = os.path.relpath(camera_folder, final_path)
        recording_id = os.path.basename(final_path)

        Recording.update_status(
            recording_id, 
            video_s3_key=s3_key, 
            camera_folder=camera_folder_relative
        )

    @staticmethod
    def _cleanup_local_video_files(video_path, upload_source_path):
        """Remove local video files after successful S3 upload."""
        if upload_source_path != video_path and os.path.exists(upload_source_path):
            os.remove(upload_source_path)
        if os.path.exists(video_path):
            os.remove(video_path)

    def _upload_recording_video_to_s3(self, final_path, recording_id, job_id):
        """Upload recording video to S3 and clean local copy when successful."""
        video_path = find_video_in_recording(final_path)
        if not video_path:
            print("⚠️ No video file found in recording")
            return

        try:
            upload_source_path = self._get_upload_source_path(video_path, job_id)

            self.redis_service.update_extraction_progress(
                job_id,
                phase="uploading",
                progress_percent=97,
            )

            print(f"📤 Uploading video to S3: {upload_source_path}")
            s3_service = S3VideoService()
            s3_key = s3_service.upload_video(upload_source_path, recording_id)

            self._update_status_with_s3_metadata(final_path, video_path, s3_key)
            self._cleanup_local_video_files(video_path, upload_source_path)
            print("✅ Video uploaded to S3, local copies deleted")
        except Exception as upload_error:
            if isinstance(upload_error, VideoEncodingError):
                print(f"⚠️ Video encoding failed, original video remains on EFS: {upload_error}")
            else:
                print(f"⚠️ S3 upload failed, video remains on EFS: {upload_error}")

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
        recording_id = None
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

                recording_id = top_levels.pop()
                print(f"✅ Single root folder found: {recording_id}")
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
            inner_candidate = os.path.join(temp_extract_path, recording_id)
            if os.path.isdir(inner_candidate):
                print(f"🔄 Collapsing duplicate folder structure")
                temp_flat = temp_extract_path + "__flat"
                os.rename(inner_candidate, temp_flat)
                shutil.rmtree(temp_extract_path)
                os.rename(temp_flat, temp_extract_path)

            # Clean macOS system files
            clean_macos_files(temp_extract_path)

            # Validate structure
            print(f"🔍 Validating structure for: {recording_id}")
            is_valid, validation_errors = self.validation_service.validate_structure(temp_extract_path, recording_id)
            
            if not is_valid:
                print(f"❌ Validation failed: {validation_errors}")
                prog["status"] = "error"
                prog["error_msg"] = "Invalid archive structure."
                prog["error_details"] = validation_errors
                self.redis_service.set_extraction_progress(job_id, prog)
                return

            # Atomic move to final location
            final_path = os.path.join(final_root, recording_id)
            
            if os.path.exists(final_path):
                print(f"❌ Recording already exists: {recording_id}")
                prog["status"] = "error"
                prog["error_msg"] = f"Recording with ID '{recording_id}' already exists."
                self.redis_service.set_extraction_progress(job_id, prog)
                return

            shutil.move(temp_extract_path, final_path)

            # Create initial status file
            update_recording_status(recording_id, "validated", "Upload and validation successful, awaiting processing.")

            # In GPU mode, defer S3 upload until after GPU re-encoding is done.
            # In local mode, keep current behavior (upload during extraction).
            if USE_GPU_INSTANCE:
                print("⚡ USE_GPU_INSTANCE=true: deferring S3 upload until post-encoding")
            else:
                # Upload video to S3 and remove local copy to save EFS space
                self._upload_recording_video_to_s3(final_path, recording_id, job_id)

            # Calculate size and mark as done
            size_bytes = compute_folder_size(final_path)
            prog["extract_size"] = size_bytes
            prog["recording_id"] = recording_id
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
            
            print(f"✅ Extraction complete: {recording_id}")
            return recording_id

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

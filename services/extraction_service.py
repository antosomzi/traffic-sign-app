"""Extraction service for handling ZIP file processing"""

import os
import shutil
import zipfile
from services.redis_service import RedisProgressService
from services.validation_service import ValidationService
from utils.file_utils import compute_folder_size, create_status_file
from utils.cleanup_utils import clean_macos_files


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
        prog = self.redis_service.get_extraction_progress(job_id)
        if not prog:
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
                    prog["status"] = "error"
                    prog["error_msg"] = "Archive must contain exactly one root folder."
                    prog["error_details"] = {"zip_structure": f"Multiple root folders: {', '.join(top_levels)}"}
                    self.redis_service.set_extraction_progress(job_id, prog)
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
                temp_flat = temp_extract_path + "__flat"
                os.rename(inner_candidate, temp_flat)
                shutil.rmtree(temp_extract_path)
                os.rename(temp_flat, temp_extract_path)

            # Clean macOS system files
            clean_macos_files(temp_extract_path)

            # Validate structure
            is_valid, validation_errors = self.validation_service.validate_structure(temp_extract_path, zip_top)
            
            if not is_valid:
                prog["status"] = "error"
                prog["error_msg"] = "Invalid archive structure."
                prog["error_details"] = validation_errors
                self.redis_service.set_extraction_progress(job_id, prog)
                return

            # Atomic move to final location
            final_path = os.path.join(final_root, zip_top)
            
            if os.path.exists(final_path):
                prog["status"] = "error"
                prog["error_msg"] = f"Recording with ID '{zip_top}' already exists."
                self.redis_service.set_extraction_progress(job_id, prog)
                return

            shutil.move(temp_extract_path, final_path)

            # Create initial status file
            create_status_file(final_path, "validated", "Upload and validation successful, awaiting processing.")

            # Calculate size and mark as done
            size_bytes = compute_folder_size(final_path)
            prog["extract_size"] = size_bytes
            prog["recording_id"] = zip_top
            prog["status"] = "done"
            self.redis_service.set_extraction_progress(job_id, prog)
            
            return zip_top

        except zipfile.BadZipFile:
            prog["status"] = "error"
            prog["error_msg"] = "Uploaded file is not a valid ZIP archive."
            self.redis_service.set_extraction_progress(job_id, prog)

        except Exception as e:
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

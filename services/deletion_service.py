"""Service for handling recording deletion"""

import os
import shutil
import json
import subprocess
import stat
from typing import Dict, Tuple
from config import Config


def can_delete_recording(recording_id: str) -> Tuple[bool, str]:
    """
    Check if a recording can be deleted (not currently processing)
    
    Args:
        recording_id: The recording ID to check
        
    Returns:
        Tuple of (can_delete: bool, reason: str)
    """
    recording_path = os.path.join(Config.EXTRACT_FOLDER, recording_id)
    
    if not os.path.exists(recording_path):
        return False, "Recording not found"
    
    # Check status.json
    status_file = os.path.join(recording_path, "status.json")
    if os.path.exists(status_file):
        try:
            with open(status_file, "r") as f:
                status_data = json.load(f)
                current_status = status_data.get("status", "")

                if current_status == "processing":
                    final_result = os.path.join(
                        recording_path,
                        "result_pipeline_stable",
                        "s7_export_csv",
                        "supports.csv"
                    )

                    if not os.path.isfile(final_result):
                        return False, "Cannot delete: recording is currently processing"
        except Exception:
            # If we can't read status, assume it's safe to delete
            pass
    
    return True, "OK"


def delete_recording(recording_id: str) -> Dict[str, any]:
    """
    Delete a recording and all associated files
    
    Args:
        recording_id: The recording ID to delete
        
    Returns:
        Dict with 'success' (bool), 'message' (str), 'recording_id' (str)
    """
    # Check if deletion is allowed
    can_delete, reason = can_delete_recording(recording_id)
    if not can_delete:
        return {
            "success": False,
            "message": reason,
            "recording_id": recording_id
        }
    
    recording_path = os.path.join(Config.EXTRACT_FOLDER, recording_id)
    
    try:
        # Delete the recording folder with permission error handling
        if os.path.exists(recording_path):
            try:
                # First attempt: normal deletion
                shutil.rmtree(recording_path)
            except PermissionError:
                # Second attempt: fix ownership with sudo (production only)
                print(f"[DELETE] Permission denied, attempting sudo chown for {recording_id}")
                
                # Use absolute path to sudo (works on both Linux and Mac)
                sudo_path = '/usr/bin/sudo'
                if not os.path.exists(sudo_path):
                    # Fallback for systems where sudo is elsewhere
                    sudo_path = 'sudo'
                
                try:
                    # Fix ownership to current user
                    subprocess.run(
                        [sudo_path, 'chown', '-R', 'ec2-user:ec2-user', recording_path],
                        check=True,
                        capture_output=True,
                        text=True
                    )
                    # Retry deletion
                    shutil.rmtree(recording_path)
                except subprocess.CalledProcessError as e:
                    return {
                        "success": False,
                        "message": f"Failed to fix ownership: {e.stderr}",
                        "recording_id": recording_id
                    }
                except FileNotFoundError:
                    # sudo not found - try manual permission fix
                    print(f"[DELETE] sudo not available, attempting manual permission fix")
                    try:
                        for root, dirs, files in os.walk(recording_path, topdown=False):
                            for name in files:
                                filepath = os.path.join(root, name)
                                try:
                                    os.chmod(filepath, stat.S_IWUSR | stat.S_IRUSR)
                                except:
                                    pass
                            for name in dirs:
                                dirpath = os.path.join(root, name)
                                try:
                                    os.chmod(dirpath, stat.S_IWUSR | stat.S_IRUSR | stat.S_IXUSR)
                                except:
                                    pass
                        # Final retry
                        shutil.rmtree(recording_path)
                    except Exception as chmod_error:
                        return {
                            "success": False,
                            "message": f"Permission denied: {str(chmod_error)}",
                            "recording_id": recording_id
                        }
        
        # Optionally delete the uploaded ZIP file (if you want to keep it, remove this)
        uploads_folder = Config.UPLOAD_FOLDER
        if os.path.exists(uploads_folder):
            for filename in os.listdir(uploads_folder):
                if recording_id in filename:
                    zip_path = os.path.join(uploads_folder, filename)
                    try:
                        os.remove(zip_path)
                    except Exception:
                        pass  # Not critical if ZIP removal fails
        
        return {
            "success": True,
            "message": f"Recording {recording_id} deleted successfully",
            "recording_id": recording_id
        }
    
    except Exception as e:
        return {
            "success": False,
            "message": f"Error deleting recording: {str(e)}",
            "recording_id": recording_id
        }

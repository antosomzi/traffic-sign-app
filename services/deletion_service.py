"""Service for handling recording deletion"""

import os
import shutil
import json
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
                current_status = status_data.get("status", "validated")
                
                # Block deletion if processing or validated (about to process)
                if current_status in ["processing", "validated"]:
                    return False, f"Cannot delete: recording is currently {current_status}"
        except Exception as e:
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
        # Delete the recording folder
        if os.path.exists(recording_path):
            shutil.rmtree(recording_path)
        
        # Optionally delete the uploaded ZIP file (if you want to keep it, remove this)
        uploads_folder = Config.UPLOAD_FOLDER
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

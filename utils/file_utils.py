"""File utility functions"""

import os
import json
from config import Config
from models.sign_app.recording import Recording


def allowed_file(filename):
    """Check if file extension is allowed"""
    return "." in filename and \
           filename.rsplit(".", 1)[1].lower() in Config.ALLOWED_EXTENSIONS


def compute_folder_size(path):
    """Calculate total size of a folder in bytes"""
    total = 0
    for root, _, files in os.walk(path):
        for fname in files:
            fp = os.path.join(root, fname)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total


def update_recording_status(recording_id, status, message="", error_details=None):
    """Updates the recording status in the database"""
    Recording.update_status(
        recording_id, 
        status=status, 
        message=message, 
        error_details=error_details
    )

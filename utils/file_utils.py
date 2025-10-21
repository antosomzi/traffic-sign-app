"""File utility functions"""

import os
import json
from config import Config


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


def create_status_file(recording_path, status, message=""):
    """Creates or updates the status.json file for a recording"""
    import datetime
    
    status_file = os.path.join(recording_path, "status.json")
    
    status_data = {
        "status": status,
        "message": message,
        "timestamp": datetime.datetime.now().isoformat()
    }
    
    with open(status_file, "w") as f:
        json.dump(status_data, f, indent=2)

"""Validation service for recording structure"""

import os


class ValidationService:
    """Service for validating recording folder structure"""
    
    @staticmethod
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
        # Vérification : le dossier device doit être uniquement composé de chiffres
        if not device_folder.isdigit():
            errors["device_folder"] = f"Device folder not available or invalid: {device_folder}"
            return False, errors
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
        
        required_subfolders = ["camera", "location"]
        missing_folders = []
        for sub in required_subfolders:
            full_sub = os.path.join(imei_path, sub)
            if not os.path.isdir(full_sub):
                missing_folders.append(sub)
        if missing_folders:
            errors["missing_folders"] = f"Missing folders: {', '.join(missing_folders)}"
            return False, errors

        missing_files = {}

        # Camera: at least one .mp4 file
        cam_dir = os.path.join(imei_path, "camera")
        cam_files = [f for f in os.listdir(cam_dir) if f.lower().endswith(".mp4")]
        if not cam_files:
            missing_files["camera"] = ["At least one .mp4 video file required"]

        # Location: at least one .csv file
        loc_dir = os.path.join(imei_path, "location")
        loc_csvs = [f for f in os.listdir(loc_dir) if f.lower().endswith(".csv")]
        if len(loc_csvs) < 1:
            missing_files["location"] = ["At least one .csv file required"]

        if missing_files:
            errors["missing_files"] = missing_files
            return False, errors

        return True, {}

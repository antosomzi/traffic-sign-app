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
        
        print(f"🔍 Validating structure at: {root_path}")
        entries = os.listdir(root_path)
        print(f"📂 Contents of root: {entries}")
        devices = [d for d in entries if os.path.isdir(os.path.join(root_path, d))]
        print(f"📂 Device folders found: {devices}")
        
        if len(devices) == 0:
            errors["device_folder"] = "No device folder found"
            print(f"❌ No device folder found")
            return False, errors
        elif len(devices) > 1:
            errors["device_folder"] = f"Multiple device folders found: {', '.join(devices)}. Only one expected."
            print(f"❌ Multiple device folders: {devices}")
            return False, errors
        
        device_folder = devices[0]
        # Vérification : le dossier device doit être uniquement composé de chiffres
        if not device_folder.isdigit():
            errors["device_folder"] = f"Device folder not available or invalid: {device_folder}"
            print(f"❌ Device folder '{device_folder}' is not numeric")
            return False, errors
        
        print(f"✅ Valid device folder: {device_folder}")
        device_path = os.path.join(root_path, device_folder)

        subentries = os.listdir(device_path)
        print(f"📂 Contents of device folder: {subentries}")
        imei_folders = [d for d in subentries if os.path.isdir(os.path.join(device_path, d))]
        print(f"📂 IMEI folders found: {imei_folders}")

        if len(imei_folders) == 0:
            errors["imei_folder"] = "No IMEI folder found"
            print(f"❌ No IMEI folder found")
            return False, errors
        elif len(imei_folders) > 1:
            errors["imei_folder"] = f"Multiple IMEI folders found: {', '.join(imei_folders)}. Only one expected."
            print(f"❌ Multiple IMEI folders: {imei_folders}")
            return False, errors

        imei_folder = imei_folders[0]
        print(f"✅ Valid IMEI folder: {imei_folder}")
        imei_path = os.path.join(device_path, imei_folder)
        
        imei_contents = os.listdir(imei_path)
        print(f"📂 Contents of IMEI folder: {imei_contents}")
        
        required_subfolders = ["camera", "location"]
        missing_folders = []
        for sub in required_subfolders:
            full_sub = os.path.join(imei_path, sub)
            if not os.path.isdir(full_sub):
                missing_folders.append(sub)
        if missing_folders:
            errors["missing_folders"] = f"Missing folders: {', '.join(missing_folders)}"
            print(f"❌ Missing required folders: {missing_folders}")
            return False, errors

        print(f"✅ All required folders present")
        missing_files = {}

        # Camera: at least one .mp4 file
        cam_dir = os.path.join(imei_path, "camera")
        cam_files = [f for f in os.listdir(cam_dir) if f.lower().endswith(".mp4")]
        print(f"📹 Camera .mp4 files: {cam_files}")
        if not cam_files:
            missing_files["camera"] = ["At least one .mp4 video file required"]

        # Location: at least one .csv file
        loc_dir = os.path.join(imei_path, "location")
        loc_csvs = [f for f in os.listdir(loc_dir) if f.lower().endswith(".csv")]
        print(f"📍 Location .csv files: {loc_csvs}")
        if len(loc_csvs) < 1:
            missing_files["location"] = ["At least one .csv file required"]

        if missing_files:
            errors["missing_files"] = missing_files
            print(f"❌ Missing required files: {missing_files}")
            return False, errors

        print(f"✅ Validation passed completely")
        return True, {}

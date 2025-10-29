"""Download routes for retrieving processing results"""

import os
import zipfile
from flask import Blueprint, abort, send_file
from config import Config

download_bp = Blueprint("download", __name__)


@download_bp.route("/download/<recording_id>", methods=["GET"])
def download_zip(recording_id):
    """Downloads the CSV results in a ZIP file."""
    base = Config.EXTRACT_FOLDER
    rec_folder = os.path.join(base, recording_id)
    
    if not os.path.isdir(rec_folder):
        return abort(404, description="Recording not found")
    
    result_folder = os.path.join(rec_folder, "result_pipeline_stable", "s7_export_csv")
    if not os.path.isdir(result_folder):
        return abort(404, description="Results folder not found")
    
    output_file1 = os.path.join(result_folder, "supports.csv")
    output_file2 = os.path.join(result_folder, "signs.csv")

    # Correction : le JSON est output.json dans le dossier s6_localization
    json_folder = os.path.join(rec_folder, "result_pipeline_stable", "s6_localization")
    json_file = os.path.join(json_folder, "output.json")

    if not (os.path.isfile(output_file1) and os.path.isfile(output_file2) and os.path.isfile(json_file)):
        missing = []
        if not os.path.isfile(output_file1):
            missing.append("supports.csv")
        if not os.path.isfile(output_file2):
            missing.append("signs.csv")
        if not os.path.isfile(json_file):
            missing.append("output.json (in s6_localisation)")
        return abort(404, description=f"Missing output files: {', '.join(missing)}")

    zip_filename = f"{recording_id}_results.zip"
    zip_path = os.path.join(base, zip_filename)

    with zipfile.ZipFile(zip_path, "w") as zipf:
        zipf.write(output_file1, arcname=os.path.basename(output_file1))
        zipf.write(output_file2, arcname=os.path.basename(output_file2))
        zipf.write(json_file, arcname=os.path.basename(json_file))

    if os.path.isfile(zip_path):
        return send_file(zip_path, as_attachment=True, download_name=zip_filename)
    else:
        return abort(404, description="Failed to create ZIP file")

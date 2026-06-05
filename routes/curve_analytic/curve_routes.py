"""
Curve routes for shared map data, curve detail, and ZIP upload.
"""
from flask import Blueprint, jsonify, request, render_template
from flask_login import current_user
from decorators.auth_decorators import token_required, login_required

from models.curve_analytic.curve import Curve
from services.curve_analytic.ingestion import UploadValidationError, ingest_recording_zip
import json

curves_bp = Blueprint("curves", __name__, url_prefix="/curves")


@curves_bp.route("/map", methods=["GET"])
@login_required
def curves_map_view():
    """Render the curves analytics map page."""
    # Fetch curves that have recordings for this organization
    curves = Curve.get_all_for_org(current_user.organization_id)
    curves_json = json.dumps([c.to_detail() for c in curves])
    return render_template("curve_analytic/curves_map.html", curves_json=curves_json)


@curves_bp.route("", methods=["GET"])
@token_required
def list_curves(user):
    """Get all curves for the user's organization."""
    curves = Curve.get_all_for_org(user.organization_id)
    return jsonify([curve.to_list_item() for curve in curves])


@curves_bp.route("/<int:curve_id>", methods=["GET"])
@token_required
def get_curve(user, curve_id):
    """Get full curve details."""
    curve = Curve.get_by_id(curve_id)
    if curve is None:
        return jsonify({"message": f"Curve {curve_id} not found"}), 404
        
    # Security check is implicitly handled by the relationship/query in a real app, 
    # but for now we return the detail as requested.
    return jsonify(curve.to_detail())


@curves_bp.route("/upload", methods=["POST"])
@login_required
def upload_curves():
    """ZIP upload for curve recordings."""
    uploaded_file = request.files.get("file")
    if uploaded_file is None or not uploaded_file.filename:
        return jsonify({"message": "Upload requires one .zip file in form field 'file'."}), 400

    try:
        result = ingest_recording_zip(uploaded_file.read(), uploaded_file.filename, current_user.organization_id)
    except UploadValidationError as exc:
        return jsonify({"message": str(exc)}), 400
    except Exception as e:
        print(f"ERROR: {e}")
        return jsonify({"message": "Upload failed while processing the recording."}), 500

    return (
        jsonify(
            {
                "message": f"Uploaded recording {result['recordingId']}",
                "recordingId": result["recordingId"],
                "curveCount": result["curveCount"],
            }
        ),
        201,
    )

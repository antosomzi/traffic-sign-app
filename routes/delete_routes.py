"""Delete routes for removing recordings"""

from flask import Blueprint, jsonify, abort
from flask_login import login_required, current_user
from services.deletion_service import delete_recording
from services.organization_service import OrganizationService

delete_bp = Blueprint("delete", __name__)


@delete_bp.route("/delete/<recording_id>", methods=["DELETE"])
@login_required
def delete_recording_route(recording_id: str):
    """
    Delete a recording by ID
    
    Args:
        recording_id: The recording ID to delete
        
    Returns:
        JSON response with success status and message
    """
    # Check if user can access this recording
    if not OrganizationService.can_access_recording(current_user, recording_id):
        abort(403)
    
    result = delete_recording(recording_id)
    
    # Also delete from database
    if result["success"]:
        OrganizationService.delete_recording(recording_id)
    
    status_code = 200 if result["success"] else 400
    
    return jsonify(result), status_code

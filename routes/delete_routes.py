"""Delete routes for removing recordings"""

from flask import Blueprint, jsonify
from services.deletion_service import delete_recording

delete_bp = Blueprint("delete", __name__)


@delete_bp.route("/delete/<recording_id>", methods=["DELETE"])
def delete_recording_route(recording_id: str):
    """
    Delete a recording by ID
    
    Args:
        recording_id: The recording ID to delete
        
    Returns:
        JSON response with success status and message
    """
    result = delete_recording(recording_id)
    
    status_code = 200 if result["success"] else 400
    
    return jsonify(result), status_code

"""Mobile authentication routes for API token-based login
Mobile app reuses existing routes with @auth_required decorator:
- POST /upload (with Authorization header)
- GET /extract_status/<job_id> (with Authorization header)

This file only contains mobile-specific login/logout endpoints
"""

from flask import Blueprint, request, jsonify
from decorators.auth_decorators import login_required
from flask_login import current_user
from models.user import User
from models.auth_token import AuthToken

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/login", methods=["POST"])
def api_login():
    """Mobile API login endpoint
    
    Expected JSON body:
    {
        "email": "user@example.com",
        "password": "password123"
    }
    
    Returns:
    {
        "success": true,
        "token": "generated_token_here",
        "user": {
            "id": 1,
            "name": "User Name",
            "email": "user@example.com",
            "organization_id": 1,
            "organization_name": "Organization Name",
            "is_admin": false
        }
    }
    """
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "Request must be JSON"}), 400
    
    email = data.get("email", "").strip()
    password = data.get("password", "")
    
    # Validation
    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400
    
    # Get user
    user = User.get_by_email(email)
    
    # Check credentials
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid email or password"}), 401
    
    # Generate token
    token = AuthToken.create(user.id, expires_days=365)
    
    return jsonify({
        "success": True,
        "token": token,
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "organization_id": user.organization_id,
            "organization_name": user.organization.name,
            "is_admin": user.is_admin
        }
    }), 200


@api_bp.route("/logout", methods=["POST"])
def api_logout():
    """Mobile API logout endpoint - deletes the current token
    
    Requires Authorization header with Bearer token
    """
    auth_header = request.headers.get('Authorization')
    
    if not auth_header:
        return jsonify({"error": "Authorization header missing"}), 401
    
    token = auth_header.split(' ')[1] if ' ' in auth_header else auth_header
    
    # Verify token exists before deleting
    user_id = AuthToken.get_by_token(token)
    if not user_id:
        return jsonify({"error": "Invalid or expired token"}), 401
    
    AuthToken.delete(token)

    return jsonify({"success": True, "message": "Logged out successfully"}), 200


@api_bp.route("/me", methods=["GET"])
@login_required
def get_current_user():
    """Get current authenticated user info"""
    return jsonify({
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "organization_id": current_user.organization_id,
        "organization_name": current_user.organization.name,
        "is_admin": current_user.is_admin,
        "is_org_owner": current_user.is_org_owner
    }), 200

"""Admin routes for managing organizations and users"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user
from decorators.auth_decorators import admin_required
from models.organization import Organization
from models.user import User
from models.api_key import APIKey

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/")
@admin_required
def dashboard():
    """Admin dashboard"""
    organizations = Organization.get_all()
    users = User.get_all()
    
    # Calculate stats
    total_orgs = len(organizations)
    total_users = len(users)
    total_recordings = sum(org.count_recordings() for org in organizations)
    
    return render_template(
        "admin/dashboard.html",
        total_orgs=total_orgs,
        total_users=total_users,
        total_recordings=total_recordings,
        organizations=organizations
    )


@admin_bp.route("/organizations")
@admin_required
def organizations():
    """List all organizations"""
    orgs = Organization.get_all()
    
    # Add stats for each org
    org_list = []
    for org in orgs:
        org_list.append({
            "id": org.id,
            "name": org.name,
            "created_at": org.created_at,
            "user_count": org.count_users(),
            "recording_count": org.count_recordings()
        })
    
    return render_template("admin/organizations.html", organizations=org_list)


@admin_bp.route("/organizations/new", methods=["GET", "POST"])
@admin_required
def create_organization():
    """Create a new organization"""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        
        if not name:
            flash("Organization name is required.", "danger")
            return render_template("admin/organization_form.html", mode="create")
        
        # Check if organization already exists
        existing = Organization.get_by_name(name)
        if existing:
            flash(f"Organization '{name}' already exists.", "danger")
            return render_template("admin/organization_form.html", mode="create")
        
        # Create organization
        org = Organization.create(name)
        flash(f"Organization '{org.name}' created successfully!", "success")
        return redirect(url_for('admin.organizations'))
    
    return render_template("admin/organization_form.html", mode="create")


@admin_bp.route("/organizations/<int:org_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_organization(org_id):
    """Edit an organization"""
    org = Organization.get_by_id(org_id)
    if not org:
        flash("Organization not found.", "danger")
        return redirect(url_for('admin.organizations'))
    
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        
        if not name:
            flash("Organization name is required.", "danger")
            return render_template("admin/organization_form.html", mode="edit", organization=org)
        
        # Check if organization name already exists (excluding current org)
        existing = Organization.get_by_name(name)
        if existing and existing.id != org.id:
            flash(f"Organization '{name}' already exists.", "danger")
            return render_template("admin/organization_form.html", mode="edit", organization=org)
        
        # Update organization
        org.update_name(name)
        flash(f"Organization renamed to '{org.name}' successfully!", "success")
        return redirect(url_for('admin.organizations'))
    
    return render_template("admin/organization_form.html", mode="edit", organization=org)


@admin_bp.route("/organizations/<int:org_id>/delete", methods=["POST"])
@admin_required
def delete_organization(org_id):
    """Delete an organization"""
    org = Organization.get_by_id(org_id)
    if not org:
        flash("Organization not found.", "danger")
        return redirect(url_for('admin.organizations'))
    
    org_name = org.name
    org.delete()
    flash(f"Organization '{org_name}' and all its users deleted successfully!", "success")
    return redirect(url_for('admin.organizations'))


@admin_bp.route("/users")
@admin_required
def users():
    """List all users"""
    all_users = User.get_all()
    
    # Add organization name for each user
    user_list = []
    for user in all_users:
        user_list.append({
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "organization": user.organization.name,
            "is_admin": user.is_admin,
            "is_org_owner": user.is_org_owner,
            "created_at": user.created_at
        })
    
    return render_template("admin/users.html", users=user_list)


@admin_bp.route("/users/new", methods=["GET", "POST"])
@admin_required
def create_user():
    """Create a new user"""
    organizations = Organization.get_all()
    
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "").strip()
        organization_id = request.form.get("organization_id", "").strip()
        is_admin = request.form.get("is_admin") == "1"
        is_org_owner = request.form.get("is_org_owner") == "1"
        
        # Validation
        if not email or not name or not password or not organization_id:
            flash("All fields are required.", "danger")
            return render_template("admin/user_form.html", mode="create", organizations=organizations)
        
        # Check if user already exists
        existing = User.get_by_email(email)
        if existing:
            flash(f"User with email '{email}' already exists.", "danger")
            return render_template("admin/user_form.html", mode="create", organizations=organizations)
        
        # Create user
        user = User.create(
            email=email,
            password=password,
            name=name,
            organization_id=int(organization_id),
            is_admin=is_admin,
            is_org_owner=is_org_owner
        )
        flash(f"User '{user.name}' created successfully!", "success")
        return redirect(url_for('admin.users'))
    
    return render_template("admin/user_form.html", mode="create", organizations=organizations)


@admin_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_user(user_id):
    """Edit user details"""
    user = User.get_by_id(user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for('admin.users'))
    
    organizations = Organization.get_all()
    
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        name = request.form.get("name", "").strip()
        organization_id = request.form.get("organization_id", "").strip()
        is_admin = request.form.get("is_admin") == "1"
        is_org_owner = request.form.get("is_org_owner") == "1"
        new_password = request.form.get("new_password", "").strip()
        
        # Validation
        if not email or not name or not organization_id:
            flash("Email, name, and organization are required.", "danger")
            return render_template("admin/user_form.html", mode="edit", user=user, organizations=organizations)
        
        # Check if email already exists (excluding current user)
        existing = User.get_by_email(email)
        if existing and existing.id != user.id:
            flash(f"User with email '{email}' already exists.", "danger")
            return render_template("admin/user_form.html", mode="edit", user=user, organizations=organizations)
        
        # Update user fields
        user.update_fields(email=email, name=name, organization_id=int(organization_id))
        
        # Update admin status
        user.update_admin_status(is_admin)
        
        # Update org owner status
        user.update_org_owner_status(is_org_owner)
        
        # Update password if provided
        if new_password:
            user.update_password(new_password)
            flash(f"User '{user.name}' updated with new password!", "success")
        else:
            flash(f"User '{user.name}' updated successfully!", "success")
        
        return redirect(url_for('admin.users'))
    
    return render_template(
        "admin/user_form.html",
        mode="edit",
        user=user,
        organizations=organizations
    )


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def delete_user(user_id):
    """Delete a user"""
    user = User.get_by_id(user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for('admin.users'))

    # Prevent deleting yourself
    if user.id == current_user.id:
        flash("You cannot delete yourself.", "danger")
        return redirect(url_for('admin.users'))

    user_name = user.name
    user.delete()
    flash(f"User '{user_name}' deleted successfully!", "success")
    return redirect(url_for('admin.users'))


# API Key Management Routes

@admin_bp.route("/api-keys")
@admin_required
def list_api_keys():
    """List all API keys for all users (admin view)"""
    users = User.get_all()
    all_keys = []

    for user in users:
        keys = APIKey.get_all_for_user(user.id)
        for key in keys:
            all_keys.append({
                "id": key["id"],
                "user_name": user.name,
                "user_email": user.email,
                "organization": user.organization.name,
                "name": key["name"],
                "created_at": key["created_at"],
                "expires_at": key["expires_at"],
                "revoked": key["revoked"]
            })

    return render_template("admin/api_keys.html", api_keys=all_keys, users=users)


@admin_bp.route("/api-keys/generate", methods=["POST"])
@admin_required
def generate_api_key():
    """Generate a new API key for a user"""
    user_id = request.form.get("user_id")
    key_name = request.form.get("name", "").strip()
    expires_days = request.form.get("expires_days", "").strip()

    if not user_id:
        flash("User ID is required.", "danger")
        return redirect(url_for('admin.list_api_keys'))

    user = User.get_by_id(int(user_id))
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for('admin.list_api_keys'))

    # Parse expires_days (None means never expires)
    expires_days_int = None
    if expires_days:
        try:
            expires_days_int = int(expires_days)
        except ValueError:
            flash("Invalid expiration days.", "danger")
            return redirect(url_for('admin.list_api_keys'))

    # Generate the API key
    key_id, plain_key = APIKey.create(
        user_id=int(user_id),
        name=key_name if key_name else None,
        expires_days=expires_days_int
    )

    # Show the key only once!
    flash(
        f"API key generated for {user.name}. Copy it now, it won't be shown again: {plain_key}",
        "success"
    )

    return redirect(url_for('admin.list_api_keys'))


@admin_bp.route("/api-keys/<int:key_id>/revoke", methods=["POST"])
@admin_required
def revoke_api_key(key_id):
    """Revoke an API key"""
    APIKey.revoke(key_id)
    flash("API key revoked successfully.", "success")
    return redirect(url_for('admin.list_api_keys'))


@admin_bp.route("/api-keys/<int:key_id>/delete", methods=["POST"])
@admin_required
def delete_api_key(key_id):
    """Delete an API key"""
    APIKey.delete_by_id(key_id)
    flash("API key deleted successfully.", "success")
    return redirect(url_for('admin.list_api_keys'))

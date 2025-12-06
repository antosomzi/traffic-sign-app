"""Admin routes for managing organizations and users"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from decorators.auth_decorators import admin_required
from models.organization import Organization
from models.user import User

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
            is_admin=is_admin
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
        is_admin = request.form.get("is_admin") == "1"
        new_password = request.form.get("new_password", "").strip()
        
        # Update admin status
        user.update_admin_status(is_admin)
        
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

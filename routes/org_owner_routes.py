"""Routes for organization owners to manage users in their organization"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from decorators.auth_decorators import org_owner_required
from models.user import User
from models.organization import Organization

org_owner_bp = Blueprint('org_owner', __name__, url_prefix='/org_owner')


@org_owner_bp.route('/users', methods=['GET'])
@org_owner_required
def list_users():
    """List all users in the organization owner's organization"""
    users = User.get_by_organization(current_user.organization_id)
    org = Organization.get_by_id(current_user.organization_id)
    
    return render_template(
        'org_owner/users.html',
        users=users,
        organization=org
    )


@org_owner_bp.route('/users/create', methods=['GET', 'POST'])
@org_owner_required
def create_user():
    """Create a new user in the organization"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        name = request.form.get('name', '').strip()
        is_org_owner = request.form.get('is_org_owner') == '1'
        
        # Validation
        if not email or not password or not name:
            flash('All fields are required', 'danger')
            return render_template(
                'admin/user_form.html', 
                mode='create',
                is_org_owner_view=True,
                organization=current_user.organization
            )
        
        # Check if user already exists
        if User.get_by_email(email):
            flash(f'User with email {email} already exists', 'danger')
            return render_template(
                'admin/user_form.html',
                mode='create',
                is_org_owner_view=True,
                organization=current_user.organization
            )
        
        # Create user in the org owner's organization
        # Can create org_owner but NOT admin
        user = User.create(
            email=email,
            password=password,
            name=name,
            organization_id=current_user.organization_id,
            is_admin=False,
            is_org_owner=is_org_owner
        )
        
        role = 'organization owner' if is_org_owner else 'user'
        flash(f'{role.capitalize()} {user.name} created successfully', 'success')
        return redirect(url_for('org_owner.list_users'))
    
    return render_template(
        'admin/user_form.html',
        mode='create',
        is_org_owner_view=True,
        organization=current_user.organization
    )


@org_owner_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@org_owner_required
def edit_user(user_id):
    """Edit a user in the organization"""
    user = User.get_by_id(user_id)
    
    if not user:
        flash('User not found', 'danger')
        return redirect(url_for('org_owner.list_users'))
    
    # Security check: can only edit users from same organization
    if user.organization_id != current_user.organization_id:
        flash('You can only edit users from your organization', 'danger')
        return redirect(url_for('org_owner.list_users'))
    
    # Prevent editing admins
    if user.is_admin:
        flash('Cannot edit admin users', 'danger')
        return redirect(url_for('org_owner.list_users'))
    
    if request.method == 'POST':
        new_password = request.form.get('new_password', '').strip()
        is_org_owner = request.form.get('is_org_owner') == '1'
        
        # Org owners CAN promote users to org_owner (but NOT to admin)
        # Update org_owner status
        if user.is_org_owner != is_org_owner:
            user.update_org_owner_status(is_org_owner)
        
        # Update password if provided
        if new_password:
            user.update_password(new_password)
            flash(f'User {user.name} updated successfully', 'success')
        else:
            flash(f'User {user.name} information updated', 'success')
        
        return redirect(url_for('org_owner.list_users'))
    
    return render_template(
        'admin/user_form.html',
        mode='edit',
        user=user,
        is_org_owner_view=True,
        organization=current_user.organization
    )


@org_owner_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@org_owner_required
def delete_user(user_id):
    """Delete a user from the organization"""
    user = User.get_by_id(user_id)
    
    if not user:
        flash('User not found', 'danger')
        return redirect(url_for('org_owner.list_users'))
    
    # Security check: can only delete users from same organization
    if user.organization_id != current_user.organization_id:
        flash('You can only delete users from your organization', 'danger')
        return redirect(url_for('org_owner.list_users'))
    
    # Prevent deleting admins (but can delete other org owners)
    if user.is_admin:
        flash('Cannot delete admin users', 'danger')
        return redirect(url_for('org_owner.list_users'))
    
    # Prevent self-deletion
    if user.id == current_user.id:
        flash('Cannot delete yourself', 'danger')
        return redirect(url_for('org_owner.list_users'))
    
    user.delete()
    flash(f'User {user.name} deleted successfully', 'success')
    return redirect(url_for('org_owner.list_users'))


@org_owner_bp.route('/users/<int:user_id>/reset_password', methods=['GET', 'POST'])
@org_owner_required
def reset_password(user_id):
    """Reset a user's password"""
    user = User.get_by_id(user_id)
    
    if not user:
        flash('User not found', 'danger')
        return redirect(url_for('org_owner.list_users'))
    
    # Security check: can only reset passwords for users in same organization
    if user.organization_id != current_user.organization_id:
        flash('You can only reset passwords for users in your organization', 'danger')
        return redirect(url_for('org_owner.list_users'))
    
    # Prevent resetting admin passwords
    if user.is_admin:
        flash('Cannot reset admin passwords', 'danger')
        return redirect(url_for('org_owner.list_users'))
    
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if not new_password or not confirm_password:
            flash('Both password fields are required', 'danger')
            return redirect(url_for('org_owner.reset_password', user_id=user_id))
        
        if new_password != confirm_password:
            flash('Passwords do not match', 'danger')
            return redirect(url_for('org_owner.reset_password', user_id=user_id))
        
        user.update_password(new_password)
        flash(f'Password reset successfully for {user.name}', 'success')
        return redirect(url_for('org_owner.list_users'))
    
    return render_template('org_owner/reset_password.html', user=user)

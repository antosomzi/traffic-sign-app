"""Organization service for multi-tenancy logic"""

from models.recording import Recording
from models.organization import Organization


class OrganizationService:
    """Service for handling organization-related operations"""
    
    @staticmethod
    def get_recordings_for_organization(organization_id, user_ids=None, sort_by='upload_date', sort_order='desc'):
        """
        Get all recording IDs belonging to an organization with optional filtering/sorting
        
        Args:
            organization_id: ID of the organization
            user_ids: Optional list of user IDs to filter by
            sort_by: 'upload_date' or 'recording_date'
            sort_order: 'asc' or 'desc'
        
        Returns:
            List of Recording objects
        """
        return Recording.get_by_organization(
            organization_id, 
            user_ids=user_ids, 
            sort_by=sort_by, 
            sort_order=sort_order
        )
    
    @staticmethod
    def get_recording_ids_for_organization(organization_id):
        """
        Get all recording IDs (strings) belonging to an organization.
        For backward compatibility with existing code.
        
        Args:
            organization_id: ID of the organization
        
        Returns:
            List of recording IDs (strings)
        """
        recordings = Recording.get_by_organization(organization_id)
        return [rec.id for rec in recordings]
    
    @staticmethod
    def get_users_with_recordings(organization_id):
        """
        Get list of users who have uploaded recordings in an organization.
        Useful for populating filter dropdowns.
        
        Args:
            organization_id: ID of the organization
        
        Returns:
            List of dicts with user id and name
        """
        return Recording.get_users_with_recordings(organization_id)
    
    @staticmethod
    def can_access_recording(user, recording_id):
        """
        Check if a user can access a specific recording
        
        Args:
            user: User object
            recording_id: Recording ID string
        
        Returns:
            Boolean indicating access permission
        """
        recording = Recording.get_by_id(recording_id)
        
        if not recording:
            return False
        
        return recording.organization_id == user.organization_id
    
    @staticmethod
    def register_recording(recording_id, organization_id, user_id=None):
        """
        Register a new recording for an organization
        
        Args:
            recording_id: Recording ID string
            organization_id: Organization ID
            user_id: User ID of the uploader (optional)
        
        Returns:
            Recording object
        """
        return Recording.create(recording_id, organization_id, user_id=user_id)
    
    @staticmethod
    def delete_recording(recording_id):
        """
        Delete a recording from the database
        
        Args:
            recording_id: Recording ID string
        """
        Recording.delete(recording_id)

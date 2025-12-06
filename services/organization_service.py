"""Organization service for multi-tenancy logic"""

from models.recording import Recording
from models.organization import Organization


class OrganizationService:
    """Service for handling organization-related operations"""
    
    @staticmethod
    def get_recordings_for_organization(organization_id):
        """
        Get all recording IDs belonging to an organization
        
        Args:
            organization_id: ID of the organization
        
        Returns:
            List of recording IDs (strings)
        """
        recordings = Recording.get_by_organization(organization_id)
        return [rec.id for rec in recordings]
    
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
    def register_recording(recording_id, organization_id):
        """
        Register a new recording for an organization
        
        Args:
            recording_id: Recording ID string
            organization_id: Organization ID
        
        Returns:
            Recording object
        """
        return Recording.create(recording_id, organization_id)
    
    @staticmethod
    def delete_recording(recording_id):
        """
        Delete a recording from the database
        
        Args:
            recording_id: Recording ID string
        """
        Recording.delete(recording_id)

"""S3 service for video storage management."""

import os
import boto3
from botocore.exceptions import ClientError
from config import Config


class S3VideoService:
    """Service for managing video files in S3."""
    
    def __init__(self):
        """Initialize S3 client."""
        self.s3_client = boto3.client('s3', region_name=Config.S3_REGION)
        self.bucket = Config.S3_BUCKET_NAME
        self.prefix = Config.S3_VIDEO_PREFIX
    
    def upload_video(self, local_path: str, recording_id: str) -> str:
        """
        Upload video file to S3.
        
        Args:
            local_path: Path to local video file
            recording_id: Recording identifier
            
        Returns:
            S3 key of uploaded file
        """
        filename = os.path.basename(local_path)
        s3_key = f"{self.prefix}{recording_id}/{filename}"
        
        print(f"📤 Uploading video to S3: {s3_key}")
        self.s3_client.upload_file(
            local_path,
            self.bucket,
            s3_key,
            ExtraArgs={'StorageClass': 'STANDARD'}
        )
        print(f"✅ Video uploaded to S3: {s3_key}")
        
        return s3_key
    
    def download_video(self, s3_key: str, local_path: str) -> bool:
        """
        Download video file from S3.
        
        Args:
            s3_key: S3 key of the video file
            local_path: Local path to save the file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            print(f"📥 Downloading video from S3: {s3_key}")
            self.s3_client.download_file(self.bucket, s3_key, local_path)
            print(f"✅ Video downloaded to: {local_path}")
            return True
        except ClientError as e:
            print(f"❌ Failed to download video from S3: {e}")
            return False
    
    def delete_video(self, s3_key: str) -> bool:
        """
        Delete video file from S3.
        
        Args:
            s3_key: S3 key of the video file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            print(f"🗑️ Deleting video from S3: {s3_key}")
            self.s3_client.delete_object(Bucket=self.bucket, Key=s3_key)
            print(f"✅ Video deleted from S3: {s3_key}")
            return True
        except ClientError as e:
            print(f"❌ Failed to delete video from S3: {e}")
            return False
    
    def video_exists(self, s3_key: str) -> bool:
        """
        Check if video exists in S3.
        
        Args:
            s3_key: S3 key of the video file
            
        Returns:
            True if exists, False otherwise
        """
        try:
            self.s3_client.head_object(Bucket=self.bucket, Key=s3_key)
            return True
        except ClientError:
            return False


def find_video_in_recording(recording_path: str) -> str | None:
    """
    Find video file (.mp4) in a recording folder.
    
    Args:
        recording_path: Path to recording folder
        
    Returns:
        Path to video file or None
    """
    for root, dirs, files in os.walk(recording_path):
        if "camera" in root:
            for f in files:
                if f.lower().endswith(".mp4"):
                    return os.path.join(root, f)
    return None


def get_camera_folder(recording_path: str) -> str | None:
    """
    Find camera folder in a recording.
    
    Args:
        recording_path: Path to recording folder
        
    Returns:
        Path to camera folder or None
    """
    for root, dirs, files in os.walk(recording_path):
        if os.path.basename(root) == "camera":
            return root
    return None

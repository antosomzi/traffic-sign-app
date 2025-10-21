"""Application Configuration"""

import os
import redis
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    """Flask application configuration"""
    
    # Auto-detect environment (EC2 vs local)
    if os.path.exists("/home/ec2-user"):
        BASE_PATH = "/home/ec2-user"
    else:
        BASE_PATH = os.path.dirname(os.path.abspath(__file__))
    
    # Folder paths
    UPLOAD_FOLDER = os.path.join(BASE_PATH, "uploads")
    EXTRACT_FOLDER = os.path.join(BASE_PATH, "recordings")
    TEMP_EXTRACT_FOLDER = os.path.join(BASE_PATH, "temp_extracts")
    
    # File upload settings
    ALLOWED_EXTENSIONS = {"zip", "tar", "tar.gz", "tgz"}
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024 * 1024  # 8 GiB
    
    # Create folders if they don't exist
    @classmethod
    def init_folders(cls):
        """Create necessary folders if they don't exist"""
        os.makedirs(cls.UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(cls.EXTRACT_FOLDER, exist_ok=True)
        os.makedirs(cls.TEMP_EXTRACT_FOLDER, exist_ok=True)


# Redis client initialization
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
if REDIS_PASSWORD:
    redis_client = redis.Redis(
        host='localhost',
        port=6379,
        db=0,
        password=REDIS_PASSWORD,
        decode_responses=True
    )
else:
    redis_client = redis.Redis(
        host='localhost',
        port=6379,
        db=0,
        decode_responses=True
    )


# Celery availability check
try:
    from tasks import run_pipeline_task
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    print("Warning: Celery not available. Pipeline tasks will not be queued.")

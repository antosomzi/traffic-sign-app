"""Redis service for managing extraction progress"""

import json
from config import redis_client


class RedisProgressService:
    """Service for managing extraction progress in Redis"""
    
    @staticmethod
    def get_extraction_progress(job_id):
        """Get extraction progress from Redis"""
        data = redis_client.get(f"extraction:{job_id}")
        if data:
            return json.loads(data)
        return None
    
    @staticmethod
    def set_extraction_progress(job_id, progress_dict):
        """Set extraction progress in Redis with 1 hour expiry"""
        redis_client.setex(
            f"extraction:{job_id}",
            3600,
            json.dumps(progress_dict)
        )
    
    @staticmethod
    def update_extraction_progress(job_id, **kwargs):
        """Update specific fields in extraction progress"""
        prog = RedisProgressService.get_extraction_progress(job_id)
        if prog:
            prog.update(kwargs)
            RedisProgressService.set_extraction_progress(job_id, prog)

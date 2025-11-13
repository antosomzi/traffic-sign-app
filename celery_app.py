from celery import Celery
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Redis configuration with optional password
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

if REDIS_PASSWORD:
    redis_url = f"redis://:{REDIS_PASSWORD}@localhost:6379/0"
else:
    redis_url = "redis://localhost:6379/0"

celery = Celery(
    "ml_pipeline",
    broker=redis_url,
    backend=redis_url
)

# Configuration
celery.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    imports=('pipeline.celery_tasks',),
)

# Import tasks to register them with Celery
import pipeline.celery_tasks  # noqa: F401

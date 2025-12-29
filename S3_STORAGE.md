# S3 Video Storage

## Overview

Video files (`.mp4`) are stored on **Amazon S3** instead of EFS to reduce storage costs. All other files (CSV, JSON, calibration) remain on EFS for fast access.

**Cost comparison:**
- EFS: ~$0.30/GB/month
- S3 Standard: ~$0.023/GB/month (13x cheaper)

## Structure

```
s3://traffic-sign-videos/
└── videos/
    ├── prod/                          # Production uploads
    │   └── <recording_id>/
    │       └── <video>.mp4
    └── local/                         # Local development uploads
        └── <recording_id>/
            └── <video>.mp4
```

Environment is auto-detected: `/home/ec2-user` exists → `prod`, otherwise → `local`.

## Data Flow

```
UPLOAD
  └── Extract ZIP → Upload video to S3 → Delete local video
                          ↓
              status.json: video_s3_key = "videos/prod/<id>/video.mp4"

PIPELINE
  └── Download video from S3 → Run pipeline → Delete local video

DOWNLOAD
  └── Download video from S3 → Include in ZIP → Return to user

DELETE
  └── Delete from S3 + Delete folder from EFS
```

## Configuration

In `config.py`:
```python
S3_BUCKET_NAME = "traffic-sign-videos"
S3_REGION = "us-east-2"
S3_VIDEO_PREFIX = f"videos/{ENVIRONMENT}/"
```

## Migration

To migrate existing videos from EFS to S3:

```bash
# Dry run (see what would be migrated)
python migrations/migrate_videos_to_s3.py --dry-run

# Migrate (upload to S3, keep local files)
python migrations/migrate_videos_to_s3.py

# Migrate and delete local files
python migrations/migrate_videos_to_s3.py --delete-local
```

## AWS Requirements

EC2 instance needs IAM permissions:
```json
{
  "Effect": "Allow",
  "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
  "Resource": "arn:aws:s3:::traffic-sign-videos/*"
}
```

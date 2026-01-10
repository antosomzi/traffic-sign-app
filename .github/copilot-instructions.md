# Traffic Sign ML Pipeline - AI Agent Instructions

## Architecture Overview

**3-Tier Asynchronous ML Processing System:**
- **Flask (app.py)**: Web interface for upload/validation, runs on Gunicorn with 4 workers
- **Celery (pipeline/celery_tasks.py)**: Asynchronous ML pipeline execution worker
- **Redis**: Message broker for Celery + shared state storage across Gunicorn workers
- **S3**: Video storage (`.mp4` files) - 13x cheaper than EFS ($0.023/GB vs $0.30/GB)

**Critical Design Decision**: Multi-worker Gunicorn means each worker has separate memory. Redis stores extraction progress as JSON strings (key: `extraction:<job_id>`) so any worker can read another worker's upload status. Without this, status checks return 404 when handled by different workers.

## Authentication Architecture

**Dual authentication system** for web and mobile clients:

**Web (Flask-Login + Sessions):**
- Cookie-based sessions with HMAC signature using `SECRET_KEY`
- `login_user()` → Signed session cookie → `current_user` object on every request
- User loader callback: `@login_manager.user_loader` fetches user from DB via user_id
- Decorators: `@login_required`, `@admin_required`, `@org_owner_required` (see `decorators/auth_decorators.py`)
- Session verification: Cookie signature recalculated on every request, invalid if tampered

**Mobile (Token-Based API):**
- Bearer tokens stored in `auth_tokens` table (365-day validity)
- Token generation: `secrets.token_urlsafe(32)` → cryptographically secure 32-byte string
- Request flow: `Authorization: Bearer <token>` → DB lookup → Check expiration → Populate `g.current_user`
- Mobile routes: `/api/login`, `/api/recordings` in `routes/mobile_auth_routes.py`
- Decorator: `@mobile_auth_required` validates token and loads user into `g.current_user`

**Key difference**: Web uses stateful sessions (server-side), mobile uses stateless tokens (client-side). Both verify on every request but use different mechanisms.

## Data Flow

1. **Upload** → Flask validates ZIP structure → Extracts to temp → Videos uploaded to S3 → Validates folder hierarchy → Moves atomically to `recordings/<recording_id>/`
2. **Processing** → Celery task queued → Downloads video from S3 → Runs 8-stage ML pipeline (`s0_detection` through `s7_export_csv`) → Deletes local video
3. **Results** → Downloads available at `/download/<recording_id>` (downloads video from S3, bundles with CSVs, returns ZIP with `supports.csv` and `signs.csv`)

**S3 Video Storage** (`S3_STORAGE.md`):
- Videos stored at `s3://traffic-sign-videos/videos/{prod|local}/<recording_id>/<video>.mp4`
- Environment auto-detected: `/home/ec2-user` exists → `prod`, else → `local`
- `status.json` contains `video_s3_key` for tracking S3 location
- Migration: `python migrations/migrate_videos_to_s3.py` (supports `--dry-run` and `--delete-local`)
- IAM permissions: `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject` on bucket

## Dual Execution Modes

Toggle with environment variable `USE_GPU_INSTANCE`:
- **false** (default): Runs pipeline locally via `simulate_pipeline.sh`
- **true**: Launches AWS EC2 GPU instance (`pipeline/gpu/runner.py`), executes via SSH, auto-stops instance after completion

GPU mode architecture:
- Main EC2 instance (t3.large) manages lifecycle
- GPU instance (g6e.xlarge) with Deep Learning AMI
- Shared EFS filesystem (`/home/ec2-user`) for recordings access
- See `pipeline/gpu/config.py` for instance IDs, regions, EFS DNS

## Critical File Structure

Strict validation in `validate_structure()` enforces:
```
<recording_id>/
└── <device_id>/
    └── <imei_folder>/
        ├── acceleration/<recording_id>_acc.csv
        ├── calibration/*_calibration.csv (≥1 file)
        ├── camera/<recording_id>_cam_<recording_id>.mp4 + camera_params.csv
        ├── location/<recording_id>_loc.csv + <recording_id>_loc_cleaned.csv
        └── processed/<recording_id>_processed_acc.csv + <recording_id>_processed_loc.csv
```

Automatic cleanup: Removes `__MACOSX/`, `.DS_Store`, `._*` files during extraction.

## Development Workflow

**Local setup requires 3 terminals:**
```bash
# Terminal 1
redis-server

# Terminal 2  
celery -A celery_app worker --loglevel=INFO

# Terminal 3
python app.py  # Dev mode (single worker, auto-reload)
```

**Production uses systemd services:**
- `flask-app.service`: Runs `start_gunicorn.sh` (4 workers, port 5000)
- `celery-worker.service`: Background task processing
- Both auto-start on boot, auto-restart on crash

## Key Conventions

- **Path detection**: Auto-detects EC2 (`/home/ec2-user` exists) vs local (script directory) for `BASE_PATH`
- **Redis auth**: Controlled by `.env` file's `REDIS_PASSWORD` (optional for local, required for production)
- **Job IDs**: UUID4 for extraction progress tracking (separate from `recording_id`)
- **Status tracking**: `status.json` in each recording folder (fields: `status`, `message`, `timestamp`, `video_s3_key`)
- **Atomic operations**: Extract to `temp_extracts/<job_id>/`, validate, upload video to S3, then move to `recordings/` (prevents partial uploads)

## Job Queue & Status Tracking (`JOB_QUEUE_STATUS.md`)

**Redis Progress Object** (key: `extraction:<job_id>`):
```json
{
  "status": "preparing|running|done|error",
  "phase": "reading|writing|extracting|running",
  "progress_percent": 0-100,
  "total_files": 100,
  "extracted_files": 50,
  "extract_size": 12345678,
  "recording_id": "2024_05_20_23_32_53_415",
  "error_msg": "...",
  "error_details": {}
}
```

**Status Progression**: `reading` → `preparing/writing` → `preparing/extracting` → `running` → `done/error`
- Updates via `RedisProgressService.set_extraction_progress(job_id, progress_dict)`
- Frontend polls `/extract_status/<job_id>` every 2s during upload
- When extraction completes (`status=done`), Celery task queued for ML pipeline

## Status Page Polling (`STATUS_POLLING.md`)

**Server-Side Rendering + Client-Side Updates:**
- Initial render: Jinja template with embedded JSON in `<script id="recordings-data">`
- Routes: `GET /status` (HTML), `GET /status/data` (JSON) - both use `_collect_recordings()` helper
- Polling: JS fetches `/status/data` every 10s when any recording is `processing`/`validated`
- Data shape includes: `id`, `status`, `message`, `timestamp`, `show_steps`, `steps[]` with `{name, done}` for each pipeline stage
- Stage detection: Inspects `result_pipeline_stable/s*/` folders for `output.json` presence
- DOM updates: `renderRecordings()` regenerates HTML, `escapeHtml()` sanitizes dynamic content, `attachActionListeners()` rebinds click events

## Testing & Debugging

- **Pipeline simulation**: `simulate_pipeline.sh <recording_path>` creates mock outputs (5s per stage)
- **Test upload**: Use `recordings/2024_05_20_23_32_53_415/` as reference valid structure
- **Check Celery tasks**: Monitor terminal 2 for task execution logs
- **Redis inspection**: `redis-cli -a <password> GET extraction:<job_id>` to view progress JSON

## Common Gotchas

1. **Missing Redis password**: Production requires `REDIS_PASSWORD` in `.env` AND Redis config (`/etc/redis6/redis6.conf`)
2. **GPU SSH key**: Must exist at `/home/ec2-user/traffic-sign-inventory_keypair.pem` with correct permissions (400)
3. **IAM role requirement**: Main EC2 instance needs `AmazonEC2FullAccess` to start/stop GPU instance
4. **EFS mount**: GPU instance must mount EFS before pipeline execution (`mount_cmd` in `pipeline/gpu/runner.py`)
5. **Gunicorn timeouts**: Set `--timeout 300` for large uploads (8GB max, configured in `MAX_CONTENT_LENGTH`)

## External Dependencies

- **AWS Services**: EC2 (boto3), EFS, Security Groups (`sg-0906d54ac3d704022`, `sg-0fc71fc185fe9b5e6`)
- **Network**: VPC `vpc-0933dfb2c976a7d1b`, Subnet `subnet-098dc7573fb6bf8bd`, Region `us-east-2`
- **SSH**: paramiko for GPU instance command execution (60s wait after instance running for SSH readiness)

## Reference Files

- **Authentication**: `AUTHENTICATION.md` (web sessions), `AUTHENTICATION_MOBILE.md` (mobile tokens)
- **Storage**: `S3_STORAGE.md` (video S3 integration)
- **Status Systems**: `JOB_QUEUE_STATUS.md` (Redis job tracking), `STATUS_POLLING.md` (frontend polling)
- **Deployment**: `README.md`, `DEPLOYMENT.md`
- **GPU configuration**: `pipeline/gpu/config.py`
- **Routes**: Split across `routes/` modules (auth, upload, status, download, delete, rerun, admin, org_owner)
- **Services**: Modular services in `services/` (redis, s3, extraction, validation, deletion, download, organization)
- **Decorators**: `decorators/auth_decorators.py` for access control

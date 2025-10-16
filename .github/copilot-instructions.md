# Traffic Sign ML Pipeline - AI Agent Instructions

## Architecture Overview

**3-Tier Asynchronous ML Processing System:**
- **Flask (app.py)**: Web interface for upload/validation, runs on Gunicorn with 4 workers
- **Celery (tasks.py)**: Asynchronous ML pipeline execution worker
- **Redis**: Message broker for Celery + shared state storage across Gunicorn workers

**Critical Design Decision**: Multi-worker Gunicorn means each worker has separate memory. Redis stores extraction progress as JSON strings (key: `extraction:<job_id>`) so any worker can read another worker's upload status. Without this, status checks return 404 when handled by different workers.

## Data Flow

1. **Upload** → Flask validates ZIP structure → Extracts to temp → Validates folder hierarchy → Moves atomically to `recordings/<recording_id>/`
2. **Processing** → Celery task queued → Runs 8-stage ML pipeline (`s0_detection` through `s7_export_csv`)
3. **Results** → Downloads available at `/download/<recording_id>` (returns ZIP with `supports.csv` and `signs.csv`)

## Dual Execution Modes

Toggle with environment variable `USE_GPU_INSTANCE`:
- **false** (default): Runs pipeline locally via `simulate_pipeline.sh`
- **true**: Launches AWS EC2 GPU instance (`gpu_pipeline_runner.py`), executes via SSH, auto-stops instance after completion

GPU mode architecture:
- Main EC2 instance (t3.large) manages lifecycle
- GPU instance (g6e.xlarge) with Deep Learning AMI
- Shared EFS filesystem (`/home/ec2-user`) for recordings access
- See `gpu_config.py` for instance IDs, regions, EFS DNS

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
celery -A tasks worker --loglevel=INFO

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
- **Status tracking**: `status.json` in each recording folder (fields: `status`, `message`, `timestamp`)
- **Atomic operations**: Extract to `temp_extracts/<job_id>/`, validate, then move to `recordings/` (prevents partial uploads)

## Testing & Debugging

- **Pipeline simulation**: `simulate_pipeline.sh <recording_path>` creates mock outputs (5s per stage)
- **Test upload**: Use `recordings/2024_05_20_23_32_53_415/` as reference valid structure
- **Check Celery tasks**: Monitor terminal 2 for task execution logs
- **Redis inspection**: `redis-cli -a <password> GET extraction:<job_id>` to view progress JSON

## Common Gotchas

1. **Missing Redis password**: Production requires `REDIS_PASSWORD` in `.env` AND Redis config (`/etc/redis6/redis6.conf`)
2. **GPU SSH key**: Must exist at `/home/ec2-user/traffic-sign-inventory_keypair.pem` with correct permissions (400)
3. **IAM role requirement**: Main EC2 instance needs `AmazonEC2FullAccess` to start/stop GPU instance
4. **EFS mount**: GPU instance must mount EFS before pipeline execution (`mount_cmd` in `gpu_pipeline_runner.py`)
5. **Gunicorn timeouts**: Set `--timeout 300` for large uploads (8GB max, configured in `MAX_CONTENT_LENGTH`)

## External Dependencies

- **AWS Services**: EC2 (boto3), EFS, Security Groups (`sg-0906d54ac3d704022`, `sg-0fc71fc185fe9b5e6`)
- **Network**: VPC `vpc-0933dfb2c976a7d1b`, Subnet `subnet-098dc7573fb6bf8bd`, Region `us-east-2`
- **SSH**: paramiko for GPU instance command execution (60s wait after instance running for SSH readiness)

## Reference Files

- Architecture details: `README.md`, `DEPLOYMENT.md`
- GPU configuration: `EC2_GPU_CONFIG.md`, `gpu_config.py`
- Routes: `app.py` lines 378-645 (upload, status, download endpoints)
- Validation logic: `app.py` lines 87-195 (strict hierarchy enforcement)

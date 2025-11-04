
# Traffic Sign ML Pipeline

> **ℹ️ All deployment, maintenance, and CI/CD commands and processes are documented in detail in [`DEPLOYMENT.md`](DEPLOYMENT.md). Please refer to that file for any production setup, server management, or automation instructions.**

Web application for uploading, validating, and asynchronously processing traffic sign recordings through a machine learning pipeline.

## 📑 Table of Contents

- [Architecture](#-architecture)
- [Data Flow](#-flow)
- [Project Structure](#-project-structure)
- [File Storage Structure](#-file-storage-structure)
- [Installation](#-installation)
- [Usage](#-usage)
- [Expected Input Data Structure](#-expected-input-data-structure)
- [Configuration](#-configuration)
- [Security](#-security)

## 🏗️ Architecture

- **Flask**: Web interface for file upload, validation, and result delivery
- **Redis**: 
  - Message broker for Celery task queue
  - Shared state storage for extraction progress (critical for multi-worker Gunicorn)
- **Celery**: Asynchronous worker for ML pipeline processing
- **Gunicorn**: Production WSGI server with 4 worker processes

### Multi-Worker Architecture

Production uses **Gunicorn with 4 workers**. Since each worker has separate memory, Redis ensures extraction progress is shared across all workers:

```
Request 1 (Upload) → Worker #1 → Stores progress in Redis
Request 2 (Status) → Worker #3 → Reads progress from Redis ✅
Request 3 (Status) → Worker #2 → Reads progress from Redis ✅
```

Without Redis, status checks would return 404 when handled by different workers.

### Execution Modes

Toggle via `USE_GPU_INSTANCE` environment variable:
- **Local mode** (default): Runs pipeline on the same instance
- **GPU mode**: Launches AWS EC2 GPU instance, executes via SSH, auto-stops after completion

For detailed deployment and GPU configuration, see **[DEPLOYMENT.md](DEPLOYMENT.md)**.

## ✨ FLow

1. User uploads file → extraction job starts (tracked by `job_id`)
2. Extraction completes → status set to `done` in Redis
3. Celery task is queued for ML pipeline (using `recording_id`)
4. Celery worker processes the task asynchronously
5. Pipeline results and status are written to the recording folder
6. User can download results or check status via the web interface

*See [`JOB_QUEUE_STATUS.md`](JOB_QUEUE_STATUS.md) for a detailed explanation of the job queue, status tracking, and Celery integration.*

## 📁 Project Structure

```
app/
├── app.py                      # Flask application entry point 
├── config.py                   # Centralized configuration management
├── celery_app.py               # Celery configuration
├── tasks.py                    # Async pipeline tasks
├── gpu_pipeline_runner.py      # GPU instance pipeline execution
├── gpu_config.py               # AWS GPU configuration
├── simulate_pipeline.sh        # Pipeline simulation script
├── start_gunicorn.sh           # Production server startup
├── requirements.txt            # Python dependencies
├── .env                        # Environment variables
├── DEPLOYMENT.md               # EC2 deployment guide
├── EC2_GPU_CONFIG.md           # GPU instance setup
├── routes/                     # Blueprint-based routing
│   ├── upload_routes.py       # Upload & extraction endpoints
│   ├── status_routes.py       # Status monitoring
│   └── download_routes.py     # Result downloads
├── services/                   # Business logic layer
│   ├── redis_service.py       # Redis operations
│   ├── validation_service.py  # Structure validation
│   └── extraction_service.py  # ZIP extraction logic
├── utils/                      # Utility functions
│   ├── file_utils.py          # File operations
│   └── cleanup_utils.py       # macOS file cleanup
├── templates/
│   ├── upload.html            # Upload interface
│   └── status.html            # Status monitoring
├── recordings/                 # Validated recordings
├── uploads/                    # Uploaded files
└── temp_extracts/             # Temporary extraction folder
```

## � File Storage Structure

**Production paths** (on EC2 main instance):
```
/home/ec2-user/
├── uploads/              # Uploaded ZIP files (persistent storage)
│   └── <uuid>_<recording_id>.zip
├── recordings/           # Extracted and validated recordings
│   └── <recording_id>/
│       ├── status.json   # Processing status tracking
│       ├── result_pipeline_stable/  # ML pipeline outputs
│       └── <device_id>/  # Original recording data
├── temp_extracts/        # Temporary extraction during validation
│   └── <job_id>/         # Cleaned up after validation
└── app/                  # Application files
```

**Local development paths**:
```
app/
├── uploads/              # Uploaded ZIP files
├── recordings/           # Validated recordings
└── temp_extracts/        # Temporary extraction
```

**Storage notes:**
- `uploads/` folder stores all uploaded ZIP files until manually deleted
- EFS-mounted filesystem (`/home/ec2-user`) enables GPU instance to access recordings
- `.gitignore` excludes all data folders from version control
- Automatic cleanup removes `__MACOSX/`, `.DS_Store`, `._*` files during extraction

## �🚀 Installation

### Prerequisites

- Python 3.11+
- Redis 6+
- Git

### Local Setup

**1. Clone the repository**
```bash
git clone <repository-url>
cd app
```

**2. Create virtual environment**
```bash
python3 -m venv venv
source venv/bin/activate
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Install and start Redis**

macOS (Homebrew):
```bash
brew install redis
redis-server
```

Ubuntu/Debian:
```bash
sudo apt-get install redis-server
sudo systemctl start redis
```

**5. Make scripts executable**
```bash
chmod +x simulate_pipeline.sh start_gunicorn.sh
```

### Running Locally (Development)

Open **3 terminals**:

```bash
# Terminal 1 - Redis
redis-server

# Terminal 2 - Celery Worker
celery -A tasks worker --loglevel=INFO

# Terminal 3 - Flask App
python app.py
```

Access the application at: **http://localhost:5000**

## 📝 Usage

### 1. Upload Recording

1. Navigate to `http://localhost:5000`
2. Drag-and-drop or select a folder containing your `.mp4` and GPS `.csv` files, organized in the required structure (see below).
3. The folder will be automatically zipped client-side (store mode, equivalent to `zip -0`) before being sent to the server.
4. Click "Upload and Validate".
5. The system will:
  - Extract the received zip
  - Validate the folder structure
  - Launch the pipeline if the structure is correct

### 2. Monitor Processing

- Click "View Recording Status"
- Track all recordings and their pipeline progress
- Page auto-refreshes every 10 seconds

### 3. Download Results

- Once processing is complete, click "Download Results"
- Downloads a ZIP containing `supports.csv` and `signs.csv`

## 🗂️ Expected Input Data Structure


The uploaded folder (which will be zipped client-side) must contain exactly one root folder with the following minimal structure:

```
recording_id/
  └── device_id/
      └── imei_folder/
          ├── camera/
          │     └── <video_file>.mp4
          └── location/
                ├── <file1>.csv
                └── <file2>.csv
```

**Notes:**
- macOS system files (`__MACOSX/`, `.DS_Store`, `._*`) are automatically removed
- Structure validation is strict – only the above folders/files are required

## ⚙️ Configuration

### Environment Variables

Create a `.env` file (optional for local development):

```bash
# Redis password (required for production)
REDIS_PASSWORD=your_password_here

# Execution mode (local or GPU instance)
USE_GPU_INSTANCE=false

# Flask environment
FLASK_ENV=production
```

## � Security

- **ZipSlip protection**: Validates file paths during extraction
- **Strict validation**: Enforces expected folder structure
- **File size limit**: 8 GB maximum
- **Allowed formats**: ZIP, TAR, TAR.GZ, TGZ
- **Automatic cleanup**: Removes partial uploads on validation failure
- **Redis authentication**: Required for production environments


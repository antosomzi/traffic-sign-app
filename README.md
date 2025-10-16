# Traffic Sign ML Pipeline

Web application for uploading, validating, and asynchronously processing traffic sign recordings through a machine learning pipeline.

## 📑 Table of Contents

- [Architecture](#-architecture)
- [Features](#-features)
- [Project Structure](#-project-structure)
- [Installation](#-installation)
- [Usage](#-usage)
- [Expected Data Structure](#-expected-data-structure)
- [Configuration](#-configuration)
- [Security](#-security)
- [Technology Stack](#-technology-stack)

## 🏗️ Architecture

**3-Tier Asynchronous Processing System:**

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

## ✨ Features

- **Drag-and-drop file upload** with real-time progress tracking
- **Strict validation** of recording structure before processing
- **Asynchronous processing** with status monitoring
- **Automatic cleanup** of macOS system files (`__MACOSX/`, `.DS_Store`)
- **Atomic operations** (extract → validate → move)
- **Multi-worker safe** progress tracking via Redis
- **GPU instance orchestration** for compute-intensive ML tasks
- **Downloadable results** (CSV exports of detected traffic signs)

## 📁 Project Structure

```
app/
├── app.py                      # Flask application & routes
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
├── templates/
│   ├── upload.html            # Upload interface
│   └── status.html            # Status monitoring
├── recordings/                 # Validated recordings
├── uploads/                    # Uploaded files
└── temp_extracts/             # Temporary extraction folder
```

## 🚀 Installation

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
2. Drag-and-drop or select a ZIP file
3. Click "Upload and Validate"
4. The system will:
   - Extract the archive
   - Validate the folder structure
   - Queue a Celery task if valid

### 2. Monitor Processing

- Click "View Recording Status"
- Track all recordings and their pipeline progress
- Page auto-refreshes every 10 seconds

### 3. Download Results

- Once processing is complete, click "Download Results"
- Downloads a ZIP containing `supports.csv` and `signs.csv`

## 🗂️ Expected Data Structure

The uploaded ZIP must contain exactly one root folder with the following structure:

```
recording_id/
  └── device_id/
      └── imei_folder/
          ├── acceleration/
          │     └── recording_id_acc.csv
          ├── calibration/
          │     └── *_calibration.csv (at least 1 file)
          ├── camera/
          │     ├── recording_id_cam_recording_id.mp4
          │     └── camera_params.csv
          ├── location/
          │     ├── recording_id_loc.csv
          │     └── recording_id_loc_cleaned.csv
          └── processed/
                ├── recording_id_processed_acc.csv
                └── recording_id_processed_loc.csv
```

**Notes:**
- macOS system files (`__MACOSX/`, `.DS_Store`, `._*`) are automatically removed
- Structure validation is strict - all folders and files must be present

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

**TTL**: 1 hour (auto-cleanup)

## � Security

- **ZipSlip protection**: Validates file paths during extraction
- **Strict validation**: Enforces expected folder structure
- **File size limit**: 8 GB maximum
- **Allowed formats**: ZIP, TAR, TAR.GZ, TGZ
- **Automatic cleanup**: Removes partial uploads on validation failure
- **Redis authentication**: Required for production environments

## �️ Technology Stack

- **Backend**: Flask 3.0, Gunicorn 21.2
- **Task Queue**: Celery 5.3, Redis 5.0
- **AWS**: boto3 1.34 (EC2, EFS)
- **SSH**: paramiko 3.3
- **Frontend**: Vanilla JavaScript (no framework)
- **UI Design**: Modern flat design with blue accent (#3b82f6)

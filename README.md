# Traffic Sign ML Pipeline

Web application for uploading, validating, and asynchronously processing traffic sign recordings through a machine learning pipeline.

## 📑 Table of Contents

- [Architecture](#-architecture)
- [Features](#-features)
- [Project Structure](#-project-structure)
- [Installation## 🛠️ Technology Stack

- **Backend**: Flask 3.0, Gunicorn 21.2
- **Task Queue**: Celery 5.3, Redis 5.0
- **AWS**: boto3 1.34 (EC2, EFS)
- **SSH**: paramiko 3.3
- **Frontend**: Vanilla JavaScript (no framework)
- **UI Design**: Modern flat design with blue accent (#3b82f6)

## 📚 Additional Documentation

- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Complete EC2 deployment guide with systemd configuration
- **[EC2_GPU_CONFIG.md](EC2_GPU_CONFIG.md)** - GPU instance setup and network configuration
- **[.github/copilot-instructions.md](.github/copilot-instructions.md)** - AI agent development guidelines

## 💡 Key Design Decisions

- **Redis for state sharing**: Solves multi-worker Gunicorn state synchronization
- **Atomic operations**: Extract → validate → move prevents partial uploads
- **Auto-cleanup**: Removes macOS artifacts automatically
- **Dual execution modes**: Flexibility between local and GPU processing
- **Real-time progress**: 300ms polling for smooth user experience
- **Status persistence**: `status.json` in each recording folder

## 🤝 Contributing

Contributions are welcome! Please ensure:
- Code follows existing patterns
- Changes are tested locally with 3-terminal setup
- Documentation is updated accordingly

## 📄 License

This project is part of the GRA traffic sign inventory system.

---

**Questions?** Refer to `DEPLOYMENT.md` for production setup or `.github/copilot-instructions.md` for development guidelines.allation)
- [Usage](#-usage)
- [Expected Data Structure](#-expected-data-structure)
- [ML Pipeline Stages](#-ml-pipeline-stages)
- [Configuration](#-configuration)
- [Deployment](#-deployment)
- [Security](#-security)

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

See `DEPLOYMENT.md` and `EC2_GPU_CONFIG.md` for GPU configuration details.

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
├── ec2_gpu_manager.py          # GPU instance orchestration
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

```
## 🗂️ Expected Data Structure

Strict validation enforces the following hierarchy:

```
<recording_id>/
└── <device_id>/
    └── <imei_folder>/
        ├── acceleration/
        │   └── <recording_id>_acc.csv
        ├── calibration/
        │   └── *_calibration.csv (at least 1 file)
        ├── camera/
        │   ├── <recording_id>_cam_<recording_id>.mp4
        │   └── camera_params.csv
        ├── location/
        │   ├── <recording_id>_loc.csv
        │   └── <recording_id>_loc_cleaned.csv
        └── processed/
            ├── <recording_id>_processed_acc.csv
            └── <recording_id>_processed_loc.csv
```

**Note**: macOS system files (`__MACOSX/`, `.DS_Store`, `._*`) are automatically removed during extraction.

## 📊 ML Pipeline Stages

8-stage processing pipeline:

1. **s0_detection** - Initial object detection
2. **s1_small_sign_filter** - Filter small signs
3. **s2_tracking** - Object tracking across frames
4. **s3_small_track_filter** - Filter short tracks
5. **s4_classification** - Sign classification
6. **s5_frames_gps_coordinates_extraction** - GPS extraction
7. **s6_localization** - Precise localization
8. **s7_export_csv** - Final CSV export

**Pipeline duration**: ~40 seconds (simulation), varies with real ML models.
```

## 📊 Pipeline de traitement

La pipeline comporte 8 étapes :

1. **s0_detection** - Détection initiale
2. **s1_small_sign_filter** - Filtrage des petits panneaux
3. **s2_tracking** - Suivi des objets
4. **s3_small_track_filter** - Filtrage des petites trajectoires
5. **s4_classification** - Classification des panneaux
6. **s5_frames_gps_coordinates_extraction** - Extraction des coordonnées GPS
7. **s6_localization** - Localisation
8. **s7_export_csv** - Export CSV final

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

### Redis Storage

Extraction progress is stored in Redis with the following format:

**Key**: `extraction:<job_id>`

**Value (JSON)**:
```json
{
  "status": "running",
  "total_files": 250,
  "extracted_files": 120,
  "extract_size": null,
  "recording_id": null,
  "error_msg": null,
  "error_details": null
}
```

**TTL**: 1 hour (auto-cleanup)

### Path Detection

The application auto-detects the environment:
- **EC2**: Uses `/home/ec2-user` if the directory exists
- **Local**: Uses script directory

## � Deployment

### Production (systemd services)

1. Install system dependencies:
```bash
sudo dnf update -y
sudo dnf install -y python3 python3-pip redis6 git
```

2. Configure Redis with password (see `DEPLOYMENT.md`)

3. Create systemd services:
   - `flask-app.service` - Gunicorn with 4 workers
   - `celery-worker.service` - Background task processing

4. Enable and start services:
```bash
sudo systemctl enable flask-app celery-worker
sudo systemctl start flask-app celery-worker
```

For detailed deployment instructions, see **`DEPLOYMENT.md`**.

For GPU instance configuration, see **`EC2_GPU_CONFIG.md`**.

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

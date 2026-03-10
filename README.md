
# Traffic Sign ML Pipeline

> **ℹ️ All deployment, maintenance, and CI/CD commands and processes are documented in detail in [`DEPLOYMENT.md`](DEPLOYMENT.md). Please refer to that file for any production setup, server management, or automation instructions.**

Web application for uploading, validating, and asynchronously processing traffic sign recordings through a machine learning pipeline.

## 📑 Table of Contents

- [Architecture](#-architecture)
- [Features](#-features)
- [Data Flow](#-flow)
- [Project Structure](#-project-structure)
- [File Storage Structure](#-file-storage-structure)
- [Installation](#-installation)
- [Usage](#-usage)
- [Expected Input Data Structure](#-expected-input-data-structure)
- [Security](#-security)

## 🏗️ Architecture

- **Flask**: Web interface for file upload, validation, and result delivery
- **Redis**: 
  - Message broker for Celery task queue
  - Shared state storage for extraction progress (critical for multi-worker Gunicorn)
- **Celery**: Asynchronous worker for ML pipeline processing
- **Gunicorn**: Production WSGI server with 4 worker processes
- **Nginx**: Reverse proxy for HTTPS/SSL (production only)
- **S3**: Video storage (reduces EFS costs). See [`S3_STORAGE.md`](S3_STORAGE.md)

### Execution Modes

Toggle via `USE_GPU_INSTANCE` environment variable:
- **Local mode** (default): Runs a local fake pipeline
- **GPU mode**: Launches AWS EC2 GPU instance, executes via SSH, auto-stops after completion

### Production Setup

In production, Nginx acts as a reverse proxy in front of Flask:
- Handles SSL/TLS termination (HTTPS)
- Forwards requests to Gunicorn (port 5000)
- Manages large file uploads (20GB limit)

For detailed deployment, Nginx configuration, and SSL setup, see **[DEPLOYMENT.md](DEPLOYMENT.md)**.

### Architecture Diagram

```
┌─────────────────────────────────────────────────────┐
│              NGINX (Reverse Proxy)                  │
│  • Handles HTTPS/SSL (port 443)                     │
│  • Forwards to Gunicorn (port 5000)                 │
│  • 20GB upload limit                                │
└─────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────┐
│           GUNICORN (4 workers)                      │
│  Handles HTTP requests in parallel                  │
│  • User 1: Upload                                   │
│  • User 2: Check status                             │
│  • User 3: Upload                                   │
│  • User 4: Download results                         │
└─────────────────────────────────────────────────────┘
                    ↓ .delay()
┌─────────────────────────────────────────────────────┐
│              REDIS QUEUE                            │
│  [Task 1] [Task 2] [Task 3] ...                    │
└─────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────┐
│         CELERY WORKER (1 worker)                    │
│  Processes ML pipelines sequentially                │
│  • Task 1 → 40 seconds                              │
│  • Task 2 → 40 seconds                              │
│  • Task 3 → 40 seconds                              │
└─────────────────────────────────────────────────────┘
```

**Key Points:**
- **Nginx**: SSL termination + reverse proxy (HTTPS → HTTP)
- **Gunicorn workers (4)**: Handle multiple HTTP requests simultaneously
- **Celery worker (1)**: Process one ML pipeline at a time
- Users can upload simultaneously, pipelines are queued

## ✨ Features

### Core Features
- **Asynchronous Processing**: Upload and process recordings without blocking
- **Multi-tenant Support**: Organization-based access control and data isolation
- **Role-based Access**: Admin, Organization Owner, and User roles with appropriate permissions
- **Dual Authentication System**: 
  - Web interface with Flask-Login sessions (see **[AUTHENTICATION.md](AUTHENTICATION.md)**)
  - Mobile API with Bearer token authentication (see **[AUTHENTICATION_MOBILE.md](AUTHENTICATION_MOBILE.md)**)
- **Video Storage in S3**: Cost-efficient video storage (13x cheaper than EFS)
- **Redis Caching**: Fast status checks and data retrieval with 1-hour TTL

### GPS Routes Visualization 🗺️
- **Interactive Map**: View all organization GPS traces on an interactive Leaflet map
- **Filtering**: Filter routes by date range, recording ID
- **Simplification**: Reduce coordinate density for faster rendering (RDP algorithm)
- **Statistics**: View total routes, GPS points, and route metadata
- **Auto-caching**: Redis-cached GeoJSON for instant loading

**Access**: `/org_owner/routes_map` (accessible to all authenticated users in an organization)

For detailed documentation on the GPS Routes feature, see **[GPS_ROUTES_MAP.md](GPS_ROUTES_MAP.md)**.

### Organization Route Filtering 🛣️
- **GeoJSON Upload**: Org owners/admins upload their road network as a GeoJSON file (`LineString`/`MultiLineString`)
- **Automatic Sign Filtering**: After pipeline completion, detected signs are filtered to only keep those within 50m of org routes
- **Pipeline Integration**: Runs automatically after `signs_merged.csv` is generated → outputs `signs_merged_filtered.csv`
- **Fallback**: If no routes are uploaded, all signs are kept (unfiltered)
- **Map Layer**: Org routes displayed as a black overlay on the GPS map (toggle on/off)
- **Storage**: GeoJSON files stored on disk at `org_routes/<org_id>/routes.geojson`
- **Dependencies**: `geopandas`, `shapely`, `pyproj`

**Access**: `/org_owner/routes` (org owners and admins only)

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
├── pipeline/                   # ML pipeline package
│   ├── __init__.py             # Package marker
│   ├── celery_tasks.py         # Celery tasks driving the pipeline
│   └── gpu/
│       ├── __init__.py         # GPU helpers package marker
│       ├── config.py           # AWS GPU configuration
│       └── runner.py           # GPU instance pipeline execution
├── simulate_pipeline.sh        # Pipeline simulation script
├── start_gunicorn.sh           # Production server startup
├── requirements.txt            # Python dependencies
├── .env                        # Environment variables
├── DEPLOYMENT.md               # EC2 deployment guide
├── EC2_GPU_CONFIG.md           # GPU instance setup
├── S3_STORAGE.md               # S3 video storage documentation
├── routes/                     # Blueprint-based routing
│   ├── upload_routes.py       # Upload & extraction endpoints
│   ├── status_routes.py       # Status monitoring
│   └── download_routes.py     # Result downloads
├── services/                   # Business logic layer
│   ├── redis_service.py       # Redis operations
│   ├── validation_service.py  # Structure validation
│   ├── extraction_service.py  # ZIP extraction logic
│   ├── s3_service.py          # S3 video storage operations
│   └── route_filtering_service.py # Org route filtering (50m buffer)
├── migrations/                 # Database and data migrations
│   └── migrate_videos_to_s3.py # Migrate existing videos to S3
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
├── org_routes/           # Organization road network GeoJSON files
│   └── <org_id>/
│       └── routes.geojson
├── temp_extracts/        # Temporary extraction during validation
│   └── <job_id>/         # Cleaned up after validation
└── app/                  # Application files
```

**Local development paths**:
```
app/
├── uploads/              # Uploaded ZIP files
├── recordings/           # Validated recordings
├── org_routes/           # Organization route GeoJSON files
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

**6. Configure environment (optional)**

Create a `.env` file for custom configuration:

```bash
# Redis password (required for production)
REDIS_PASSWORD=your_password_here

# Execution mode (local or GPU instance)
USE_GPU_INSTANCE=false
```

### Running Locally (Development)

Open **3 terminals**:

```bash
# Terminal 1 - Redis
redis-server

# Terminal 2 - Celery Worker
celery -A celery_app worker --loglevel=INFO

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

## 🔒 Security

- **Authentication**:
  - Web interface: Flask-Login with signed session cookies (see **[AUTHENTICATION.md](AUTHENTICATION.md)**)
  - Mobile API: Bearer token authentication with 365-day validity (see **[AUTHENTICATION_MOBILE.md](AUTHENTICATION_MOBILE.md)**)
  - B2B API: API key authentication via `X-API-Key` header (see **[API_B2B.md](API_B2B.md)**)
- **Role-based Access Control**: Admin, Organization Owner, and User roles with fine-grained permissions
- **Multi-tenant Isolation**: Organization-based data segregation
- **ZipSlip protection**: Validates file paths during extraction
- **Strict validation**: Enforces expected folder structure
- **File size limit**: 8 GB maximum
- **Allowed formats**: ZIP, TAR, TAR.GZ, TGZ
- **Automatic cleanup**: Removes partial uploads on validation failure
- **Redis authentication**: Required for production environments


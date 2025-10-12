#!/bin/bash

# Start script for production with Gunicorn

# Activate virtual environment
source venv/bin/activate

# Start Gunicorn with 4 worker processes
# -w 4: 4 worker processes (adjust based on CPU cores)
# -b 0.0.0.0:5000: Bind to all interfaces on port 5000
# --timeout 300: 5 minutes timeout for long uploads
# --log-level info: Log level
# app:app: module_name:flask_app_variable

gunicorn -w 4 \
    -b 0.0.0.0:5000 \
    --timeout 300 \
    --log-level info \
    --access-logfile logs/access.log \
    --error-logfile logs/error.log \
    app:app

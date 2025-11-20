# Deployment Guide

## Prerequisites

- EC2 instance running Amazon Linux 2023
- Python 3.11+
- Redis 6 installed
- Git installed

## Installation Steps

### 1. Install System Dependencies

```bash
sudo dnf update -y
sudo dnf install -y python3 python3-pip redis6 git
```

### 2. Clone Repository

```bash
cd /home/ec2-user
git clone <your-repo-url> app
cd app
```

### 3. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Configure Redis

```bash
# Edit Redis configuration
sudo nano /etc/redis6/redis6.conf

# Add or modify these lines:
bind 127.0.0.1
requirepass Moulines1

# Save and restart Redis
sudo systemctl enable redis6
sudo systemctl restart redis6

# Verify Redis is running
redis6-cli -a Moulines1 ping
# Should return: PONG
```

### 5. Configure Environment Variables

The `.env` file should already exist with the correct password. If not:

```bash
cat > .env <<EOF
REDIS_PASSWORD=Moulines1
USE_GPU_INSTANCE=True
EOF
```

### 6. Make Scripts Executable

```bash
chmod +x simulate_pipeline.sh
chmod +x start_gunicorn.sh
```

### 7. Configure sudoers for Recording Deletion

**Why is this needed?**  
When the ML pipeline runs (especially on GPU instance), it may create files as `root` user. This prevents the Flask application (running as `ec2-user`) from deleting these recordings through the web interface.

**Solution:** Grant `ec2-user` limited sudo privileges to manage recordings ownership and deletion.

```bash
# Edit sudoers file safely
sudo visudo
```

**Add these lines at the end of the file:**

```bash
# Allow ec2-user to manage recordings ownership and deletion without password
ec2-user ALL=(ALL) NOPASSWD: /bin/chown -R ec2-user\:ec2-user /home/ec2-user/recordings/*
ec2-user ALL=(ALL) NOPASSWD: /bin/rm -rf /home/ec2-user/recordings/*
```

### 8. Create systemd Services

**What is systemd?**  
systemd is Linux's service manager. It ensures your application:
- ✅ Starts automatically when the server boots
- ✅ Runs in the background (survives SSH disconnection)
- ✅ Restarts automatically if it crashes
- ✅ Can be controlled with simple commands: `systemctl start/stop/restart`

**Why do we need it?**  
Without systemd:
- You SSH to the server and run `python app.py`
- You close SSH → application stops ❌
- Server reboots → you must SSH and manually restart ❌

With systemd:
- Application runs as a service
- You close SSH → application continues ✅
- Server reboots → application restarts automatically ✅

**We will create 2 services:**
1. **flask-app**: Flask web server (via Gunicorn)
2. **celery-worker**: Background worker for ML pipelines

---

#### Flask Service (with Gunicorn - 4 HTTP workers)

This creates a systemd service file that will:
- Start Flask (via Gunicorn) automatically on server boot
- Restart Flask automatically if it crashes
- Run Flask in the background (survives SSH disconnection)

```bash
sudo tee /etc/systemd/system/flask-app.service > /dev/null <<EOF
[Unit]
Description=Flask ML Pipeline (Gunicorn)
After=network.target redis6.service

[Service]
User=ec2-user
WorkingDirectory=/home/ec2-user/app
Environment="PATH=/home/ec2-user/app/venv/bin"
ExecStart=/home/ec2-user/app/venv/bin/gunicorn -w 4 -b 0.0.0.0:5000 app:app --timeout 300 --log-level info
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

**What this does:**
- Creates file `/etc/systemd/system/flask-app.service`
- `ExecStart` = command to run: `gunicorn -w 4 -b 0.0.0.0:5000 app:app`
- `-w 4` = 4 Gunicorn workers to handle HTTP requests in parallel
- `-b 0.0.0.0:5000` = listen on all interfaces, port 5000
- `--timeout 300` = 5 minutes timeout for long uploads
- `Restart=always` = auto-restart on crash
- `WantedBy=multi-user.target` = start on server boot

#### Celery Worker Service (1 ML pipeline worker)

This creates a systemd service file that will:
- Start Celery worker automatically on server boot
- Restart Celery automatically if it crashes
- Run Celery in the background (survives SSH disconnection)

```bash
sudo tee /etc/systemd/system/celery-worker.service > /dev/null <<EOF
[Unit]
Description=Celery Worker (ML Pipeline)
After=network.target redis6.service

[Service]
User=ec2-user
WorkingDirectory=/home/ec2-user/app
Environment="PATH=/home/ec2-user/app/venv/bin"
ExecStart=/home/ec2-user/app/venv/bin/celery -A celery_app worker --loglevel=info --concurrency=1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

**What this does:**
- Creates file `/etc/systemd/system/celery-worker.service`
- `ExecStart` = command to run: `celery -A celery_app worker --loglevel=info --concurrency=1`
- `--concurrency=1` = process 1 ML pipeline at a time
- `Restart=always` = auto-restart on crash
- `WantedBy=multi-user.target` = start on server boot

#### Enable and Start Services

Now that both service files are created, we need to:
1. **Enable** them = Start automatically on server boot
2. **Start** them = Start now

```bash
# Reload systemd to recognize new service files
sudo systemctl daemon-reload

# Enable both services (start on boot)
sudo systemctl enable flask-app celery-worker

# Start both services now
sudo systemctl start flask-app celery-worker
```

**Note:** `flask-app celery-worker` is a shortcut for doing both services at once.  
It's the same as running these commands separately:
```bash
sudo systemctl enable flask-app
sudo systemctl enable celery-worker
sudo systemctl start flask-app
sudo systemctl start celery-worker
```

### 8. Configure Nginx Reverse Proxy (Production)

Nginx acts as a reverse proxy to handle HTTPS/SSL and forward requests to Flask.

#### Install Nginx

```bash
sudo yum install nginx -y
sudo systemctl enable nginx
```

#### Create Nginx Configuration

```bash
sudo nano /etc/nginx/conf.d/sci.conf
```

**Add this configuration:**

```nginx
server {
    listen 80;
    server_name sci.ce.gatech.edu;

    # Logs for monitoring and debugging
    access_log /var/log/nginx/sci_access.log;
    error_log /var/log/nginx/sci_error.log;

    # Allow large file uploads (20GB)
    client_max_body_size 20G;
    client_body_timeout 300s;

    # Reverse proxy to Flask (Gunicorn on port 5000)
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts for long uploads
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }
}
```

#### Test and Start Nginx

```bash
# Test configuration
sudo nginx -t

# Start Nginx
sudo systemctl restart nginx
sudo systemctl status nginx
```

#### Configure SSL with Let's Encrypt (Free HTTPS)

**Prerequisites:**
- DNS must point to your EC2 IP address
- Port 80 and 443 must be open in AWS Security Group

```bash
# Install Certbot
sudo yum install certbot python3-certbot-nginx -y

# Obtain SSL certificate (Certbot will modify Nginx config automatically)
sudo certbot --nginx -d sci.ce.gatech.edu
```

**Certbot will:**
- ✅ Obtain a free SSL certificate from Let's Encrypt
- ✅ Configure Nginx to listen on port 443 (HTTPS)
- ✅ Set up automatic certificate renewal (certificates expire after 90 days)
- ✅ Redirect HTTP to HTTPS automatically

**Verify HTTPS works:**

```bash
curl -I https://sci.ce.gatech.edu/
```

### 9. Configure Firewall (AWS Security Group)

In AWS Console, configure Security Group to allow:
- **Port 80** (HTTP) - for Let's Encrypt validation and HTTP redirect
- **Port 443** (HTTPS) - for secure HTTPS access
- **Port 22** (SSH) - from your IP only

**Important Security Notes:**
- **DO NOT** expose port 5000 publicly (Flask should only be accessible via Nginx)
- **DO NOT** expose port 6379 (Redis is bound to localhost only)

**Recommended Security Group Rules:**

| Type  | Protocol | Port Range | Source          | Description              |
|-------|----------|------------|-----------------|--------------------------|
| HTTP  | TCP      | 80         | 0.0.0.0/0       | HTTP (for SSL redirect)  |
| HTTPS | TCP      | 443        | 0.0.0.0/0       | HTTPS (secure access)    |
| SSH   | TCP      | 22         | Your IP only    | SSH access               |

### 10. Verify Services

```bash
# Check services status
sudo systemctl status flask-app
sudo systemctl status celery-worker
sudo systemctl status nginx

# Test Redis connection
redis6-cli -a Moulines1 ping
# Should return: PONG

# View logs in real-time (follow pipeline progress)
sudo journalctl -u flask-app -f
sudo journalctl -u celery-worker -f
sudo tail -f /var/log/nginx/sci_access.log
```

## Maintenance Commands

```bash
# Restart services after code changes
sudo systemctl restart flask-app celery-worker nginx

# View logs in real-time
sudo journalctl -u flask-app -f
sudo journalctl -u celery-worker -f
sudo tail -f /var/log/nginx/sci_access.log
sudo tail -f /var/log/nginx/sci_error.log

# View last 100 lines of logs
sudo journalctl -u flask-app -n 100
sudo journalctl -u celery-worker -n 100

# Stop services
sudo systemctl stop flask-app celery-worker

# Check service status
sudo systemctl status flask-app
sudo systemctl status celery-worker
sudo systemctl status nginx
```

## Updating the Application

```bash
# 1. Pull latest code
cd /home/ec2-user/app
git pull origin main

# 2. Update dependencies (if requirements.txt changed)
source venv/bin/activate
pip install -r requirements.txt

# 3. Restart services
sudo systemctl restart flask-app celery-worker

# 4. Verify services are running
sudo systemctl status flask-app celery-worker
```

## Troubleshooting

### Redis Connection Issues

```bash
# Check if Redis is running
sudo systemctl status redis6

# Test Redis connection
redis6-cli -a Moulines1 ping

# Check Redis logs
sudo journalctl -u redis6 -f

# Check if Redis is listening on localhost
sudo netstat -tlnp | grep 6379
```

### Flask Not Starting

```bash
# Check logs
sudo journalctl -u flask-app -n 100 --no-pager

# Check if port 5000 is already in use
sudo lsof -i :5000

# Test manually with Gunicorn
cd /home/ec2-user/app
source venv/bin/activate
gunicorn -w 2 -b 0.0.0.0:5000 app:app --log-level debug

# Or test with Flask development server
python app.py
```

### Celery Worker Not Processing Tasks

```bash
# Check worker logs
sudo journalctl -u celery-worker -n 100 --no-pager

# Check Redis queue length
redis6-cli -a Moulines1 LLEN celery

# List all Redis keys
redis6-cli -a Moulines1 KEYS '*'

# Test manually with debug mode
cd /home/ec2-user/app
source venv/bin/activate
celery -A celery_app worker --loglevel=debug
```

### Permission Issues

```bash
# Fix ownership of application files
sudo chown -R ec2-user:ec2-user /home/ec2-user/app

# Fix permissions on directories
chmod 755 /home/ec2-user/app
chmod 755 /home/ec2-user/app/uploads
chmod 755 /home/ec2-user/app/recordings
chmod 755 /home/ec2-user/app/temp_extracts

# Fix ownership of recordings (especially if pipeline created files as root)
sudo chown -R ec2-user:ec2-user /home/ec2-user/recordings/

# Verify ownership
ls -la /home/ec2-user/recordings/
# All files should show "ec2-user ec2-user"
```

### Recording Deletion Issues

If you encounter "Permission denied" when deleting recordings through the web interface:

```bash
# Check who owns the files
ls -la /home/ec2-user/recordings/<recording_id>/result_pipeline_stable/

# If files are owned by root, fix the ownership
sudo chown -R ec2-user:ec2-user /home/ec2-user/recordings/

# Verify sudoers is configured correctly
sudo -l -U ec2-user
# Should show the chown and rm commands for /home/ec2-user/recordings/*

# Test deletion manually
sudo rm -rf /home/ec2-user/recordings/test_recording
# Should work without password prompt
```

**Note:** The application will automatically attempt to use `sudo chown` when encountering permission errors during deletion, but this requires the sudoers configuration from step 7.

# Deployment Guide

## Prerequisites

- EC2 instance running Amazon Linux 2 or similar
- Python 3.11+
- Redis installed
- Git installed

## Installation Steps

### 1. Install System Dependencies

```bash
sudo yum update -y
sudo yum install -y python3 python3-pip redis git
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
sudo nano /etc/redis.conf

# Add or modify these lines:
bind 127.0.0.1
requirepass Moulines1

# Save and restart Redis
sudo systemctl enable redis
sudo systemctl restart redis

# Verify Redis is running
redis-cli -a Moulines1 ping
# Should return: PONG
```

### 5. Configure Environment Variables

The `.env` file should already exist with the correct password. If not:

```bash
cat > .env <<EOF
REDIS_PASSWORD=Moulines1
FLASK_ENV=production
SECRET_KEY=change-this-to-a-random-secret-key-in-production
EOF
```

### 6. Make Scripts Executable

```bash
chmod +x simulate_pipeline.sh
chmod +x start_gunicorn.sh
```

### 7. Create systemd Services

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
After=network.target redis.service

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
After=network.target redis.service

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

### 8. Verify Services

```bash
# Check Flask status
sudo systemctl status flask-app

# Check Celery status
sudo systemctl status celery-worker

# View Flask logs
sudo journalctl -u flask-app -f

# View Celery logs
sudo journalctl -u celery-worker -f
```

### 9. Configure Firewall (AWS Security Group)

In AWS Console, configure Security Group to allow:
- Port 5000 (HTTP) from your IP or lab network
- Port 22 (SSH) from your IP only

**Note:** Redis port 6379 should NOT be exposed (it's bound to localhost only)

## Architecture Overview

```
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
- **Gunicorn workers (4)**: Handle multiple HTTP requests simultaneously
- **Celery worker (1)**: Process one ML pipeline at a time
- Users can upload simultaneously, pipelines are queued

## Testing

1. Access the application:
   ```bash
   curl http://your-ec2-ip:5000
   ```

2. Test Redis connection:
   ```bash
   redis-cli -a Moulines1 ping
   ```

3. Test Celery worker:
   ```bash
   # Should show worker logs
   sudo journalctl -u celery-worker -n 50
   ```

## Maintenance Commands

```bash
# Restart services after code changes
sudo systemctl restart flask-app celery-worker

# View logs in real-time
sudo journalctl -u flask-app -f
sudo journalctl -u celery-worker -f

# View last 100 lines of logs
sudo journalctl -u flask-app -n 100
sudo journalctl -u celery-worker -n 100

# Stop services
sudo systemctl stop flask-app celery-worker

# Check service status
sudo systemctl status flask-app
sudo systemctl status celery-worker
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
sudo systemctl status redis

# Test Redis connection
redis-cli -a Moulines1 ping

# Check Redis logs
sudo journalctl -u redis -f

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
redis-cli -a Moulines1 LLEN celery

# List all Redis keys
redis-cli -a Moulines1 KEYS '*'

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
```

## Performance Tuning

### Adjust Gunicorn Workers

```bash
# Formula: (2 × CPU cores) + 1
# For t2.medium (2 vCPUs): 2 × 2 + 1 = 5 workers

# Edit systemd service
sudo nano /etc/systemd/system/flask-app.service

# Change -w 4 to -w 5
ExecStart=.../gunicorn -w 5 -b 0.0.0.0:5000 app:app --timeout 300

# Reload and restart
sudo systemctl daemon-reload
sudo systemctl restart flask-app
```

### Monitor Resource Usage

```bash
# Check CPU and memory usage
htop

# Check disk usage
df -h

# Check Redis memory usage
redis-cli -a Moulines1 INFO memory
```

## Security Notes

- **Redis**: Bound to `127.0.0.1` (localhost only) - no external access possible
- **Redis password**: `Moulines1` (configured in `.env` and `redis.conf`)
- **Environment variables**: `.env` file contains secrets - DO NOT commit to git (already in `.gitignore`)
- **Flask SECRET_KEY**: Change to a random value in production:
  ```bash
  # Generate a secure key
  python -c 'import secrets; print(secrets.token_hex(32))'
  
  # Update .env
  nano .env
  # Change: SECRET_KEY=<generated-key>
  ```
- **AWS Security Group**: Only open ports 22 (SSH) and 5000 (HTTP), restrict to your IP/network
- **systemd services**: Run as `ec2-user` (non-root) for security

## Backup Strategy

```bash
# Backup recordings folder (contains all uploaded data and results)
tar -czf backup_$(date +%Y%m%d).tar.gz recordings/

# Copy to S3 (optional)
aws s3 cp backup_$(date +%Y%m%d).tar.gz s3://your-bucket/backups/

# Automated daily backup (add to crontab)
crontab -e
# Add:
0 2 * * * cd /home/ec2-user/app && tar -czf /tmp/backup_$(date +\%Y\%m\%d).tar.gz recordings/
```

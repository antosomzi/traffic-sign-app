"""GPU instance manager: start, run the pipeline over SSH, and shut down."""

import json
import os
import re
import shlex
import time
from datetime import datetime

import boto3
import paramiko
from botocore.exceptions import WaiterError

from pipeline.gpu.config import AWS_REGION, EFS_DNS, EFS_MOUNT_POINT, GPU_INSTANCE_ID
from pipeline.gpu.diagnostics import capture_instance_diagnostics
from services.sign_app.s3_service import S3VideoService, find_video_in_recording
from models.sign_app.recording import Recording

SSH_KEY_PATH = "/home/ec2-user/traffic-sign-inventory_keypair.pem"


def _write_gpu_status(recording_id, message):
    """Update recording status in the database from the orchestrator."""
    try:
        Recording.update_status(recording_id, status="processing", message=message)
    except Exception as e:
        print(f"⚠️ Could not update status in DB: {e}")


def _build_nvenc_encode_command(recording_path):
    """Build remote shell command to re-encode the recording camera video with NVENC + CFR."""
    escaped_recording_path = shlex.quote(recording_path)
    return (
        "set -e; "
        f"VIDEO_PATH=$(find {escaped_recording_path} -type f -path '*/camera/*.mp4' | head -n 1); "
        'if [ -z "$VIDEO_PATH" ]; then echo "No camera mp4 found"; exit 12; fi; '
        'ENCODED_PATH="${VIDEO_PATH%.mp4}__nvenc.mp4"; '
        "ffmpeg -y -i \"$VIDEO_PATH\" "
        "-c:v h264_nvenc "
        "-preset p4 "
        "-cq 18 "
        "-fps_mode cfr "
        "-g 10 "
        "-keyint_min 10 "
        "-sc_threshold 0 "
        "-an "
        "-movflags +faststart "
        "\"$ENCODED_PATH\"; "
        "mv \"$ENCODED_PATH\" \"$VIDEO_PATH\""
    )


def _build_vfrdet_probe_command(recording_path):
    """Build remote shell command to compute VFR score on the camera video."""
    escaped_recording_path = shlex.quote(recording_path)
    return (
        "set -e; "
        f"VIDEO_PATH=$(find {escaped_recording_path} -type f -path '*/camera/*.mp4' | head -n 1); "
        'if [ -z "$VIDEO_PATH" ]; then echo "No camera mp4 found for vfrdet"; exit 12; fi; '
        "ffmpeg -hide_banner -i \"$VIDEO_PATH\" -vf vfrdet -an -f null -"
    )


def _extract_vfr_score(ffmpeg_output: str) -> float | None:
    """Extract VFR score from ffmpeg vfrdet output."""
    match = re.search(r"VFR:([0-9]*\.?[0-9]+)", ffmpeg_output)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _sync_encoded_video_to_s3(
    recording_path: str,
    recording_id: str,
) -> tuple[bool, str]:
    """Upload encoded camera video to S3 and persist S3 metadata in the database."""

    encoded_video_path = find_video_in_recording(recording_path)
    if not encoded_video_path or not os.path.exists(encoded_video_path):
        return False, "Encoded camera video not found for S3 sync"

    try:
        s3_service = S3VideoService()
        s3_key = s3_service.upload_video(encoded_video_path, recording_id)

        camera_folder = os.path.dirname(encoded_video_path)
        camera_folder_relative = os.path.relpath(camera_folder, recording_path)

        Recording.update_status(
            recording_id,
            video_s3_key=s3_key,
            camera_folder=camera_folder_relative
        )

        return True, s3_key
    except Exception as e:
        return False, f"Failed to sync encoded video to S3: {e}"


def start_and_run_pipeline_ssh(recording_id):
    """Start existing GPU instance, run pipeline via SSH, stop instance."""

    ec2 = boto3.client("ec2", region_name=AWS_REGION)
    ssh = None

    def _stop_instance_best_effort(reason: str):
        """Try to stop GPU instance for any failure path without raising."""
        try:
            print(f"[GPU] Stopping instance {GPU_INSTANCE_ID} ({reason})...")
            ec2.stop_instances(InstanceIds=[GPU_INSTANCE_ID])
            print("✅ Instance stop requested")
        except Exception as stop_error:
            print(f"⚠️ Could not stop instance after {reason}: {stop_error}")

    try:
        print(f"[GPU] Checking instance {GPU_INSTANCE_ID} state...")
        response = ec2.describe_instances(InstanceIds=[GPU_INSTANCE_ID])
        current_state = response["Reservations"][0]["Instances"][0]["State"]["Name"]
        print(f"   Current state: {current_state}")

        if current_state == "stopping":
            print("   Instance is stopping, waiting for it to stop (2-3 min)...")
            waiter = ec2.get_waiter("instance_stopped")
            waiter.wait(InstanceIds=[GPU_INSTANCE_ID])
            print("   ✅ Instance stopped")
        elif current_state == "running":
            print("   Instance already running, skipping start")
        elif current_state != "stopped":
            raise Exception(f"Instance is in unexpected state: {current_state}")

        if current_state in ["stopped", "stopping"]:
            print(f"[GPU] Starting instance {GPU_INSTANCE_ID}...")
            ec2.start_instances(InstanceIds=[GPU_INSTANCE_ID])
            print("✅ Instance start initiated")

        print("[GPU] Waiting for instance to be running...")
        waiter = ec2.get_waiter("instance_running")
        try:
            waiter.wait(
                InstanceIds=[GPU_INSTANCE_ID],
                WaiterConfig={"Delay": 10, "MaxAttempts": 60}
            )
        except WaiterError as we:
            print(f"❌ Waiter failed: {we}")
            # Capture full diagnostics
            diagnostics = capture_instance_diagnostics(ec2, GPU_INSTANCE_ID)
            error_details = {
                "error_type": "waiter_failed",
                "waiter_error": str(we),
                "diagnostics": diagnostics,
                "timestamp": datetime.now().isoformat(),
            }
            print(f"[DEBUG] Diagnostics: {json.dumps(diagnostics, indent=2, default=str)}")
            _stop_instance_best_effort("waiter failure")
            return False, GPU_INSTANCE_ID, "EC2 instance failed to start", error_details

        response = ec2.describe_instances(InstanceIds=[GPU_INSTANCE_ID])
        public_ip = response["Reservations"][0]["Instances"][0]["PublicIpAddress"]
        print(f"✅ Instance running: {public_ip}")

        print("[GPU] Waiting for SSH to be ready (60s)...")
        time.sleep(60)

        print("[GPU] Connecting via SSH...")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(
                hostname=public_ip,
                username="ec2-user",
                key_filename=SSH_KEY_PATH,
                timeout=30,
                look_for_keys=False,
                allow_agent=False,
            )
            print("✅ SSH connected")
        except Exception as ssh_error:
            print(f"❌ SSH connection failed: {ssh_error}")
            diagnostics = capture_instance_diagnostics(ec2, GPU_INSTANCE_ID)
            error_details = {
                "error_type": "ssh_connection_failed",
                "ssh_error": str(ssh_error),
                "public_ip": public_ip,
                "diagnostics": diagnostics,
                "timestamp": datetime.now().isoformat(),
            }
            _stop_instance_best_effort("ssh connection failure")
            return False, GPU_INSTANCE_ID, f"SSH connection failed: {ssh_error}", error_details

        print("[GPU] Mounting EFS...")
        mount_cmd = (
            f"sudo mkdir -p {EFS_MOUNT_POINT} && "
            f"sudo mount -t nfs4 -o nfsvers=4.1 {EFS_DNS}:/ {EFS_MOUNT_POINT}"
        )
        stdin, stdout, stderr = ssh.exec_command(mount_cmd)
        exit_code = stdout.channel.recv_exit_status()
        if exit_code != 0:
            mount_error = stderr.read().decode()
            print(f"❌ EFS mount failed: {mount_error}")
            error_details = {
                "error_type": "efs_mount_failed",
                "mount_command": mount_cmd,
                "exit_code": exit_code,
                "stderr": mount_error,
                "timestamp": datetime.now().isoformat(),
            }
            _stop_instance_best_effort("efs mount failure")
            return False, GPU_INSTANCE_ID, f"EFS mount failed: {mount_error}", error_details
        print("✅ EFS mounted")
      

        print("✅ EFS mounted")

        # Mise à jour du statut
        recording_path = f"{EFS_MOUNT_POINT}/recordings/{recording_id}"
        try:
            _write_gpu_status(recording_id, "Re-encoding video on GPU (NVENC)...")
        except Exception as status_err:
            print(f"[GPU] ⚠️ Impossible d'écrire le statut : {status_err}")

        print("[GPU] 🔍 Diagnostic de l'environnement en cours...")
        
        # 1. On DEFINIT la commande
        diag_cmd = f"""
echo '--- GPU ---'
nvidia-smi || echo 'NVIDIA-SMI FAILED'
echo '--- FFMPEG ---'
ffmpeg -version | head -n 1 || echo 'FFMPEG NOT FOUND'
echo '--- DISK ---'
df -h /
echo '--- EFS FILE ---'
ls -la "{recording_path}"
"""
        
        # 2. On EXECUTE la commande
        _, diag_stdout, diag_stderr = ssh.exec_command(diag_cmd)
        diag_output = diag_stdout.read().decode(errors="replace").strip()
        diag_err = diag_stderr.read().decode(errors="replace").strip()
        
        print(f"[GPU] 📊 Résultat du diagnostic :\n{diag_output}\n{diag_err}")

        # --- VOTRE CODE ORIGINAL REPREND ICI ---
        vfrdet_cmd = _build_vfrdet_probe_command(recording_path)

        vfrdet_cmd = _build_vfrdet_probe_command(recording_path)
        _, vfr_before_stdout, vfr_before_stderr = ssh.exec_command(vfrdet_cmd, timeout=600)
        vfr_before_exit = vfr_before_stdout.channel.recv_exit_status()
        vfr_before_stdout_text = vfr_before_stdout.read().decode(errors="replace")
        vfr_before_stderr_text = vfr_before_stderr.read().decode(errors="replace")
        vfr_before_combined = f"{vfr_before_stdout_text}\n{vfr_before_stderr_text}"
        if vfr_before_exit == 0:
            vfr_before = _extract_vfr_score(vfr_before_combined)
            if vfr_before is not None:
                print(f"[GPU] 🎯 vfrdet source score: {vfr_before:.6f}")
            else:
                print("[GPU] ⚠️ vfrdet source score not found in ffmpeg output")
        else:
            print(f"[GPU] ⚠️ vfrdet source probe failed (code={vfr_before_exit})")

        encode_cmd = _build_nvenc_encode_command(recording_path)
        print(f"[GPU] Commande exécutée : {encode_cmd}") # <-- On affiche la commande exacte
        _, encode_stdout, encode_stderr = ssh.exec_command(encode_cmd, timeout=3600)
        encode_exit_code = encode_stdout.channel.recv_exit_status()
        _ = encode_stdout.read().decode(errors="replace")
        encode_stderr_text = encode_stderr.read().decode(errors="replace")
        if encode_exit_code != 0:
            print("❌ GPU video encoding failed")
            print(f"[GPU] Détails de l'erreur FFmpeg : {encode_stderr_text}") # <--- AJOUTEZ CETTE LIGNE
            error_details = {
                "error_type": "gpu_video_encoding_failed",
                "exit_code": encode_exit_code,
                "stderr": encode_stderr_text[:4000],
                "encode_command": encode_cmd,
                "timestamp": datetime.now().isoformat(),
            }
            _stop_instance_best_effort("gpu video encoding failure")
            return False, GPU_INSTANCE_ID, "GPU video encoding failed", error_details

        _, vfr_after_stdout, vfr_after_stderr = ssh.exec_command(vfrdet_cmd, timeout=600)
        vfr_after_exit = vfr_after_stdout.channel.recv_exit_status()
        vfr_after_stdout_text = vfr_after_stdout.read().decode(errors="replace")
        vfr_after_stderr_text = vfr_after_stderr.read().decode(errors="replace")
        vfr_after_combined = f"{vfr_after_stdout_text}\n{vfr_after_stderr_text}"
        if vfr_after_exit == 0:
            vfr_after = _extract_vfr_score(vfr_after_combined)
            if vfr_after is not None:
                print(f"[GPU] 🎯 vfrdet encoded score: {vfr_after:.6f}")
            else:
                print("[GPU] ⚠️ vfrdet encoded score not found in ffmpeg output")
        else:
            print(f"[GPU] ⚠️ vfrdet encoded probe failed (code={vfr_after_exit})")

        s3_sync_ok, s3_sync_message = _sync_encoded_video_to_s3(
            recording_path,
            recording_id,
        )
        if not s3_sync_ok:
            error_details = {
                "error_type": "gpu_s3_sync_failed",
                "message": s3_sync_message,
                "timestamp": datetime.now().isoformat(),
            }
            _stop_instance_best_effort("gpu s3 sync failure")
            return False, GPU_INSTANCE_ID, "Failed to sync encoded video to S3", error_details
        print(f"✅ Encoded video synced to S3: {s3_sync_message}")

        _write_gpu_status(recording_id, "Pipeline running on GPU...")

        print("[GPU] Running real pipeline in Docker (may take several minutes)...")
        docker_cmd = (
            "sudo docker run --rm --gpus all "
            "-v /home/ec2-user/traffic_sign_pipeline/traffic_sign_pipeline:/usr/src/app "
            f"-v {recording_path}:/data "
            "-v /home/ec2-user/traffic_sign_pipeline/traffic_sign_pipeline/weights:/usr/src/app/weights "
            "traffic-pipeline:gpu -i /data > /home/ec2-user/pipeline.log 2>&1"
        )
        print(f"[GPU] Running: {docker_cmd}")
        stdin, stdout, stderr = ssh.exec_command(docker_cmd, timeout=7200)

        start_time = time.time()
        while not stdout.channel.exit_status_ready():
            elapsed = int(time.time() - start_time)
            if elapsed % 60 == 0:
                print(f"   Pipeline running... {elapsed // 60}min")
            time.sleep(5)

        exit_code = stdout.channel.recv_exit_status()
        elapsed = int(time.time() - start_time)

        # Fix permissions so Celery worker on main node can write the post-processing CSVs
        chown_cmd = f"sudo chown -R ec2-user:ec2-user {recording_path}"
        print(f"[GPU] Fixing permissions: {chown_cmd}")
        _, chown_stdout, _ = ssh.exec_command(chown_cmd)
        chown_stdout.channel.recv_exit_status() # Wait for chown to finish
        time.sleep(1) # Give EFS a second to propagate the ownership change

        if exit_code != 0:
            error_stderr = stderr.read().decode()
            print(f"❌ Pipeline failed (exit {exit_code})")
            
            # Try to fetch the full pipeline log from the GPU instance
            pipeline_log = ""
            try:
                stdin_log, stdout_log, stderr_log = ssh.exec_command("tail -n 500 /home/ec2-user/pipeline.log 2>&1")
                pipeline_log = stdout_log.read().decode()
            except Exception as log_err:
                pipeline_log = f"Could not retrieve pipeline.log: {log_err}"
            
            error_details = {
                "error_type": "pipeline_execution_failed",
                "exit_code": exit_code,
                "docker_stderr": error_stderr[:2000],  # First 2000 chars
                "pipeline_log_tail": pipeline_log[:5000],  # Last 500 lines (up to 5000 chars)
                "elapsed_seconds": elapsed,
                "docker_command": docker_cmd,
                "timestamp": datetime.now().isoformat(),
            }
            _stop_instance_best_effort("pipeline execution failure")
            return False, GPU_INSTANCE_ID, f"Pipeline failed (exit {exit_code})", error_details

        print(f"✅ Pipeline completed in {elapsed // 60}min")

        # Keep historical cleanup behavior: once S3 is synced and pipeline is done,
        # remove local camera video to save EFS space.
        local_video_path = find_video_in_recording(recording_path)
        if local_video_path:
            try:
                os.remove(local_video_path)
                print(f"🗑️ Local video deleted after successful S3 sync: {local_video_path}")
            except OSError as cleanup_error:
                print(f"⚠️ Could not delete local video after S3 sync: {cleanup_error}")

        ssh.close()
        print("✅ SSH closed")

        print(f"[GPU] Stopping instance {GPU_INSTANCE_ID}...")
        ec2.stop_instances(InstanceIds=[GPU_INSTANCE_ID])
        print("✅ Instance stopped")

        return True, GPU_INSTANCE_ID, "Pipeline execution completed successfully", {}

    except Exception as e:  # pragma: no cover - defensive logging
        error_msg = str(e)
        print(f"❌ ERROR: {error_msg}")

        if ssh:
            try:
                ssh.close()
            except Exception:
                pass

        _stop_instance_best_effort("unexpected exception")

        # For unexpected exceptions, capture diagnostics
        diagnostics = capture_instance_diagnostics(ec2, GPU_INSTANCE_ID)
        error_details = {
            "error_type": "unexpected_exception",
            "exception": str(e),
            "exception_type": type(e).__name__,
            "diagnostics": diagnostics,
            "timestamp": datetime.now().isoformat(),
        }
        return False, GPU_INSTANCE_ID, error_msg, error_details

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

SSH_KEY_PATH = "/home/ec2-user/traffic-sign-inventory_keypair.pem"


def _tail_lines(text: str, max_lines: int = 20) -> str:
    """Return the tail of multiline text for concise logs."""
    if not text:
        return ""
    lines = text.strip().splitlines()
    if len(lines) <= max_lines:
        return "\n".join(lines)
    return "\n".join(lines[-max_lines:])


def _write_gpu_status(status_file, message):
    """Update status.json from the orchestrator while preserving S3 metadata fields."""
    try:
        existing_data = {}
        try:
            with open(status_file, "r") as f:
                existing_data = json.load(f)
        except Exception:
            pass

        status_data = {
            "status": "processing",
            "message": message,
            "timestamp": datetime.now().isoformat(),
        }

        if existing_data.get("video_s3_key"):
            status_data["video_s3_key"] = existing_data["video_s3_key"]
        if existing_data.get("camera_folder"):
            status_data["camera_folder"] = existing_data["camera_folder"]

        with open(status_file, "w") as f:
            json.dump(status_data, f, indent=2)
    except Exception as e:  # pragma: no cover - remote filesystem side effect
        print(f"⚠️ Could not update status file: {e}")


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


def _build_video_inspect_command(recording_path):
    """Build remote shell command to inspect current camera video metadata."""
    escaped_recording_path = shlex.quote(recording_path)
    return (
        "set -e; "
        f"VIDEO_PATH=$(find {escaped_recording_path} -type f -path '*/camera/*.mp4' | head -n 1); "
        'if [ -z "$VIDEO_PATH" ]; then echo "No camera mp4 found for inspect"; exit 12; fi; '
        'echo "VIDEO_PATH=$VIDEO_PATH"; '
        'ls -lh "$VIDEO_PATH"; '
        'ffprobe -v error -select_streams v:0 '
        '-show_entries stream=codec_name,avg_frame_rate,r_frame_rate,nb_frames,width,height,duration '
        '-of default=noprint_wrappers=1:nokey=0 "$VIDEO_PATH"'
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


def _log_remote_command(ssh, label: str, cmd: str, timeout: int = 120, tail_lines: int = 20):
    """Run a remote command over SSH and log compact diagnostics."""
    print(f"[GPU][DIAG] {label}: {cmd}")
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out_text = stdout.read().decode(errors="replace")
    err_text = stderr.read().decode(errors="replace")

    print(f"[GPU][DIAG] {label} exit={exit_code}")
    out_tail = _tail_lines(out_text, max_lines=tail_lines)
    err_tail = _tail_lines(err_text, max_lines=tail_lines)
    if out_tail:
        print(f"[GPU][DIAG] {label} stdout tail:\n{out_tail}")
    if err_tail:
        print(f"[GPU][DIAG] {label} stderr tail:\n{err_tail}")
    return exit_code, out_text, err_text


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

        # Runtime diagnostics for ffmpeg/cuda environment on the remote GPU host
        _log_remote_command(ssh, "which ffmpeg/ffprobe", "which ffmpeg; which ffprobe", timeout=30, tail_lines=10)
        _log_remote_command(ssh, "ffmpeg version", "ffmpeg -version | head -n 2", timeout=30, tail_lines=10)
        _log_remote_command(ssh, "ffprobe version", "ffprobe -version | head -n 2", timeout=30, tail_lines=10)
        _log_remote_command(
            ssh,
            "nvenc encoder availability",
            "ffmpeg -hide_banner -encoders 2>/dev/null | grep -i 'h264_nvenc' || true",
            timeout=30,
            tail_lines=10,
        )
        _log_remote_command(
            ssh,
            "nvidia-smi",
            "nvidia-smi --query-gpu=name,driver_version --format=csv,noheader || nvidia-smi || true",
            timeout=30,
            tail_lines=20,
        )

        # Update status.json to show encoding/pipeline state (avoid circular import)
        recording_path = f"{EFS_MOUNT_POINT}/recordings/{recording_id}"
        status_file = f"{recording_path}/status.json"
        _write_gpu_status(status_file, "Re-encoding video on GPU (NVENC)...")

        _log_remote_command(
            ssh,
            "video metadata before encode",
            _build_video_inspect_command(recording_path),
            timeout=120,
            tail_lines=40,
        )

        vfrdet_cmd = _build_vfrdet_probe_command(recording_path)
        print("[GPU] Running vfrdet on source video...")
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
                print(f"[GPU][DIAG] vfrdet source tail:\n{_tail_lines(vfr_before_combined, max_lines=25)}")
        else:
            print(f"[GPU] ⚠️ vfrdet source probe failed (code={vfr_before_exit})")
            print(f"[GPU][DIAG] vfrdet source tail:\n{_tail_lines(vfr_before_combined, max_lines=25)}")

        print("[GPU] Re-encoding camera video with NVENC + CFR before pipeline...")
        encode_cmd = _build_nvenc_encode_command(recording_path)
        encode_start = time.time()
        _, encode_stdout, encode_stderr = ssh.exec_command(encode_cmd, timeout=3600)
        encode_exit_code = encode_stdout.channel.recv_exit_status()
        encode_elapsed = time.time() - encode_start
        encode_stdout_text = encode_stdout.read().decode(errors="replace")
        encode_stderr_text = encode_stderr.read().decode(errors="replace")
        print(f"[GPU][DIAG] encode exit={encode_exit_code}, elapsed={encode_elapsed:.2f}s")
        if encode_exit_code != 0:
            encode_error = encode_stderr_text
            print(f"❌ GPU video encoding failed: {encode_error}")
            error_details = {
                "error_type": "gpu_video_encoding_failed",
                "exit_code": encode_exit_code,
                "stderr": encode_error[:4000],
                "encode_command": encode_cmd,
                "timestamp": datetime.now().isoformat(),
            }
            _stop_instance_best_effort("gpu video encoding failure")
            return False, GPU_INSTANCE_ID, "GPU video encoding failed", error_details

        print("✅ GPU video encoding completed")
        if encode_stderr_text.strip():
            print(f"[GPU][DIAG] encode stderr tail:\n{_tail_lines(encode_stderr_text, max_lines=25)}")
        if encode_stdout_text.strip():
            print(f"[GPU][DIAG] encode stdout tail:\n{_tail_lines(encode_stdout_text, max_lines=10)}")

        _log_remote_command(
            ssh,
            "video metadata after encode",
            _build_video_inspect_command(recording_path),
            timeout=120,
            tail_lines=40,
        )

        print("[GPU] Running vfrdet on encoded video...")
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
                print(f"[GPU][DIAG] vfrdet encoded tail:\n{_tail_lines(vfr_after_combined, max_lines=25)}")
        else:
            print(f"[GPU] ⚠️ vfrdet encoded probe failed (code={vfr_after_exit})")
            print(f"[GPU][DIAG] vfrdet encoded tail:\n{_tail_lines(vfr_after_combined, max_lines=25)}")

        _write_gpu_status(status_file, "Pipeline running on GPU...")

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

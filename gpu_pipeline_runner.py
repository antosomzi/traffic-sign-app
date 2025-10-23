"""GPU Instance Manager - Start existing GPU instance, run pipeline, stop"""

import boto3
import paramiko
import time
import os
from gpu_config import (
    AWS_REGION, GPU_INSTANCE_ID, KEY_NAME,
    EFS_DNS, EFS_MOUNT_POINT
)

SSH_KEY_PATH = "/home/ec2-user/traffic-sign-inventory_keypair.pem"


def start_and_run_pipeline_ssh(recording_id):
    """Start existing GPU instance, run pipeline via SSH, stop instance."""
    
    ec2 = boto3.client('ec2', region_name=AWS_REGION)
    ssh = None
    
    try:
        print(f"[GPU] Checking instance {GPU_INSTANCE_ID} state...")
        response = ec2.describe_instances(InstanceIds=[GPU_INSTANCE_ID])
        current_state = response['Reservations'][0]['Instances'][0]['State']['Name']
        print(f"   Current state: {current_state}")
        
        if current_state == 'stopping':
            print("   Instance is stopping, waiting for it to stop (2-3 min)...")
            waiter = ec2.get_waiter('instance_stopped')
            waiter.wait(InstanceIds=[GPU_INSTANCE_ID])
            print("   ✅ Instance stopped")
        elif current_state == 'running':
            print("   Instance already running, skipping start")
        elif current_state != 'stopped':
            raise Exception(f"Instance is in unexpected state: {current_state}")
        
        if current_state in ['stopped', 'stopping']:
            print(f"[GPU] Starting instance {GPU_INSTANCE_ID}...")
            ec2.start_instances(InstanceIds=[GPU_INSTANCE_ID])
            print(f"✅ Instance start initiated")
        
        print("[GPU] Waiting for instance to be running...")
        waiter = ec2.get_waiter('instance_running')
        waiter.wait(InstanceIds=[GPU_INSTANCE_ID])
        
        response = ec2.describe_instances(InstanceIds=[GPU_INSTANCE_ID])
        public_ip = response['Reservations'][0]['Instances'][0]['PublicIpAddress']
        print(f"✅ Instance running: {public_ip}")
        
        print("[GPU] Waiting for SSH to be ready (60s)...")
        time.sleep(60)
        
        print("[GPU] Connecting via SSH...")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=public_ip,
            username='ec2-user',
            key_filename=SSH_KEY_PATH,
            timeout=30,
            look_for_keys=False,
            allow_agent=False
        )
        print("✅ SSH connected")
        
        print("[GPU] Mounting EFS...")
        mount_cmd = (
            f"sudo mkdir -p {EFS_MOUNT_POINT} && "
            f"sudo mount -t nfs4 -o nfsvers=4.1 {EFS_DNS}:/ {EFS_MOUNT_POINT}"
        )
        stdin, stdout, stderr = ssh.exec_command(mount_cmd)
        exit_code = stdout.channel.recv_exit_status()
        if exit_code != 0:
            raise Exception(f"EFS mount failed: {stderr.read().decode()}")
        print("✅ EFS mounted")
        
        print(f"[GPU] Running real pipeline in Docker (may take several minutes)...")
        recording_path = f"{EFS_MOUNT_POINT}/recordings/{recording_id}"
        docker_cmd = (
            "sudo docker run --rm --gpus all "
            "-v /home/ec2-user/pipeline_21102025/traffic_sign_pipeline:/usr/src/app "
            f"-v {recording_path}:/data "
            "-v /home/ec2-user/pipeline_21102025/traffic_sign_pipeline/weights:/usr/src/app/weights "
            "traffic-pipeline:gpu -i /data"
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

        if exit_code != 0:
            error = stderr.read().decode()
            raise Exception(f"Pipeline failed (exit {exit_code}): {error[:200]}")

        print(f"✅ Pipeline completed in {elapsed // 60}min")
        
        ssh.close()
        print("✅ SSH closed")
        
        print(f"[GPU] Stopping instance {GPU_INSTANCE_ID}...")
        ec2.stop_instances(InstanceIds=[GPU_INSTANCE_ID])
        print("✅ Instance stopped")
        
        return True, GPU_INSTANCE_ID, "Pipeline execution completed successfully"
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ ERROR: {error_msg}")
        
        if ssh:
            try:
                ssh.close()
            except:
                pass
        
        try:
            print(f"[GPU] Stopping instance {GPU_INSTANCE_ID} after error...")
            ec2.stop_instances(InstanceIds=[GPU_INSTANCE_ID])
        except:
            pass
        
        return False, GPU_INSTANCE_ID, error_msg


"""GPU Instance Manager - Launch, SSH connect, run pipeline, stop"""

import boto3
import paramiko
import time
import os
from gpu_config import (
    AWS_REGION, GPU_AMI_ID, GPU_INSTANCE_TYPE, KEY_NAME,
    SUBNET_ID, SECURITY_GROUP_IDS, EFS_DNS, EFS_MOUNT_POINT,
    get_instance_tags
)

SSH_KEY_PATH = "/home/ec2-user/traffic-sign-inventory_keypair.pem"


def launch_and_run_pipeline_ssh(recording_id):
    """Launch GPU instance, run pipeline via SSH, stop instance."""
    
    ec2 = boto3.client('ec2', region_name=AWS_REGION)
    instance_id = None
    ssh = None
    
    try:
        print(f"[GPU] Launching instance for {recording_id}...")
        response = ec2.run_instances(
            ImageId=GPU_AMI_ID,
            InstanceType=GPU_INSTANCE_TYPE,
            KeyName=KEY_NAME,
            MinCount=1,
            MaxCount=1,
            SubnetId=SUBNET_ID,
            SecurityGroupIds=SECURITY_GROUP_IDS,
            TagSpecifications=get_instance_tags(recording_id),
            BlockDeviceMappings=[{
                'DeviceName': '/dev/xvda',
                'Ebs': {'VolumeSize': 100, 'VolumeType': 'gp3', 'DeleteOnTermination': True}
            }]
        )
        instance_id = response['Instances'][0]['InstanceId']
        print(f"✅ Instance launched: {instance_id}")
        
        print("[GPU] Waiting for instance to start...")
        waiter = ec2.get_waiter('instance_running')
        waiter.wait(InstanceIds=[instance_id])
        
        response = ec2.describe_instances(InstanceIds=[instance_id])
        public_ip = response['Reservations'][0]['Instances'][0]['PublicIpAddress']
        print(f"✅ Instance running: {public_ip}")
        
        print("[GPU] Waiting for SSH ready...")
        time.sleep(60)
        
        print("[GPU] Connecting SSH...")
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
        
        print(f"[GPU] Running pipeline (may take several minutes)...")
        recording_path = f"{EFS_MOUNT_POINT}/recordings/{recording_id}"
        pipeline_cmd = f"bash {EFS_MOUNT_POINT}/app/simulate_pipeline.sh {recording_path}"
        
        stdin, stdout, stderr = ssh.exec_command(pipeline_cmd, timeout=7200)
        
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
        
        output_file = f"{EFS_MOUNT_POINT}/recordings/{recording_id}/result_pipeline_stable/s7_export_csv/supports.csv"
        if not os.path.exists(output_file):
            raise Exception("Output file not found")
        print("✅ Output verified")
        
        ssh.close()
        print("✅ SSH closed")
        
        print(f"[GPU] Stopping instance {instance_id}...")
        ec2.stop_instances(InstanceIds=[instance_id])
        print("✅ Instance stopped")
        
        return True, instance_id, "Pipeline completed successfully"
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ ERROR: {error_msg}")
        
        if ssh:
            try:
                ssh.close()
            except:
                pass
        
        if instance_id:
            try:
                print(f"[GPU] Terminating instance {instance_id} after error...")
                ec2.terminate_instances(InstanceIds=[instance_id])
            except:
                pass
        
        return False, instance_id, error_msg


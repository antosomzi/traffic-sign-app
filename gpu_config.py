"""GPU Instance Configuration - AWS EC2 and EFS settings"""

import os

AWS_REGION = "us-east-2"

# GPU Instance
GPU_AMI_ID = "ami-0d67eb9a9a933bd88"
GPU_INSTANCE_TYPE = "g6e.xlarge"
KEY_NAME = "traffic-sign-inventory_keypair"

# Network
VPC_ID = "vpc-0933dfb2c976a7d1b"
SUBNET_ID = "subnet-098dc7573fb6bf8bd"
SECURITY_GROUP_IDS = [
    "sg-0906d54ac3d704022",
    "sg-0fc71fc185fe9b5e6"
]

# EFS
EFS_ID = "fs-0fdfeb8ca8304e991"
EFS_DNS = f"{EFS_ID}.efs.{AWS_REGION}.amazonaws.com"
EFS_MOUNT_POINT = "/home/ec2-user"

# Paths
PIPELINE_SCRIPT = f"{EFS_MOUNT_POINT}/app/simulate_pipeline.sh"
RECORDINGS_PATH = f"{EFS_MOUNT_POINT}/recordings"
FINAL_FILE_PATH = "result_pipeline_stable/s7_export_csv/supports.csv"

# Timeouts
INSTANCE_STOP_TIMEOUT = 7200
POLLING_INTERVAL = 30
PIPELINE_TIMEOUT = 7200

def get_instance_tags(recording_id):
    """Generate tags for GPU instance."""
    return [{
        'ResourceType': 'instance',
        'Tags': [
            {'Key': 'Name', 'Value': f'GPU-Pipeline-{recording_id}'},
            {'Key': 'Recording', 'Value': recording_id},
            {'Key': 'Type', 'Value': 'ML-Pipeline-GPU'},
            {'Key': 'ManagedBy', 'Value': 'TrafficSignInventory'},
            {'Key': 'AutoShutdown', 'Value': 'true'}
        ]
    }]


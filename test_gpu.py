#!/usr/bin/env python3
"""Test script to manually trigger the GPU pipeline task"""

import os
from tasks import run_pipeline_task

# Set to true to test GPU instance launch
os.environ['USE_GPU_INSTANCE'] = 'true'

# Use an existing recording ID from your recordings folder
recording_id = "2024_05_20_23_32_53_415"

print(f"🧪 Testing GPU pipeline for recording: {recording_id}")
print(f"   GPU mode: {os.getenv('USE_GPU_INSTANCE')}")
print("-" * 60)

try:
    result = run_pipeline_task(recording_id)
    print("-" * 60)
    print(f"✅ SUCCESS: {result}")
except Exception as e:
    print("-" * 60)
    print(f"❌ ERROR: {e}")
    import traceback
    traceback.print_exc()

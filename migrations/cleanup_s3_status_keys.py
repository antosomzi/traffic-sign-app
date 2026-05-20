#!/usr/bin/env python3
"""
Cleanup script to:
1) Update status.json video_s3_key from videos/prod/... to videos/production/...
2) Delete S3 recordings not in the allowlist (supports dry-run).

Default behavior is dry-run. Use --apply to perform changes.
"""

import argparse
import json
import os
import sys
from typing import Iterable, List, Tuple

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
import boto3


ALLOWED_RECORDING_IDS = {
    "2026_01_16_13_41_04",
    "2026_01_16_15_20_19",
    "2026_02_25_14_48_59_579",
    "2026_02_25_15_42_56_260",
    "2026_03_27_17_36_52_140",
    "2026_03_29_18_11_57_361",
    "2026_04_07_12_38_10_036",
    "2026_04_08_09_00_28_146",
    "2026_04_08_11_27_12_661",
    "2026_04_18_15_34_20_904",
    "2026_04_18_15_54_12_398",
    "2026_04_18_16_18_16_331",
    "2026_04_18_16_33_45_167",
    "2026_05_01_18_33_19_456",
    "2026_05_01_18_51_08_218",
    "2026_05_09_15_06_02_088",
    "2026_05_09_15_34_58_287",
}


def iter_recording_dirs(root: str) -> Iterable[str]:
    if not os.path.isdir(root):
        return
    for entry in os.listdir(root):
        full_path = os.path.join(root, entry)
        if os.path.isdir(full_path):
            yield full_path


def find_status_updates(recordings_root: str) -> List[Tuple[str, str, str]]:
    """Return list of (status_path, old_key, new_key) updates needed."""
    updates = []
    for recording_path in iter_recording_dirs(recordings_root):
        status_path = os.path.join(recording_path, "status.json")
        if not os.path.exists(status_path):
            continue
        try:
            with open(status_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        s3_key = data.get("video_s3_key")
        if not s3_key or "videos/prod/" not in s3_key:
            continue

        new_key = s3_key.replace("videos/prod/", "videos/production/")
        updates.append((status_path, s3_key, new_key))

    return updates


def apply_status_updates(updates: List[Tuple[str, str, str]]) -> None:
    for status_path, _, new_key in updates:
        with open(status_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["video_s3_key"] = new_key
        with open(status_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


def list_recording_prefixes(s3_client, bucket: str, prefix_root: str) -> List[str]:
    """Return recording IDs under a prefix root like 'videos/production/' or 'videos/prod/'."""
    paginator = s3_client.get_paginator("list_objects_v2")
    recording_ids = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix_root, Delimiter="/"):
        for common_prefix in page.get("CommonPrefixes", []):
            full_prefix = common_prefix.get("Prefix", "")
            # Expected: videos/{env}/{recording_id}/
            parts = full_prefix.strip("/").split("/")
            if len(parts) >= 3:
                recording_ids.append(parts[2])
    return recording_ids


def list_objects_for_recording(s3_client, bucket: str, prefix_root: str, recording_id: str) -> List[str]:
    prefix = f"{prefix_root}{recording_id}/"
    paginator = s3_client.get_paginator("list_objects_v2")
    keys = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def chunked(items: List[str], size: int = 1000) -> Iterable[List[str]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def delete_objects(s3_client, bucket: str, keys: List[str]) -> None:
    for batch in chunked(keys, 1000):
        s3_client.delete_objects(
            Bucket=bucket,
            Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True},
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cleanup status.json S3 keys and remove non-allowlisted S3 recordings",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes (default is dry-run)",
    )
    parser.add_argument(
        "--recordings-root",
        default=Config.EXTRACT_FOLDER,
        help="Recordings root folder (default: Config.EXTRACT_FOLDER)",
    )
    parser.add_argument(
        "--include-prod-prefix",
        action="store_true",
        help="Also scan/delete objects under videos/prod/ (legacy)",
    )

    args = parser.parse_args()
    dry_run = not args.apply

    print("=" * 60)
    print("Cleanup: status.json S3 keys + S3 recordings")
    print("=" * 60)
    print(f"Dry run: {dry_run}")
    print(f"Recordings root: {args.recordings_root}")
    print(f"S3 bucket: {Config.S3_BUCKET_NAME}")
    print(f"S3 region: {Config.S3_REGION}")
    print("=" * 60)

    # 1) status.json updates
    updates = find_status_updates(args.recordings_root)
    if updates:
        print("\n[STATUS.JSON UPDATES]")
        for status_path, old_key, new_key in updates:
            print(f"- {status_path}")
            print(f"  {old_key} -> {new_key}")
        print(f"Total status.json updates: {len(updates)}")
        if not dry_run:
            apply_status_updates(updates)
            print("✅ status.json updates applied")
    else:
        print("\n[STATUS.JSON UPDATES] None needed")

    # 2) S3 cleanup
    s3_client = boto3.client("s3", region_name=Config.S3_REGION)
    bucket = Config.S3_BUCKET_NAME

    prefix_roots = ["videos/production/"]
    if args.include_prod_prefix:
        prefix_roots.append("videos/prod/")

    keys_to_delete: List[str] = []
    recordings_to_delete: List[str] = []
    total_prefixes_found = 0
    kept_prefixes = 0

    print("\n[S3 CLEANUP]")
    for prefix_root in prefix_roots:
        recording_ids = list_recording_prefixes(s3_client, bucket, prefix_root)
        total_prefixes_found += len(recording_ids)
        for recording_id in recording_ids:
            if recording_id in ALLOWED_RECORDING_IDS:
                kept_prefixes += 1
                continue
            recordings_to_delete.append(f"{prefix_root}{recording_id}/")
            keys = list_objects_for_recording(s3_client, bucket, prefix_root, recording_id)
            keys_to_delete.extend(keys)

    print(
        f"Summary: total prefixes found={total_prefixes_found}, "
        f"kept (allowlist)={kept_prefixes}, "
        f"to delete={len(set(recordings_to_delete))}"
    )

    if recordings_to_delete:
        print("Recordings to delete (prefixes):")
        for prefix in sorted(set(recordings_to_delete)):
            print(f"- {prefix}")
    else:
        print("No recording prefixes to delete.")

    if keys_to_delete:
        print("\nS3 objects to delete:")
        for key in keys_to_delete:
            print(f"- {key}")
        print(f"Total objects to delete: {len(keys_to_delete)}")
        if not dry_run:
            delete_objects(s3_client, bucket, keys_to_delete)
            print("✅ S3 deletions applied")
    else:
        print("No S3 objects to delete.")


if __name__ == "__main__":
    main()

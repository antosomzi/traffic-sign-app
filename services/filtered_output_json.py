"""Enrich output.json with filtered cluster IDs when route-filter CSV exists."""

import csv
import json
import os

from config import Config


def _extract_sorted_cluster_ids(data: dict) -> list:
    """Extract unique cluster_id values from output.frames and sort them."""
    frames = data["output"]["frames"]
    unique_cluster_ids = set()

    for frame in frames:
        for sign in frame["signs"]:
            unique_cluster_ids.add(sign["cluster_id"])

    return sorted(unique_cluster_ids)


def _load_filtered_indices(filtered_csv_path: str) -> set[int]:
    """Read ID column from signs_merged_filtered.csv (cluster index list)."""
    filtered_indices: set[int] = set()
    with open(filtered_csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_id = (row.get("ID") or "").strip()
            if not raw_id:
                continue
            try:
                filtered_indices.add(int(raw_id))
            except ValueError:
                # Ignore malformed IDs and continue processing.
                continue
    return filtered_indices


def filter_output_json(recording_id):
    """Add root field `filtered_cluster_ids` into output.json when filtered CSV exists.

    The CSV `ID` values are interpreted as indices into the sorted unique list of
    cluster IDs found in `output.json`.
    """
    recording_path = os.path.join(Config.EXTRACT_FOLDER, recording_id)
    filtered_csv_path = os.path.join(
        recording_path,
        "result_pipeline_stable",
        "signs_merged_filtered.csv",
    )
    if not os.path.isfile(filtered_csv_path):
        print(
            f"[ROUTE-FILTER] ℹ️  signs_merged_filtered.csv not found for recording {recording_id}, skipping output.json enrichment"
        )
        return None

    output_json_path = os.path.join(
        recording_path,
        "result_pipeline_stable",
        "s6_localization",
        "output.json",
    )
    if not os.path.isfile(output_json_path):
        print(f"[ROUTE-FILTER] ⚠️  output.json not found for recording {recording_id}, skipping")
        return None

    with open(output_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    sorted_cluster_ids = _extract_sorted_cluster_ids(data)
    if not sorted_cluster_ids:
        data["filtered_cluster_ids"] = []
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        print(f"[ROUTE-FILTER] ℹ️  No cluster_id found in output.json for recording {recording_id}")
        return output_json_path

    filtered_indices = _load_filtered_indices(filtered_csv_path)
    selected_cluster_ids = [
        cluster_id
        for idx, cluster_id in enumerate(sorted_cluster_ids)
        if idx in filtered_indices
    ]

    data["filtered_cluster_ids"] = selected_cluster_ids

    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    print(
        f"[ROUTE-FILTER] ✅ Added filtered_cluster_ids ({len(selected_cluster_ids)} items) to output.json for recording {recording_id}"
    )
    return output_json_path

"""Tests for filtered_output_json service behavior on real fixtures."""

import csv
import json
import shutil
from pathlib import Path

from config import Config
from services.filtered_output_json import filter_output_json


def _load_sorted_cluster_ids(output_json_path: Path) -> list[int]:
    with open(output_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    unique_ids = set()
    for frame in data["output"]["frames"]:
        for sign in frame["signs"]:
            unique_ids.add(sign["cluster_id"])

    return sorted(unique_ids)


def _load_allowed_indices(signs_csv_path: Path) -> set[int]:
    allowed = set()
    with open(signs_csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            allowed.add(int(row["ID"]))
    return allowed


def test_filter_output_json_adds_root_filtered_list_without_touching_frames(tmp_path, monkeypatch):
    """Only root filtered list is added; frames/signs content must stay unchanged."""
    recording_id = "rec_fixture"

    # Build expected recording structure for filter_output_json(...)
    recording_path = tmp_path / "recordings" / recording_id
    localization_dir = recording_path / "result_pipeline_stable" / "s6_localization"
    localization_dir.mkdir(parents=True, exist_ok=True)

    fixture_output = Path(__file__).with_name("output.json")
    fixture_signs = Path(__file__).with_name("signs.csv")

    output_path = localization_dir / "output.json"
    filtered_csv_path = recording_path / "result_pipeline_stable" / "signs_merged_filtered.csv"

    shutil.copyfile(fixture_output, output_path)
    shutil.copyfile(fixture_signs, filtered_csv_path)

    # Snapshot original JSON (to ensure frames are not modified)
    with open(output_path, "r", encoding="utf-8") as f:
        original = json.load(f)

    # Compute expected mapping from ORIGINAL output file
    sorted_cluster_ids = _load_sorted_cluster_ids(output_path)
    allowed_indices = _load_allowed_indices(filtered_csv_path)
    expected_cluster_ids = [
        cid for idx, cid in enumerate(sorted_cluster_ids) if idx in allowed_indices
    ]

    monkeypatch.setattr(Config, "EXTRACT_FOLDER", str(tmp_path / "recordings"))

    updated_output_path = filter_output_json(recording_id)
    assert updated_output_path is not None

    with open(updated_output_path, "r", encoding="utf-8") as f:
        updated = json.load(f)

    # Root attribute should match the expected cluster IDs selected via CSV index IDs
    assert updated.get("filtered_cluster_ids") == expected_cluster_ids

    # Frames/signs content must stay unchanged
    assert updated["output"]["frames"] == original["output"]["frames"]

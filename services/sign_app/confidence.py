import csv
import json
import os
from typing import Optional


def _build_confidence_stats(data: dict) -> dict[int, dict[str, float]]:
    """Aggregate confidence sums and counts per cluster_id."""
    frames = data.get("output", {}).get("frames", [])
    stats: dict[int, dict[str, float]] = {}

    for frame in frames:
        for sign in frame.get("signs", []):
            cluster_id = sign.get("cluster_id")
            if cluster_id is None:
                continue

            if cluster_id not in stats:
                stats[cluster_id] = {
                    "classification_sum": 0.0,
                    "classification_count": 0.0,
                    "detection_sum": 0.0,
                    "detection_count": 0.0,
                }

            classification_confidence = sign.get("classification_confidence")
            detection_confidence = sign.get("detection_confidence")

            if isinstance(classification_confidence, (int, float)):
                stats[cluster_id]["classification_sum"] += float(classification_confidence)
                stats[cluster_id]["classification_count"] += 1.0

            if isinstance(detection_confidence, (int, float)):
                stats[cluster_id]["detection_sum"] += float(detection_confidence)
                stats[cluster_id]["detection_count"] += 1.0

    return stats


def _format_mean(total: float, count: float) -> str:
    if count <= 0:
        return "0"
    return f"{total / count:.6f}"


def add_confidence_to_merged_signs_csv(recording_path: str) -> Optional[str]:
    result_folder = os.path.join(recording_path, "result_pipeline_stable")
    merged_csv = os.path.join(result_folder, "signs_merged.csv")
    output_json_path = os.path.join(
        recording_path,
        "result_pipeline_stable",
        "s6_localization",
        "output.json",
    )

    if not os.path.isfile(merged_csv):
        print("[CONFIDENCE] ⚠️  signs_merged.csv not found, skipping")
        return None

    if not os.path.isfile(output_json_path):
        print("[CONFIDENCE] ⚠️  output.json not found, skipping")
        return None

    try:
        with open(output_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        print(f"[CONFIDENCE] ❌ Error reading output.json: {exc}")
        return None

    confidence_stats = _build_confidence_stats(data)
    if not confidence_stats:
        print("[CONFIDENCE] ⚠️  No cluster_id found in output.json, skipping")
        return None

    updated_rows: list[dict[str, str]] = []
    header: list[str] = []

    try:
        with open(merged_csv, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            header = list(reader.fieldnames or [])

            if "classificationConfidence" not in header:
                header.append("classificationConfidence")
            if "detectionConfidence" not in header:
                header.append("detectionConfidence")

            for row in reader:
                raw_id = (row.get("ID") or "").strip()
                classification_value = "0"
                detection_value = "0"

                try:
                    cluster_id = int(raw_id)
                    stats = confidence_stats.get(cluster_id)
                    if stats:
                        classification_value = _format_mean(
                            stats["classification_sum"], stats["classification_count"]
                        )
                        detection_value = _format_mean(
                            stats["detection_sum"], stats["detection_count"]
                        )
                except ValueError:
                    pass

                row["classificationConfidence"] = classification_value
                row["detectionConfidence"] = detection_value
                updated_rows.append(row)
    except Exception as exc:
        print(f"[CONFIDENCE] ❌ Error reading signs_merged.csv: {exc}")
        return None

    try:
        with open(merged_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=header)
            writer.writeheader()
            writer.writerows(updated_rows)
        print(f"[CONFIDENCE] ✅ Added confidence columns to {merged_csv}")
        return merged_csv
    except Exception as exc:
        print(f"[CONFIDENCE] ❌ Error writing signs_merged.csv: {exc}")
        return None



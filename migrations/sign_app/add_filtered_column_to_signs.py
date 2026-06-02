"""
Migration script to backfill `filtered` column into signs_merged.csv.

For each recording that has both signs_merged.csv and signs_merged_filtered.csv,
this script adds a `filtered` column to signs_merged.csv and sets it to:
- 1 if the sign ID exists in signs_merged_filtered.csv
- 0 otherwise

Run:
    python migrations/add_filtered_column_to_signs.py
"""

import csv
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config


def _load_filtered_ids(filtered_csv_path: str) -> set[str]:
    filtered_ids: set[str] = set()
    with open(filtered_csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_id = (row.get("ID") or "").strip()
            if raw_id:
                filtered_ids.add(raw_id)
    return filtered_ids


def _update_merged_csv(merged_csv_path: str, filtered_ids: set[str]) -> bool:
    updated_rows: list[dict[str, str]] = []

    with open(merged_csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])

        if "filtered" not in fieldnames:
            fieldnames.append("filtered")

        for row in reader:
            raw_id = (row.get("ID") or "").strip()
            row["filtered"] = "1" if raw_id in filtered_ids else "0"
            updated_rows.append(row)

    with open(merged_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(updated_rows)

    return True


def main() -> int:
    recordings_root = Config.EXTRACT_FOLDER

    if not os.path.isdir(recordings_root):
        print(f"Recordings folder not found: {recordings_root}")
        return 1

    updated_count = 0
    skipped_count = 0
    error_count = 0

    for rec_id in os.listdir(recordings_root):
        rec_folder = os.path.join(recordings_root, rec_id)
        if not os.path.isdir(rec_folder):
            continue

        result_folder = os.path.join(rec_folder, "result_pipeline_stable")
        merged_csv = os.path.join(result_folder, "signs_merged.csv")
        filtered_csv = os.path.join(result_folder, "signs_merged_filtered.csv")

        if not os.path.isfile(merged_csv) or not os.path.isfile(filtered_csv):
            skipped_count += 1
            continue

        try:
            filtered_ids = _load_filtered_ids(filtered_csv)
            _update_merged_csv(merged_csv, filtered_ids)

            try:
                os.remove(filtered_csv)
            except OSError as exc:
                print(f"  ⚠️ {rec_id}: could not delete signs_merged_filtered.csv - {exc}")

            print(f"  ✅ {rec_id}: updated filtered column")
            updated_count += 1
        except Exception as exc:
            print(f"  ❌ {rec_id}: error updating merged CSV - {exc}")
            error_count += 1

    print("=" * 60)
    print("Migration Summary:")
    print(f"  ✅ Updated: {updated_count}")
    print(f"  ⏭️ Skipped (missing CSVs): {skipped_count}")
    print(f"  ❌ Errors: {error_count}")
    print("=" * 60)

    return 1 if error_count else 0


if __name__ == "__main__":
    sys.exit(main())

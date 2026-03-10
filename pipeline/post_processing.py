"""Post-processing step: merge signs.csv + supports.csv into a single file.

After the ML pipeline finishes (s7_export_csv), this module reads both raw
CSV files from that stage, joins them via the Foreign Key → Support ID
relationship, and writes a single ``signs_merged.csv`` to
``result_pipeline_stable/``.

Output format (one row per detected sign):
    ID,MUTCD Code,Position on the Support,Height (in),Width (in),Longitude,Latitude

Every consumer (download, map, DB import) can then read this single file
instead of re-doing the merge at runtime.
"""

import csv
import os


MERGED_FILENAME = "signs_merged.csv"

MERGED_HEADER = [
    "ID",
    "MUTCD Code",
    "Position on the Support",
    "Height (in)",
    "Width (in)",
    "Longitude",
    "Latitude",
]


def generate_merged_signs_csv(recording_path: str) -> str | None:
    """Merge ``s7_export_csv/signs.csv`` and ``supports.csv`` and write the
    result into ``result_pipeline_stable/signs_merged.csv``.

    Args:
        recording_path: Absolute path to the recording directory,
            e.g. ``/home/ec2-user/recordings/2024_05_20_23_32_53_415``

    Returns:
        The absolute path to the written ``signs_merged.csv``, or ``None``
        if the source CSV files are missing / empty.
    """
    result_folder = os.path.join(recording_path, "result_pipeline_stable")
    s7_folder = os.path.join(result_folder, "s7_export_csv")

    supports_csv = os.path.join(s7_folder, "supports.csv")
    signs_csv = os.path.join(s7_folder, "signs.csv")

    if not os.path.isfile(supports_csv) or not os.path.isfile(signs_csv):
        print(f"[POST] ⚠️  Missing source CSV(s) in {s7_folder}, skipping merge")
        return None

    # ------------------------------------------------------------------
    # 1. Load support coordinates keyed by ID
    # ------------------------------------------------------------------
    support_coords: dict[str, tuple[str, str]] = {}
    try:
        with open(supports_csv, "r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                sid = row.get("ID", "").strip()
                lon = row.get("Longitude", "").strip()
                lat = row.get("Latitude", "").strip()
                if sid and lon and lat:
                    support_coords[sid] = (lon, lat)
    except Exception as e:
        print(f"[POST] ❌ Error reading supports.csv: {e}")
        return None

    # ------------------------------------------------------------------
    # 2. Read signs.csv and join with supports
    # ------------------------------------------------------------------
    merged_rows: list[list[str]] = []
    try:
        with open(signs_csv, "r", newline="", encoding="utf-8") as f:
            for idx, row in enumerate(csv.DictReader(f)):
                foreign_key = row.get("Foreign Key", "").strip()
                mutcd = row.get("MUTCD Code", "").strip()
                position = row.get("Position on the Support", "1").strip()
                height = row.get("Height (in)", "0").strip()
                width = row.get("Width (in)", "0").strip()

                lon, lat = support_coords.get(foreign_key, ("", ""))
                merged_rows.append([str(idx), mutcd, position, height, width, lon, lat])
    except Exception as e:
        print(f"[POST] ❌ Error reading signs.csv: {e}")
        return None

    if not merged_rows:
        print(f"[POST] ⚠️  No sign rows produced after merge, skipping write")
        return None

    # ------------------------------------------------------------------
    # 3. Write the merged file
    # ------------------------------------------------------------------
    output_path = os.path.join(result_folder, MERGED_FILENAME)
    try:
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(MERGED_HEADER)
            writer.writerows(merged_rows)
        print(f"[POST] ✅ Wrote {len(merged_rows)} signs → {output_path}")
        return output_path
    except Exception as e:
        print(f"[POST] ❌ Error writing {MERGED_FILENAME}: {e}")
        return None


def get_merged_signs_csv_path(recording_path: str) -> str | None:
    """Return the path to ``signs_merged.csv`` if it already exists.

    Args:
        recording_path: Absolute path to the recording directory.

    Returns:
        Absolute path to the file, or ``None`` if it doesn't exist.
    """
    path = os.path.join(recording_path, "result_pipeline_stable", MERGED_FILENAME)
    return path if os.path.isfile(path) else None

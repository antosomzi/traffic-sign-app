"""
Migration script: generate signs_merged.csv for all existing recordings.

For every recording that has s7_export_csv/signs.csv + supports.csv but is
missing result_pipeline_stable/signs_merged.csv, this script performs the
merge and writes the file.

Run once locally and once on the production server:
    python migrations/generate_merged_signs.py

Options:
    --dry-run   Show what would be generated without writing anything.
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from pipeline.post_processing import generate_merged_signs_csv, get_merged_signs_csv_path


def migrate(dry_run: bool = False):
    recordings_root = Config.EXTRACT_FOLDER

    if not os.path.isdir(recordings_root):
        print(f"❌ Recordings folder not found: {recordings_root}")
        return

    print(f"📂 Scanning recordings in: {recordings_root}")
    print(f"   Environment: {Config.ENVIRONMENT}")
    if dry_run:
        print("   ⚠️  DRY-RUN mode – no files will be written\n")
    print()

    already = 0
    generated = 0
    skipped = 0
    errors = 0

    entries = sorted(os.listdir(recordings_root))
    for rec_id in entries:
        rec_folder = os.path.join(recordings_root, rec_id)
        if not os.path.isdir(rec_folder):
            continue

        s7_folder = os.path.join(rec_folder, "result_pipeline_stable", "s7_export_csv")
        signs_csv = os.path.join(s7_folder, "signs.csv")
        supports_csv = os.path.join(s7_folder, "supports.csv")

        # Skip recordings that never completed the pipeline
        if not os.path.isfile(signs_csv) or not os.path.isfile(supports_csv):
            print(f"  ⏭  {rec_id}: no s7_export_csv output, skipping")
            skipped += 1
            continue

        # Skip if already migrated
        if get_merged_signs_csv_path(rec_folder):
            print(f"  ✅ {rec_id}: signs_merged.csv already exists")
            already += 1
            continue

        if dry_run:
            print(f"  🔧 {rec_id}: would generate signs_merged.csv")
            generated += 1
            continue

        # Generate the merged file
        result = generate_merged_signs_csv(rec_folder)
        if result:
            print(f"  ✅ {rec_id}: generated {result}")
            generated += 1
        else:
            print(f"  ❌ {rec_id}: merge failed (empty or error)")
            errors += 1

    print()
    print("=" * 50)
    print(f"  Already existed : {already}")
    print(f"  Generated       : {generated}")
    print(f"  Skipped (no s7) : {skipped}")
    print(f"  Errors          : {errors}")
    print(f"  Total scanned   : {already + generated + skipped + errors}")
    print("=" * 50)


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    migrate(dry_run=dry_run)

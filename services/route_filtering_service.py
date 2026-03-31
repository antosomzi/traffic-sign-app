"""Route filtering service: keep only signs near organization routes.

After the ML pipeline produces ``signs_merged.csv``, this module loads the
organisation's GeoJSON routes file, creates a generous buffer zone around
every route LineString, and filters the signs so that only those falling
inside the buffer are kept.  The result is written to
``signs_merged_filtered.csv`` next to the original file.

Design decisions
~~~~~~~~~~~~~~~~
* **Buffer distance**: 50 metres (~164 ft).  This is deliberately generous
  so that no real sign is ever discarded (no false negatives).  A sign that
  is 50 m from the nearest road centreline is extremely unlikely in
  practice, so this is very safe.
* **Projection**: We reproject both the routes and the sign points to a
  local UTM zone derived from the centroid of the routes, so that the
  buffer is metric and accurate regardless of where in the world the data
  comes from.
* **Fallback**: If the organisation has no routes file, or if geopandas is
  not available, the function returns ``None`` and the unfiltered CSV is
  left as-is.  Consumers should prefer ``signs_merged_filtered.csv`` when
  it exists and fall back to ``signs_merged.csv``.
"""

import csv
import json
import os
from typing import Optional

FILTERED_FILENAME = "signs_merged_filtered.csv"

# Buffer distance in metres – intentionally large to avoid false negatives
BUFFER_METRES = 50


def _get_org_routes_path(org_id: int) -> str:
    """Return the canonical path for an organisation's routes GeoJSON file."""
    from config import Config
    return os.path.join(Config.ORG_ROUTES_FOLDER, str(org_id), "routes.geojson")


def _get_org_id_for_recording(recording_id: str) -> Optional[int]:
    """Look up the organisation that owns *recording_id*."""
    import sys
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if APP_DIR not in sys.path:
        sys.path.insert(0, APP_DIR)
        
    try:
        from models.recording import Recording
        rec = Recording.get_by_id(recording_id)
        if rec:
            return rec.organization_id
    except Exception as exc:
        print(f"[ROUTE-FILTER] ⚠️  Could not look up org for {recording_id}: {exc}")
    return None


def filter_signs_by_org_routes(
    recording_path: str,
    recording_id: str,
    org_id: Optional[int] = None,
) -> Optional[str]:
    """Filter ``signs_merged.csv`` to keep only signs near org routes.

    Args:
        recording_path: Absolute path to the recording directory.
        recording_id: The recording ID (used to look up org if *org_id* is
            not supplied).
        org_id: Organisation ID.  If ``None`` the function will try to
            resolve it from the DB.

    Returns:
        Path to the written ``signs_merged_filtered.csv``, or ``None`` if
        filtering was skipped (no routes, no signs, library missing …).
    """
    # ------------------------------------------------------------------
    # 0. Locate the merged CSV
    # ------------------------------------------------------------------
    result_folder = os.path.join(recording_path, "result_pipeline_stable")
    merged_csv = os.path.join(result_folder, "signs_merged.csv")

    if not os.path.isfile(merged_csv):
        print("[ROUTE-FILTER] ⚠️  signs_merged.csv not found, skipping filter")
        return None

    # ------------------------------------------------------------------
    # 1. Resolve organisation and locate its routes GeoJSON
    # ------------------------------------------------------------------
    if org_id is None:
        org_id = _get_org_id_for_recording(recording_id)
    if org_id is None:
        print("[ROUTE-FILTER] ⚠️  Cannot resolve org for recording, skipping filter")
        return None

    routes_path = _get_org_routes_path(org_id)
    if not os.path.isfile(routes_path):
        print(f"[ROUTE-FILTER] ℹ️  No routes file for org {org_id}, skipping filter")
        return None

    # ------------------------------------------------------------------
    # 2. Import heavy geospatial libs (fail gracefully)
    # ------------------------------------------------------------------
    try:
        import geopandas as gpd
        from shapely.geometry import Point
        from shapely.ops import unary_union
        from pyproj import CRS
    except ImportError as exc:
        print(f"[ROUTE-FILTER] ⚠️  Geospatial library missing ({exc}), skipping filter")
        return None

    # ------------------------------------------------------------------
    # 3. Load routes and build a buffered zone
    # ------------------------------------------------------------------
    try:
        routes_gdf = gpd.read_file(routes_path)
    except Exception as exc:
        print(f"[ROUTE-FILTER] ❌ Error reading routes GeoJSON: {exc}")
        return None

    if routes_gdf.empty:
        print("[ROUTE-FILTER] ⚠️  Routes GeoJSON is empty, skipping filter")
        return None

    # Ensure CRS is WGS84 first
    if routes_gdf.crs is None:
        routes_gdf = routes_gdf.set_crs("EPSG:4326")
    else:
        routes_gdf = routes_gdf.to_crs("EPSG:4326")

    # Determine a suitable UTM CRS from the centroid of the routes
    centroid = routes_gdf.geometry.unary_union.centroid
    utm_crs = CRS.from_proj4(
        f"+proj=utm +zone={_utm_zone(centroid.x)} "
        f"+{'south ' if centroid.y < 0 else ''}+datum=WGS84"
    )

    routes_utm = routes_gdf.to_crs(utm_crs)
    buffered_union = unary_union(routes_utm.geometry.buffer(BUFFER_METRES))

    # ------------------------------------------------------------------
    # 4. Read signs and filter
    # ------------------------------------------------------------------
    header = None
    kept_rows: list[list[str]] = []
    total = 0

    try:
        with open(merged_csv, "r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)  # first row is header

            lon_idx = header.index("Longitude")
            lat_idx = header.index("Latitude")

            for row in reader:
                total += 1
                try:
                    lon = float(row[lon_idx])
                    lat = float(row[lat_idx])
                except (ValueError, IndexError):
                    # Keep rows with invalid coords (better safe)
                    kept_rows.append(row)
                    continue

                # Project point to UTM and test containment
                pt_wgs = Point(lon, lat)
                pt_utm = gpd.GeoSeries([pt_wgs], crs="EPSG:4326").to_crs(utm_crs).iloc[0]

                if buffered_union.contains(pt_utm):
                    kept_rows.append(row)
    except Exception as exc:
        print(f"[ROUTE-FILTER] ❌ Error reading signs_merged.csv: {exc}")
        return None

    if header is None:
        print("[ROUTE-FILTER] ⚠️  signs_merged.csv appears empty, skipping filter")
        return None

    # ------------------------------------------------------------------
    # 5. Write filtered CSV
    # ------------------------------------------------------------------
    output_path = os.path.join(result_folder, FILTERED_FILENAME)
    try:
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(kept_rows)
        print(
            f"[ROUTE-FILTER] ✅ Kept {len(kept_rows)}/{total} signs "
            f"(buffer={BUFFER_METRES}m) → {output_path}"
        )
        return output_path
    except Exception as exc:
        print(f"[ROUTE-FILTER] ❌ Error writing filtered CSV: {exc}")
        return None


def _utm_zone(longitude: float) -> int:
    """Return the UTM zone number for a given longitude."""
    return int((longitude + 180) / 6) + 1


def get_filtered_signs_csv_path(recording_path: str) -> Optional[str]:
    """Return path to ``signs_merged_filtered.csv`` if it exists."""
    path = os.path.join(recording_path, "result_pipeline_stable", FILTERED_FILENAME)
    return path if os.path.isfile(path) else None


def get_best_signs_csv_path(recording_path: str) -> Optional[str]:
    """Return the best available signs CSV: filtered if it exists, else merged."""
    filtered = get_filtered_signs_csv_path(recording_path)
    if filtered:
        return filtered
    merged = os.path.join(recording_path, "result_pipeline_stable", "signs_merged.csv")
    return merged if os.path.isfile(merged) else None

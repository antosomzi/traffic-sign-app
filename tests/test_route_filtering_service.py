"""Tests for route filtering service."""

import csv
import json
from pathlib import Path

from pyproj import CRS, Transformer

from services.route_filtering_service import (
    BUFFER_METRES,
    _utm_zone,
    filter_signs_by_org_routes,
    get_best_signs_csv_path,
)


def _write_merged_csv(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "ID",
            "MUTCD Code",
            "Position on the Support",
            "Height (in)",
            "Width (in)",
            "Longitude",
            "Latitude",
        ])
        # Near the route (should be kept)
        writer.writerow(["0", "R1-1", "1", "30", "30", "-111.0000", "32.3050"])
        # Far from the route (should be filtered out)
        writer.writerow(["1", "W1-1", "1", "30", "30", "-111.0200", "32.3050"])


def _write_org_routes(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [-111.0000, 32.3000],
                        [-111.0000, 32.3100],
                    ],
                },
            }
        ],
    }
    path.write_text(json.dumps(geojson), encoding="utf-8")


def _build_meter_accurate_route_and_points():
    """Build a route and sign points in UTM then convert to WGS84.

    Returns:
        tuple[dict, list[dict]]: (geojson_routes, points)
        where points entries are: {"id": str, "lon": float, "lat": float}
    """
    # Reference location (Arizona-ish, same area as existing samples)
    ref_lon, ref_lat = -111.0, 32.305
    zone = _utm_zone(ref_lon)
    utm_crs = CRS.from_proj4(f"+proj=utm +zone={zone} +datum=WGS84")

    to_utm = Transformer.from_crs("EPSG:4326", utm_crs, always_xy=True)
    to_wgs = Transformer.from_crs(utm_crs, "EPSG:4326", always_xy=True)

    x0, y0 = to_utm.transform(ref_lon, ref_lat)

    # Main vertical route centered at ref point (in meters)
    route_main_utm = [
        (x0, y0 - 300),
        (x0, y0 + 300),
    ]

    # Extra route as MultiLineString branch ~700m east (ensures MultiLineString is handled)
    route_branch_utm = [
        (x0 + 700, y0 - 150),
        (x0 + 700, y0 + 150),
    ]

    def to_wgs_coords(line_utm):
        return [list(to_wgs.transform(x, y)) for x, y in line_utm]

    routes_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "main_line"},
                "geometry": {
                    "type": "LineString",
                    "coordinates": to_wgs_coords(route_main_utm),
                },
            },
            {
                "type": "Feature",
                "properties": {"name": "branch_lines"},
                "geometry": {
                    "type": "MultiLineString",
                    "coordinates": [
                        to_wgs_coords(route_branch_utm),
                        to_wgs_coords([(x0 + 1000, y0 - 120), (x0 + 1000, y0 + 120)]),
                    ],
                },
            },
        ],
    }

    # Signs at controlled distances from main route centerline (x-axis offset)
    # BUFFER_METRES=50 => 49m should be kept, 51m should be filtered.
    points_utm = [
        ("in_center", x0, y0),
        ("in_30m", x0 + 30, y0 + 20),
        ("in_49m", x0 + (BUFFER_METRES - 1), y0 - 10),
        ("out_51m", x0 + (BUFFER_METRES + 1), y0 + 5),
        ("out_200m", x0 + 200, y0),
        # Near branch route in MultiLineString => should be kept
        ("in_branch_10m", x0 + 700 + 10, y0),
    ]

    points = []
    for pid, x, y in points_utm:
        lon, lat = to_wgs.transform(x, y)
        points.append({"id": pid, "lon": lon, "lat": lat})

    return routes_geojson, points


def _write_merged_csv_with_points(path: Path, points):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "ID",
            "MUTCD Code",
            "Position on the Support",
            "Height (in)",
            "Width (in)",
            "Longitude",
            "Latitude",
        ])

        for p in points:
            writer.writerow([
                p["id"],
                "R1-1",
                "1",
                "30",
                "30",
                f"{p['lon']:.8f}",
                f"{p['lat']:.8f}",
            ])

        # Invalid coordinate row is intentionally kept by implementation (safe fallback)
        writer.writerow([
            "invalid_coord",
            "W1-1",
            "1",
            "30",
            "30",
            "not_a_lon",
            "not_a_lat",
        ])


def _write_routes_geojson(path: Path, geojson_data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(geojson_data), encoding="utf-8")


def test_filter_signs_by_org_routes_keeps_only_signs_near_routes(tmp_path, monkeypatch):
    recording_id = "rec_test"
    org_id = 42

    recording_path = tmp_path / "recordings" / recording_id
    merged_csv = recording_path / "result_pipeline_stable" / "signs_merged.csv"
    _write_merged_csv(merged_csv)

    org_routes_root = tmp_path / "org_routes"
    _write_org_routes(org_routes_root / str(org_id) / "routes.geojson")

    from config import Config

    monkeypatch.setattr(Config, "ORG_ROUTES_FOLDER", str(org_routes_root))

    output = filter_signs_by_org_routes(
        recording_path=str(recording_path),
        recording_id=recording_id,
        org_id=org_id,
    )

    assert output is not None
    output_path = Path(output)
    assert output_path.exists()

    with open(output_path, "r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 1
    assert rows[0]["ID"] == "0"


def test_get_best_signs_csv_path_falls_back_to_merged_when_filtered_missing(tmp_path):
    recording_path = tmp_path / "recordings" / "rec_fallback"
    merged_csv = recording_path / "result_pipeline_stable" / "signs_merged.csv"
    _write_merged_csv(merged_csv)

    best_path = get_best_signs_csv_path(str(recording_path))
    assert best_path is not None
    assert best_path.endswith("signs_merged.csv")


def test_filter_signs_by_org_routes_complex_meter_cases(tmp_path, monkeypatch):
    """Complex scenario with near/limit/outside signs + MultiLineString route.

    This test creates geometries in UTM metres to control exact offsets from
    route centerlines, then converts back to WGS84 for CSV/GeoJSON realism.
    """
    recording_id = "rec_complex"
    org_id = 777

    recording_path = tmp_path / "recordings" / recording_id
    merged_csv = recording_path / "result_pipeline_stable" / "signs_merged.csv"

    routes_geojson, points = _build_meter_accurate_route_and_points()
    _write_merged_csv_with_points(merged_csv, points)

    org_routes_root = tmp_path / "org_routes"
    _write_routes_geojson(org_routes_root / str(org_id) / "routes.geojson", routes_geojson)

    from config import Config

    monkeypatch.setattr(Config, "ORG_ROUTES_FOLDER", str(org_routes_root))

    output = filter_signs_by_org_routes(
        recording_path=str(recording_path),
        recording_id=recording_id,
        org_id=org_id,
    )

    assert output is not None
    output_path = Path(output)
    assert output_path.exists()

    with open(output_path, "r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    kept_ids = {row["ID"] for row in rows}

    # Expected kept
    assert "in_center" in kept_ids
    assert "in_30m" in kept_ids
    assert "in_49m" in kept_ids
    assert "in_branch_10m" in kept_ids
    assert "invalid_coord" in kept_ids

    # Expected filtered out
    assert "out_51m" not in kept_ids
    assert "out_200m" not in kept_ids

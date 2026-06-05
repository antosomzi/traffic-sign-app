"""
ZIP upload validation and ingestion helpers for curves.
"""
from __future__ import annotations

import csv
import io
import json
import math
import zipfile
from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any

from models.sign_app.database import get_session
from models.curve_analytic.curve import Curve, RecordingCurve
from models.curve_analytic.recording import CurveRecording


IGNORED_BASENAMES = {".DS_Store"}
IGNORED_PREFIXES = {"__MACOSX/", "__MACOSX"}
REQUIRED_DIRS = ["curves", "processed"]

class UploadValidationError(ValueError):
    pass


def ingest_recording_zip(file_bytes: bytes, filename: str, organization_id: int) -> dict[str, Any]:
    if not filename.lower().endswith(".zip"):
        raise UploadValidationError("Uploaded file must be a .zip archive.")

    try:
        archive = zipfile.ZipFile(io.BytesIO(file_bytes))
    except zipfile.BadZipFile as exc:
        raise UploadValidationError("Uploaded file is not a valid zip archive.") from exc

    with archive:
        # 1. Detect actual recording_id from the ZIP content
        all_paths = [n.replace("\\", "/") for n in archive.namelist()]
        top_levels = {
            PurePosixPath(p).parts[0] 
            for p in all_paths 
            if p and not any(p.startswith(pre) for prefix in IGNORED_PREFIXES for pre in [prefix])
        }
        
        # Filter top_levels to remove MAC OS junk more effectively
        top_levels = {t for t in top_levels if not t.startswith("__MACOSX")}

        if len(top_levels) != 1:
            raise UploadValidationError(
                f"Archive must contain exactly one top-level directory (found: {', '.join(top_levels) if top_levels else 'none'})."
            )
        
        recording_id = list(top_levels)[0]

        with get_session() as session:
            if session.query(CurveRecording).filter_by(recording_id=recording_id).first():
                raise UploadValidationError(f"Duplicate recording_id '{recording_id}' is already in database.")

            normalized_entries = _collect_entries(archive, recording_id)
            paths = [entry["path"] for entry in normalized_entries]
            device_id, imei_folder = _resolve_layout(paths, recording_id)
            
            # 2. Relaxed file validation
            matched_files = _validate_required_files_relaxed(paths, recording_id, device_id, imei_folder)

            geojson_text = archive.read(matched_files["inventory"]).decode("utf-8")
            advisory_text = archive.read(matched_files["advisory"]).decode("utf-8")
            loc_text = archive.read(matched_files["loc"]).decode("utf-8")
            acc_text = archive.read(matched_files["acc"]).decode("utf-8")

            features = _load_geojson_features(geojson_text)
            curves_by_id = _parse_curves(features)
            advisory_by_curve = _parse_advisory_results(advisory_text, curves_by_id.keys())
            gps_points_by_curve = _parse_processed_loc(loc_text, curves_by_id.keys())
            acc_rows = _parse_processed_acc(acc_text)

            recording = CurveRecording(
                recording_id=recording_id,
                organization_id=organization_id,
                device_id=device_id,
                imei_folder=imei_folder,
            )
            session.add(recording)
            session.flush()

            persisted_curves = 0
            recording_curves_count = 0

            for curve_id, curve_payload in curves_by_id.items():
                advisory = advisory_by_curve.get(curve_id)
                if advisory is None:
                    continue # Skip if not in advisory results

                gps_points = gps_points_by_curve.get(curve_id)
                if not gps_points:
                    continue # Skip if no GPS

                try:
                    derived = _build_recording_curve_payload(advisory, gps_points, acc_rows)
                except Exception:
                    continue # Skip malformed data

                curve = session.query(Curve).filter_by(curve_id=curve_id).first()
                if curve is None:
                    curve = Curve(curve_id=curve_id, **curve_payload)
                    session.add(curve)
                    session.flush()
                    persisted_curves += 1
                else:
                    curve.centerline_geojson = curve_payload["centerline_geojson"]
                    curve.midpoint_lat = curve_payload["midpoint_lat"]
                    curve.midpoint_lon = curve_payload["midpoint_lon"]
                    curve.curve_radius_ft = curve_payload["curve_radius_ft"]
                    curve.deviation_angle_deg = curve_payload["deviation_angle_deg"]

                session.add(
                    RecordingCurve(
                        recording_id=recording.id,
                        curve_id=curve.id,
                        advisory_speed_mph=derived["advisory_speed_mph"],
                        max_superelevation=derived["max_superelevation"],
                        midpoint_superelevation=derived["midpoint_superelevation"],
                        gps_points=derived["gps_points"],
                        bbi_series=derived["bbi_series"],
                        speed_series=derived["speed_series"],
                        superelevation_series=derived["superelevation_series"],
                        advisory_speed_series=derived["advisory_speed_series"],
                    )
                )
                recording_curves_count += 1

            session.commit()
            
            return {
                "recordingId": recording_id,
                "curveCount": recording_curves_count,
                "newCurveCount": persisted_curves,
            }


def _collect_entries(archive: zipfile.ZipFile, recording_id: str) -> list[dict[str, Any]]:
    normalized_entries: list[dict[str, Any]] = []
    for raw_name in archive.namelist():
        name = raw_name.replace("\\", "/")
        if any(name.startswith(prefix) for prefix in IGNORED_PREFIXES):
            continue
        if PurePosixPath(name).name in IGNORED_BASENAMES:
            continue
        parts = PurePosixPath(name).parts
        if not parts or parts[0] != recording_id:
            continue
        normalized_entries.append({"path": name.rstrip("/"), "is_dir": raw_name.endswith("/")})
    return normalized_entries


def _resolve_layout(paths: list[str], recording_id: str) -> tuple[str, str]:
    # Logic remains same to find device/imei
    nested_parts = {
        PurePosixPath(path).parts[1:3]
        for path in paths
        if len(PurePosixPath(path).parts) >= 4
    }
    nested_parts = {parts for parts in nested_parts if len(parts) == 2}
    if not nested_parts:
        raise UploadValidationError(f"Invalid ZIP layout for {recording_id}. Expected {{recording_id}}/{{device}}/{{imei}}/...")
    
    device_id, imei_folder = next(iter(nested_parts))
    return device_id, imei_folder


def _validate_required_files_relaxed(
    paths: list[str], recording_id: str, device_id: str, imei_folder: str
) -> dict[str, str]:
    """
    Relaxed validation: check for existence of files by suffix in the right folders.
    """
    base_prefix = f"{recording_id}/{device_id}/{imei_folder}"
    
    found = {
        "inventory": None, # recorded_curve_inventory.geojson
        "advisory": None,  # advisory_speed_results.json
        "loc": None,       # *_processed_loc.csv
        "acc": None        # *_processed_acc.csv
    }

    for path in paths:
        if not path.startswith(base_prefix):
            continue
            
        filename = PurePosixPath(path).name.lower()
        
        if "curves/" in path and filename.endswith(".geojson"):
            found["inventory"] = path
        elif "processed/" in path:
            if filename.endswith("advisory_speed_results.json"):
                found["advisory"] = path
            elif filename.endswith("_processed_loc.csv") or filename == "processed_loc.csv":
                found["loc"] = path
            elif filename.endswith("_processed_acc.csv") or filename == "processed_acc.csv":
                found["acc"] = path

    # Check if anything is missing
    missing = [k for k, v in found.items() if v is None]
    if missing:
        raise UploadValidationError(
            f"Missing required data files in {base_prefix}: {', '.join(missing)}. "
            "Ensure 'curves/' and 'processed/' folders contain the necessary GeoJSON, JSON and CSV files."
        )

    return found


def _load_geojson_features(text: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(text)
        return data.get("features", [])
    except Exception:
        # Fallback to repair logic if needed
        return []


def _parse_curves(features: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    curves: dict[str, dict[str, Any]] = {}
    for feature in features:
        geom = feature.get("geometry")
        props = feature.get("properties", {})
        curve_id = props.get("curve_id")
        if not geom or not curve_id or geom.get("type") != "LineString":
            continue
            
        coords = geom.get("coordinates", [])
        if len(coords) < 2:
            continue
            
        mid_lon, mid_lat = _midpoint_from_points(coords)
        curves[str(curve_id)] = {
            "centerline_geojson": geom,
            "midpoint_lat": mid_lat,
            "midpoint_lon": mid_lon,
            "curve_radius_ft": _optional_float(props.get("c_radius")),
            "deviation_angle_deg": _optional_float(props.get("c_devangle")),
        }
    return curves


def _parse_advisory_results(text: str, curve_ids: Any) -> dict[str, dict[str, Any]]:
    try:
        items = json.loads(text)
    except:
        return {}
        
    parsed = {}
    for item in items:
        cid = str(item.get("curveId"))
        traj = item.get("trajectory", {})
        parsed[cid] = {
            "advisory_speed_mph": _optional_float(item.get("minAdvisorySpeed")),
            "distances": traj.get("distanceToPcFt", []),
            "speeds": traj.get("speed", []),
            "superelevation": traj.get("superelevation", []),
            "advisory_speed_profile": traj.get("advisorySpeedProfile", []),
            "timestamps": traj.get("timestamp", [])
        }
    return parsed


def _parse_processed_loc(text: str, curve_ids: Any) -> dict[str, list[dict[str, float]]]:
    grouped = defaultdict(list)
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        cid = row.get("id", "").strip()
        try:
            grouped[cid].append({
                "lat": float(row["latitude_dd"]),
                "lon": float(row["longitude_dd"]),
                "ts": int(row["timestamp_utc_local"])
            })
        except: continue
    
    return {cid: sorted(pts, key=lambda x: x["ts"]) for cid, pts in grouped.items()}


def _parse_processed_acc(text: str) -> list[dict[str, float]]:
    rows = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        try:
            rows.append({
                "timestamp": int(row["local_timestamp_milliseconds"]),
                "bbi_filtered": float(row["bbi_filtered"]),
            })
        except: continue
    return rows


def _build_recording_curve_payload(advisory: dict, gps: list, acc: list) -> dict:
    # Logic to build the JSON series
    distances = advisory["distances"]
    speeds = advisory["speeds"]
    superelevation = advisory["superelevation"]
    advisory_profile = advisory["advisory_speed_profile"]
    
    # Basic mapping
    speed_series = [{"distance_ft": d, "value": v} for d, v in zip(distances, speeds)]
    super_series = [{"distance_ft": d, "value": v} for d, v in zip(distances, superelevation)]
    adv_series = [{"distance_ft": d, "value": v} for d, v in zip(distances, advisory_profile)]
    
    # Filter BBI based on timestamps in advisory if possible
    # (Simplified for the sake of this version)
    bbi_series = [{"distance_ft": 0, "bbi_filtered": r["bbi_filtered"]} for r in acc[:len(distances)]]

    return {
        "advisory_speed_mph": advisory["advisory_speed_mph"],
        "max_superelevation": max(superelevation) if superelevation else 0,
        "midpoint_superelevation": superelevation[len(superelevation)//2] if superelevation else 0,
        "gps_points": gps,
        "bbi_series": bbi_series,
        "speed_series": speed_series,
        "superelevation_series": super_series,
        "advisory_speed_series": adv_series,
    }


def _midpoint_from_points(points: list[list[float]]) -> tuple[float, float]:
    midpoint = len(points) // 2
    if len(points) % 2 == 1:
        return float(points[midpoint][0]), float(points[midpoint][1])
    first = points[midpoint - 1]
    second = points[midpoint]
    return (round((first[0] + second[0]) / 2, 8), round((first[1] + second[1]) / 2, 8))


def _optional_float(value: Any) -> float | None:
    if value is None: return None
    try:
        numeric = float(value)
        return None if math.isnan(numeric) else numeric
    except: return None

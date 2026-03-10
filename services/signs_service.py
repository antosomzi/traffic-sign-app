"""Signs service for importing and managing traffic signs from pipeline results"""

import os
import csv
from models.sign import Sign
from config import Config
from pipeline.post_processing import get_merged_signs_csv_path
from services.route_filtering_service import get_best_signs_csv_path


def parse_signs_csv(recording_id):
    """
    Parse the best available signs CSV to extract sign data for DB import.

    Prefers ``signs_merged_filtered.csv`` (route-filtered) when it exists,
    and falls back to ``signs_merged.csv``.

    Merged CSV columns:
        ID, MUTCD Code, Position on the Support, Height (in), Width (in), Longitude, Latitude

    Args:
        recording_id: The recording ID to parse signs for

    Returns:
        List of tuples (recording_id, mutcd_code, latitude, longitude)
    """
    rec_path = os.path.join(Config.EXTRACT_FOLDER, recording_id)
    csv_path = get_best_signs_csv_path(rec_path)

    if not csv_path:
        print(f"No signs CSV found for {recording_id}")
        return []

    print(f"[SIGNS] Using signs CSV: {os.path.basename(csv_path)}")
    signs_data = []

    try:
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    mutcd_code = row.get('MUTCD Code', '').strip()
                    lat_str = row.get('Latitude', '').strip()
                    lon_str = row.get('Longitude', '').strip()

                    if not mutcd_code or not lat_str or not lon_str:
                        continue

                    latitude = float(lat_str)
                    longitude = float(lon_str)

                    # Validate coordinates
                    if (-90 <= latitude <= 90) and (-180 <= longitude <= 180):
                        signs_data.append((recording_id, mutcd_code, latitude, longitude))
                except (ValueError, KeyError):
                    continue
    except Exception as e:
        print(f"Error parsing signs_merged.csv: {e}")
        return []

    print(f"Parsed {len(signs_data)} signs for recording {recording_id}")
    return signs_data


def import_signs_for_recording(recording_id):
    """
    Import all signs from a recording's pipeline results into the database.
    Deletes existing signs first to avoid duplicates.
    
    Args:
        recording_id: The recording ID to import signs for
        
    Returns:
        Number of signs imported
    """
    # Delete existing signs for this recording first
    deleted_count = Sign.delete_by_recording(recording_id)
    if deleted_count > 0:
        print(f"Deleted {deleted_count} existing signs for recording {recording_id}")
    
    # Parse the signs CSV
    signs_data = parse_signs_csv(recording_id)
    
    if not signs_data:
        print(f"No signs found for recording {recording_id}")
        return 0
    
    # Bulk create signs
    created_count = Sign.bulk_create(signs_data)
    print(f"Imported {created_count} signs for recording {recording_id}")
    
    return created_count


def delete_signs_for_recording(recording_id):
    """
    Delete all signs for a recording.
    
    Args:
        recording_id: The recording ID to delete signs for
        
    Returns:
        Number of signs deleted
    """
    return Sign.delete_by_recording(recording_id)


def get_signs_geojson(organization_id, recording_ids=None, mutcd_codes=None):
    """
    Get signs as GeoJSON FeatureCollection.
    
    Args:
        organization_id: Filter by organization
        recording_ids: Optional list of recording IDs to filter by
        mutcd_codes: Optional list of MUTCD codes to filter by
        
    Returns:
        GeoJSON FeatureCollection
    """
    signs = Sign.get_by_organization(
        organization_id,
        recording_ids=recording_ids,
        mutcd_codes=mutcd_codes
    )
    
    return Sign.to_geojson_collection(signs)


def get_filter_options(organization_id):
    """
    Get available filter options for signs (recordings and MUTCD codes).
    
    Args:
        organization_id: The organization to get filter options for
        
    Returns:
        Dict with 'recordings' and 'mutcd_codes' lists
    """
    return {
        'recordings': Sign.get_recordings_with_signs(organization_id),
        'mutcd_codes': Sign.get_unique_mutcd_codes(organization_id)
    }

"""Signs service for importing and managing traffic signs from pipeline results"""

import os
import csv
from models.sign import Sign
from config import Config


def _load_supports_coordinates(supports_csv_path):
    """
    Load support coordinates from supports.csv.
    
    Returns:
        Dict mapping support ID to (latitude, longitude)
    """
    coordinates = {}
    
    if not os.path.isfile(supports_csv_path):
        return coordinates
    
    try:
        with open(supports_csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    support_id = row.get('ID', '').strip()
                    lat_str = row.get('Latitude', '')
                    lon_str = row.get('Longitude', '')
                    
                    if support_id and lat_str and lon_str:
                        latitude = float(lat_str)
                        longitude = float(lon_str)
                        
                        # Validate coordinates
                        if (-90 <= latitude <= 90) and (-180 <= longitude <= 180):
                            coordinates[support_id] = (latitude, longitude)
                except (ValueError, KeyError):
                    continue
    except Exception as e:
        print(f"Error loading supports: {e}")
    
    return coordinates


def parse_signs_csv(recording_id):
    """
    Parse signs.csv and join with supports.csv to get coordinates.
    
    signs.csv has: ID, Foreign Key, MUTCD Code, ...
    supports.csv has: ID, Mounting Height, Longitude, Latitude
    
    Join on: signs['Foreign Key'] = supports['ID']
    
    Args:
        recording_id: The recording ID to parse signs for
        
    Returns:
        List of tuples (recording_id, mutcd_code, latitude, longitude)
    """
    base_path = os.path.join(
        Config.EXTRACT_FOLDER,
        recording_id,
        "result_pipeline_stable",
        "s7_export_csv"
    )
    
    signs_csv_path = os.path.join(base_path, "signs.csv")
    supports_csv_path = os.path.join(base_path, "supports.csv")
    
    if not os.path.isfile(signs_csv_path):
        print(f"Signs CSV not found: {signs_csv_path}")
        return []
    
    if not os.path.isfile(supports_csv_path):
        print(f"Supports CSV not found: {supports_csv_path}")
        return []
    
    # Load support coordinates first
    support_coords = _load_supports_coordinates(supports_csv_path)
    if not support_coords:
        print(f"No valid coordinates found in supports.csv")
        return []
    
    signs_data = []
    
    try:
        with open(signs_csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                try:
                    mutcd_code = row.get('MUTCD Code', '').strip()
                    foreign_key = row.get('Foreign Key', '').strip()
                    
                    if not mutcd_code or not foreign_key:
                        continue
                    
                    # Look up coordinates from supports
                    coords = support_coords.get(foreign_key)
                    if not coords:
                        continue
                    
                    latitude, longitude = coords
                    signs_data.append((recording_id, mutcd_code, latitude, longitude))
                    
                except (ValueError, KeyError):
                    continue
                    
    except Exception as e:
        print(f"Error parsing signs CSV: {e}")
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

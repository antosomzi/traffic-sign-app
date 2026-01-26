"""Geographic service for GPS traces and GeoJSON generation"""

import os
import csv
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from config import Config
from models.recording import Recording
from models.user import User
from services.redis_service import RedisProgressService
from config import redis_client


class GeoService:
    """Service for handling GPS traces and GeoJSON conversion"""
    # Fixed simplification tolerance (degrees). Controlled here to keep frontend simple.
    FIXED_SIMPLIFY = 0.00005
    
    # CSV column name aliases for different formats
    LAT_ALIASES = ['lat', 'latitude', 'Latitude', 'LAT', 'latitude_dd']
    LON_ALIASES = ['lon', 'long', 'longitude', 'Longitude', 'LON', 'LONG', 'longitude_dd']
    TIME_ALIASES = ['timestamp', 'time', 'ts', 'Time', 'Timestamp', 'TIMESTAMP', 'timestamp_utc_gps', 'timestamp_utc_local']
    
    @staticmethod
    def _find_location_csv(recording_path: str, recording_id: str) -> Optional[str]:
        """
        Find location CSV file in recording directory structure.
        Prefers *_loc_cleaned.csv over *_loc.csv
        
        Args:
            recording_path: Path to recording directory
            recording_id: Recording ID
            
        Returns:
            Path to CSV file or None if not found
        """
        # Search pattern: recordings/<recording_id>/<device_id>/<imei>/location/
        recording_dir = Path(recording_path)
        
        if not recording_dir.exists():
            return None
        
        # Walk through subdirectories to find location folder
        for device_dir in recording_dir.iterdir():
            if not device_dir.is_dir():
                continue
            for imei_dir in device_dir.iterdir():
                if not imei_dir.is_dir():
                    continue
                location_dir = imei_dir / "location"
                if not location_dir.exists():
                    continue
                
                # Prefer cleaned CSV
                cleaned_csv = location_dir / f"{recording_id}_loc_cleaned.csv"
                if cleaned_csv.exists():
                    return str(cleaned_csv)
                
                # Fallback to regular CSV
                regular_csv = location_dir / f"{recording_id}_loc.csv"
                if regular_csv.exists():
                    return str(regular_csv)
        
        return None
    
    @staticmethod
    def _detect_csv_columns(csv_path: str) -> Optional[Tuple[str, str, str]]:
        """
        Detect column names for latitude, longitude, and timestamp
        
        Args:
            csv_path: Path to CSV file
            
        Returns:
            Tuple of (lat_col, lon_col, time_col) or None if not found
        """
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames
                
                if not headers:
                    return None
                
                # Find columns
                lat_col = next((h for h in headers if h in GeoService.LAT_ALIASES), None)
                lon_col = next((h for h in headers if h in GeoService.LON_ALIASES), None)
                time_col = next((h for h in headers if h in GeoService.TIME_ALIASES), None)
                
                if lat_col and lon_col:
                    return (lat_col, lon_col, time_col)
                
                return None
        except Exception:
            return None
    
    @staticmethod
    def _parse_timestamp(ts_str: str) -> Optional[datetime]:
        """
        Parse timestamp from various formats
        
        Args:
            ts_str: Timestamp string
            
        Returns:
            datetime object or None
        """
        if not ts_str:
            return None
        
        formats = [
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(ts_str, fmt)
            except (ValueError, TypeError):
                continue
        
        # Try Unix timestamp (seconds)
        try:
            timestamp_float = float(ts_str)
            # If timestamp is in milliseconds (> year 2100 in seconds), convert to seconds
            if timestamp_float > 4102444800:  # Jan 1, 2100 in seconds
                timestamp_float = timestamp_float / 1000.0
            return datetime.fromtimestamp(timestamp_float)
        except (ValueError, TypeError, OSError):
            pass
        
        return None
    
    @staticmethod
    def _simplify_coordinates(coords: List[List[float]], tolerance: float = 0.0001) -> List[List[float]]:
        """
        Simplify coordinate array using Ramer-Douglas-Peucker algorithm
        
        Args:
            coords: List of [lon, lat] coordinates
            tolerance: Simplification tolerance (degrees)
            
        Returns:
            Simplified coordinate list
        """
        if len(coords) <= 2:
            return coords
        
        def perpendicular_distance(point, line_start, line_end):
            """Calculate perpendicular distance from point to line"""
            if line_start == line_end:
                return ((point[0] - line_start[0])**2 + (point[1] - line_start[1])**2)**0.5
            
            # Calculate using cross product
            dx = line_end[0] - line_start[0]
            dy = line_end[1] - line_start[1]
            norm = (dx**2 + dy**2)**0.5
            
            if norm == 0:
                return 0
            
            return abs(dy * point[0] - dx * point[1] + line_end[0] * line_start[1] - line_end[1] * line_start[0]) / norm
        
        def rdp(points, epsilon):
            """Ramer-Douglas-Peucker algorithm"""
            if len(points) < 3:
                return points
            
            # Find point with maximum distance
            dmax = 0
            index = 0
            end = len(points) - 1
            
            for i in range(1, end):
                d = perpendicular_distance(points[i], points[0], points[end])
                if d > dmax:
                    index = i
                    dmax = d
            
            # If max distance is greater than epsilon, recursively simplify
            if dmax > epsilon:
                rec_results1 = rdp(points[:index + 1], epsilon)
                rec_results2 = rdp(points[index:], epsilon)
                
                return rec_results1[:-1] + rec_results2
            else:
                return [points[0], points[end]]
        
        return rdp(coords, tolerance)
    
    @staticmethod
    def recording_to_geojson_feature(
        recording_id: str,
        simplify: Optional[float] = None,
        max_points: int = 5000
    ) -> Optional[Dict]:
        """
        Convert a single recording's GPS trace to GeoJSON Feature

        Args:
            recording_id: Recording ID
            simplify: Simplification tolerance (degrees), None for no simplification
            max_points: Maximum number of points to include

        Returns:
            GeoJSON Feature dict or None if error/no data
        """
        # Find recording path
        recording_path = os.path.join(Config.BASE_PATH, "recordings", recording_id)

        if not os.path.exists(recording_path):
            return None

        # Find CSV file
        csv_path = GeoService._find_location_csv(recording_path, recording_id)
        if not csv_path:
            return None

        # Detect columns
        columns = GeoService._detect_csv_columns(csv_path)
        if not columns:
            return None

        lat_col, lon_col, time_col = columns

        # Parse CSV
        coordinates = []
        timestamps = []
        device_id = None

        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)

                for row in reader:
                    try:
                        lat = float(row[lat_col])
                        lon = float(row[lon_col])

                        # Validate coordinates (rough bounds check)
                        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                            continue

                        # Skip invalid/zero coordinates
                        if lat == 0 and lon == 0:
                            continue

                        coordinates.append([lon, lat])  # GeoJSON uses [lon, lat]

                        # Parse timestamp if available
                        if time_col and row.get(time_col):
                            ts = GeoService._parse_timestamp(row[time_col])
                            if ts:
                                timestamps.append(ts)
                    except (ValueError, KeyError):
                        continue

            # Extract device_id from path
            path_parts = csv_path.split(os.sep)
            if 'recordings' in path_parts:
                rec_idx = path_parts.index('recordings')
                if len(path_parts) > rec_idx + 2:
                    device_id = path_parts[rec_idx + 2]

        except Exception as e:
            print(f"Error parsing CSV {csv_path}: {e}")
            return None

        # Need at least 2 points for a line
        if len(coordinates) < 2:
            return None

        # Limit points if needed
        if len(coordinates) > max_points:
            step = len(coordinates) // max_points
            coordinates = coordinates[::step]
            timestamps = timestamps[::step] if timestamps else []

        # Simplify if requested
        # Use backend-fixed simplify value when simplify is not provided. This
        # ensures the tolerance is controlled server-side (frontend should not
        # be able to change it).
        if simplify is None:
            simplify = GeoService.FIXED_SIMPLIFY

        if simplify and simplify > 0:
            coordinates = GeoService._simplify_coordinates(coordinates, simplify)

        # Get recording information to include uploader name
        recording_obj = Recording.get_by_id(recording_id)
        uploader_name = recording_obj.uploader_name if recording_obj else "Unknown"

        # Build properties
        properties = {
            "recording_id": recording_id,
            "device_id": device_id,
            "num_points": len(coordinates),
            "source_file": os.path.basename(csv_path),
            "user_name": uploader_name
        }

        if timestamps:
            properties["start_time"] = timestamps[0].isoformat()
            properties["end_time"] = timestamps[-1].isoformat()
            properties["duration_seconds"] = (timestamps[-1] - timestamps[0]).total_seconds()

        # Create GeoJSON Feature
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates
            },
            "properties": properties
        }

        return feature
    
    @staticmethod
    def organization_routes_to_geojson(
        org_id: int,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        recording_ids: Optional[List[str]] = None,
        user_ids: Optional[List[str]] = None,
        simplify: Optional[float] = None,
        use_cache: bool = True
    ) -> Dict:
        """
        Generate GeoJSON FeatureCollection for all recordings in an organization
        
        Args:
            org_id: Organization ID
            from_date: Start date filter (ISO format)
            to_date: End date filter (ISO format)
            recording_ids: List of specific recording IDs to include
            simplify: Simplification tolerance
            use_cache: Whether to use Redis cache
            
        Returns:
            GeoJSON FeatureCollection dict
        """
        # Generate cache key. Use the backend-fixed simplification value so cache
        # entries are consistent regardless of any frontend input.
        fixed_simplify = GeoService.FIXED_SIMPLIFY
        params_str = f"{org_id}_{from_date}_{to_date}_{recording_ids}_{user_ids}_{fixed_simplify}"
        cache_key = f"org_routes:{hashlib.md5(params_str.encode()).hexdigest()}"

        # Check cache
        if use_cache:
            cached = redis_client.get(cache_key)
            if cached:
                try:
                    return json.loads(cached)
                except json.JSONDecodeError:
                    pass
        
        # Get recordings for organization
        recordings = Recording.get_by_organization(org_id, user_ids=user_ids)
        
        # Apply filters
        if from_date:
            try:
                from_dt = datetime.fromisoformat(from_date)
                recordings = [r for r in recordings if r.recording_date and r.recording_date >= from_dt]
            except ValueError:
                pass
        
        if to_date:
            try:
                to_dt = datetime.fromisoformat(to_date)
                recordings = [r for r in recordings if r.recording_date and r.recording_date <= to_dt]
            except ValueError:
                pass
        
        if recording_ids:
            recordings = [r for r in recordings if r.id in recording_ids]
        
        # Convert each recording to GeoJSON feature
        features = []
        for recording in recordings:
            feature = GeoService.recording_to_geojson_feature(
                recording.id,
                simplify=fixed_simplify
            )
            if feature:
                features.append(feature)
        
        # Build FeatureCollection
        geojson = {
            "type": "FeatureCollection",
            "features": features,
            "properties": {
                "organization_id": org_id,
                "generated_at": datetime.utcnow().isoformat(),
                "count": len(features)
            }
        }
        
        # Cache for 1 hour
        if use_cache:
            try:
                redis_client.setex(cache_key, 3600, json.dumps(geojson))
            except Exception as e:
                print(f"Error caching GeoJSON: {e}")

        return geojson

    @staticmethod
    def refresh_organization_routes_cache(org_id: int, from_date: Optional[str] = None,
                                       to_date: Optional[str] = None,
                                       recording_ids: Optional[List[str]] = None,
                                       user_ids: Optional[List[str]] = None) -> bool:
        """
        Refresh the cache for organization routes by deleting the cached entry

        Args:
            org_id: Organization ID
            from_date: Start date filter (ISO format)
            to_date: End date filter (ISO format)
            recording_ids: List of specific recording IDs to include

        Returns:
            True if cache was successfully invalidated, False otherwise
        """
        # Generate cache key using the same logic as in organization_routes_to_geojson
        fixed_simplify = GeoService.FIXED_SIMPLIFY
        params_str = f"{org_id}_{from_date}_{to_date}_{recording_ids}_{user_ids}_{fixed_simplify}"
        cache_key = f"org_routes:{hashlib.md5(params_str.encode()).hexdigest()}"

        try:
            # Delete the cache key (even if it doesn't exist, this is fine)
            deleted_count = redis_client.delete(cache_key)
            print(f"Cache refresh: Attempted to delete {deleted_count} keys for {cache_key}")
            return True
        except Exception as e:
            print(f"Error refreshing cache for {cache_key}: {e}")
            # Still return True since the operation is considered successful
            # even if the key didn't exist or there was a connection issue
            return True


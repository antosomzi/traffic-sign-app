"""Tests for GPS service and GeoJSON generation"""

import os
import json
import pytest
import tempfile
import shutil
from pathlib import Path
from services.geo_service import GeoService


class TestGeoService:
    """Test cases for GeoService"""
    
    @pytest.fixture
    def temp_recording_dir(self):
        """Create temporary recording directory structure"""
        temp_dir = tempfile.mkdtemp()
        recording_id = "2024_05_20_23_32_53_415"
        
        # Create directory structure
        recording_path = Path(temp_dir) / "recordings" / recording_id / "123456" / "IMEINotAvailable" / "location"
        recording_path.mkdir(parents=True, exist_ok=True)
        
        yield temp_dir, recording_id, recording_path
        
        # Cleanup
        shutil.rmtree(temp_dir)
    
    def test_find_location_csv_cleaned_preferred(self, temp_recording_dir):
        """Test that cleaned CSV is preferred over regular CSV"""
        temp_dir, recording_id, location_path = temp_recording_dir
        recording_path = Path(temp_dir) / "recordings" / recording_id
        
        # Create both CSV files
        regular_csv = location_path / f"{recording_id}_loc.csv"
        cleaned_csv = location_path / f"{recording_id}_loc_cleaned.csv"
        
        regular_csv.write_text("timestamp,lat,lon\n")
        cleaned_csv.write_text("timestamp,lat,lon\n")
        
        # Should return cleaned CSV
        result = GeoService._find_location_csv(str(recording_path), recording_id)
        assert result is not None
        assert "cleaned" in result
    
    def test_find_location_csv_fallback_to_regular(self, temp_recording_dir):
        """Test fallback to regular CSV when cleaned not available"""
        temp_dir, recording_id, location_path = temp_recording_dir
        recording_path = Path(temp_dir) / "recordings" / recording_id
        
        # Create only regular CSV
        regular_csv = location_path / f"{recording_id}_loc.csv"
        regular_csv.write_text("timestamp,lat,lon\n")
        
        result = GeoService._find_location_csv(str(recording_path), recording_id)
        assert result is not None
        assert "cleaned" not in result
    
    def test_find_location_csv_not_found(self, temp_recording_dir):
        """Test when no CSV file exists"""
        temp_dir, recording_id, location_path = temp_recording_dir
        recording_path = Path(temp_dir) / "recordings" / recording_id
        
        result = GeoService._find_location_csv(str(recording_path), recording_id)
        assert result is None
    
    def test_detect_csv_columns_standard(self, temp_recording_dir):
        """Test column detection with standard names"""
        temp_dir, recording_id, location_path = temp_recording_dir
        
        csv_path = location_path / f"{recording_id}_loc.csv"
        csv_path.write_text("timestamp,lat,lon,alt\n1234567890,40.7128,-74.0060,10\n")
        
        result = GeoService._detect_csv_columns(str(csv_path))
        assert result is not None
        lat_col, lon_col, time_col = result
        assert lat_col == "lat"
        assert lon_col == "lon"
        assert time_col == "timestamp"
    
    def test_detect_csv_columns_aliases(self, temp_recording_dir):
        """Test column detection with alternative names"""
        temp_dir, recording_id, location_path = temp_recording_dir
        
        csv_path = location_path / f"{recording_id}_loc.csv"
        csv_path.write_text("time,latitude,longitude\n1234567890,40.7128,-74.0060\n")
        
        result = GeoService._detect_csv_columns(str(csv_path))
        assert result is not None
        lat_col, lon_col, time_col = result
        assert lat_col == "latitude"
        assert lon_col == "longitude"
        assert time_col == "time"
    
    def test_detect_csv_columns_missing(self, temp_recording_dir):
        """Test when required columns are missing"""
        temp_dir, recording_id, location_path = temp_recording_dir
        
        csv_path = location_path / f"{recording_id}_loc.csv"
        csv_path.write_text("foo,bar,baz\n1,2,3\n")
        
        result = GeoService._detect_csv_columns(str(csv_path))
        assert result is None
    
    def test_parse_timestamp_iso_format(self):
        """Test parsing ISO format timestamp"""
        ts = GeoService._parse_timestamp("2024-05-20 23:32:53.415")
        assert ts is not None
        assert ts.year == 2024
        assert ts.month == 5
        assert ts.day == 20
    
    def test_parse_timestamp_unix(self):
        """Test parsing Unix timestamp"""
        ts = GeoService._parse_timestamp("1716248673.415")
        assert ts is not None
    
    def test_parse_timestamp_invalid(self):
        """Test parsing invalid timestamp"""
        ts = GeoService._parse_timestamp("invalid")
        assert ts is None
    
    def test_simplify_coordinates_small_list(self):
        """Test simplification with small coordinate list"""
        coords = [[0, 0], [1, 1]]
        result = GeoService._simplify_coordinates(coords, 0.0001)
        assert len(result) == 2
    
    def test_simplify_coordinates_reduces_points(self):
        """Test that simplification reduces number of points"""
        # Create a line with many points
        coords = [[i * 0.0001, i * 0.0001] for i in range(100)]
        result = GeoService._simplify_coordinates(coords, 0.001)
        assert len(result) < len(coords)
        assert len(result) >= 2
    
    def test_recording_to_geojson_feature_valid(self, temp_recording_dir, monkeypatch):
        """Test converting valid recording to GeoJSON feature"""
        temp_dir, recording_id, location_path = temp_recording_dir
        recording_path = Path(temp_dir) / "recordings" / recording_id
        
        # Create valid CSV
        csv_path = location_path / f"{recording_id}_loc.csv"
        csv_content = """timestamp,lat,lon
2024-05-20 23:32:53,40.7128,-74.0060
2024-05-20 23:33:53,40.7138,-74.0070
2024-05-20 23:34:53,40.7148,-74.0080
"""
        csv_path.write_text(csv_content)
        
        # Mock BASE_PATH
        from config import Config
        monkeypatch.setattr(Config, 'BASE_PATH', temp_dir)
        
        result = GeoService.recording_to_geojson_feature(recording_id)
        
        assert result is not None
        assert result['type'] == 'Feature'
        assert result['geometry']['type'] == 'LineString'
        assert len(result['geometry']['coordinates']) == 3
        assert result['properties']['recording_id'] == recording_id
        assert result['properties']['num_points'] == 3
    
    def test_recording_to_geojson_feature_invalid_coords(self, temp_recording_dir, monkeypatch):
        """Test handling of invalid coordinates"""
        temp_dir, recording_id, location_path = temp_recording_dir
        recording_path = Path(temp_dir) / "recordings" / recording_id
        
        # Create CSV with invalid coordinates
        csv_path = location_path / f"{recording_id}_loc.csv"
        csv_content = """timestamp,lat,lon
2024-05-20 23:32:53,0,0
2024-05-20 23:33:53,999,-999
"""
        csv_path.write_text(csv_content)
        
        from config import Config
        monkeypatch.setattr(Config, 'BASE_PATH', temp_dir)
        
        result = GeoService.recording_to_geojson_feature(recording_id)
        
        # Should return None (not enough valid points)
        assert result is None
    
    def test_recording_to_geojson_feature_insufficient_points(self, temp_recording_dir, monkeypatch):
        """Test handling when less than 2 points available"""
        temp_dir, recording_id, location_path = temp_recording_dir
        recording_path = Path(temp_dir) / "recordings" / recording_id
        
        # Create CSV with single point
        csv_path = location_path / f"{recording_id}_loc.csv"
        csv_content = """timestamp,lat,lon
2024-05-20 23:32:53,40.7128,-74.0060
"""
        csv_path.write_text(csv_content)
        
        from config import Config
        monkeypatch.setattr(Config, 'BASE_PATH', temp_dir)
        
        result = GeoService.recording_to_geojson_feature(recording_id)
        
        assert result is None
    
    def test_recording_to_geojson_feature_with_simplification(self, temp_recording_dir, monkeypatch):
        """Test simplification parameter"""
        temp_dir, recording_id, location_path = temp_recording_dir
        recording_path = Path(temp_dir) / "recordings" / recording_id
        
        # Create CSV with many points
        csv_path = location_path / f"{recording_id}_loc.csv"
        lines = ["timestamp,lat,lon"]
        for i in range(100):
            lines.append(f"2024-05-20 23:{i%60:02d}:00,{40.7 + i*0.0001},{-74.0 + i*0.0001}")
        csv_path.write_text("\n".join(lines))
        
        from config import Config
        monkeypatch.setattr(Config, 'BASE_PATH', temp_dir)
        
        result = GeoService.recording_to_geojson_feature(recording_id, simplify=0.001)
        
        assert result is not None
        # Should have fewer points due to simplification
        assert len(result['geometry']['coordinates']) < 100
    
    def test_recording_to_geojson_feature_nonexistent(self):
        """Test with non-existent recording"""
        result = GeoService.recording_to_geojson_feature("nonexistent_recording")
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

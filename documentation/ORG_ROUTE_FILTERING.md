# Organization Route Filtering — Quick Reference

This document describes how organization route filtering works and how the 50‑metre buffer is computed and applied.

Summary
- Owners/admins upload a GeoJSON (LineString / MultiLineString) representing their road network.
- Uploaded GeoJSON is stored on disk at `org_routes/<org_id>/routes.geojson`.
- After the ML pipeline produces `result_pipeline_stable/signs_merged.csv`, the route filtering step runs automatically and writes `signs_merged_filtered.csv` in the same folder.
- If no routes file exists for an organization, the filtering step is skipped and the unfiltered CSV is used.

How the 50 m buffer works (brief, concrete)
1. Read org routes GeoJSON (WGS84 lon/lat).
2. Convert (reproject) the geometries to a metric coordinate system so distances are in metres. The implementation uses an appropriate UTM CRS chosen from feature centroids (this preserves accuracy across the area).
3. Create a 50 metre buffer around all route LineStrings using the metric CRS. MultiLineString and overlapping segments are merged (buffer on the full geometry).
4. Reproject the buffered polygon(s) back to WGS84 (lon/lat).
5. Filter `signs_merged.csv` by checking whether each sign's latitude/longitude point falls inside the buffered polygon(s). Only signs within the buffer are kept.

Notes & edge cases
- CRS: Input GeoJSON must be WGS84 (EPSG:4326). The reprojection step handles accurate metric buffering; arbitrary lon/lat buffering would be inaccurate.
- Small or sparse routes: If routes are very short or disconnected, the 50 m buffer still applies per segment; small islands of coverage may result.
- No routes uploaded: filtering is a no-op and the original `signs_merged.csv` is treated as the best source.
- Fallbacks: If `geopandas`/`shapely`/`pyproj` are not available or an error occurs, the filter step fails gracefully (pipeline continues and unfiltered CSV is used).

Implementation contract (inputs / outputs)
- Inputs:
  - `recording_path`: path to a recording folder containing `result_pipeline_stable/signs_merged.csv`
  - `org_id` (optional): organization id to find `org_routes/<org_id>/routes.geojson`
- Outputs:
  - `result_pipeline_stable/signs_merged_filtered.csv` (created if routes and filter succeed)
  - Returns path to the chosen CSV (filtered if available, otherwise unfiltered)

Minimal pseudo-code

```python
# load routes
routes = geopandas.read_file(org_routes_path)
# ensure WGS84
routes = routes.to_crs(epsg=4326)
# choose metric CRS (UTM) based on centroid
utm = choose_utm_crs(routes.geometry.unary_union.centroid)
routes_metric = routes.to_crs(utm)
# buffer and merge
routes_buffered = routes_metric.geometry.buffer(50).unary_union
# back to WGS84
buffer_wgs84 = shapely.ops.transform(lambda x, y: pyproj.Transformer.from_crs(utm, 4326, always_xy=True).transform(x, y), routes_buffered)
# filter signs
signs = pandas.read_csv(signs_csv)
sign_points = geopandas.GeoDataFrame(signs, geometry=geopandas.points_from_xy(signs.Longitude, signs.Latitude), crs='EPSG:4326')
inside = sign_points.within(buffer_wgs84)
signs_filtered = signs[inside]
signs_filtered.to_csv(filtered_csv, index=False)
```

Where to find code
- Service: `services/route_filtering_service.py`
- Pipeline integration: `pipeline/celery_tasks.py` (called after `generate_merged_signs_csv()`)

Dependencies
- geopandas, shapely, pyproj

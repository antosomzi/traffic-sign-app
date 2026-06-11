# Curve API Documentation

This document describes the API for curve analytics, including the expected input format for uploads and the subsequent data processing pipeline.

## 1. Input Format

### Full Recording Structure
A full recording produced by the mobile app typically has the following structure:

```text
2026_03_23_15_33_53_921/
└── 123456/
    └── IMEINotAvailable/
        ├── acceleration/
        │   └── 2026_03_23_15_33_53_921_acc.csv
        ├── calibration/
        │   └── 2026_03_23_15_16_48_218_calibration.csv
        ├── camera/
        │   └── 2026_03_23_15_33_53_921_cam_2026_03_23_15_33_53_921.mp4
        ├── curves/
        │   ├── recorded_curve_inventory.geojson
        │   └── recorded_historical_advisory_speed.json
        ├── location/
        │   └── 2026_03_23_15_33_53_921_loc.csv
        └── processed/
            ├── 2026_03_23_15_33_53_921_processed_acc.csv
            ├── 2026_03_23_15_33_53_921_processed_loc.csv
            └── advisory_speed_results.json
```

- **Méthode :** `POST`
- **Type de contenu (Content-Type) :** `multipart/form-data`
- **Authentification :** Requis (Supporte soit le cookie de session Web, soit le Token API "Bearer" dans le header Authorization)
- **Corps de la requête (Body) :**
    - `file` : Un fichier compressé au format **.zip** contenant les données de courbes.

### **Exemples d'authentification**

#### **1. Via Token API (Recommandé pour Mobile)**
```bash
curl -X POST https://sci.ce.gatech.edu/curves/upload \
     -H "Authorization: Bearer <votre_token>" \
     -F "file=@votre_fichier.zip"
```

#### **2. Via Cookie de Session (Navigateur)**
Utilisé automatiquement par le front-end web.

---

## 2. Data Processing

### Scope
The web app supports two upload approaches:
1. Upload a `.zip` file in the browser.
2. Upload a `.zip` file directly from the mobile app.

For now, the focus is on the browser `.zip` upload flow. The malformed GeoJSON issue applies to both approaches.

### Processing Goal
For each upload, the system will:
1. Validate the uploaded `.zip` structure.
2. Repair `curves/recorded_curve_inventory.geojson` if it matches a known malformed shape.
3. Parse the files needed by the current UI.
4. Build the SQL data (recordings, curves, recording_curves).
5. Reject the whole upload if any required step fails.

### Files Used By Current Processing
- `curves/recorded_curve_inventory.geojson`
- `processed/advisory_speed_results.json`
- `processed/{recording_id}_processed_loc.csv`
- `processed/{recording_id}_processed_acc.csv`

### Malformed GeoJSON Issue & Repair Rule
Every upload should assume that `curves/recorded_curve_inventory.geojson` may be malformed in a specific, known way.

**Known Malformed Shape:**
The file starts with the header but misses the `"features": [` line before the feature objects begin.

**Repair Rule:**
1. Check if the GeoJSON is valid.
2. If invalid and matching the known malformed shape (missing `"features": [` after the `crs` block), repair it by inserting that line.
3. If parsing still fails after repair, or if it is malformed in any other way, reject the upload.

### Processing Steps
For one uploaded recording:
1. Validate structure as defined in the Input Format section.
2. Extract `recording_id`, `device_id`, and `imei_folder`.
3. Load and validate/repair `curves/recorded_curve_inventory.geojson`.
4. Parse curve data from GeoJSON (geometry, radius, deviation angle, midpoint).
5. Parse `processed/advisory_speed_results.json` (advisory speeds, trajectory data).
6. Parse `processed/{recording_id}_processed_loc.csv` (GPS coordinates).
7. Parse `processed/{recording_id}_processed_acc.csv` (BBI data).
8. Build the SQL model.
9. Derive chart and UI fields (GPS points, advisory speed, superelevation, BBI vs distance/time, speed vs distance).

### Distance Normalization
For all distance-based plots:
1. Use `trajectory.distanceToPcFt[]` from `processed/advisory_speed_results.json`.
2. Compute total curve length as `max(trajectory.distanceToPcFt[])`.
3. Normalize so distance always increases from left to right.

### Timestamp Alignment
BBI data comes from `processed/{recording_id}_processed_acc.csv`.
1. Align BBI points using the timestamp range from `trajectory.timestamp[]` in `processed/advisory_speed_results.json`.
2. Distribute distance equally across the BBI points from `0` to the total curve length.

### Failure Rules
Reject the whole upload if:
- Structure is invalid or a required file is missing/malformed.
- GeoJSON repair fails or is invalid beyond the known pattern.
- A required JSON or CSV file cannot be parsed.
- Required per-curve data cannot be derived.

## 3. Test Plan

To verify the integration:
1. Upload a valid `.zip` file through the web app.
2. Confirm automatic GeoJSON repair (if applicable).
3. Confirm curves appear on the map and clicking opens the sidebar.
4. Confirm recordings appear under the correct `curve_id`.
5. Confirm GPS points and all plots (BBI, Speed, Superelevation, Advisory Speed) render correctly.
6. Confirm invalid uploads are rejected with appropriate error messages.

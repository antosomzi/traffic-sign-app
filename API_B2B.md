# B2B API Authentication & Usage Guide

Complete guide for using the B2B API to download traffic sign data programmatically.

## Table of Contents

- [Overview](#overview)
- [Generating an API Key](#generating-an-api-key)
- [Managing API Keys](#managing-api-keys)
- [CSV Format](#csv-format)
- [API Endpoints](#api-endpoints)
  - [Single Recording (Web App)](#1-download-csv-for-a-single-recording-web-app)
  - [Date Range (B2B API)](#2-download-csvs-by-date-range-b2b-api)
- [Implementation Examples](#implementation-examples)
- [Error Handling](#error-handling)
- [Best Practices](#best-practices)

---

## Overview

The B2B API allows programmatic access to download CSV results without using passwords in scripts. Authentication is done via API keys passed in the `X-API-Key` header.

**Key Features:**
- **Secure**: Keys are hashed before storage (like passwords)
- **Revocable**: Keys can be revoked anytime from the admin dashboard
- **Expirable**: Optional expiration dates for temporary access
- **User-scoped**: Each key is linked to a specific user and their organization

**Key Format:** `sk_live_xxxxxxxxxxxxx` (Stripe-like)

---

## Generating an API Key

### Via Admin Dashboard

1. Log in to the web interface as an **admin**
2. Navigate to **Admin Dashboard** → **API Keys** (`/admin/api-keys`)
3. Click **+ Generate API Key**
4. Fill in the form:
   - **User**: Select the user the key will be associated with
   - **Key Name** (optional): Descriptive name (e.g., "Production Script", "Data Pipeline")
   - **Expiration** (optional): Choose from 30 days, 90 days, 180 days, 1 year, or never
5. Click **Generate Key**
6. ⚠️ **Copy the key immediately** – it will never be shown again!

---

## Managing API Keys

### Viewing Keys

The API Keys page (`/admin/api-keys`) shows all keys with:
- User name and email
- Organization
- Key name
- Creation date
- Expiration date
- Status (Active, Expiring, Revoked)

### Revoking a Key

1. Find the key in the table
2. Click **Revoke** (soft delete – key is disabled but retained in database)

### Deleting a Key

1. Find the key in the table
2. Click **Delete** (permanent removal from database)

---

## CSV Format

All endpoints return a **single merged CSV** combining signs and supports data.

**Columns:**

| Column                    | Description                          |
|---------------------------|--------------------------------------|
| `ID`                      | Unique sign identifier               |
| `MUTCD Code`              | MUTCD traffic sign code              |
| `Position on the Support` | Sign position on the support pole    |
| `Height (in)`             | Sign height in inches                |
| `Width (in)`              | Sign width in inches                 |
| `Longitude`               | GPS longitude (WGS84)                |
| `Latitude`                | GPS latitude (WGS84)                 |

**Example:**
```csv
ID,MUTCD Code,Position on the Support,Height (in),Width (in),Longitude,Latitude
1,R1-1,Top,30,30,-73.985130,40.758896
2,W3-1,Bottom,24,24,-73.985200,40.758900
```

---

## API Endpoints



### 1. Download CSVs by Date Range (B2B API)

Downloads merged CSV results for all recordings within a specified date range. Returns a ZIP where each recording has its own merged CSV file.

**Endpoint:**
```
GET https://sci.ce.gatech.edu/download/csv-only-range

```

**Authentication:**
```
Header: X-API-Key: sk_live_xxxxxxxxxxxxx
```

**Query Parameters:**

| Parameter | Type   | Required | Description              | Example      |
|-----------|--------|----------|--------------------------|--------------|
| `start`   | string | Yes      | Start date (ISO format)  | `2024-01-01` |
| `end`     | string | Yes      | End date (ISO format)    | `2024-01-31` |

**Response:**
- **Success (200)**: ZIP file containing one merged `signs.csv` per matching recording
- **Filename format**: `recordings_csv_{start}_{end}.zip`
- **ZIP structure**:
  ```
  recordings_csv_2024-01-01_2024-01-31.zip
  ├── <recording_id_1>/
  │   └── signs.csv
  └── <recording_id_2>/
      └── signs.csv
  ```

**Error Codes:**

| Status | Description                        |
|--------|------------------------------------|
| 400    | Missing or invalid parameters      |
| 401    | Missing or invalid API key         |
| 404    | No recordings in date range        |

---

## Implementation Examples

### cURL – Download by Date Range

```bash
curl -X GET \
  "https://your-api.com/download/csv-only-range?start=2024-01-01&end=2024-01-31" \
  -H "X-API-Key: sk_live_xxxxxxxxxxxxx" \
  -o recordings_january.zip
```

The ZIP will contain one `signs.csv` per recording folder, each with columns:
`ID,MUTCD Code,Position on the Support,Height (in),Width (in),Longitude,Latitude`

### Python - Basic

```python
import requests
import zipfile
import io

API_KEY = "sk_live_xxxxxxxxxxxxx"
BASE_URL = "https://your-api.com"

params = {"start": "2024-01-01", "end": "2024-01-31"}
headers = {"X-API-Key": API_KEY}

response = requests.get(
    f"{BASE_URL}/download/csv-only-range",
    params=params,
    headers=headers
)

if response.status_code == 200:
    with open("recordings_january.zip", "wb") as f:
        f.write(response.content)
    print("✅ Download successful!")

    # Inspect the merged CSVs inside the ZIP
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        for name in z.namelist():
            print(name)  # e.g. <recording_id>/signs.csv
else:
    print(f"❌ Error: {response.status_code} - {response.text}")
```

### Python - With Environment Variable

```python
import requests
import os
import zipfile
import io

API_KEY = os.getenv("TRAFFIC_SIGN_API_KEY")
BASE_URL = "https://your-api.com"

def download_csv_range(start_date, end_date, output_path):
    """Download merged CSV results for a date range.
    
    Returns a ZIP where each recording folder contains a single signs.csv with columns:
    ID, MUTCD Code, Position on the Support, Height (in), Width (in), Longitude, Latitude
    """
    params = {"start": start_date, "end": end_date}
    headers = {"X-API-Key": API_KEY}
    
    response = requests.get(
        f"{BASE_URL}/download/csv-only-range",
        params=params,
        headers=headers,
        timeout=300
    )
    
    if response.status_code == 200:
        with open(output_path, "wb") as f:
            f.write(response.content)
        return True
    else:
        print(f"Error: {response.text}")
        return False

# Usage
download_csv_range("2024-01-01", "2024-01-31", "january_2024.zip")
```


## Error Handling

### Common Errors

**401 Unauthorized - Missing API Key**
```json
{"error": "X-API-Key header missing"}
```
**Solution:** Add the `X-API-Key` header to your request.

**401 Unauthorized - Invalid API Key**
```json
{"error": "Invalid or revoked API key"}
```
**Solution:** Verify the key is correct and not revoked.

**400 Bad Request - Missing Parameters**
```json
{"error": "Missing 'start' or 'end' query parameter"}
```
**Solution:** Include both `start` and `end` query parameters.

**404 Not Found - No Recordings**
```json
{"error": "No completed recordings found in the provided date range."}
```
**Solution:** Verify recordings exist for the specified date range.


---

## Support

For issues or questions:
1. Check the admin dashboard for API key status
2. Review error messages in API responses
3. Contact your system administrator

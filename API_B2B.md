# B2B API Authentication & Usage Guide

Complete guide for using the B2B API to download traffic sign data programmatically.

## Table of Contents

- [Overview](#overview)
- [Generating an API Key](#generating-an-api-key)
- [Managing API Keys](#managing-api-keys)
- [API Endpoint](#api-endpoint)
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

## API Endpoint

### Download CSVs by Date Range

Downloads CSV results for all recordings within a specified date range.

**Endpoint:**
```
GET /download/csv-only-range
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
- **Success (200)**: ZIP file containing `supports.csv` and `signs.csv` for all matching recordings
- **Filename format**: `recordings_csv_{start}_{end}.zip`

**Error Codes:**

| Status | Description                        |
|--------|------------------------------------|
| 400    | Missing or invalid parameters      |
| 401    | Missing or invalid API key         |
| 404    | No recordings in date range        |

---

## Implementation Examples

### cURL

```bash
curl -X GET \
  "https://your-api.com/download/csv-only-range?start=2024-01-01&end=2024-01-31" \
  -H "X-API-Key: sk_live_xxxxxxxxxxxxx" \
  -o recordings_january.zip
```

### Python - Basic

```python
import requests

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
else:
    print(f"❌ Error: {response.status_code} - {response.text}")
```

### Python - With Environment Variable

```python
import requests
import os

API_KEY = os.getenv("TRAFFIC_SIGN_API_KEY")
BASE_URL = "https://your-api.com"

def download_csv_range(start_date, end_date, output_path):
    """Download CSV results for a date range."""
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

### Python - With Retry Logic

```python
import requests
import time

def download_with_retry(api_key, start, end, output_path, max_retries=3):
    """Download with automatic retry on failure."""
    headers = {"X-API-Key": api_key}
    params = {"start": start, "end": end}
    
    for attempt in range(max_retries):
        try:
            response = requests.get(
                "https://your-api.com/download/csv-only-range",
                params=params,
                headers=headers,
                timeout=300
            )
            response.raise_for_status()
            
            with open(output_path, "wb") as f:
                f.write(response.content)
            return True
            
        except requests.exceptions.RequestException as e:
            wait_time = 2 ** attempt  # Exponential backoff
            print(f"Attempt {attempt + 1} failed: {e}")
            time.sleep(wait_time)
    
    return False

# Usage
download_with_retry(API_KEY, "2024-01-01", "2024-01-31", "january_2024.zip")
```

### Bash Script - Monthly Downloads

```bash
#!/bin/bash

API_KEY="sk_live_xxxxxxxxxxxxx"
BASE_URL="https://your-api.com"

download_csv() {
    local start=$1
    local end=$2
    local output="recordings_${start}_to_${end}.zip"
    
    curl -X GET \
        "$BASE_URL/download/csv-only-range?start=$start&end=$end" \
        -H "X-API-Key: $API_KEY" \
        -o "$output"
    
    echo "Downloaded: $output"
}

# Download Q1 2024
download_csv "2024-01-01" "2024-01-31"
download_csv "2024-02-01" "2024-02-29"
download_csv "2024-03-01" "2024-03-31"
```

---

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

## Best Practices

### Security

1. **Store keys in environment variables**
   ```bash
   export TRAFFIC_SIGN_API_KEY="sk_live_xxxxxxxxxxxxx"
   ```

2. **Never commit keys to version control**
   ```bash
   # .gitignore
   .env
   ```

3. **Use descriptive key names** (e.g., "Production Server", "Data Pipeline")

4. **Set expiration dates** for temporary access

5. **Rotate keys periodically** (every 90 days recommended)

6. **Revoke compromised keys immediately**

### Recommendations

- Implement retry logic with exponential backoff
- Set appropriate timeouts for large downloads
- Log all API requests with timestamps
- Validate downloaded ZIP files before extraction

---

## Support

For issues or questions:
1. Check the admin dashboard for API key status
2. Review error messages in API responses
3. Contact your system administrator

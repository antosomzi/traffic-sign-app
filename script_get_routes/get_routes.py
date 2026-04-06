import requests
import json
import time

BASE_URL = (
    "https://gisdata.pima.gov/arcgis1/rest/services/GISOpenData/Transportation"
    "/MapServer/15/query"
)

PARAMS = {
    "where": "PAVECO_CD in (1, 2, 3, 4)",
    "outFields": "PAVECO_CD",
    "returnGeometry": "true",
    "f": "geojson",
    "resultRecordCount": 2000,
}

TOTAL_RECORDS = 6438
PAGE_SIZE = 2000


def fetch_page(offset: int) -> list:
    params = {**PARAMS, "resultOffset": offset}
    response = requests.get(BASE_URL, params=params, timeout=60)
    response.raise_for_status()
    data = response.json()
    features = data.get("features", [])
    return features


def main():
    all_features = []
    offset = 0
    page = 1

    while offset < TOTAL_RECORDS:
        print(f"Page {page} (offset={offset})...")
        features = fetch_page(offset)
        all_features.extend(features)
        print(f"  -> {len(features)} routes fetched | total cumulé : {len(all_features)}")
        offset += PAGE_SIZE
        page += 1

        if len(features) < PAGE_SIZE:
            break

        time.sleep(0.5)

    print(f"\n{'='*40}")
    print(f"TOTAL : {len(all_features)} routes fetched sur {TOTAL_RECORDS} attendues")
    print(f"{'='*40}")

    geojson_output = {
        "type": "FeatureCollection",
        "features": all_features,
    }

    output_path = "pima_roads.geojson"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(geojson_output, f)

    print(f"Fichier sauvegardé : {output_path}")


if __name__ == "__main__":
    main()
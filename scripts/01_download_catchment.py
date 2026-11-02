"""
Stage 3A-1
Download the upstream drainage basin for USGS streamgage 02361000.

Source:
USGS Network Linked Data Index (NLDI)

The standard NLDI basin endpoint is used without optional
processing parameters.

The downloaded geometry is considered a candidate basin until
its area is independently checked during Stage 3A-2.

Raw files must never be manually edited.
"""

from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

import requests
import yaml


# =========================================================
# Project paths
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CONFIG_FILE = PROJECT_ROOT / "config" / "project_config.yaml"


# =========================================================
# Read configuration
# =========================================================

with open(CONFIG_FILE, "r", encoding="utf-8") as file:
    config = yaml.safe_load(file)

station_id = config["catchment"]["usgs_station"]
feature_id = config["catchment"]["usgs_feature_id"]

raw_output_dir = (
    PROJECT_ROOT
    / config["paths"]["raw_catchment"]
)

raw_output_dir.mkdir(
    parents=True,
    exist_ok=True,
)


# =========================================================
# USGS NLDI basin endpoint
# =========================================================

url = (
    "https://api.water.usgs.gov/"
    "nldi/linked-data/"
    f"nwissite/{feature_id}/basin"
)

headers = {
    "Accept": "application/geo+json, application/json",
    "User-Agent": "satellite-rainfall-runoff-research/0.1",
}


# =========================================================
# Request basin
# =========================================================

print("=" * 60)
print("Stage 3A-1: Catchment download")
print("=" * 60)

print(f"USGS station : {station_id}")
print(f"NLDI feature : {feature_id}")
print()
print(f"URL:")
print(url)
print()
print("Requesting upstream basin from USGS NLDI...")


try:

    response = requests.get(
        url,
        headers=headers,
        timeout=120,
    )

    response.raise_for_status()

except requests.exceptions.RequestException as exc:

    print()
    print("ERROR: Catchment download failed.")
    print(exc)

    raise SystemExit(1)


# =========================================================
# Parse GeoJSON
# =========================================================

try:

    geojson = response.json()

except json.JSONDecodeError:

    print()
    print("ERROR: USGS response is not valid JSON/GeoJSON.")

    raise SystemExit(1)


if "features" not in geojson:

    print()
    print("ERROR: Response is not a GeoJSON FeatureCollection.")

    raise SystemExit(1)


if len(geojson["features"]) == 0:

    print()
    print("ERROR: No basin geometry was returned.")

    raise SystemExit(1)


# =========================================================
# Save immutable raw basin
# =========================================================

output_file = (
    raw_output_dir
    / f"USGS_{station_id}_NLDI_basin_raw.geojson"
)


with open(
    output_file,
    "w",
    encoding="utf-8",
) as file:

    json.dump(
        geojson,
        file,
        indent=2,
    )


# =========================================================
# Calculate SHA-256 checksum
# =========================================================

with open(output_file, "rb") as file:

    sha256 = hashlib.sha256(
        file.read()
    ).hexdigest()


# =========================================================
# Save provenance metadata
# =========================================================

metadata = {

    "download_timestamp_utc":
        datetime.now(timezone.utc).isoformat(),

    "source":
        "USGS Network Linked Data Index (NLDI)",

    "station_id":
        station_id,

    "feature_id":
        feature_id,

    "endpoint":
        url,

    "optional_parameters":
        None,

    "nldi_default_simplified":
        True,

    "nldi_default_splitCatchment":
        False,

    "http_status":
        response.status_code,

    "raw_file":
        output_file.name,

    "sha256":
        sha256,

    "scientific_status":
        "candidate basin pending Stage 3A-2 area QC",
}


metadata_file = (
    raw_output_dir
    / f"USGS_{station_id}_NLDI_basin_source_metadata.json"
)


with open(
    metadata_file,
    "w",
    encoding="utf-8",
) as file:

    json.dump(
        metadata,
        file,
        indent=2,
    )


# =========================================================
# Report
# =========================================================

feature_count = len(
    geojson["features"]
)

geometry_types = sorted({

    feature["geometry"]["type"]

    for feature in geojson["features"]

    if feature.get("geometry")

})


print()
print("=" * 60)
print("DOWNLOAD SUCCESSFUL")
print("=" * 60)

print(f"HTTP status       : {response.status_code}")
print(f"Number of features: {feature_count}")
print(f"Geometry type(s)  : {geometry_types}")

print()
print("Raw catchment:")
print(output_file)

print()
print("Metadata:")
print(metadata_file)

print()
print("SHA-256:")
print(sha256)

print()
print(
    "STATUS: Candidate basin downloaded successfully."
)

print(
    "The basin is NOT yet scientifically accepted."
)

print(
    "Stage 3A-2 must calculate its area and compare it "
    "with the official USGS drainage area."
)

print()
print(
    "IMPORTANT: Do not manually edit files in data/raw."
)

print()
print("Stage 3A-1 COMPLETE.")
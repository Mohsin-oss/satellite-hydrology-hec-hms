"""
Stage 3A-3
Download continuous observed discharge for USGS station 02361000.

Study period:
2015-01-01 through 2024-12-31

Source:
USGS Water Data OGC API
Continuous Values collection

Parameter:
00060 = Discharge

Important:
- Data are downloaded year-by-year.
- Each API response page is preserved unchanged in data/raw/discharge.
- Raw data must never be manually edited.
- No cleaning, resampling, unit conversion, or gap filling occurs here.
- QC is performed later in Stage 3A-4.
"""

from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import time

import requests
import yaml


# =========================================================
# Project paths
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CONFIG_FILE = (
    PROJECT_ROOT
    / "config"
    / "project_config.yaml"
)


# =========================================================
# Read configuration
# =========================================================

with open(CONFIG_FILE, "r", encoding="utf-8") as file:
    config = yaml.safe_load(file)


station_id = config["catchment"]["usgs_station"]

monitoring_location_id = f"USGS-{station_id}"

study_start = config["study_period"]["start"]
study_end = config["study_period"]["end"]


raw_output_dir = (
    PROJECT_ROOT
    / config["paths"]["raw_discharge"]
)

raw_output_dir.mkdir(
    parents=True,
    exist_ok=True,
)


# =========================================================
# USGS settings
# =========================================================

PARAMETER_CODE = "00060"

API_URL = (
    "https://api.waterdata.usgs.gov/"
    "ogcapi/v1/collections/continuous/items"
)

PAGE_LIMIT = 10000


# =========================================================
# Optional API key
# =========================================================

# You may optionally define a USGS_API_KEY environment
# variable. The script also works without one unless the
# anonymous request rate limit is reached.

api_key = os.getenv("USGS_API_KEY")

headers = {
    "Accept": "application/geo+json, application/json",
    "User-Agent": "satellite-rainfall-runoff-research/0.1",
}

if api_key:
    headers["X-Api-Key"] = api_key


# =========================================================
# Utility functions
# =========================================================

def sha256_file(path):
    """Return SHA-256 checksum for a file."""

    sha256 = hashlib.sha256()

    with open(path, "rb") as file:

        for block in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            sha256.update(block)

    return sha256.hexdigest()


def get_next_link(response_json):
    """Return next-page URL if supplied by USGS."""

    for link in response_json.get("links", []):

        if link.get("rel") == "next":
            return link.get("href")

    return None


def download_page(url, params=None, retries=4):
    """Download one API page with basic retry handling."""

    for attempt in range(1, retries + 1):

        try:

            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=180,
            )

        except requests.exceptions.RequestException as exc:

            print(
                f"Network error on attempt "
                f"{attempt}/{retries}: {exc}"
            )

            if attempt < retries:
                time.sleep(3 * attempt)
                continue

            raise


        if response.status_code == 200:

            try:
                return response.json()

            except json.JSONDecodeError as exc:

                raise RuntimeError(
                    "USGS returned HTTP 200 but the "
                    "response was not valid JSON."
                ) from exc


        if response.status_code == 429:

            raise RuntimeError(
                "USGS returned HTTP 429: Too Many Requests.\n"
                "The anonymous API rate limit was reached.\n"
                "Use a free USGS/API.Data.gov API key and set "
                "it as the USGS_API_KEY environment variable."
            )


        if response.status_code in (
            500,
            502,
            503,
            504,
        ):

            print(
                f"USGS server error "
                f"{response.status_code} "
                f"on attempt {attempt}/{retries}."
            )

            if attempt < retries:
                time.sleep(4 * attempt)
                continue


        raise RuntimeError(
            f"USGS request failed.\n"
            f"HTTP status: {response.status_code}\n"
            f"URL: {response.url}\n"
            f"Response: {response.text[:500]}"
        )


    raise RuntimeError(
        "USGS request failed after all retries."
    )


# =========================================================
# Determine requested years
# =========================================================

start_year = int(study_start[:4])
end_year = int(study_end[:4])

years = range(
    start_year,
    end_year + 1,
)


# =========================================================
# Begin download
# =========================================================

print("=" * 70)
print("Stage 3A-3: USGS continuous discharge download")
print("=" * 70)

print(f"Station              : {monitoring_location_id}")
print(f"Parameter            : {PARAMETER_CODE} (discharge)")
print(f"Study period         : {study_start} to {study_end}")
print(f"API                  : USGS Water Data OGC API")

if api_key:

    print("API key              : detected")

else:

    print("API key              : not detected (anonymous access)")

print()


manifest = {
    "download_timestamp_utc":
        datetime.now(timezone.utc).isoformat(),

    "source":
        "USGS Water Data OGC API",

    "collection":
        "continuous",

    "monitoring_location_id":
        monitoring_location_id,

    "parameter_code":
        PARAMETER_CODE,

    "study_period": {
        "start": study_start,
        "end": study_end,
    },

    "api_endpoint":
        API_URL,

    "years": {},

    "total_observations": 0,

    "scientific_status":
        "raw discharge pending Stage 3A-4 QC",
}


# =========================================================
# Download year by year
# =========================================================

for year in years:

    print("=" * 70)
    print(f"Downloading {year}")
    print("=" * 70)

    start_time = (
        f"{year}-01-01T00:00:00Z"
    )

    end_time = (
        f"{year}-12-31T23:59:59Z"
    )


    params = {
        "f": "json",
        "monitoring_location_id":
            monitoring_location_id,
        "parameter_code":
            PARAMETER_CODE,
        "datetime":
            f"{start_time}/{end_time}",
        "limit":
            PAGE_LIMIT,
    }


    current_url = API_URL
    current_params = params

    page_number = 1
    year_observation_count = 0

    year_files = []


    while current_url:

        print(
            f"  Requesting page {page_number}..."
        )


        page_json = download_page(
            current_url,
            params=current_params,
        )


        features = page_json.get(
            "features",
            [],
        )

        number_returned = len(features)

        year_observation_count += (
            number_returned
        )


        filename = (
            f"USGS_{station_id}_"
            f"{PARAMETER_CODE}_"
            f"continuous_{year}_"
            f"page{page_number:03d}.geojson"
        )


        output_file = (
            raw_output_dir
            / filename
        )


        with open(
            output_file,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                page_json,
                file,
                indent=2,
            )


        checksum = sha256_file(
            output_file
        )


        year_files.append({
            "file":
                filename,

            "page":
                page_number,

            "observations":
                number_returned,

            "sha256":
                checksum,
        })


        print(
            f"    Observations returned: "
            f"{number_returned}"
        )


        next_url = get_next_link(
            page_json
        )


        if next_url:

            current_url = next_url

            # The next URL supplied by USGS already
            # contains the query parameters.
            current_params = None

            page_number += 1

            # Small delay to be courteous to the service.
            time.sleep(0.5)

        else:

            current_url = None


    print()
    print(
        f"{year} complete: "
        f"{year_observation_count:,} observations"
    )
    print()


    manifest["years"][str(year)] = {
        "observations":
            year_observation_count,

        "pages":
            len(year_files),

        "files":
            year_files,
    }


    manifest["total_observations"] += (
        year_observation_count
    )


# =========================================================
# Save manifest
# =========================================================

manifest_file = (
    raw_output_dir
    / (
        f"USGS_{station_id}_"
        f"{PARAMETER_CODE}_"
        "continuous_download_manifest.json"
    )
)


with open(
    manifest_file,
    "w",
    encoding="utf-8",
) as file:

    json.dump(
        manifest,
        file,
        indent=2,
    )


# =========================================================
# Final report
# =========================================================

print()
print("=" * 70)
print("DOWNLOAD COMPLETE")
print("=" * 70)

print()
print(
    f"Total observations downloaded: "
    f"{manifest['total_observations']:,}"
)

print()
print("Raw data directory:")
print(raw_output_dir)

print()
print("Manifest:")
print(manifest_file)

print()
print(
    "STATUS: Raw discharge downloaded."
)

print(
    "No cleaning, gap filling, resampling, "
    "or unit conversion has been performed."
)

print()
print(
    "Next step: Stage 3A-4 discharge QC."
)

print()
print(
    "IMPORTANT: Do not manually edit files "
    "inside data/raw/discharge."
)
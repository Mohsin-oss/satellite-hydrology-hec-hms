"""
Stage 3B-1
Verify Google Earth Engine and GPM IMERG V07 access.

Objectives
----------
1. Authenticate and initialize Google Earth Engine.
2. Load the accepted NLDI catchment.
3. Access NASA/GPM_L3/IMERG_V07.
4. Restrict to permanent IMERG products.
5. Verify expected 30-minute cadence.
6. Verify required bands.
7. Calculate catchment-mean precipitation for a short test period.
8. Save a small verification table.

This script DOES NOT perform the full 2018-2024 extraction.
"""

from pathlib import Path
import json

import ee
import geopandas as gpd
import pandas as pd
import yaml

from shapely.geometry import mapping


# =========================================================
# Project paths
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CONFIG_FILE = (
    PROJECT_ROOT
    / "config"
    / "project_config.yaml"
)


with open(CONFIG_FILE, "r", encoding="utf-8") as file:
    config = yaml.safe_load(file)


# =========================================================
# Configuration
# =========================================================

EE_PROJECT = config["earth_engine"]["cloud_project"]

IMERG_COLLECTION = (
    config["precipitation"]["gee_collection"]
)

CALIBRATED_BAND = (
    config["precipitation"]["calibrated_band"]
)

UNCALIBRATED_BAND = (
    config["precipitation"]["uncalibrated_band"]
)

RANDOM_ERROR_BAND = (
    config["precipitation"]["random_error_band"]
)


station_id = config["catchment"]["usgs_station"]


catchment_file = (
    PROJECT_ROOT
    / config["paths"]["interim_catchment"]
    / f"USGS_{station_id}_NLDI_basin_qc.gpkg"
)


results_dir = (
    PROJECT_ROOT
    / "results"
    / "tables"
)

results_dir.mkdir(
    parents=True,
    exist_ok=True,
)


# =========================================================
# Short verification period
# =========================================================

TEST_START = "2020-06-01"
TEST_END = "2020-06-03"

# Earth Engine filterDate uses an exclusive end date.
#
# Therefore this represents:
#
# 2020-06-01 00:00 UTC
# through
# 2020-06-02 23:30 UTC
#
# Expected images:
# 2 days × 48 half-hour periods = 96


# =========================================================
# Earth Engine authentication
# =========================================================

print("=" * 72)
print("Stage 3B-1: GPM IMERG access verification")
print("=" * 72)

print(f"Google Cloud project : {EE_PROJECT}")
print(f"IMERG collection     : {IMERG_COLLECTION}")
print(f"Test period          : {TEST_START} to {TEST_END}")
print()


print("Authenticating Google Earth Engine...")

ee.Authenticate()


print("Initializing Earth Engine...")

ee.Initialize(
    project=EE_PROJECT
)


print("Earth Engine initialization successful.")


# =========================================================
# Load catchment
# =========================================================

print()
print("Loading accepted catchment...")

if not catchment_file.exists():

    raise SystemExit(
        f"ERROR: Catchment file not found:\n{catchment_file}"
    )


catchment_gdf = gpd.read_file(
    catchment_file
)


if catchment_gdf.crs is None:

    raise SystemExit(
        "ERROR: Catchment CRS is undefined."
    )


catchment_gdf = catchment_gdf.to_crs(
    "EPSG:4326"
)


catchment_geometry = (
    catchment_gdf.geometry.union_all()
)


if not catchment_geometry.is_valid:

    raise SystemExit(
        "ERROR: Catchment geometry is invalid."
    )


ee_catchment = ee.Geometry(
    mapping(catchment_geometry)
)


print("Catchment loaded successfully.")


# =========================================================
# Load IMERG
# =========================================================

collection_all = (
    ee.ImageCollection(
        IMERG_COLLECTION
    )
    .filterDate(
        TEST_START,
        TEST_END,
    )
    .filterBounds(
        ee_catchment
    )
)


all_count = collection_all.size().getInfo()


# =========================================================
# Permanent products only
# =========================================================

collection = collection_all.filter(
    ee.Filter.eq(
        "status",
        "permanent",
    )
)


permanent_count = (
    collection.size().getInfo()
)


print()
print("=" * 72)
print("COLLECTION CHECK")
print("=" * 72)

print(
    f"All IMERG images       : "
    f"{all_count}"
)

print(
    f"Permanent IMERG images : "
    f"{permanent_count}"
)

print(
    f"Expected for 2 days    : "
    f"{2 * 48}"
)


if permanent_count == 0:

    raise SystemExit(
        "ERROR: No permanent IMERG images found."
    )


# =========================================================
# Inspect first image
# =========================================================

first_image = ee.Image(
    collection.first()
)


band_names = (
    first_image
    .bandNames()
    .getInfo()
)


required_bands = [
    CALIBRATED_BAND,
    UNCALIBRATED_BAND,
    RANDOM_ERROR_BAND,
]


missing_bands = [
    band
    for band in required_bands
    if band not in band_names
]


print()
print("=" * 72)
print("BAND CHECK")
print("=" * 72)

print("Required bands:")

for band in required_bands:
    print(f"  {band}")


print()
print(
    f"Total bands available: "
    f"{len(band_names)}"
)


if missing_bands:

    print()
    print(
        "ERROR: Required bands missing:"
    )

    for band in missing_bands:
        print(f"  {band}")

    raise SystemExit(1)


print()
print(
    "All required IMERG bands are available."
)


# =========================================================
# Inspect timestamps
# =========================================================

timestamps_ms = (
    collection
    .aggregate_array(
        "system:time_start"
    )
    .getInfo()
)


timestamps = pd.to_datetime(
    timestamps_ms,
    unit="ms",
    utc=True,
)


timestamps = pd.Series(
    timestamps
).sort_values().reset_index(drop=True)


interval_minutes = (
    timestamps
    .diff()
    .dt.total_seconds()
    / 60
)


print()
print("=" * 72)
print("TEMPORAL CHECK")
print("=" * 72)

print(
    f"First image : "
    f"{timestamps.iloc[0]}"
)

print(
    f"Last image  : "
    f"{timestamps.iloc[-1]}"
)

print(
    f"Median interval : "
    f"{interval_minutes.dropna().median():.1f} min"
)

print(
    f"Modal interval  : "
    f"{interval_minutes.dropna().mode().iloc[0]:.1f} min"
)


# =========================================================
# Catchment mean extraction function
# =========================================================

def image_to_feature(image):
    """
    Calculate catchment-mean calibrated precipitation,
    uncalibrated precipitation, and random error.

    IMERG precipitation is a RATE in mm/hr.
    """

    image = ee.Image(image)

    selected = image.select(
        [
            CALIBRATED_BAND,
            UNCALIBRATED_BAND,
            RANDOM_ERROR_BAND,
        ]
    )


    means = selected.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=ee_catchment,
        scale=11132,
        bestEffort=True,
        maxPixels=1_000_000,
    )


    timestamp = image.date()


    return ee.Feature(
        None,
        {
            "time_start":
                timestamp.format(
                    "YYYY-MM-dd HH:mm"
                ),

            "time_start_ms":
                image.get(
                    "system:time_start"
                ),

            "status":
                image.get("status"),

            "precipitation_mm_hr":
                means.get(
                    CALIBRATED_BAND
                ),

            "precipitation_uncal_mm_hr":
                means.get(
                    UNCALIBRATED_BAND
                ),

            "random_error_mm_hr":
                means.get(
                    RANDOM_ERROR_BAND
                ),
        },
    )


# =========================================================
# Extract short test series
# =========================================================

print()
print(
    "Calculating catchment-mean IMERG "
    "for the two-day test period..."
)


test_features = (
    collection.map(
        image_to_feature
    )
)


feature_info = (
    test_features
    .getInfo()
)


rows = []

for feature in feature_info["features"]:

    props = feature["properties"]

    rows.append(props)


test_df = pd.DataFrame(rows)


# =========================================================
# Parse and sort
# =========================================================

test_df["time_utc"] = pd.to_datetime(
    test_df["time_start_ms"],
    unit="ms",
    utc=True,
)


test_df = test_df.sort_values(
    "time_utc"
).reset_index(drop=True)


# =========================================================
# Convert rainfall rate to 30-minute depth
# =========================================================

# IMERG precipitation units:
# mm/hr
#
# Each image represents a 30-minute interval.
#
# rainfall depth =
# rate × 0.5 hour

test_df["precipitation_mm_30min"] = (
    test_df["precipitation_mm_hr"]
    * 0.5
)


test_df[
    "precipitation_uncal_mm_30min"
] = (
    test_df[
        "precipitation_uncal_mm_hr"
    ]
    * 0.5
)


# =========================================================
# Basic output checks
# =========================================================

missing_calibrated = (
    test_df[
        "precipitation_mm_hr"
    ]
    .isna()
    .sum()
)

missing_uncalibrated = (
    test_df[
        "precipitation_uncal_mm_hr"
    ]
    .isna()
    .sum()
)


total_depth = (
    test_df[
        "precipitation_mm_30min"
    ]
    .sum()
)


print()
print("=" * 72)
print("CATCHMENT-MEAN EXTRACTION CHECK")
print("=" * 72)

print(
    f"Rows extracted              : "
    f"{len(test_df)}"
)

print(
    f"Missing calibrated values   : "
    f"{missing_calibrated}"
)

print(
    f"Missing uncalibrated values : "
    f"{missing_uncalibrated}"
)

print(
    f"2-day calibrated rainfall   : "
    f"{total_depth:.3f} mm"
)


print()
print("First 10 observations:")

display_columns = [
    "time_utc",
    "status",
    "precipitation_mm_hr",
    "precipitation_mm_30min",
    "precipitation_uncal_mm_hr",
]


print(
    test_df[
        display_columns
    ]
    .head(10)
    .to_string(
        index=False
    )
)


# =========================================================
# Save verification output
# =========================================================

output_file = (
    results_dir
    / (
        f"IMERG_V07_verification_"
        f"USGS_{station_id}_"
        f"{TEST_START}_to_{TEST_END}.csv"
    )
)


test_df.to_csv(
    output_file,
    index=False,
)


# =========================================================
# Verification summary
# =========================================================

verification = {

    "earth_engine_project":
        EE_PROJECT,

    "collection":
        IMERG_COLLECTION,

    "test_start":
        TEST_START,

    "test_end_exclusive":
        TEST_END,

    "expected_images":
        96,

    "all_images":
        all_count,

    "permanent_images":
        permanent_count,

    "required_bands_present":
        len(missing_bands) == 0,

    "median_interval_minutes":
        float(
            interval_minutes
            .dropna()
            .median()
        ),

    "modal_interval_minutes":
        float(
            interval_minutes
            .dropna()
            .mode()
            .iloc[0]
        ),

    "missing_calibrated_values":
        int(missing_calibrated),

    "missing_uncalibrated_values":
        int(missing_uncalibrated),

    "calibrated_rainfall_total_mm":
        float(total_depth),

    "scientific_status":
        "pending Stage 3B-1 review",
}


summary_file = (
    results_dir
    / (
        f"IMERG_V07_verification_"
        f"USGS_{station_id}_summary.json"
    )
)


with open(
    summary_file,
    "w",
    encoding="utf-8",
) as file:

    json.dump(
        verification,
        file,
        indent=2,
    )


# =========================================================
# Final report
# =========================================================

print()
print("=" * 72)
print("FILES CREATED")
print("=" * 72)

print()
print(output_file)
print(summary_file)

print()
print("=" * 72)
print("Stage 3B-1 VERIFICATION COMPLETE")
print("=" * 72)

print()
print(
    "No full-period IMERG extraction "
    "has been performed."
)

print(
    "Review verification results before "
    "processing 2018-2024."
)
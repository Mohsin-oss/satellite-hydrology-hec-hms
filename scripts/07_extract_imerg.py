"""
Stage 3B-2
Extract basin-average GPM IMERG V07 precipitation for 2018-2024.

Catchment:
USGS 02361000 — Choctawhatchee River near Newton

Method
------
- Google Earth Engine
- IMERG Final V07
- Permanent products only
- Native IMERG spatial scale
- Area-weighted mean over accepted catchment
- Monthly extraction chunks
- 30-minute precipitation depth derived from mm/hr rate

Outputs
-------
Monthly CSV files are written to data/interim/precipitation.

No temporal interpolation or rainfall correction is performed.
"""

from pathlib import Path
from datetime import datetime, timezone
import calendar
import json
import time

import ee
import geopandas as gpd
import pandas as pd
import yaml

from shapely.geometry import mapping


# =========================================================
# Paths and configuration
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CONFIG_FILE = (
    PROJECT_ROOT
    / "config"
    / "project_config.yaml"
)

with open(CONFIG_FILE, "r", encoding="utf-8") as file:
    config = yaml.safe_load(file)


EE_PROJECT = config["earth_engine"]["cloud_project"]

station_id = config["catchment"]["usgs_station"]

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

STATUS_FILTER = (
    config["precipitation"]["status_filter"]
)


START_DATE = pd.Timestamp(
    config["precipitation"]["extraction_start"]
)

END_DATE = pd.Timestamp(
    config["precipitation"]["extraction_end"]
)


catchment_file = (
    PROJECT_ROOT
    / config["paths"]["interim_catchment"]
    / f"USGS_{station_id}_NLDI_basin_qc.gpkg"
)

output_dir = (
    PROJECT_ROOT
    / config["paths"]["interim_precipitation"]
)

results_dir = (
    PROJECT_ROOT
    / "results"
    / "tables"
)

output_dir.mkdir(parents=True, exist_ok=True)
results_dir.mkdir(parents=True, exist_ok=True)


# =========================================================
# Earth Engine
# =========================================================

print("=" * 74)
print("Stage 3B-2: Full IMERG basin-average extraction")
print("=" * 74)

print(f"Earth Engine project : {EE_PROJECT}")
print(f"Station              : USGS-{station_id}")
print(f"Collection           : {IMERG_COLLECTION}")
print(f"Period               : {START_DATE.date()} to {END_DATE.date()}")
print()


ee.Authenticate()

ee.Initialize(
    project=EE_PROJECT
)


# =========================================================
# Load accepted catchment
# =========================================================

if not catchment_file.exists():
    raise SystemExit(
        f"ERROR: Catchment file not found:\n{catchment_file}"
    )


catchment_gdf = gpd.read_file(
    catchment_file
).to_crs("EPSG:4326")


catchment_geometry = (
    catchment_gdf.geometry.union_all()
)


if not catchment_geometry.is_valid:
    raise SystemExit(
        "ERROR: Accepted catchment geometry is invalid."
    )


ee_catchment = ee.Geometry(
    mapping(catchment_geometry)
)


# =========================================================
# Determine native IMERG scale
# =========================================================

reference_image = (
    ee.ImageCollection(IMERG_COLLECTION)
    .filterDate(
        START_DATE.strftime("%Y-%m-%d"),
        (
            START_DATE
            + pd.Timedelta(days=1)
        ).strftime("%Y-%m-%d"),
    )
    .first()
)


native_scale = (
    ee.Image(reference_image)
    .select(CALIBRATED_BAND)
    .projection()
    .nominalScale()
    .getInfo()
)


print(
    f"Native IMERG nominal scale: "
    f"{native_scale:.2f} m"
)


# =========================================================
# Extraction function
# =========================================================

def image_to_feature(image):

    image = ee.Image(image)

    selected = image.select(
        [
            CALIBRATED_BAND,
            UNCALIBRATED_BAND,
            RANDOM_ERROR_BAND,
        ]
    )

    # ee.Reducer.mean() is a weighted reducer.
    #
    # For pixels intersecting the catchment boundary,
    # Earth Engine weights their contribution according
    # to the fraction of the pixel covered by the region.

    means = selected.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=ee_catchment,
        scale=native_scale,
        maxPixels=10000,
    )


    return ee.Feature(
        None,
        {
            "time_start_ms":
                image.get("system:time_start"),

            "status":
                image.get("status"),

            "precipitation_mm_hr":
                means.get(CALIBRATED_BAND),

            "precipitation_uncal_mm_hr":
                means.get(UNCALIBRATED_BAND),

            "random_error_mm_hr":
                means.get(RANDOM_ERROR_BAND),
        },
    )


# =========================================================
# Monthly extraction helper
# =========================================================

def extract_month(year, month, retries=3):

    start = pd.Timestamp(
        year=year,
        month=month,
        day=1,
    )

    if month == 12:
        end = pd.Timestamp(
            year=year + 1,
            month=1,
            day=1,
        )
    else:
        end = pd.Timestamp(
            year=year,
            month=month + 1,
            day=1,
        )


    collection = (
        ee.ImageCollection(IMERG_COLLECTION)
        .filterDate(
            start.strftime("%Y-%m-%d"),
            end.strftime("%Y-%m-%d"),
        )
        .filterBounds(ee_catchment)
        .filter(
            ee.Filter.eq(
                "status",
                STATUS_FILTER,
            )
        )
    )


    image_count = collection.size().getInfo()


    expected_count = (
        (end - start).days
        * 48
    )


    print()
    print(
        f"{year}-{month:02d}"
        f" | expected={expected_count:,}"
        f" | available={image_count:,}"
    )


    if image_count != expected_count:

        print(
            "WARNING: IMERG image count does not "
            "match expected 30-minute coverage."
        )


    feature_collection = collection.map(
        image_to_feature
    )


    for attempt in range(
        1,
        retries + 1,
    ):

        try:

            info = feature_collection.getInfo()

            break

        except Exception as exc:

            print(
                f"  Extraction attempt "
                f"{attempt}/{retries} failed:"
            )

            print(
                f"  {exc}"
            )

            if attempt == retries:
                raise

            time.sleep(
                5 * attempt
            )


    rows = [
        feature["properties"]
        for feature
        in info["features"]
    ]


    month_df = pd.DataFrame(
        rows
    )


    if month_df.empty:
        raise RuntimeError(
            f"No IMERG records returned "
            f"for {year}-{month:02d}."
        )


    # -----------------------------------------------------
    # Timestamp
    # -----------------------------------------------------

    month_df["time_utc"] = pd.to_datetime(
        month_df["time_start_ms"],
        unit="ms",
        utc=True,
    )


    month_df = (
        month_df
        .sort_values("time_utc")
        .reset_index(drop=True)
    )


    # -----------------------------------------------------
    # Convert rate to 30-minute depth
    # -----------------------------------------------------

    month_df[
        "precipitation_mm_30min"
    ] = (
        month_df["precipitation_mm_hr"]
        * 0.5
    )


    month_df[
        "precipitation_uncal_mm_30min"
    ] = (
        month_df[
            "precipitation_uncal_mm_hr"
        ]
        * 0.5
    )


    # -----------------------------------------------------
    # Basic local QC
    # -----------------------------------------------------

    month_df["interval_minutes"] = (
        month_df["time_utc"]
        .diff()
        .dt.total_seconds()
        / 60
    )


    duplicate_count = (
        month_df["time_utc"]
        .duplicated()
        .sum()
    )


    missing_calibrated = (
        month_df["precipitation_mm_hr"]
        .isna()
        .sum()
    )


    missing_uncalibrated = (
        month_df[
            "precipitation_uncal_mm_hr"
        ]
        .isna()
        .sum()
    )


    modal_interval = (
        month_df["interval_minutes"]
        .dropna()
        .mode()
        .iloc[0]
    )


    # -----------------------------------------------------
    # Save monthly derived extraction
    # -----------------------------------------------------

    output_file = (
        output_dir
        / (
            f"IMERG_V07_"
            f"USGS_{station_id}_"
            f"{year}_{month:02d}.csv"
        )
    )


    output_columns = [
        "time_utc",
        "status",
        "precipitation_mm_hr",
        "precipitation_mm_30min",
        "precipitation_uncal_mm_hr",
        "precipitation_uncal_mm_30min",
        "random_error_mm_hr",
    ]


    month_df[
        output_columns
    ].to_csv(
        output_file,
        index=False,
    )


    return {
        "year":
            year,

        "month":
            month,

        "expected_images":
            expected_count,

        "available_images":
            image_count,

        "rows_saved":
            len(month_df),

        "duplicates":
            int(duplicate_count),

        "missing_calibrated":
            int(missing_calibrated),

        "missing_uncalibrated":
            int(missing_uncalibrated),

        "modal_interval_minutes":
            float(modal_interval),

        "calibrated_total_mm":
            float(
                month_df[
                    "precipitation_mm_30min"
                ].sum()
            ),

        "output_file":
            output_file.name,
    }


# =========================================================
# Extraction loop
# =========================================================

manifest_rows = []


for year in range(
    START_DATE.year,
    END_DATE.year + 1,
):

    for month in range(1, 13):

        month_start = pd.Timestamp(
            year=year,
            month=month,
            day=1,
        )


        if month_start < START_DATE:
            continue


        if month_start > END_DATE:
            continue


        output_file = (
            output_dir
            / (
                f"IMERG_V07_"
                f"USGS_{station_id}_"
                f"{year}_{month:02d}.csv"
            )
        )


        # Resume capability:
        #
        # Do not recompute successfully downloaded months.

        if output_file.exists():

            print()
            print(
                f"{year}-{month:02d} "
                f"already exists — skipping."
            )

            continue


        result = extract_month(
            year,
            month,
        )


        manifest_rows.append(
            result
        )


        print(
            f"  Saved {result['rows_saved']:,} rows"
        )

        print(
            f"  Rainfall total: "
            f"{result['calibrated_total_mm']:.2f} mm"
        )

        print(
            f"  Missing calibrated: "
            f"{result['missing_calibrated']}"
        )

        print(
            f"  Duplicates: "
            f"{result['duplicates']}"
        )


# =========================================================
# Manifest
# =========================================================

manifest_file = (
    results_dir
    / (
        f"IMERG_V07_"
        f"USGS_{station_id}_"
        "extraction_manifest.csv"
    )
)


if manifest_rows:

    new_manifest = pd.DataFrame(
        manifest_rows
    )

    if manifest_file.exists():

        old_manifest = pd.read_csv(
            manifest_file
        )

        manifest_df = pd.concat(
            [
                old_manifest,
                new_manifest,
            ],
            ignore_index=True,
        )

        manifest_df = (
            manifest_df
            .drop_duplicates(
                subset=[
                    "year",
                    "month",
                ],
                keep="last",
            )
            .sort_values(
                [
                    "year",
                    "month",
                ]
            )
        )

    else:

        manifest_df = new_manifest


    manifest_df.to_csv(
        manifest_file,
        index=False,
    )


# =========================================================
# Provenance metadata
# =========================================================

metadata = {

    "created_utc":
        datetime.now(
            timezone.utc
        ).isoformat(),

    "earth_engine_project":
        EE_PROJECT,

    "collection":
        IMERG_COLLECTION,

    "station":
        f"USGS-{station_id}",

    "period":
        {
            "start":
                str(START_DATE.date()),

            "end":
                str(END_DATE.date()),
        },

    "status_filter":
        STATUS_FILTER,

    "bands":
        [
            CALIBRATED_BAND,
            UNCALIBRATED_BAND,
            RANDOM_ERROR_BAND,
        ],

    "native_scale_m":
        native_scale,

    "spatial_reducer":
        "ee.Reducer.mean()",

    "spatial_weighting":
        (
            "Earth Engine default weighted region "
            "reduction using fractional pixel-region "
            "intersection for boundary pixels"
        ),

    "temporal_resolution_minutes":
        30,

    "rate_to_depth_conversion":
        "30-minute depth = precipitation rate (mm/hr) * 0.5",

    "chunking":
        "monthly",

    "raw_rasters_downloaded":
        False,

    "scientific_status":
        "pending Stage 3B-3 precipitation QC",
}


metadata_file = (
    results_dir
    / (
        f"IMERG_V07_"
        f"USGS_{station_id}_"
        "extraction_metadata.json"
    )
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
# Final report
# =========================================================

print()
print("=" * 74)
print("Stage 3B-2 EXTRACTION LOOP COMPLETE")
print("=" * 74)

print()
print("Monthly extraction directory:")
print(output_dir)

print()
print("Manifest:")
print(manifest_file)

print()
print("Metadata:")
print(metadata_file)

print()
print(
    "No interpolation, temporal aggregation, "
    "bias correction, or rainfall calibration "
    "was performed locally."
)

print()
print(
    "Next step: Stage 3B-3 IMERG temporal "
    "completeness and rainfall QC."
)
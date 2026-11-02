"""
Stage 3D-2A1
USGS 3DEP terrain acquisition and QC.

Objectives
----------
1. Load the accepted USGS 02361000 catchment.
2. Verify USGS 3DEP 10 m coverage.
3. Calculate elevation statistics.
4. Calculate preliminary terrain-slope statistics.
5. Export the DEM in EPSG:5070 for subsequent local
   hydrological terrain processing.
6. Record provenance and export-task metadata.

IMPORTANT
---------
This stage does NOT:
- delineate a new catchment;
- calculate flow direction;
- calculate flow accumulation;
- calculate longest flow path;
- estimate Clark Tc;
- alter the accepted NLDI basin.

The Earth Engine slope result is diagnostic only.
Later terrain processing will be performed from the
exported DEM using a reproducible local workflow.
"""

from pathlib import Path
from datetime import datetime, timezone
import json

import ee
import geopandas as gpd
import pandas as pd
import yaml

from shapely.geometry import mapping


# =========================================================
# Project configuration
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CONFIG_FILE = (
    PROJECT_ROOT
    / "config"
    / "project_config.yaml"
)

with open(CONFIG_FILE, "r", encoding="utf-8") as file:
    config = yaml.safe_load(file)


station_id = config["catchment"]["usgs_station"]

EE_PROJECT = config["earth_engine"]["cloud_project"]

DEM_COLLECTION = config["terrain"]["dataset"]

ELEVATION_BAND = config["terrain"]["elevation_band"]

ANALYSIS_CRS = config["terrain"]["analysis_crs"]

EXPORT_SCALE_M = float(
    config["terrain"]["export_scale_m"]
)

EXPORT_BUFFER_M = float(
    config["terrain"]["export_buffer_m"]
)

MIN_COVERAGE_PERCENT = float(
    config["terrain"]["minimum_coverage_percent"]
)


# =========================================================
# Paths
# =========================================================

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
# Initialize Earth Engine
# =========================================================

print("=" * 76)
print("Stage 3D-2A1: USGS 3DEP terrain acquisition and QC")
print("=" * 76)

print(f"Station           : USGS-{station_id}")
print(f"3DEP collection   : {DEM_COLLECTION}")
print(f"Analysis CRS      : {ANALYSIS_CRS}")
print(f"Export scale      : {EXPORT_SCALE_M:.1f} m")
print(f"Export buffer     : {EXPORT_BUFFER_M:.0f} m")
print()


try:

    ee.Initialize(
        project=EE_PROJECT
    )

except Exception:

    print(
        "Existing Earth Engine authentication "
        "could not be used."
    )

    print(
        "Starting Earth Engine authentication..."
    )

    ee.Authenticate()

    ee.Initialize(
        project=EE_PROJECT
    )


print(
    "Earth Engine initialization successful."
)


# =========================================================
# Load accepted catchment
# =========================================================

if not catchment_file.exists():

    raise SystemExit(
        f"ERROR: Catchment file not found:\n"
        f"{catchment_file}"
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


# Add a modest buffer around the basin for the DEM export.
#
# The accepted catchment itself is NOT being changed.
# The buffer simply provides terrain context at the boundary
# for later flow-routing calculations.

ee_export_region = (
    ee_catchment.buffer(
        EXPORT_BUFFER_M
    )
)


print(
    "Accepted catchment loaded successfully."
)


# =========================================================
# Load 3DEP
# =========================================================

collection = (
    ee.ImageCollection(
        DEM_COLLECTION
    )
    .filterBounds(
        ee_export_region
    )
    .select(
        ELEVATION_BAND
    )
)


tile_count = (
    collection
    .size()
    .getInfo()
)


print()
print("=" * 76)
print("3DEP COLLECTION CHECK")
print("=" * 76)

print(
    f"Intersecting 3DEP images : "
    f"{tile_count}"
)


if tile_count == 0:

    raise SystemExit(
        "ERROR: No 3DEP images intersect the basin."
    )


# =========================================================
# Preserve native 3DEP projection
# =========================================================

# ImageCollection mosaics otherwise default to EPSG:4326
# at 1-degree resolution in Earth Engine. Terrain operations
# such as slope require the DEM's native grid.

native_projection = (
    ee.Image(
        collection.first()
    )
    .select(
        ELEVATION_BAND
    )
    .projection()
)


dem = (
    collection
    .mosaic()
    .setDefaultProjection(
        native_projection
    )
    .rename("elevation")
)


native_scale = (
    native_projection
    .nominalScale()
    .getInfo()
)

print(
    f"Reported nominal scale   : "
    f"{native_scale:.2f} m"
)


# =========================================================
# DEM coverage check
# =========================================================

# Use the same projected CRS for both catchment area
# and valid DEM area so the coverage comparison is
# internally consistent.

analysis_projection = ee.Projection(
    ANALYSIS_CRS
)


catchment_area_m2 = (
    ee_catchment
    .area(
        maxError=1,
        proj=analysis_projection,
    )
    .getInfo()
)

valid_dem_area = (
    ee.Image.pixelArea()
    .updateMask(
        dem.mask()
    )
    .reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=ee_catchment,
        scale=EXPORT_SCALE_M,
        crs=ANALYSIS_CRS,
        maxPixels=1_000_000_000,
        tileScale=4,
    )
    .get("area")
    .getInfo()
)


coverage_percent = (
    valid_dem_area
    / catchment_area_m2
    * 100
)


print()
print("=" * 76)
print("COVERAGE CHECK")
print("=" * 76)

print(
    f"Catchment area       : "
    f"{catchment_area_m2 / 1e6:.2f} km²"
)

print(
    f"Valid DEM area       : "
    f"{valid_dem_area / 1e6:.2f} km²"
)

print(
    f"DEM coverage         : "
    f"{coverage_percent:.3f}%"
)


if coverage_percent < MIN_COVERAGE_PERCENT:

    raise SystemExit(
        "ERROR: 3DEP coverage does not meet "
        "the configured minimum threshold."
    )


print(
    "Coverage threshold  : PASS"
)


# =========================================================
# Terrain statistics reducer
# =========================================================

stats_reducer = (
    ee.Reducer.minMax()
    .combine(
        reducer2=ee.Reducer.mean(),
        sharedInputs=True,
    )
    .combine(
        reducer2=ee.Reducer.stdDev(),
        sharedInputs=True,
    )
    .combine(
        reducer2=ee.Reducer.percentile(
            [5, 25, 50, 75, 95]
        ),
        sharedInputs=True,
    )
)


# =========================================================
# Elevation statistics
# =========================================================

elevation_stats = (
    dem
    .reduceRegion(
        reducer=stats_reducer,
        geometry=ee_catchment,
        scale=EXPORT_SCALE_M,
        crs=ANALYSIS_CRS,
        maxPixels=1_000_000_000,
        tileScale=4,
    )
    .getInfo()
)


# =========================================================
# Preliminary slope
# =========================================================

# This is a QC terrain diagnostic.
#
# We will later derive the hydrologically conditioned
# terrain and flow-path metrics locally from the exported DEM.

slope = (
    ee.Terrain
    .slope(dem)
    .rename("slope")
)


slope_stats = (
    slope
    .reduceRegion(
        reducer=stats_reducer,
        geometry=ee_catchment,
        scale=EXPORT_SCALE_M,
        crs=ANALYSIS_CRS,
        maxPixels=1_000_000_000,
        tileScale=4,
    )
    .getInfo()
)


# =========================================================
# Print terrain statistics
# =========================================================

def get_stat(stats, prefix, key):
    return stats.get(
        f"{prefix}_{key}"
    )


print()
print("=" * 76)
print("ELEVATION STATISTICS")
print("=" * 76)

print(
    f"Minimum       : "
    f"{get_stat(elevation_stats, 'elevation', 'min'):.2f} m"
)

print(
    f"5th percentile: "
    f"{get_stat(elevation_stats, 'elevation', 'p5'):.2f} m"
)

print(
    f"25th percentile: "
    f"{get_stat(elevation_stats, 'elevation', 'p25'):.2f} m"
)

print(
    f"Median        : "
    f"{get_stat(elevation_stats, 'elevation', 'p50'):.2f} m"
)

print(
    f"Mean          : "
    f"{get_stat(elevation_stats, 'elevation', 'mean'):.2f} m"
)

print(
    f"75th percentile: "
    f"{get_stat(elevation_stats, 'elevation', 'p75'):.2f} m"
)

print(
    f"95th percentile: "
    f"{get_stat(elevation_stats, 'elevation', 'p95'):.2f} m"
)

print(
    f"Maximum       : "
    f"{get_stat(elevation_stats, 'elevation', 'max'):.2f} m"
)

print(
    f"Standard dev. : "
    f"{get_stat(elevation_stats, 'elevation', 'stdDev'):.2f} m"
)


relief_m = (
    get_stat(
        elevation_stats,
        "elevation",
        "max",
    )
    -
    get_stat(
        elevation_stats,
        "elevation",
        "min",
    )
)


print(
    f"Total relief  : "
    f"{relief_m:.2f} m"
)


print()
print("=" * 76)
print("SLOPE STATISTICS")
print("=" * 76)

print(
    f"Minimum       : "
    f"{get_stat(slope_stats, 'slope', 'min'):.3f}°"
)

print(
    f"5th percentile: "
    f"{get_stat(slope_stats, 'slope', 'p5'):.3f}°"
)

print(
    f"Median        : "
    f"{get_stat(slope_stats, 'slope', 'p50'):.3f}°"
)

print(
    f"Mean          : "
    f"{get_stat(slope_stats, 'slope', 'mean'):.3f}°"
)

print(
    f"95th percentile: "
    f"{get_stat(slope_stats, 'slope', 'p95'):.3f}°"
)

print(
    f"Maximum       : "
    f"{get_stat(slope_stats, 'slope', 'max'):.3f}°"
)


# =========================================================
# Save QC statistics
# =========================================================

summary = {

    "station":
        f"USGS-{station_id}",

    "dataset":
        DEM_COLLECTION,

    "elevation_band":
        ELEVATION_BAND,

    "earth_engine_project":
        EE_PROJECT,

    "intersecting_3dep_images":
        tile_count,

    "reported_nominal_scale_m":
        native_scale,

    "analysis_crs":
        ANALYSIS_CRS,

    "analysis_scale_m":
        EXPORT_SCALE_M,

    "catchment_area_km2":
        catchment_area_m2 / 1e6,

    "valid_dem_area_km2":
        valid_dem_area / 1e6,

    "coverage_percent":
        coverage_percent,

    "elevation_m":
        elevation_stats,

    "relief_m":
        relief_m,

    "slope_degrees":
        slope_stats,

    "scientific_status":
        (
            "3DEP terrain QC passed; "
            "flow-path analysis not yet performed"
        ),
}


summary_file = (
    results_dir
    / (
        f"USGS_{station_id}_"
        "3DEP_terrain_qc.json"
    )
)


with open(
    summary_file,
    "w",
    encoding="utf-8",
) as file:

    json.dump(
        summary,
        file,
        indent=2,
    )


# =========================================================
# Save simple tabular summary
# =========================================================

table = pd.DataFrame(
    [
        {
            "variable": "elevation",
            "unit": "m",
            "min": get_stat(
                elevation_stats,
                "elevation",
                "min",
            ),
            "p05": get_stat(
                elevation_stats,
                "elevation",
                "p5",
            ),
            "p25": get_stat(
                elevation_stats,
                "elevation",
                "p25",
            ),
            "median": get_stat(
                elevation_stats,
                "elevation",
                "p50",
            ),
            "mean": get_stat(
                elevation_stats,
                "elevation",
                "mean",
            ),
            "p75": get_stat(
                elevation_stats,
                "elevation",
                "p75",
            ),
            "p95": get_stat(
                elevation_stats,
                "elevation",
                "p95",
            ),
            "max": get_stat(
                elevation_stats,
                "elevation",
                "max",
            ),
        },
        {
            "variable": "slope",
            "unit": "degrees",
            "min": get_stat(
                slope_stats,
                "slope",
                "min",
            ),
            "p05": get_stat(
                slope_stats,
                "slope",
                "p5",
            ),
            "p25": get_stat(
                slope_stats,
                "slope",
                "p25",
            ),
            "median": get_stat(
                slope_stats,
                "slope",
                "p50",
            ),
            "mean": get_stat(
                slope_stats,
                "slope",
                "mean",
            ),
            "p75": get_stat(
                slope_stats,
                "slope",
                "p75",
            ),
            "p95": get_stat(
                slope_stats,
                "slope",
                "p95",
            ),
            "max": get_stat(
                slope_stats,
                "slope",
                "max",
            ),
        },
    ]
)


table_file = (
    results_dir
    / (
        f"USGS_{station_id}_"
        "3DEP_terrain_statistics.csv"
    )
)


table.to_csv(
    table_file,
    index=False,
)


# =========================================================
# Export clipped DEM to Google Drive
# =========================================================

export_description = (
    f"USGS_{station_id}_3DEP_10m_DEM"
)


export_filename = (
    f"USGS_{station_id}_"
    "3DEP_10m_EPSG5070"
)


export_image = (
    dem
    .clip(
        ee_export_region
    )
)


task = ee.batch.Export.image.toDrive(

    image=export_image,

    description=export_description,

    folder="satellite_rainfall_runoff_exports",

    fileNamePrefix=export_filename,

    region=ee_export_region,

    scale=EXPORT_SCALE_M,

    crs=ANALYSIS_CRS,

    maxPixels=1_000_000_000,

    fileFormat="GeoTIFF",

    formatOptions={
        "cloudOptimized": True,
    },
)


task.start()


task_status = task.status()


# =========================================================
# Save export metadata
# =========================================================

export_metadata = {

    "created_utc":
        datetime.now(
            timezone.utc
        ).isoformat(),

    "task_id":
        task_status.get("id"),

    "task_state":
        task_status.get("state"),

    "description":
        export_description,

    "google_drive_folder":
        "satellite_rainfall_runoff_exports",

    "filename_prefix":
        export_filename,

    "dataset":
        DEM_COLLECTION,

    "band":
        ELEVATION_BAND,

    "crs":
        ANALYSIS_CRS,

    "scale_m":
        EXPORT_SCALE_M,

    "catchment_buffer_m":
        EXPORT_BUFFER_M,

    "purpose":
        (
            "Local hydrological terrain processing "
            "for flow path, slope and Clark Tc "
            "initial parameter estimation"
        ),

    "local_destination_after_download":
        (
            "data/raw/dem/"
            f"{export_filename}.tif"
        ),
}


metadata_file = (
    results_dir
    / (
        f"USGS_{station_id}_"
        "3DEP_export_metadata.json"
    )
)


with open(
    metadata_file,
    "w",
    encoding="utf-8",
) as file:

    json.dump(
        export_metadata,
        file,
        indent=2,
    )


# =========================================================
# Final report
# =========================================================

print()
print("=" * 76)
print("FILES CREATED")
print("=" * 76)

print()
print("Terrain QC JSON:")
print(summary_file)

print()
print("Terrain statistics CSV:")
print(table_file)

print()
print("Export metadata:")
print(metadata_file)


print()
print("=" * 76)
print("EARTH ENGINE DEM EXPORT")
print("=" * 76)

print(
    f"Task ID    : "
    f"{task_status.get('id')}"
)

print(
    f"Task state : "
    f"{task_status.get('state')}"
)

print(
    "Drive folder:"
)

print(
    "satellite_rainfall_runoff_exports"
)

print()
print(
    "Expected filename prefix:"
)

print(
    export_filename
)


print()
print("=" * 76)
print("Stage 3D-2A1 COMPLETE")
print("=" * 76)

print()
print(
    "Terrain statistics have been computed."
)

print(
    "Clark Tc has NOT been estimated."
)

print(
    "Flow direction and longest flow path "
    "have NOT been calculated."
)
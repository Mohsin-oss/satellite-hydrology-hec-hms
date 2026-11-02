"""
Stage 3D-2A1b
Directly download the verified USGS 3DEP DEM from Earth Engine
to the local project directory.

This replaces the failed Google Drive export only.

The scientific dataset and processing choices are unchanged:
- USGS 3DEP 10 m
- EPSG:5070
- 10 m export scale
- accepted NLDI basin
- 1000 m export buffer

The raw downloaded DEM must remain unedited.
"""

from pathlib import Path
from shapely.geometry import mapping

import ee
import geopandas as gpd
import geemap
import yaml


# =========================================================
# Project configuration
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CONFIG_FILE = (
    PROJECT_ROOT
    / "config"
    / "project_config.yaml"
)

with open(
    CONFIG_FILE,
    "r",
    encoding="utf-8",
) as file:

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


# =========================================================
# Input / output paths
# =========================================================

catchment_file = (
    PROJECT_ROOT
    / config["paths"]["interim_catchment"]
    / f"USGS_{station_id}_NLDI_basin_qc.gpkg"
)


output_dir = (
    PROJECT_ROOT
    / config["paths"]["raw_dem"]
)

output_dir.mkdir(
    parents=True,
    exist_ok=True,
)


output_file = (
    output_dir
    / (
        f"USGS_{station_id}_"
        "3DEP_10m_EPSG5070.tif"
    )
)


# =========================================================
# Initialize Earth Engine
# =========================================================

print("=" * 76)
print("Direct local download: USGS 3DEP DEM")
print("=" * 76)

print(f"Station       : USGS-{station_id}")
print(f"Dataset       : {DEM_COLLECTION}")
print(f"Output CRS    : {ANALYSIS_CRS}")
print(f"Output scale  : {EXPORT_SCALE_M:.1f} m")
print(f"Buffer        : {EXPORT_BUFFER_M:.0f} m")
print()
print(f"Destination:")
print(output_file)
print()


try:

    ee.Initialize(
        project=EE_PROJECT
    )

except Exception:

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


catchment = gpd.read_file(
    catchment_file
)


catchment = catchment.to_crs(
    "EPSG:4326"
)


geometry = (
    catchment.geometry.union_all()
)


ee_catchment = ee.Geometry(
    mapping(geometry)
)


download_region = (
    ee_catchment.buffer(
        EXPORT_BUFFER_M
    )
)


print(
    "Accepted catchment loaded."
)


# =========================================================
# Prepare 3DEP DEM
# =========================================================

collection = (
    ee.ImageCollection(
        DEM_COLLECTION
    )
    .filterBounds(
        download_region
    )
    .select(
        ELEVATION_BAND
    )
)


count = collection.size().getInfo()

print(
    f"Intersecting 3DEP images: {count}"
)


if count == 0:

    raise SystemExit(
        "ERROR: No 3DEP image intersects the catchment."
    )


# Preserve the source projection before mosaicking.

native_projection = (
    ee.Image(
        collection.first()
    )
    .select(
        ELEVATION_BAND
    )
    .projection()
)


native_scale = (
    native_projection
    .nominalScale()
    .getInfo()
)


print(
    f"Native scale: {native_scale:.2f} m"
)


dem = (
    collection
    .mosaic()
    .setDefaultProjection(
        native_projection
    )
    .rename(
        "elevation"
    )
    .clip(
        download_region
    )
)


# =========================================================
# Direct local download
# =========================================================

print()
print("=" * 76)
print("STARTING LOCAL DOWNLOAD")
print("=" * 76)

print(
    "Large images may be downloaded as multiple "
    "temporary tiles and automatically reassembled."
)

print()


geemap.download_ee_image(

    image=dem,

    filename=str(
        output_file
    ),

    region=download_region,

    scale=EXPORT_SCALE_M,

    crs=ANALYSIS_CRS,

    resampling="near",

    overwrite=True,

    num_threads=4,

    max_tile_size=16,

    max_tile_dim=10000,
)


# =========================================================
# Verify
# =========================================================

if not output_file.exists():

    raise SystemExit(
        "ERROR: Local DEM download did not create "
        "the expected GeoTIFF."
    )


size_mb = (
    output_file.stat().st_size
    / 1024
    / 1024
)


print()
print("=" * 76)
print("LOCAL DOWNLOAD COMPLETE")
print("=" * 76)

print()
print(
    f"File:"
)

print(
    output_file
)

print()
print(
    f"File size: {size_mb:.1f} MB"
)

print()
print(
    "The DEM is now the immutable RAW terrain input."
)

print(
    "Do not manually edit or overwrite it."
)
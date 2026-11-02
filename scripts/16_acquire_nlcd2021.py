"""
Stage 3D-2B1
Acquire and QC NLCD 2021 land cover and imperviousness
for USGS 02361000.

Outputs
-------
1. Raw 30 m land-cover GeoTIFF.
2. Raw 30 m imperviousness GeoTIFF.
3. Land-cover class area/percentage table.
4. Imperviousness summary.
5. Acquisition/QC metadata.

This stage does NOT:
- calculate Curve Number;
- combine land cover with soils;
- modify NLCD classes.
"""

from pathlib import Path
from shapely.geometry import mapping
import json

import ee
import geopandas as gpd
import geemap
import pandas as pd
import yaml


# =========================================================
# Configuration
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CONFIG_FILE = PROJECT_ROOT / "config" / "project_config.yaml"

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)


station_id = config["catchment"]["usgs_station"]

EE_PROJECT = config["earth_engine"]["cloud_project"]

DATASET = config["landcover"]["dataset"]
IMAGE_INDEX = config["landcover"]["image_index"]
LANDCOVER_BAND = config["landcover"]["landcover_band"]
IMPERVIOUS_BAND = config["landcover"]["impervious_band"]
ANALYSIS_CRS = config["landcover"]["analysis_crs"]
SCALE_M = float(config["landcover"]["scale_m"])


# =========================================================
# Paths
# =========================================================

catchment_file = (
    PROJECT_ROOT
    / config["paths"]["interim_catchment"]
    / f"USGS_{station_id}_NLDI_basin_qc.gpkg"
)

output_dir = (
    PROJECT_ROOT
    / config["paths"]["raw_landcover"]
)

results_dir = PROJECT_ROOT / "results" / "tables"

output_dir.mkdir(parents=True, exist_ok=True)
results_dir.mkdir(parents=True, exist_ok=True)


landcover_file = (
    output_dir
    / f"USGS_{station_id}_NLCD2021_landcover_30m.tif"
)

impervious_file = (
    output_dir
    / f"USGS_{station_id}_NLCD2021_impervious_30m.tif"
)


# =========================================================
# NLCD legend
# =========================================================

NLCD_CLASSES = {
    11: "Open Water",
    12: "Perennial Ice/Snow",
    21: "Developed, Open Space",
    22: "Developed, Low Intensity",
    23: "Developed, Medium Intensity",
    24: "Developed, High Intensity",
    31: "Barren Land",
    41: "Deciduous Forest",
    42: "Evergreen Forest",
    43: "Mixed Forest",
    52: "Shrub/Scrub",
    71: "Grassland/Herbaceous",
    81: "Pasture/Hay",
    82: "Cultivated Crops",
    90: "Woody Wetlands",
    95: "Emergent Herbaceous Wetlands",
}


# =========================================================
# Earth Engine
# =========================================================

print("=" * 78)
print("Stage 3D-2B1: NLCD 2021 land-cover acquisition and QC")
print("=" * 78)

ee.Initialize(project=EE_PROJECT)

print("Earth Engine initialization successful.")


# =========================================================
# Catchment
# =========================================================

if not catchment_file.exists():
    raise SystemExit(
        f"ERROR: catchment file not found:\n{catchment_file}"
    )


catchment = gpd.read_file(catchment_file)

catchment_5070 = catchment.to_crs(ANALYSIS_CRS)

catchment_area_km2 = (
    catchment_5070.geometry.union_all().area
    / 1_000_000
)


catchment_wgs84 = catchment.to_crs("EPSG:4326")

geom = catchment_wgs84.geometry.union_all()

ee_catchment = ee.Geometry(mapping(geom))


print(
    f"Accepted catchment area: "
    f"{catchment_area_km2:.2f} km²"
)


# =========================================================
# Load NLCD 2021
# =========================================================

collection = ee.ImageCollection(DATASET)

image = (
    collection
    .filter(
        ee.Filter.eq(
            "system:index",
            IMAGE_INDEX
        )
    )
    .first()
)


if image is None:
    raise SystemExit(
        "ERROR: NLCD 2021 image was not found."
    )


bands = image.bandNames().getInfo()

print()
print("=" * 78)
print("NLCD DATASET CHECK")
print("=" * 78)

print(f"Dataset     : {DATASET}")
print(f"Image index : {IMAGE_INDEX}")
print(f"Bands       : {bands}")


for required_band in [
    LANDCOVER_BAND,
    IMPERVIOUS_BAND,
]:
    if required_band not in bands:
        raise SystemExit(
            f"ERROR: required band missing: "
            f"{required_band}"
        )


landcover = image.select(
    LANDCOVER_BAND
).rename("landcover")

impervious = image.select(
    IMPERVIOUS_BAND
).rename("impervious")


native_projection = landcover.projection()

native_scale = (
    native_projection
    .nominalScale()
    .getInfo()
)

native_crs = (
    native_projection
    .crs()
    .getInfo()
)


print(
    f"Native CRS   : {native_crs}"
)

print(
    f"Native scale : {native_scale:.2f} m"
)


# =========================================================
# Coverage
# =========================================================

valid_area_m2 = (
    ee.Image.pixelArea()
    .updateMask(
        landcover.mask()
    )
    .reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=ee_catchment,
        scale=SCALE_M,
        crs=ANALYSIS_CRS,
        maxPixels=1_000_000_000,
    )
    .get("area")
    .getInfo()
)


coverage_percent = (
    valid_area_m2
    / (
        catchment_area_km2
        * 1_000_000
    )
    * 100
)


print()
print("=" * 78)
print("COVERAGE CHECK")
print("=" * 78)

print(
    f"Valid NLCD area : "
    f"{valid_area_m2 / 1e6:.2f} km²"
)

print(
    f"Coverage        : "
    f"{coverage_percent:.3f}%"
)


if coverage_percent < 99.5:
    raise SystemExit(
        "ERROR: NLCD coverage below 99.5%."
    )


print("Coverage threshold: PASS")


# =========================================================
# Land-cover class areas
# =========================================================

area_with_classes = (
    ee.Image.pixelArea()
    .rename("area")
    .addBands(landcover)
)


grouped = (
    area_with_classes
    .reduceRegion(
        reducer=(
            ee.Reducer.sum()
            .group(
                groupField=1,
                groupName="class_value",
            )
        ),
        geometry=ee_catchment,
        scale=SCALE_M,
        crs=ANALYSIS_CRS,
        maxPixels=1_000_000_000,
    )
    .get("groups")
    .getInfo()
)


rows = []

for item in grouped:

    class_value = int(
        item["class_value"]
    )

    area_km2 = (
        float(item["sum"])
        / 1_000_000
    )

    percent = (
        area_km2
        / catchment_area_km2
        * 100
    )

    rows.append({
        "class_value":
            class_value,

        "class_name":
            NLCD_CLASSES.get(
                class_value,
                "Unknown",
            ),

        "area_km2":
            area_km2,

        "percent_basin":
            percent,
    })


class_table = (
    pd.DataFrame(rows)
    .sort_values(
        "area_km2",
        ascending=False,
    )
    .reset_index(drop=True)
)


class_table_file = (
    results_dir
    / (
        f"USGS_{station_id}_"
        "NLCD2021_landcover_summary.csv"
    )
)


class_table.to_csv(
    class_table_file,
    index=False,
)


print()
print("=" * 78)
print("LAND-COVER COMPOSITION")
print("=" * 78)

print(
    class_table.to_string(
        index=False,
        formatters={
            "area_km2":
                "{:.2f}".format,
            "percent_basin":
                "{:.2f}".format,
        },
    )
)


# =========================================================
# Developed area summary
# =========================================================

developed_classes = [
    21,
    22,
    23,
    24,
]


developed_area_km2 = (
    class_table[
        class_table[
            "class_value"
        ].isin(
            developed_classes
        )
    ]["area_km2"]
    .sum()
)


developed_percent = (
    developed_area_km2
    / catchment_area_km2
    * 100
)


# =========================================================
# Impervious statistics
# =========================================================

impervious_reducer = (
    ee.Reducer.mean()
    .combine(
        reducer2=ee.Reducer.stdDev(),
        sharedInputs=True,
    )
    .combine(
        reducer2=ee.Reducer.percentile(
            [
                5,
                25,
                50,
                75,
                95,
            ]
        ),
        sharedInputs=True,
    )
    .combine(
        reducer2=ee.Reducer.max(),
        sharedInputs=True,
    )
)


impervious_stats = (
    impervious
    .reduceRegion(
        reducer=impervious_reducer,
        geometry=ee_catchment,
        scale=SCALE_M,
        crs=ANALYSIS_CRS,
        maxPixels=1_000_000_000,
    )
    .getInfo()
)


# Area with any imperviousness > 0%

impervious_positive_area = (
    ee.Image.pixelArea()
    .updateMask(
        impervious.gt(0)
    )
    .reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=ee_catchment,
        scale=SCALE_M,
        crs=ANALYSIS_CRS,
        maxPixels=1_000_000_000,
    )
    .get("area")
    .getInfo()
)


impervious_positive_percent = (
    impervious_positive_area
    / (
        catchment_area_km2
        * 1_000_000
    )
    * 100
)


print()
print("=" * 78)
print("IMPERVIOUSNESS")
print("=" * 78)

print(
    f"Mean imperviousness    : "
    f"{impervious_stats['impervious_mean']:.2f}%"
)

print(
    f"Median imperviousness  : "
    f"{impervious_stats['impervious_p50']:.2f}%"
)

print(
    f"95th percentile        : "
    f"{impervious_stats['impervious_p95']:.2f}%"
)

print(
    f"Maximum                : "
    f"{impervious_stats['impervious_max']:.2f}%"
)

print(
    f"Area with impervious>0 : "
    f"{impervious_positive_percent:.2f}%"
)

print(
    f"Developed NLCD classes : "
    f"{developed_percent:.2f}%"
)


# =========================================================
# Direct local downloads
# =========================================================

print()
print("=" * 78)
print("LOCAL DOWNLOAD")
print("=" * 78)


if not landcover_file.exists():

    geemap.download_ee_image(
        image=landcover.clip(
            ee_catchment
        ),
        filename=str(
            landcover_file
        ),
        region=ee_catchment,
        scale=SCALE_M,
        crs=ANALYSIS_CRS,
        resampling="near",
        overwrite=False,
        max_tile_size=16,
        max_tile_dim=10000,
    )

else:

    print(
        "Land-cover raster already exists; "
        "reusing it."
    )


if not impervious_file.exists():

    geemap.download_ee_image(
        image=impervious.clip(
            ee_catchment
        ),
        filename=str(
            impervious_file
        ),
        region=ee_catchment,
        scale=SCALE_M,
        crs=ANALYSIS_CRS,
        resampling="near",
        overwrite=False,
        max_tile_size=16,
        max_tile_dim=10000,
    )

else:

    print(
        "Impervious raster already exists; "
        "reusing it."
    )


# =========================================================
# Metadata
# =========================================================

metadata = {

    "station":
        f"USGS-{station_id}",

    "dataset":
        DATASET,

    "image_index":
        IMAGE_INDEX,

    "landcover_band":
        LANDCOVER_BAND,

    "impervious_band":
        IMPERVIOUS_BAND,

    "native_crs":
        native_crs,

    "native_scale_m":
        native_scale,

    "analysis_crs":
        ANALYSIS_CRS,

    "analysis_scale_m":
        SCALE_M,

    "coverage_percent":
        coverage_percent,

    "catchment_area_km2":
        catchment_area_km2,

    "developed_area_km2":
        developed_area_km2,

    "developed_percent":
        developed_percent,

    "impervious_statistics":
        impervious_stats,

    "impervious_positive_percent":
        impervious_positive_percent,

    "scientific_status":
        (
            "NLCD 2021 land-cover and "
            "imperviousness acquisition/QC passed; "
            "Curve Number not yet calculated"
        ),
}


metadata_file = (
    results_dir
    / (
        f"USGS_{station_id}_"
        "NLCD2021_qc.json"
    )
)


with open(
    metadata_file,
    "w",
    encoding="utf-8",
) as f:

    json.dump(
        metadata,
        f,
        indent=2,
    )


# =========================================================
# Final
# =========================================================

print()
print("=" * 78)
print("FILES CREATED")
print("=" * 78)

print(landcover_file)
print(impervious_file)
print(class_table_file)
print(metadata_file)


print()
print("=" * 78)
print("Stage 3D-2B1 COMPLETE")
print("=" * 78)

print()
print(
    "Land cover has NOT yet been converted "
    "to Curve Number."
)

print(
    "SSURGO hydrologic soil groups are still required."
)
"""
Stage 3D-2C2
Audit SSURGO HSG ambiguity against NLCD 2021 land cover.

Purpose
-------
1. Cross-tabulate NLCD land cover and SSURGO HSG.
2. Identify what land-cover classes occur on:
   - A/D
   - B/D
   - C/D
   - UNRATED soil areas
3. Quantify the area affected by each ambiguity.
4. Support a transparent drained/undrained HSG decision.

This stage does NOT:
- calculate Curve Number;
- resolve dual HSG classes automatically;
- impute unrated soils;
- modify source rasters.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import yaml


# =========================================================
# Configuration
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


# =========================================================
# Inputs
# =========================================================

landcover_file = (
    PROJECT_ROOT
    / config["paths"]["raw_landcover"]
    / f"USGS_{station_id}_NLCD2021_landcover_30m.tif"
)

hsg_file = (
    PROJECT_ROOT
    / config["paths"].get(
        "interim_soils",
        "data/interim/soils",
    )
    / f"USGS_{station_id}_SSURGO_HSG_DCD_30m.tif"
)


# =========================================================
# Outputs
# =========================================================

results_dir = (
    PROJECT_ROOT
    / "results"
    / "tables"
)

results_dir.mkdir(
    parents=True,
    exist_ok=True,
)


crosswalk_file = (
    results_dir
    / f"USGS_{station_id}_NLCD_HSG_crosstab.csv"
)

ambiguity_file = (
    results_dir
    / f"USGS_{station_id}_HSG_ambiguity_by_landcover.csv"
)


# =========================================================
# Legends
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


HSG_CLASSES = {
    0: "UNRATED",
    1: "A",
    2: "B",
    3: "C",
    4: "D",
    5: "A/D",
    6: "B/D",
    7: "C/D",
}


# =========================================================
# Validate raster alignment
# =========================================================

print("=" * 78)
print("Stage 3D-2C2: HSG x NLCD ambiguity audit")
print("=" * 78)


with rasterio.open(landcover_file) as lc_src:
    lc = lc_src.read(1)
    lc_crs = lc_src.crs
    lc_transform = lc_src.transform
    lc_shape = lc.shape


with rasterio.open(hsg_file) as hsg_src:
    hsg = hsg_src.read(1)
    hsg_crs = hsg_src.crs
    hsg_transform = hsg_src.transform
    hsg_shape = hsg.shape


print()
print("RASTER ALIGNMENT")
print("-" * 78)

print(f"NLCD shape : {lc_shape}")
print(f"HSG shape  : {hsg_shape}")
print(f"NLCD CRS   : {lc_crs}")
print(f"HSG CRS    : {hsg_crs}")


if lc_shape != hsg_shape:
    raise SystemExit(
        "ERROR: NLCD and HSG raster dimensions differ."
    )


if lc_crs != hsg_crs:
    raise SystemExit(
        "ERROR: NLCD and HSG CRS differ."
    )


if lc_transform != hsg_transform:
    raise SystemExit(
        "ERROR: NLCD and HSG grids are not aligned."
    )


print("Raster alignment: PASS")


# =========================================================
# Pixel area
# =========================================================

pixel_area_km2 = (
    abs(lc_transform.a)
    * abs(lc_transform.e)
    / 1_000_000
)


# HSG 255 is outside accepted watershed.

inside = (
    hsg != 255
)


total_pixels = int(
    inside.sum()
)


total_area_km2 = (
    total_pixels
    * pixel_area_km2
)


# =========================================================
# Full cross-tab
# =========================================================

records = []


for hsg_code, hsg_name in HSG_CLASSES.items():

    hsg_mask = (
        inside
        &
        (hsg == hsg_code)
    )


    if not np.any(hsg_mask):
        continue


    values, counts = np.unique(
        lc[hsg_mask],
        return_counts=True,
    )


    for lc_code, count in zip(
        values,
        counts,
    ):

        lc_code = int(lc_code)
        count = int(count)

        area_km2 = (
            count
            * pixel_area_km2
        )


        records.append({
            "hsg_code":
                hsg_code,

            "hsg":
                hsg_name,

            "nlcd_code":
                lc_code,

            "nlcd_class":
                NLCD_CLASSES.get(
                    lc_code,
                    f"Unknown_{lc_code}",
                ),

            "pixels":
                count,

            "area_km2":
                area_km2,

            "percent_basin":
                area_km2
                / total_area_km2
                * 100,
        })


crosswalk = pd.DataFrame(
    records
)


crosswalk = (
    crosswalk
    .sort_values(
        [
            "hsg_code",
            "area_km2",
        ],
        ascending=[
            True,
            False,
        ],
    )
    .reset_index(
        drop=True
    )
)


crosswalk.to_csv(
    crosswalk_file,
    index=False,
)


# =========================================================
# Ambiguous groups only
# =========================================================

ambiguous_groups = [
    "A/D",
    "B/D",
    "C/D",
    "UNRATED",
]


ambiguity = (
    crosswalk[
        crosswalk["hsg"].isin(
            ambiguous_groups
        )
    ]
    .copy()
)


# Percentage within each ambiguous HSG group.

group_totals = (
    ambiguity
    .groupby(
        "hsg"
    )["area_km2"]
    .transform(
        "sum"
    )
)


ambiguity[
    "percent_within_hsg"
] = (
    ambiguity[
        "area_km2"
    ]
    / group_totals
    * 100
)


ambiguity = (
    ambiguity
    .sort_values(
        [
            "hsg",
            "area_km2",
        ],
        ascending=[
            True,
            False,
        ],
    )
    .reset_index(
        drop=True
    )
)


ambiguity.to_csv(
    ambiguity_file,
    index=False,
)


# =========================================================
# Terminal report
# =========================================================

print()
print("=" * 78)
print("DUAL / UNRATED HSG LAND-COVER AUDIT")
print("=" * 78)


for hsg_name in ambiguous_groups:

    subset = ambiguity[
        ambiguity["hsg"]
        == hsg_name
    ]


    if subset.empty:
        continue


    group_area = (
        subset[
            "area_km2"
        ]
        .sum()
    )


    print()
    print(
        f"{hsg_name}"
        f" — {group_area:.2f} km²"
        f" ({group_area / total_area_km2 * 100:.2f}% of basin)"
    )

    print(
        "-" * 78
    )


    print(
        subset[
            [
                "nlcd_code",
                "nlcd_class",
                "area_km2",
                "percent_within_hsg",
            ]
        ]
        .to_string(
            index=False,
            formatters={
                "area_km2":
                    "{:.2f}".format,

                "percent_within_hsg":
                    "{:.2f}".format,
            },
        )
    )


# =========================================================
# High-level totals
# =========================================================

dual_area = (
    ambiguity[
        ambiguity["hsg"].isin(
            [
                "A/D",
                "B/D",
                "C/D",
            ]
        )
    ]["area_km2"]
    .sum()
)


unrated_area = (
    ambiguity[
        ambiguity["hsg"]
        == "UNRATED"
    ]["area_km2"]
    .sum()
)


print()
print("=" * 78)
print("SUMMARY")
print("=" * 78)

print(
    f"Total basin raster area : "
    f"{total_area_km2:.2f} km²"
)

print(
    f"Dual-HSG area           : "
    f"{dual_area:.2f} km² "
    f"({dual_area / total_area_km2 * 100:.2f}%)"
)

print(
    f"Unrated HSG area        : "
    f"{unrated_area:.2f} km² "
    f"({unrated_area / total_area_km2 * 100:.2f}%)"
)


print()
print("=" * 78)
print("FILES CREATED")
print("=" * 78)

print(crosswalk_file)
print(ambiguity_file)


print()
print("=" * 78)
print("Stage 3D-2C2 COMPLETE")
print("=" * 78)

print()
print(
    "No HSG ambiguity has been resolved automatically."
)

print(
    "No Curve Number has been calculated."
)
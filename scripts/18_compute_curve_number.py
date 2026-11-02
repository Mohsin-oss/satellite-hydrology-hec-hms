"""
Stage 3D-2D1
Compute physically based basin Curve Number from
NLCD 2021 + SSURGO HSG.

Baseline assumptions
--------------------
1. Normal HSG A/B/C/D retained.
2. Dual HSG:
       A/D -> D
       B/D -> D
       C/D -> D
   because no functioning drainage evidence is available.
3. Unrated HSG -> D
   as a conservative baseline assumption.
4. A drained-dual alternative is also calculated:
       A/D -> A
       B/D -> B
       C/D -> C
5. NLCD -> CN values follow the published HEC-HMS
   NLCD/HSG lookup example.
6. Developed-class CN values are treated as composite
   urban CN values; HEC-HMS directly connected
   impervious area is therefore initialized at 0%.

Outputs
-------
1. Baseline CN raster.
2. Drained-dual CN raster.
3. Basin composite CN values.
4. CN contribution table.
5. Initial S and Ia values for HEC-HMS.
6. Parameter summary JSON.

This stage does NOT calibrate CN.
"""

from pathlib import Path
import json

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

with open(
    CONFIG_FILE,
    "r",
    encoding="utf-8",
) as file:

    config = yaml.safe_load(file)


station_id = config["catchment"]["usgs_station"]


# =========================================================
# Paths
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


processed_dir = (
    PROJECT_ROOT
    / config["paths"].get(
        "processed_soils",
        "data/processed/soils",
    )
)

results_dir = (
    PROJECT_ROOT
    / "results"
    / "tables"
)


processed_dir.mkdir(
    parents=True,
    exist_ok=True,
)

results_dir.mkdir(
    parents=True,
    exist_ok=True,
)


baseline_cn_file = (
    processed_dir
    / f"USGS_{station_id}_CN_baseline.tif"
)


drained_cn_file = (
    processed_dir
    / f"USGS_{station_id}_CN_drained_dual.tif"
)


contribution_file = (
    results_dir
    / f"USGS_{station_id}_CN_contributions.csv"
)


parameter_file = (
    results_dir
    / f"USGS_{station_id}_initial_HECHMS_parameters.json"
)


# =========================================================
# NLCD -> CN lookup table
# =========================================================

# Values:
# NLCD : {HSG: CN}
#
# Based on the published HEC-HMS GIS tutorial
# NLCD / Hydrologic Soil Group lookup table.

CN_LOOKUP = {

    11: {
        "A": 98,
        "B": 98,
        "C": 98,
        "D": 98,
    },

    12: {
        "A": 98,
        "B": 98,
        "C": 98,
        "D": 98,
    },

    21: {
        "A": 49,
        "B": 69,
        "C": 79,
        "D": 84,
    },

    22: {
        "A": 57,
        "B": 72,
        "C": 81,
        "D": 86,
    },

    23: {
        "A": 61,
        "B": 75,
        "C": 83,
        "D": 87,
    },

    24: {
        "A": 81,
        "B": 88,
        "C": 91,
        "D": 93,
    },

    31: {
        "A": 78,
        "B": 86,
        "C": 91,
        "D": 93,
    },

    41: {
        "A": 45,
        "B": 66,
        "C": 77,
        "D": 83,
    },

    42: {
        "A": 25,
        "B": 55,
        "C": 70,
        "D": 77,
    },

    43: {
        "A": 36,
        "B": 60,
        "C": 73,
        "D": 79,
    },

    52: {
        "A": 55,
        "B": 72,
        "C": 81,
        "D": 86,
    },

    71: {
        "A": 50,
        "B": 69,
        "C": 79,
        "D": 84,
    },

    81: {
        "A": 49,
        "B": 69,
        "C": 79,
        "D": 84,
    },

    82: {
        "A": 67,
        "B": 78,
        "C": 85,
        "D": 89,
    },

    90: {
        "A": 30,
        "B": 58,
        "C": 71,
        "D": 78,
    },

    95: {
        "A": 30,
        "B": 58,
        "C": 71,
        "D": 78,
    },
}


NLCD_NAMES = {
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
# HSG coding
# =========================================================

# Raster from Stage 3D-2C1:
#
# 0 = UNRATED
# 1 = A
# 2 = B
# 3 = C
# 4 = D
# 5 = A/D
# 6 = B/D
# 7 = C/D
# 255 = outside watershed


BASELINE_HSG = {
    0: "D",
    1: "A",
    2: "B",
    3: "C",
    4: "D",
    5: "D",
    6: "D",
    7: "D",
}


DRAINED_HSG = {
    0: "D",
    1: "A",
    2: "B",
    3: "C",
    4: "D",
    5: "A",
    6: "B",
    7: "C",
}


# =========================================================
# Load rasters
# =========================================================

print("=" * 78)
print("Stage 3D-2D1: Physical Curve Number derivation")
print("=" * 78)


with rasterio.open(
    landcover_file
) as lc_src:

    landcover = lc_src.read(
        1
    )

    lc_profile = (
        lc_src.profile.copy()
    )

    lc_transform = (
        lc_src.transform
    )

    lc_crs = (
        lc_src.crs
    )


with rasterio.open(
    hsg_file
) as hsg_src:

    hsg = hsg_src.read(
        1
    )

    hsg_transform = (
        hsg_src.transform
    )

    hsg_crs = (
        hsg_src.crs
    )


# =========================================================
# Alignment QC
# =========================================================

print()
print("RASTER ALIGNMENT")
print("-" * 78)

print(
    f"NLCD shape : "
    f"{landcover.shape}"
)

print(
    f"HSG shape  : "
    f"{hsg.shape}"
)

print(
    f"NLCD CRS   : "
    f"{lc_crs}"
)

print(
    f"HSG CRS    : "
    f"{hsg_crs}"
)


if (
    landcover.shape
    !=
    hsg.shape
):

    raise SystemExit(
        "ERROR: NLCD and HSG raster dimensions differ."
    )


if (
    lc_crs
    !=
    hsg_crs
):

    raise SystemExit(
        "ERROR: NLCD and HSG CRS differ."
    )


if (
    lc_transform
    !=
    hsg_transform
):

    raise SystemExit(
        "ERROR: NLCD and HSG grids are not aligned."
    )


print(
    "Raster alignment: PASS"
)


# =========================================================
# Watershed mask
# =========================================================

inside = (
    hsg != 255
)


total_pixels = int(
    inside.sum()
)


pixel_area_m2 = (
    abs(
        lc_transform.a
    )
    *
    abs(
        lc_transform.e
    )
)


basin_area_km2 = (
    total_pixels
    * pixel_area_m2
    / 1_000_000
)


print()
print(
    f"Raster basin area : "
    f"{basin_area_km2:.2f} km²"
)


# =========================================================
# Validate NLCD classes
# =========================================================

observed_nlcd = set(
    np.unique(
        landcover[
            inside
        ]
    ).tolist()
)


unknown_nlcd = (
    observed_nlcd
    -
    set(
        CN_LOOKUP.keys()
    )
)


if unknown_nlcd:

    raise SystemExit(
        "ERROR: No CN lookup exists for "
        f"NLCD classes: {sorted(unknown_nlcd)}"
    )


# =========================================================
# Function to build CN raster
# =========================================================

def create_cn_raster(
    hsg_rule,
):

    cn = np.full(
        hsg.shape,
        255,
        dtype=np.uint8,
    )


    for hsg_code, hsg_name in hsg_rule.items():

        soil_mask = (
            inside
            &
            (
                hsg
                ==
                hsg_code
            )
        )


        if not np.any(
            soil_mask
        ):
            continue


        for nlcd_code, values in CN_LOOKUP.items():

            mask = (
                soil_mask
                &
                (
                    landcover
                    ==
                    nlcd_code
                )
            )


            if np.any(
                mask
            ):

                cn[
                    mask
                ] = (
                    values[
                        hsg_name
                    ]
                )


    return cn


# =========================================================
# Baseline CN raster
# =========================================================

baseline_cn = create_cn_raster(
    BASELINE_HSG
)


drained_cn = create_cn_raster(
    DRAINED_HSG
)


# =========================================================
# Ensure every watershed cell received CN
# =========================================================

baseline_missing = (
    inside
    &
    (
        baseline_cn
        ==
        255
    )
)


drained_missing = (
    inside
    &
    (
        drained_cn
        ==
        255
    )
)


if np.any(
    baseline_missing
):

    raise SystemExit(
        "ERROR: Some watershed pixels "
        "did not receive baseline CN."
    )


if np.any(
    drained_missing
):

    raise SystemExit(
        "ERROR: Some watershed pixels "
        "did not receive drained-dual CN."
    )


# =========================================================
# Composite CN
# =========================================================

baseline_composite_cn = float(
    baseline_cn[
        inside
    ]
    .mean()
)


drained_composite_cn = float(
    drained_cn[
        inside
    ]
    .mean()
)


difference_cn = (
    drained_composite_cn
    -
    baseline_composite_cn
)


print()
print("=" * 78)
print("COMPOSITE CURVE NUMBER")
print("=" * 78)

print(
    f"Baseline CN "
    f"(dual + unrated -> D) : "
    f"{baseline_composite_cn:.2f}"
)

print(
    f"Drained-dual CN            : "
    f"{drained_composite_cn:.2f}"
)

print(
    f"Difference                  : "
    f"{difference_cn:+.2f} CN"
)


# =========================================================
# Initial retention / abstraction
# =========================================================

def cn_to_retention_mm(
    cn,
):

    return (
        25400.0
        / cn
        -
        254.0
    )


baseline_S_mm = (
    cn_to_retention_mm(
        baseline_composite_cn
    )
)


baseline_Ia_mm = (
    0.20
    * baseline_S_mm
)


drained_S_mm = (
    cn_to_retention_mm(
        drained_composite_cn
    )
)


drained_Ia_mm = (
    0.20
    * drained_S_mm
)


print()
print("=" * 78)
print("INITIAL SCS-CN PARAMETERS")
print("=" * 78)

print(
    f"Baseline retention S : "
    f"{baseline_S_mm:.2f} mm"
)

print(
    f"Baseline Ia = 0.2S   : "
    f"{baseline_Ia_mm:.2f} mm"
)

print()
print(
    f"Drained retention S  : "
    f"{drained_S_mm:.2f} mm"
)

print(
    f"Drained Ia = 0.2S    : "
    f"{drained_Ia_mm:.2f} mm"
)


# =========================================================
# Build contribution table
# =========================================================

records = []


for hsg_code, baseline_hsg_name in BASELINE_HSG.items():

    hsg_mask = (
        inside
        &
        (
            hsg
            ==
            hsg_code
        )
    )


    if not np.any(
        hsg_mask
    ):
        continue


    nlcd_values, counts = np.unique(
        landcover[
            hsg_mask
        ],
        return_counts=True,
    )


    for nlcd_code, count in zip(
        nlcd_values,
        counts,
    ):

        nlcd_code = int(
            nlcd_code
        )

        count = int(
            count
        )


        cn_value = (
            CN_LOOKUP[
                nlcd_code
            ][
                baseline_hsg_name
            ]
        )


        area_km2 = (
            count
            * pixel_area_m2
            / 1_000_000
        )


        records.append({

            "hsg_raster_code":
                hsg_code,

            "baseline_hsg":
                baseline_hsg_name,

            "nlcd_code":
                nlcd_code,

            "nlcd_class":
                NLCD_NAMES.get(
                    nlcd_code,
                    str(
                        nlcd_code
                    ),
                ),

            "curve_number":
                cn_value,

            "pixels":
                count,

            "area_km2":
                area_km2,

            "percent_basin":
                (
                    count
                    / total_pixels
                    * 100
                ),

            "weighted_cn_contribution":
                (
                    cn_value
                    * count
                    / total_pixels
                ),
        })


contributions = (
    pd.DataFrame(
        records
    )
    .sort_values(
        "area_km2",
        ascending=False,
    )
    .reset_index(
        drop=True
    )
)


contributions.to_csv(
    contribution_file,
    index=False,
)


# =========================================================
# Save rasters
# =========================================================

profile = (
    lc_profile.copy()
)


profile.update(
    {
        "driver":
            "GTiff",

        "dtype":
            "uint8",

        "count":
            1,

        "nodata":
            255,

        "compress":
            "deflate",
    }
)


with rasterio.open(
    baseline_cn_file,
    "w",
    **profile,
) as dst:

    dst.write(
        baseline_cn,
        1,
    )


    dst.update_tags(

        METHOD=(
            "HEC-HMS NLCD-HSG CN lookup"
        ),

        DUAL_HSG=(
            "treated as D"
        ),

        UNRATED_HSG=(
            "treated as D"
        ),

        COMPOSITE_CN=(
            f"{baseline_composite_cn:.4f}"
        ),
    )


with rasterio.open(
    drained_cn_file,
    "w",
    **profile,
) as dst:

    dst.write(
        drained_cn,
        1,
    )


    dst.update_tags(

        METHOD=(
            "HEC-HMS NLCD-HSG CN lookup"
        ),

        DUAL_HSG=(
            "treated as first/drained group"
        ),

        UNRATED_HSG=(
            "treated as D"
        ),

        COMPOSITE_CN=(
            f"{drained_composite_cn:.4f}"
        ),
    )


# =========================================================
# HEC-HMS initial parameter package
# =========================================================

parameter_summary = {

    "station":
        f"USGS-{station_id}",

    "loss_method":
        "SCS Curve Number",

    "curve_number": {

        "baseline":
            baseline_composite_cn,

        "drained_dual_scenario":
            drained_composite_cn,

        "baseline_assumption":
            (
                "A/D, B/D and C/D treated as D; "
                "unrated HSG treated as D"
            ),

        "alternative_assumption":
            (
                "A/D->A, B/D->B, C/D->C; "
                "unrated HSG remains D"
            ),
    },

    "potential_maximum_retention_mm": {

        "baseline":
            baseline_S_mm,

        "drained_dual":
            drained_S_mm,
    },

    "initial_abstraction_mm": {

        "baseline_0_2S":
            baseline_Ia_mm,

        "drained_dual_0_2S":
            drained_Ia_mm,

        "hec_hms_setting":
            (
                "leave blank initially and allow "
                "HEC-HMS to use Ia = 0.2S"
            ),
    },

    "directly_connected_impervious_percent":
        0.0,

    "impervious_reason":
        (
            "Developed NLCD classes use composite "
            "urban CN lookup values; separate DCIA "
            "would risk double counting imperviousness."
        ),

    "nlcd_year":
        2021,

    "scientific_status":
        (
            "physical initial CN derived; "
            "not calibrated"
        ),
}


with open(
    parameter_file,
    "w",
    encoding="utf-8",
) as file:

    json.dump(
        parameter_summary,
        file,
        indent=2,
    )


# =========================================================
# Final summary
# =========================================================

print()
print("=" * 78)
print("FILES CREATED")
print("=" * 78)

print(
    baseline_cn_file
)

print(
    drained_cn_file
)

print(
    contribution_file
)

print(
    parameter_file
)


print()
print("=" * 78)
print("Stage 3D-2D1 COMPLETE")
print("=" * 78)

print()
print(
    f"Initial baseline HEC-HMS CN : "
    f"{baseline_composite_cn:.2f}"
)

print(
    "Initial HEC-HMS DCIA       : "
    "0.00%"
)

print(
    "Curve Number has NOT been calibrated."
)
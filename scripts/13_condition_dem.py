"""
Stage 3D-2A2
Hydrologically condition the exported USGS 3DEP DEM.

Objectives
----------
1. Validate the locally downloaded raw DEM.
2. Preserve the raw DEM unchanged.
3. Hydrologically condition the DEM using
   WhiteboxTools BreachDepressionsLeastCost.
4. Generate D8 flow direction.
5. Generate D8 flow accumulation.
6. Quantify how much the conditioning changed the DEM.
7. Produce QC metadata and a flow-accumulation diagnostic map.

This stage does NOT:
- alter the accepted NLDI catchment;
- snap the USGS outlet;
- delineate a replacement watershed;
- calculate longest flow path;
- calculate Clark Tc.
"""
from rasterio.warp import reproject
from rasterio.transform import from_bounds
from pathlib import Path
import json
import math


import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.enums import Resampling
import whitebox
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

with open(CONFIG_FILE, "r", encoding="utf-8") as file:
    config = yaml.safe_load(file)


station_id = config["catchment"]["usgs_station"]

ANALYSIS_CRS = config["terrain"]["analysis_crs"]

BREACH_DISTANCE_CELLS = int(
    config["conditioning"][
        "breach_search_distance_cells"
    ]
)

FILL_REMAINING = bool(
    config["conditioning"][
        "fill_remaining_depressions"
    ]
)


# =========================================================
# Paths
# =========================================================

raw_dem = (
    PROJECT_ROOT
    / config["paths"]["raw_dem"]
    / f"USGS_{station_id}_3DEP_10m_EPSG5070.tif"
)

interim_dir = (
    PROJECT_ROOT
    / config["paths"]["interim_dem"]
)

results_dir = (
    PROJECT_ROOT
    / "results"
    / "tables"
)

figures_dir = (
    PROJECT_ROOT
    / "figures"
    / "diagnostics"
)

interim_dir.mkdir(
    parents=True,
    exist_ok=True,
)

results_dir.mkdir(
    parents=True,
    exist_ok=True,
)

figures_dir.mkdir(
    parents=True,
    exist_ok=True,
)


conditioned_dem = (
    interim_dir
    / f"USGS_{station_id}_3DEP_10m_conditioned.tif"
)

d8_pointer = (
    interim_dir
    / f"USGS_{station_id}_D8_pointer.tif"
)

flow_accum = (
    interim_dir
    / f"USGS_{station_id}_D8_flow_accum_cells.tif"
)


# =========================================================
# Initial DEM validation
# =========================================================

print("=" * 78)
print("Stage 3D-2A2: Hydrologic DEM conditioning")
print("=" * 78)

print(f"Raw DEM       : {raw_dem}")
print(f"Expected CRS  : {ANALYSIS_CRS}")
print()


if not raw_dem.exists():

    raise SystemExit(
        "ERROR: Raw DEM not found.\n"
        "Download the completed Earth Engine export and place it at:\n"
        f"{raw_dem}"
    )


with rasterio.open(raw_dem) as src:

    raw_crs = src.crs

    transform = src.transform

    pixel_width = abs(
        transform.a
    )

    pixel_height = abs(
        transform.e
    )

    width = src.width
    height = src.height
    nodata = src.nodata
    bounds = src.bounds

    raw_min = math.inf
    raw_max = -math.inf
    valid_pixels = 0


    for _, window in src.block_windows(1):

        arr = src.read(
            1,
            window=window,
            masked=True,
        )

        if arr.count() == 0:
            continue

        raw_min = min(
            raw_min,
            float(arr.min()),
        )

        raw_max = max(
            raw_max,
            float(arr.max()),
        )

        valid_pixels += int(
            arr.count()
        )


print("=" * 78)
print("RAW DEM CHECK")
print("=" * 78)

print(f"CRS             : {raw_crs}")
print(
    f"Raster size     : "
    f"{width:,} columns x {height:,} rows"
)

print(
    f"Pixel size      : "
    f"{pixel_width:.3f} m x {pixel_height:.3f} m"
)

print(f"NoData          : {nodata}")

print(
    f"Valid pixels    : "
    f"{valid_pixels:,}"
)

print(
    f"Elevation range : "
    f"{raw_min:.2f} to {raw_max:.2f} m"
)


if raw_crs is None:

    raise SystemExit(
        "ERROR: Raw DEM has no CRS."
    )


if raw_crs.to_string() != ANALYSIS_CRS:

    raise SystemExit(
        f"ERROR: Expected {ANALYSIS_CRS}, "
        f"but DEM CRS is {raw_crs}."
    )


if not (
    9.0 <= pixel_width <= 11.0
    and
    9.0 <= pixel_height <= 11.0
):

    raise SystemExit(
        "ERROR: DEM pixel resolution is not approximately 10 m."
    )


print("Raw DEM validation: PASS")


# =========================================================
# WhiteboxTools
# =========================================================

print()
print("=" * 78)
print("WHITEBOXTOOLS")
print("=" * 78)


wbt = whitebox.WhiteboxTools()

wbt.verbose = True


print(
    f"WhiteboxTools version: "
    f"{wbt.version()}"
)


# =========================================================
# Hydrologic conditioning
# =========================================================

print()
print("=" * 78)
print("HYDROLOGIC CONDITIONING")
print("=" * 78)

print(
    "Method: BreachDepressionsLeastCost"
)

print(
    f"Maximum search distance: "
    f"{BREACH_DISTANCE_CELLS} cells "
    f"(~{BREACH_DISTANCE_CELLS * pixel_width:.0f} m)"
)

print(
    f"Fill remaining depressions: "
    f"{FILL_REMAINING}"
)


if conditioned_dem.exists():

    print(
        "Conditioned DEM already exists; "
        "reusing existing output."
    )

else:

    wbt.breach_depressions_least_cost(
        str(raw_dem),
        str(conditioned_dem),
        dist=BREACH_DISTANCE_CELLS,
        min_dist=True,
        fill=FILL_REMAINING,
    )


if not conditioned_dem.exists():

    raise SystemExit(
        "ERROR: Conditioned DEM was not created."
    )


# =========================================================
# D8 flow pointer
# =========================================================

print()
print("=" * 78)
print("D8 FLOW DIRECTION")
print("=" * 78)


if d8_pointer.exists():

    print(
        "D8 pointer already exists; "
        "reusing existing output."
    )

else:

    wbt.d8_pointer(
        str(conditioned_dem),
        str(d8_pointer),
        esri_pntr=False,
    )

if not d8_pointer.exists():

    raise SystemExit(
        "ERROR: D8 pointer raster was not created."
    )


# =========================================================
# D8 flow accumulation
# =========================================================

print()
print("=" * 78)
print("D8 FLOW ACCUMULATION")
print("=" * 78)


if flow_accum.exists():

    print(
        "D8 accumulation already exists; "
        "reusing existing output."
    )

else:

    wbt.d8_flow_accumulation(
        str(d8_pointer),
        str(flow_accum),
        out_type="cells",
        log=False,
        clip=False,
        pntr=True,
        esri_pntr=False,
    )

if not flow_accum.exists():

    raise SystemExit(
        "ERROR: D8 flow accumulation raster was not created."
    )

# =========================================================
# Conditioning-change QC
# =========================================================

print()
print("=" * 78)
print("DEM CONDITIONING QC")
print("=" * 78)


modified_pixels = 0
compared_pixels = 0

sum_abs_change = 0.0

max_raise = -math.inf
max_lower = math.inf


with (
    rasterio.open(raw_dem) as raw_src,
    rasterio.open(conditioned_dem) as cond_src,
):

    if (
        raw_src.width != cond_src.width
        or
        raw_src.height != cond_src.height
    ):

        raise SystemExit(
            "ERROR: Conditioned DEM dimensions changed."
        )


    for _, window in raw_src.block_windows(1):

        raw = raw_src.read(
            1,
            window=window,
            masked=True,
        )

        conditioned = cond_src.read(
            1,
            window=window,
            masked=True,
        )


        valid = (
            ~np.ma.getmaskarray(raw)
            &
            ~np.ma.getmaskarray(conditioned)
        )


        if not np.any(valid):
            continue


        difference = (
            np.asarray(
                conditioned,
                dtype=np.float64,
            )[valid]
            -
            np.asarray(
                raw,
                dtype=np.float64,
            )[valid]
        )


        compared_pixels += int(
            difference.size
        )


        changed = (
            np.abs(difference)
            > 1e-6
        )


        modified_pixels += int(
            changed.sum()
        )


        sum_abs_change += float(
            np.abs(difference).sum()
        )


        max_raise = max(
            max_raise,
            float(
                difference.max()
            ),
        )


        max_lower = min(
            max_lower,
            float(
                difference.min()
            ),
        )


modified_percent = (
    modified_pixels
    / compared_pixels
    * 100
)


mean_abs_change = (
    sum_abs_change
    / compared_pixels
)


print(
    f"Compared pixels      : "
    f"{compared_pixels:,}"
)

print(
    f"Modified pixels      : "
    f"{modified_pixels:,}"
)

print(
    f"Modified percentage  : "
    f"{modified_percent:.4f}%"
)

print(
    f"Mean absolute change : "
    f"{mean_abs_change:.4f} m"
)

print(
    f"Maximum raising      : "
    f"{max_raise:+.3f} m"
)

print(
    f"Maximum lowering     : "
    f"{max_lower:+.3f} m"
)


# =========================================================
# Flow accumulation QC
# =========================================================

max_accumulation = -math.inf
positive_accumulation = 0


with rasterio.open(
    flow_accum
) as accum_src:

    for _, window in accum_src.block_windows(1):

        accum = accum_src.read(
            1,
            window=window,
            masked=True,
        )

        if accum.count() == 0:
            continue


        max_accumulation = max(
            max_accumulation,
            float(
                accum.max()
            ),
        )


        positive_accumulation += int(
            (
                np.asarray(accum.filled(0))
                > 1
            ).sum()
        )


max_contributing_area_km2 = (
    max_accumulation
    * pixel_width
    * pixel_height
    / 1_000_000
)


print()
print("=" * 78)
print("FLOW ACCUMULATION QC")
print("=" * 78)

print(
    f"Maximum accumulated cells : "
    f"{max_accumulation:,.0f}"
)

print(
    f"Equivalent contributing area "
    f"at max cell: "
    f"{max_contributing_area_km2:.2f} km²"
)


# =========================================================
# Diagnostic flow-accumulation image
# =========================================================

# =========================================================
# Diagnostic flow-accumulation image
# =========================================================

with rasterio.open(flow_accum) as src:

    target_width = min(
        src.width,
        1800,
    )

    scale_factor = (
        src.width
        / target_width
    )

    target_height = max(
        1,
        int(
            src.height
            / scale_factor
        ),
    )


    # Reduced-resolution transform covering exactly
    # the same raster extent.
    display_transform = from_bounds(
        src.bounds.left,
        src.bounds.bottom,
        src.bounds.right,
        src.bounds.top,
        target_width,
        target_height,
    )


    # Float array is sufficient for display.
    display = np.zeros(
        (
            target_height,
            target_width,
        ),
        dtype=np.float32,
    )


    # Resampling.max is supported as a warp operation.
    # This is preferable for flow accumulation because
    # high-accumulation stream cells remain visible when
    # reducing the raster for plotting.
    reproject(
        source=rasterio.band(
            src,
            1,
        ),

        destination=display,

        src_transform=src.transform,

        src_crs=src.crs,

        src_nodata=src.nodata,

        dst_transform=display_transform,

        dst_crs=src.crs,

        dst_nodata=0,

        resampling=Resampling.max,
    )


display_array = np.log10(
    np.maximum(
        display,
        1,
    )
)

fig, ax = plt.subplots(
    figsize=(10, 8)
)

image = ax.imshow(
    display_array,
)

ax.set_title(
    "USGS 02361000 — D8 Flow Accumulation (log10 cells)"
)

ax.set_xlabel(
    "Raster column"
)

ax.set_ylabel(
    "Raster row"
)

fig.colorbar(
    image,
    ax=ax,
    label="log10 accumulated cells",
)

plt.tight_layout()


figure_file = (
    figures_dir
    / (
        f"USGS_{station_id}_"
        "D8_flow_accumulation_QC.png"
    )
)


plt.savefig(
    figure_file,
    dpi=250,
    bbox_inches="tight",
)

plt.close()


# =========================================================
# QC summary
# =========================================================

summary = {

    "station":
        f"USGS-{station_id}",

    "raw_dem":
        str(raw_dem),

    "raw_dem_crs":
        str(raw_crs),

    "pixel_width_m":
        pixel_width,

    "pixel_height_m":
        pixel_height,

    "raw_elevation_min_m":
        raw_min,

    "raw_elevation_max_m":
        raw_max,

    "conditioning": {

        "method":
            "WhiteboxTools BreachDepressionsLeastCost",

        "breach_search_distance_cells":
            BREACH_DISTANCE_CELLS,

        "breach_search_distance_m":
            BREACH_DISTANCE_CELLS
            * pixel_width,

        "fill_remaining_depressions":
            FILL_REMAINING,

        "modified_pixels":
            modified_pixels,

        "modified_percent":
            modified_percent,

        "mean_absolute_change_m":
            mean_abs_change,

        "maximum_raise_m":
            max_raise,

        "maximum_lower_m":
            max_lower,
    },

    "flow_direction":
        "D8",

    "flow_accumulation_unit":
        "cells",

    "maximum_accumulated_cells":
        max_accumulation,

    "maximum_equivalent_contributing_area_km2":
        max_contributing_area_km2,

    "scientific_status":
        (
            "hydrologic conditioning and D8 "
            "flow-routing surfaces generated; "
            "outlet alignment pending"
        ),
}


summary_file = (
    results_dir
    / (
        f"USGS_{station_id}_"
        "DEM_conditioning_qc.json"
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
# Final output
# =========================================================

print()
print("=" * 78)
print("FILES CREATED")
print("=" * 78)

print()
print("Conditioned DEM:")
print(conditioned_dem)

print()
print("D8 pointer:")
print(d8_pointer)

print()
print("D8 accumulation:")
print(flow_accum)

print()
print("QC summary:")
print(summary_file)

print()
print("Diagnostic figure:")
print(figure_file)


print()
print("=" * 78)
print("Stage 3D-2A2 COMPLETE")
print("=" * 78)

print()
print(
    "Clark Tc has NOT been estimated."
)

print(
    "The USGS outlet has NOT yet been snapped "
    "to the DEM-derived drainage network."
)

print(
    "The longest hydraulic flow path has NOT "
    "yet been calculated."
)
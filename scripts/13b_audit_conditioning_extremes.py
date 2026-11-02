"""
Stage 3D-2A2b
Audit extreme elevation changes introduced during
hydrologic DEM conditioning.

Purpose
-------
Determine whether the extreme -36 m breach:
- occurs inside the accepted watershed,
- affects many pixels or only a tiny localized feature,
- represents an isolated artifact or an extensive trench.

This stage does NOT modify any raster.
"""

from pathlib import Path
import csv

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.features import geometry_mask
import yaml


# =========================================================
# Configuration
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CONFIG_FILE = PROJECT_ROOT / "config" / "project_config.yaml"

with open(CONFIG_FILE, "r", encoding="utf-8") as file:
    config = yaml.safe_load(file)

station_id = config["catchment"]["usgs_station"]


# =========================================================
# Paths
# =========================================================

raw_dem = (
    PROJECT_ROOT
    / config["paths"]["raw_dem"]
    / f"USGS_{station_id}_3DEP_10m_EPSG5070.tif"
)

conditioned_dem = (
    PROJECT_ROOT
    / config["paths"]["interim_dem"]
    / f"USGS_{station_id}_3DEP_10m_conditioned.tif"
)

catchment_file = (
    PROJECT_ROOT
    / config["paths"]["interim_catchment"]
    / f"USGS_{station_id}_NLDI_basin_qc.gpkg"
)

results_dir = PROJECT_ROOT / "results" / "tables"
figures_dir = PROJECT_ROOT / "figures" / "diagnostics"

results_dir.mkdir(parents=True, exist_ok=True)
figures_dir.mkdir(parents=True, exist_ok=True)


# =========================================================
# Load basin
# =========================================================

catchment = gpd.read_file(catchment_file)


with rasterio.open(raw_dem) as src:

    raster_crs = src.crs
    transform = src.transform
    shape = (src.height, src.width)

    if catchment.crs != raster_crs:
        catchment = catchment.to_crs(raster_crs)

    basin_geoms = [
        geom.__geo_interface__
        for geom in catchment.geometry
    ]


    basin_mask = geometry_mask(
        basin_geoms,
        out_shape=shape,
        transform=transform,
        invert=True,
    )


# =========================================================
# Threshold counters
# =========================================================

thresholds = [
    0.01,
    0.10,
    0.50,
    1.0,
    5.0,
    10.0,
    20.0,
    30.0,
]

counts_all = {t: 0 for t in thresholds}
counts_basin = {t: 0 for t in thresholds}


minimum_difference = np.inf
maximum_difference = -np.inf

minimum_location = None
maximum_location = None


# Keep largest absolute changes
top_changes = []


# =========================================================
# Process raster by blocks
# =========================================================

with (
    rasterio.open(raw_dem) as raw_src,
    rasterio.open(conditioned_dem) as cond_src,
):

    for _, window in raw_src.block_windows(1):

        raw = raw_src.read(
            1,
            window=window,
            masked=True,
        )

        cond = cond_src.read(
            1,
            window=window,
            masked=True,
        )

        valid = (
            ~np.ma.getmaskarray(raw)
            &
            ~np.ma.getmaskarray(cond)
        )

        if not np.any(valid):
            continue


        raw_values = np.asarray(
            raw,
            dtype=np.float64,
        )

        cond_values = np.asarray(
            cond,
            dtype=np.float64,
        )

        diff = cond_values - raw_values


        rows, cols = np.where(valid)

        global_rows = rows + int(window.row_off)
        global_cols = cols + int(window.col_off)

        valid_diff = diff[valid]


        # Basin membership for the valid pixels
        inside = basin_mask[
            global_rows,
            global_cols,
        ]


        # -----------------------------------------
        # Threshold statistics
        # -----------------------------------------

        abs_diff = np.abs(valid_diff)

        for threshold in thresholds:

            counts_all[threshold] += int(
                np.sum(abs_diff >= threshold)
            )

            counts_basin[threshold] += int(
                np.sum(
                    (abs_diff >= threshold)
                    & inside
                )
            )


        # -----------------------------------------
        # Global min/max change
        # -----------------------------------------

        local_min_idx = np.argmin(valid_diff)
        local_max_idx = np.argmax(valid_diff)

        local_min = float(
            valid_diff[local_min_idx]
        )

        local_max = float(
            valid_diff[local_max_idx]
        )


        if local_min < minimum_difference:

            minimum_difference = local_min

            r = int(
                global_rows[local_min_idx]
            )

            c = int(
                global_cols[local_min_idx]
            )

            x, y = rasterio.transform.xy(
                transform,
                r,
                c,
                offset="center",
            )

            minimum_location = {
                "row": r,
                "col": c,
                "x": x,
                "y": y,
                "inside_basin": bool(
                    basin_mask[r, c]
                ),
                "raw_elevation_m": float(
                    raw_values[
                        rows[local_min_idx],
                        cols[local_min_idx],
                    ]
                ),
                "conditioned_elevation_m": float(
                    cond_values[
                        rows[local_min_idx],
                        cols[local_min_idx],
                    ]
                ),
            }


        if local_max > maximum_difference:

            maximum_difference = local_max

            r = int(
                global_rows[local_max_idx]
            )

            c = int(
                global_cols[local_max_idx]
            )

            x, y = rasterio.transform.xy(
                transform,
                r,
                c,
                offset="center",
            )

            maximum_location = {
                "row": r,
                "col": c,
                "x": x,
                "y": y,
                "inside_basin": bool(
                    basin_mask[r, c]
                ),
                "raw_elevation_m": float(
                    raw_values[
                        rows[local_max_idx],
                        cols[local_max_idx],
                    ]
                ),
                "conditioned_elevation_m": float(
                    cond_values[
                        rows[local_max_idx],
                        cols[local_max_idx],
                    ]
                ),
            }


        # -----------------------------------------
        # Keep candidate extreme pixels
        # -----------------------------------------

        candidate_indices = np.where(
            abs_diff >= 5.0
        )[0]

        for idx in candidate_indices:

            r = int(
                global_rows[idx]
            )

            c = int(
                global_cols[idx]
            )

            x, y = rasterio.transform.xy(
                transform,
                r,
                c,
                offset="center",
            )

            top_changes.append({
                "row": r,
                "col": c,
                "x": x,
                "y": y,
                "difference_m": float(
                    valid_diff[idx]
                ),
                "absolute_difference_m": float(
                    abs_diff[idx]
                ),
                "inside_basin": bool(
                    basin_mask[r, c]
                ),
            })


# =========================================================
# Sort top changes
# =========================================================

top_changes = sorted(
    top_changes,
    key=lambda item:
        item["absolute_difference_m"],
    reverse=True,
)


top_changes = top_changes[:100]


# =========================================================
# Terminal report
# =========================================================

print("=" * 78)
print("Stage 3D-2A2b: Conditioning extremes audit")
print("=" * 78)

print()

print("EXTREME VALUES")
print("-" * 78)

print(
    f"Maximum lowering : "
    f"{minimum_difference:.3f} m"
)

print(
    f"Inside basin     : "
    f"{minimum_location['inside_basin']}"
)

print(
    f"Raw elevation    : "
    f"{minimum_location['raw_elevation_m']:.3f} m"
)

print(
    f"Conditioned elev.: "
    f"{minimum_location['conditioned_elevation_m']:.3f} m"
)

print(
    f"Coordinate       : "
    f"{minimum_location['x']:.2f}, "
    f"{minimum_location['y']:.2f}"
)


print()

print(
    f"Maximum raising  : "
    f"{maximum_difference:+.3f} m"
)

print(
    f"Inside basin     : "
    f"{maximum_location['inside_basin']}"
)


print()
print("CHANGE THRESHOLDS")
print("-" * 78)

for threshold in thresholds:

    print(
        f"|Δz| >= {threshold:5.2f} m : "
        f"{counts_all[threshold]:8,d} total | "
        f"{counts_basin[threshold]:8,d} inside basin"
    )


# =========================================================
# Save table
# =========================================================

csv_file = (
    results_dir
    / f"USGS_{station_id}_conditioning_extremes.csv"
)


with open(
    csv_file,
    "w",
    newline="",
    encoding="utf-8",
) as file:

    if top_changes:

        writer = csv.DictWriter(
            file,
            fieldnames=top_changes[0].keys(),
        )

        writer.writeheader()
        writer.writerows(top_changes)


# =========================================================
# Create local diagnostic around deepest breach
# =========================================================

row = minimum_location["row"]
col = minimum_location["col"]

half_window = 100


with (
    rasterio.open(raw_dem) as raw_src,
    rasterio.open(conditioned_dem) as cond_src,
):

    row_start = max(
        0,
        row - half_window,
    )

    row_stop = min(
        raw_src.height,
        row + half_window + 1,
    )

    col_start = max(
        0,
        col - half_window,
    )

    col_stop = min(
        raw_src.width,
        col + half_window + 1,
    )


    window = rasterio.windows.Window(
        col_start,
        row_start,
        col_stop - col_start,
        row_stop - row_start,
    )


    raw_local = raw_src.read(
        1,
        window=window,
        masked=True,
    )

    cond_local = cond_src.read(
        1,
        window=window,
        masked=True,
    )


difference_local = (
    cond_local.astype(np.float64)
    -
    raw_local.astype(np.float64)
)


# =========================================================
# Plot three separate figures
# =========================================================

raw_figure = (
    figures_dir
    / f"USGS_{station_id}_deepest_breach_raw.png"
)

plt.figure(figsize=(8, 7))

plt.imshow(
    raw_local,
)

plt.title(
    "Raw 3DEP DEM around deepest conditioning change"
)

plt.colorbar(
    label="Elevation (m)"
)

plt.tight_layout()

plt.savefig(
    raw_figure,
    dpi=250,
    bbox_inches="tight",
)

plt.close()


conditioned_figure = (
    figures_dir
    / f"USGS_{station_id}_deepest_breach_conditioned.png"
)

plt.figure(figsize=(8, 7))

plt.imshow(
    cond_local,
)

plt.title(
    "Conditioned DEM around deepest conditioning change"
)

plt.colorbar(
    label="Elevation (m)"
)

plt.tight_layout()

plt.savefig(
    conditioned_figure,
    dpi=250,
    bbox_inches="tight",
)

plt.close()


difference_figure = (
    figures_dir
    / f"USGS_{station_id}_deepest_breach_difference.png"
)

plt.figure(figsize=(8, 7))

plt.imshow(
    difference_local,
)

plt.title(
    "Conditioning elevation difference around deepest breach"
)

plt.colorbar(
    label="Conditioned - raw elevation (m)"
)

plt.tight_layout()

plt.savefig(
    difference_figure,
    dpi=250,
    bbox_inches="tight",
)

plt.close()


print()
print("=" * 78)
print("FILES CREATED")
print("=" * 78)

print(csv_file)
print(raw_figure)
print(conditioned_figure)
print(difference_figure)

print()
print("=" * 78)
print("Stage 3D-2A2b COMPLETE")
print("=" * 78)
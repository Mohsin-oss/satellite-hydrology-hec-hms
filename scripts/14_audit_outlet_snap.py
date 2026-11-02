"""
Stage 3D-2A3
Audit potential DEM-derived outlet locations around
USGS station 02361000.

Purpose
-------
1. Project the official USGS station coordinate to EPSG:5070.
2. Inspect D8 flow accumulation at the original gauge location.
3. Search multiple radii around the gauge.
4. For each radius, locate the highest-flow-accumulation cell.
5. Compare its contributing area against:
   - official USGS drainage area;
   - accepted NLDI watershed area.
6. Create a diagnostic outlet-area map.

IMPORTANT
---------
This stage does NOT:
- choose the final outlet automatically;
- alter the accepted watershed;
- calculate a longest flow path;
- estimate Clark Tc.

The purpose is diagnostic comparison before locking the outlet.
"""

from pathlib import Path
import json
import math

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import Window
from pyproj import Transformer
from shapely.geometry import Point
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

gauge_lat = float(
    config["outlet"]["latitude_wgs84"]
)

gauge_lon = float(
    config["outlet"]["longitude_wgs84"]
)

official_area_mi2 = float(
    config["outlet"]["official_drainage_area_mi2"]
)

snap_radii = [
    float(value)
    for value
    in config["outlet"]["snap_test_radii_m"]
]


MI2_TO_KM2 = 2.589988110336

official_area_km2 = (
    official_area_mi2
    * MI2_TO_KM2
)


# =========================================================
# Paths
# =========================================================

flow_accum_file = (
    PROJECT_ROOT
    / config["paths"]["interim_dem"]
    / f"USGS_{station_id}_D8_flow_accum_cells.tif"
)

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

figure_dir = (
    PROJECT_ROOT
    / "figures"
    / "diagnostics"
)

interim_dir = (
    PROJECT_ROOT
    / config["paths"]["interim_dem"]
)

results_dir.mkdir(
    parents=True,
    exist_ok=True,
)

figure_dir.mkdir(
    parents=True,
    exist_ok=True,
)

interim_dir.mkdir(
    parents=True,
    exist_ok=True,
)


# =========================================================
# Validate inputs
# =========================================================

print("=" * 78)
print("Stage 3D-2A3: USGS outlet candidate audit")
print("=" * 78)


for required_file in [
    flow_accum_file,
    catchment_file,
]:

    if not required_file.exists():

        raise SystemExit(
            f"ERROR: Required file not found:\n"
            f"{required_file}"
        )


# =========================================================
# Flow-accumulation raster information
# =========================================================

with rasterio.open(
    flow_accum_file
) as src:

    raster_crs = src.crs

    transform = src.transform

    width = src.width
    height = src.height

    pixel_width = abs(
        transform.a
    )

    pixel_height = abs(
        transform.e
    )

    nodata = src.nodata


if raster_crs is None:

    raise SystemExit(
        "ERROR: Flow accumulation raster has no CRS."
    )


if not math.isclose(
    pixel_width,
    pixel_height,
    rel_tol=0.001,
):

    raise SystemExit(
        "ERROR: Raster cells are not approximately square."
    )


pixel_area_m2 = (
    pixel_width
    * pixel_height
)


print()
print("FLOW ACCUMULATION RASTER")
print("-" * 78)

print(
    f"CRS            : {raster_crs}"
)

print(
    f"Pixel size     : "
    f"{pixel_width:.3f} m"
)

print(
    f"Raster size    : "
    f"{width:,} x {height:,}"
)


# =========================================================
# Load accepted NLDI catchment
# =========================================================

catchment = gpd.read_file(
    catchment_file
)


if catchment.crs is None:

    raise SystemExit(
        "ERROR: Catchment CRS missing."
    )


catchment_projected = (
    catchment
    .to_crs(
        raster_crs
    )
)


catchment_geometry = (
    catchment_projected
    .geometry
    .union_all()
)


nldi_area_km2 = (
    catchment_geometry.area
    / 1_000_000
)


# =========================================================
# Project USGS gauge coordinate
# =========================================================

transformer = Transformer.from_crs(
    "EPSG:4326",
    raster_crs,
    always_xy=True,
)


gauge_x, gauge_y = transformer.transform(
    gauge_lon,
    gauge_lat,
)


print()
print("USGS GAUGE")
print("-" * 78)

print(
    f"WGS84 longitude : {gauge_lon:.12f}"
)

print(
    f"WGS84 latitude  : {gauge_lat:.12f}"
)

print(
    f"Projected X     : {gauge_x:.2f} m"
)

print(
    f"Projected Y     : {gauge_y:.2f} m"
)

print(
    f"Official area   : "
    f"{official_area_km2:.2f} km²"
)

print(
    f"NLDI polygon    : "
    f"{nldi_area_km2:.2f} km²"
)


# =========================================================
# Utility
# =========================================================

def accumulation_to_area_km2(
    accumulated_cells
):

    return (
        accumulated_cells
        * pixel_area_m2
        / 1_000_000
    )


# =========================================================
# Accumulation at original gauge cell
# =========================================================

with rasterio.open(
    flow_accum_file
) as src:

    gauge_row, gauge_col = src.index(
        gauge_x,
        gauge_y,
    )


    if (
        gauge_row < 0
        or gauge_col < 0
        or gauge_row >= src.height
        or gauge_col >= src.width
    ):

        raise SystemExit(
            "ERROR: Gauge lies outside flow-accumulation raster."
        )


    gauge_value = src.read(
        1,
        window=Window(
            gauge_col,
            gauge_row,
            1,
            1,
        ),
        masked=True,
    )[0, 0]


if np.ma.is_masked(
    gauge_value
):

    gauge_accumulation = np.nan
    gauge_area_km2 = np.nan

else:

    gauge_accumulation = float(
        gauge_value
    )

    gauge_area_km2 = (
        accumulation_to_area_km2(
            gauge_accumulation
        )
    )


print()
print("ORIGINAL GAUGE CELL")
print("-" * 78)

print(
    f"Raster row/col       : "
    f"{gauge_row}, {gauge_col}"
)

print(
    f"Accumulated cells    : "
    f"{gauge_accumulation:,.0f}"
)

print(
    f"Contributing area    : "
    f"{gauge_area_km2:.2f} km²"
)


# =========================================================
# Candidate search function
# =========================================================

def find_max_accumulation_within_radius(
    src,
    center_x,
    center_y,
    radius_m,
):

    pad_cells = int(
        math.ceil(
            radius_m
            / min(
                pixel_width,
                pixel_height,
            )
        )
    ) + 2


    center_row, center_col = src.index(
        center_x,
        center_y,
    )


    row_start = max(
        0,
        center_row - pad_cells,
    )

    row_stop = min(
        src.height,
        center_row + pad_cells + 1,
    )

    col_start = max(
        0,
        center_col - pad_cells,
    )

    col_stop = min(
        src.width,
        center_col + pad_cells + 1,
    )


    window = Window(
        col_start,
        row_start,
        col_stop - col_start,
        row_stop - row_start,
    )


    array = src.read(
        1,
        window=window,
        masked=True,
    )


    window_transform = (
        src.window_transform(
            window
        )
    )


    rows, cols = np.indices(
        array.shape
    )


    # North-up projected raster expected.
    xs = (
        window_transform.c
        +
        (
            cols + 0.5
        )
        * window_transform.a
    )

    ys = (
        window_transform.f
        +
        (
            rows + 0.5
        )
        * window_transform.e
    )


    distances = np.sqrt(
        (
            xs - center_x
        ) ** 2
        +
        (
            ys - center_y
        ) ** 2
    )


    valid = (
        ~np.ma.getmaskarray(
            array
        )
        &
        np.isfinite(
            np.asarray(
                array
            )
        )
        &
        (
            distances
            <= radius_m
        )
    )


    if not np.any(
        valid
    ):

        return None


    data = np.asarray(
        array,
        dtype=np.float64,
    )


    masked_values = np.where(
        valid,
        data,
        -np.inf,
    )


    local_index = np.unravel_index(
        np.argmax(
            masked_values
        ),
        masked_values.shape,
    )


    local_row = int(
        local_index[0]
    )

    local_col = int(
        local_index[1]
    )


    global_row = (
        int(row_start)
        + local_row
    )

    global_col = (
        int(col_start)
        + local_col
    )


    x = float(
        xs[
            local_row,
            local_col
        ]
    )

    y = float(
        ys[
            local_row,
            local_col
        ]
    )


    distance = float(
        distances[
            local_row,
            local_col
        ]
    )


    accumulation = float(
        data[
            local_row,
            local_col
        ]
    )


    area_km2 = (
        accumulation_to_area_km2(
            accumulation
        )
    )


    return {

        "radius_m":
            radius_m,

        "row":
            global_row,

        "col":
            global_col,

        "x":
            x,

        "y":
            y,

        "snap_distance_m":
            distance,

        "accumulated_cells":
            accumulation,

        "contributing_area_km2":
            area_km2,

        "difference_vs_usgs_km2":
            area_km2
            - official_area_km2,

        "difference_vs_usgs_percent":
            (
                area_km2
                - official_area_km2
            )
            / official_area_km2
            * 100,

        "difference_vs_nldi_km2":
            area_km2
            - nldi_area_km2,

        "difference_vs_nldi_percent":
            (
                area_km2
                - nldi_area_km2
            )
            / nldi_area_km2
            * 100,
    }


# =========================================================
# Search candidate outlets
# =========================================================

candidate_rows = []


with rasterio.open(
    flow_accum_file
) as src:

    for radius in snap_radii:

        candidate = (
            find_max_accumulation_within_radius(
                src,
                gauge_x,
                gauge_y,
                radius,
            )
        )


        if candidate is not None:

            candidate_rows.append(
                candidate
            )


candidates = pd.DataFrame(
    candidate_rows
)


if candidates.empty:

    raise SystemExit(
        "ERROR: No valid outlet candidates found."
    )


# =========================================================
# Candidate report
# =========================================================

print()
print("=" * 78)
print("OUTLET CANDIDATES")
print("=" * 78)

print()


print(
    candidates[
        [
            "radius_m",
            "snap_distance_m",
            "accumulated_cells",
            "contributing_area_km2",
            "difference_vs_usgs_percent",
            "difference_vs_nldi_percent",
        ]
    ]
    .to_string(
        index=False,
        formatters={
            "radius_m":
                "{:.0f}".format,

            "snap_distance_m":
                "{:.1f}".format,

            "accumulated_cells":
                "{:,.0f}".format,

            "contributing_area_km2":
                "{:.2f}".format,

            "difference_vs_usgs_percent":
                "{:+.3f}".format,

            "difference_vs_nldi_percent":
                "{:+.3f}".format,
        },
    )
)


# =========================================================
# Save candidate table
# =========================================================

candidate_file = (
    results_dir
    / (
        f"USGS_{station_id}_"
        "outlet_snap_candidates.csv"
    )
)


candidates.to_csv(
    candidate_file,
    index=False,
)


# =========================================================
# Save original gauge point
# =========================================================

gauge_gdf = gpd.GeoDataFrame(

    {
        "station": [
            f"USGS-{station_id}"
        ],

        "type": [
            "official_USGS_coordinate"
        ],
    },

    geometry=[
        Point(
            gauge_x,
            gauge_y,
        )
    ],

    crs=raster_crs,
)


gauge_file = (
    interim_dir
    / (
        f"USGS_{station_id}_"
        "official_gauge_point.gpkg"
    )
)


gauge_gdf.to_file(
    gauge_file,
    driver="GPKG",
)


# =========================================================
# Save candidate points
# =========================================================

candidate_gdf = gpd.GeoDataFrame(

    candidates.copy(),

    geometry=[
        Point(
            row["x"],
            row["y"],
        )
        for _, row
        in candidates.iterrows()
    ],

    crs=raster_crs,
)


candidate_points_file = (
    interim_dir
    / (
        f"USGS_{station_id}_"
        "outlet_snap_candidates.gpkg"
    )
)


candidate_gdf.to_file(
    candidate_points_file,
    driver="GPKG",
)


# =========================================================
# Diagnostic map
# =========================================================

plot_radius = (
    max(
        snap_radii
    )
    + 500
)


with rasterio.open(
    flow_accum_file
) as src:

    center_row, center_col = src.index(
        gauge_x,
        gauge_y,
    )

    plot_cells = int(
        math.ceil(
            plot_radius
            / pixel_width
        )
    )


    row_start = max(
        0,
        center_row - plot_cells,
    )

    row_stop = min(
        src.height,
        center_row + plot_cells + 1,
    )

    col_start = max(
        0,
        center_col - plot_cells,
    )

    col_stop = min(
        src.width,
        center_col + plot_cells + 1,
    )


    plot_window = Window(
        col_start,
        row_start,
        col_stop - col_start,
        row_stop - row_start,
    )


    plot_data = src.read(
        1,
        window=plot_window,
        masked=True,
    )


    plot_transform = (
        src.window_transform(
            plot_window
        )
    )


    left = (
        plot_transform.c
    )

    top = (
        plot_transform.f
    )

    right = (
        left
        +
        plot_transform.a
        * plot_data.shape[1]
    )

    bottom = (
        top
        +
        plot_transform.e
        * plot_data.shape[0]
    )


plot_array = np.log10(
    np.maximum(
        plot_data.filled(0),
        1,
    )
)


fig, ax = plt.subplots(
    figsize=(10, 9)
)


image = ax.imshow(

    plot_array,

    extent=[
        left,
        right,
        bottom,
        top,
    ],

    origin="upper",
)


catchment_projected.boundary.plot(
    ax=ax,
    linewidth=1.0,
)


ax.scatter(
    gauge_x,
    gauge_y,
    marker="x",
    s=90,
    label="Official USGS coordinate",
)


for _, row in candidates.iterrows():

    ax.scatter(
        row["x"],
        row["y"],
        s=35,
    )

    ax.annotate(
        f"{row['radius_m']:.0f} m",
        (
            row["x"],
            row["y"],
        ),
        xytext=(4, 4),
        textcoords="offset points",
        fontsize=8,
    )


ax.set_title(
    (
        "USGS 02361000 — outlet snapping audit\n"
        "D8 flow accumulation"
    )
)

ax.set_xlabel(
    "Easting (m, EPSG:5070)"
)

ax.set_ylabel(
    "Northing (m, EPSG:5070)"
)


fig.colorbar(
    image,
    ax=ax,
    label="log10 accumulated cells",
)


ax.legend()


plt.tight_layout()


figure_file = (
    figure_dir
    / (
        f"USGS_{station_id}_"
        "outlet_snap_audit.png"
    )
)


plt.savefig(
    figure_file,
    dpi=300,
    bbox_inches="tight",
)

plt.close()


# =========================================================
# Save metadata
# =========================================================

metadata = {

    "station":
        f"USGS-{station_id}",

    "official_coordinate_wgs84": {
        "longitude":
            gauge_lon,

        "latitude":
            gauge_lat,
    },

    "official_drainage_area_mi2":
        official_area_mi2,

    "official_drainage_area_km2":
        official_area_km2,

    "accepted_nldi_area_km2":
        nldi_area_km2,

    "gauge_cell_contributing_area_km2":
        gauge_area_km2,

    "snap_radii_tested_m":
        snap_radii,

    "scientific_status":
        (
            "candidate outlet audit only; "
            "no final snapped outlet selected"
        ),
}


metadata_file = (
    results_dir
    / (
        f"USGS_{station_id}_"
        "outlet_snap_audit.json"
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
print("=" * 78)
print("FILES CREATED")
print("=" * 78)

print(candidate_file)
print(candidate_points_file)
print(gauge_file)
print(metadata_file)
print(figure_file)

print()
print("=" * 78)
print("Stage 3D-2A3 AUDIT COMPLETE")
print("=" * 78)

print()
print(
    "No final outlet has been selected automatically."
)

print(
    "Longest flow path has NOT been calculated."
)

print(
    "Clark Tc has NOT been estimated."
)
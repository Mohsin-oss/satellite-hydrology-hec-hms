"""
Stage 3D-2A4
Lock the DEM outlet, delineate the watershed, and derive
the longest hydraulic flow path.

Objectives
----------
1. Select the locked 100 m outlet candidate.
2. Save a permanent snapped outlet point.
3. Delineate the D8 watershed from that outlet.
4. Compare its area with:
   - official USGS drainage area;
   - accepted NLDI polygon.
5. Quantify spatial overlap with the NLDI watershed.
6. Derive the longest D8 flow path.
7. Calculate flow-path length and slope diagnostics.
8. Calculate the 10-85% flow-path slope.

IMPORTANT
---------
This stage does NOT:
- change the accepted reference watershed;
- calculate Clark Tc;
- calculate Clark R;
- calibrate HEC-HMS.

The DEM watershed is a QC/terrain derivative.
The NLDI polygon remains the accepted catchment boundary.
"""

from pathlib import Path
import json
import math

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask
from shapely.geometry import Point
import whitebox
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

FINAL_RADIUS = float(
    config["outlet"]["final_snap_radius_m"]
)

official_area_mi2 = float(
    config["outlet"]["official_drainage_area_mi2"]
)

MI2_TO_KM2 = 2.589988110336

official_area_km2 = (
    official_area_mi2
    * MI2_TO_KM2
)


# =========================================================
# Input files
# =========================================================

conditioned_dem = (
    PROJECT_ROOT
    / config["paths"]["interim_dem"]
    / f"USGS_{station_id}_3DEP_10m_conditioned.tif"
)

d8_pointer = (
    PROJECT_ROOT
    / config["paths"]["interim_dem"]
    / f"USGS_{station_id}_D8_pointer.tif"
)

flow_accum = (
    PROJECT_ROOT
    / config["paths"]["interim_dem"]
    / f"USGS_{station_id}_D8_flow_accum_cells.tif"
)

candidate_file = (
    PROJECT_ROOT
    / "results"
    / "tables"
    / f"USGS_{station_id}_outlet_snap_candidates.csv"
)

nldi_file = (
    PROJECT_ROOT
    / config["paths"]["interim_catchment"]
    / f"USGS_{station_id}_NLDI_basin_qc.gpkg"
)


# =========================================================
# Output directories
# =========================================================

interim_dir = (
    PROJECT_ROOT
    / config["paths"]["interim_dem"]
)

processed_dir = (
    PROJECT_ROOT
    / config["paths"]["processed_dem"]
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


for directory in [
    interim_dir,
    processed_dir,
    results_dir,
    figure_dir,
]:

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )


# =========================================================
# Validate inputs
# =========================================================

print("=" * 78)
print("Stage 3D-2A4: Watershed and longest-flow-path analysis")
print("=" * 78)


for required_file in [
    conditioned_dem,
    d8_pointer,
    flow_accum,
    candidate_file,
    nldi_file,
]:

    if not required_file.exists():

        raise SystemExit(
            f"ERROR: Required file not found:\n"
            f"{required_file}"
        )


# =========================================================
# Select locked outlet
# =========================================================

candidates = pd.read_csv(
    candidate_file
)


selected = candidates[
    np.isclose(
        candidates["radius_m"],
        FINAL_RADIUS,
    )
].copy()


if len(selected) != 1:

    raise SystemExit(
        f"ERROR: Expected exactly one "
        f"{FINAL_RADIUS:.0f} m outlet candidate; "
        f"found {len(selected)}."
    )


selected = selected.iloc[0]


outlet_x = float(
    selected["x"]
)

outlet_y = float(
    selected["y"]
)

snap_distance = float(
    selected["snap_distance_m"]
)

outlet_accum = float(
    selected["accumulated_cells"]
)

outlet_area_km2 = float(
    selected["contributing_area_km2"]
)


print()
print("LOCKED OUTLET")
print("-" * 78)

print(
    f"Search radius         : "
    f"{FINAL_RADIUS:.0f} m"
)

print(
    f"Actual snap distance  : "
    f"{snap_distance:.2f} m"
)

print(
    f"Outlet X              : "
    f"{outlet_x:.2f}"
)

print(
    f"Outlet Y              : "
    f"{outlet_y:.2f}"
)

print(
    f"Accumulated cells     : "
    f"{outlet_accum:,.0f}"
)

print(
    f"Contributing area     : "
    f"{outlet_area_km2:.2f} km²"
)


# =========================================================
# Raster CRS
# =========================================================

with rasterio.open(
    d8_pointer
) as src:

    raster_crs = src.crs
    transform = src.transform
    pixel_area_m2 = (
        abs(transform.a)
        * abs(transform.e)
    )


# =========================================================
# Save snapped outlet
# =========================================================

outlet_gdf = gpd.GeoDataFrame(

    {
        "station": [
            f"USGS-{station_id}"
        ],

        "snap_radius_m": [
            FINAL_RADIUS
        ],

        "snap_distance_m": [
            snap_distance
        ],

        "accum_cells": [
            outlet_accum
        ],

        "area_km2": [
            outlet_area_km2
        ],
    },

    geometry=[
        Point(
            outlet_x,
            outlet_y,
        )
    ],

    crs=raster_crs,
)


# GPKG for project use.

outlet_gpkg = (
    processed_dir
    / f"USGS_{station_id}_locked_outlet.gpkg"
)


if outlet_gpkg.exists():
    outlet_gpkg.unlink()


outlet_gdf.to_file(
    outlet_gpkg,
    driver="GPKG",
)


# WhiteboxTools currently expects Shapefile
# for vector inputs.

outlet_shp = (
    interim_dir
    / f"USGS_{station_id}_locked_outlet.shp"
)


# Remove old shapefile sidecars if present.

for suffix in [
    ".shp",
    ".shx",
    ".dbf",
    ".prj",
    ".cpg",
]:

    old_file = outlet_shp.with_suffix(
        suffix
    )

    if old_file.exists():
        old_file.unlink()


outlet_gdf.to_file(
    outlet_shp,
    driver="ESRI Shapefile",
)


# =========================================================
# Delineate watershed
# =========================================================

watershed_raster = (
    interim_dir
    / f"USGS_{station_id}_DEM_watershed.tif"
)


wbt = whitebox.WhiteboxTools()

wbt.verbose = True


print()
print("=" * 78)
print("DEM WATERSHED DELINEATION")
print("=" * 78)


if watershed_raster.exists():

    print(
        "Watershed raster already exists; "
        "reusing existing output."
    )

else:

    wbt.watershed(
        str(d8_pointer),
        str(outlet_shp),
        str(watershed_raster),
        esri_pntr=False,
    )


if not watershed_raster.exists():

    raise SystemExit(
        "ERROR: Watershed raster not created."
    )


# =========================================================
# Load accepted NLDI polygon
# =========================================================

nldi = gpd.read_file(
    nldi_file
)


nldi = nldi.to_crs(
    raster_crs
)


nldi_geometry = (
    nldi.geometry.union_all()
)


nldi_area_km2 = (
    nldi_geometry.area
    / 1_000_000
)


# =========================================================
# Compare raster watershed with NLDI polygon
# =========================================================

watershed_cells = 0
nldi_cells = 0
intersection_cells = 0
union_cells = 0
extra_cells = 0
missing_cells = 0


nldi_shapes = [
    nldi_geometry.__geo_interface__
]


with rasterio.open(
    watershed_raster
) as src:

    for _, window in src.block_windows(1):

        data = src.read(
            1,
            window=window,
            masked=True,
        )


        dem_watershed = (
            ~np.ma.getmaskarray(data)
            &
            np.isfinite(
                np.asarray(data)
            )
            &
            (
                np.asarray(data)
                > 0
            )
        )


        window_transform = (
            src.window_transform(
                window
            )
        )


        nldi_mask = geometry_mask(

            nldi_shapes,

            out_shape=(
                int(window.height),
                int(window.width),
            ),

            transform=window_transform,

            invert=True,
        )


        watershed_cells += int(
            dem_watershed.sum()
        )

        nldi_cells += int(
            nldi_mask.sum()
        )


        intersection = (
            dem_watershed
            &
            nldi_mask
        )


        union = (
            dem_watershed
            |
            nldi_mask
        )


        extra = (
            dem_watershed
            &
            ~nldi_mask
        )


        missing = (
            nldi_mask
            &
            ~dem_watershed
        )


        intersection_cells += int(
            intersection.sum()
        )

        union_cells += int(
            union.sum()
        )

        extra_cells += int(
            extra.sum()
        )

        missing_cells += int(
            missing.sum()
        )


dem_area_km2 = (
    watershed_cells
    * pixel_area_m2
    / 1_000_000
)


rasterized_nldi_area_km2 = (
    nldi_cells
    * pixel_area_m2
    / 1_000_000
)


intersection_area_km2 = (
    intersection_cells
    * pixel_area_m2
    / 1_000_000
)


extra_area_km2 = (
    extra_cells
    * pixel_area_m2
    / 1_000_000
)


missing_area_km2 = (
    missing_cells
    * pixel_area_m2
    / 1_000_000
)


jaccard = (
    intersection_cells
    / union_cells
)


nldi_coverage_percent = (
    intersection_cells
    / nldi_cells
    * 100
)


dem_inside_nldi_percent = (
    intersection_cells
    / watershed_cells
    * 100
)


print()
print("=" * 78)
print("WATERSHED QC")
print("=" * 78)

print(
    f"DEM watershed area       : "
    f"{dem_area_km2:.2f} km²"
)

print(
    f"Flow-accumulation area    : "
    f"{outlet_area_km2:.2f} km²"
)

print(
    f"USGS official area        : "
    f"{official_area_km2:.2f} km²"
)

print(
    f"NLDI polygon area         : "
    f"{nldi_area_km2:.2f} km²"
)

print(
    f"DEM vs USGS difference    : "
    f"{dem_area_km2 - official_area_km2:+.2f} km² "
    f"({(dem_area_km2 - official_area_km2) / official_area_km2 * 100:+.3f}%)"
)

print(
    f"DEM vs NLDI difference    : "
    f"{dem_area_km2 - nldi_area_km2:+.2f} km² "
    f"({(dem_area_km2 - nldi_area_km2) / nldi_area_km2 * 100:+.3f}%)"
)

print()
print(
    f"Spatial intersection      : "
    f"{intersection_area_km2:.2f} km²"
)

print(
    f"DEM area outside NLDI     : "
    f"{extra_area_km2:.2f} km²"
)

print(
    f"NLDI area missing in DEM  : "
    f"{missing_area_km2:.2f} km²"
)

print(
    f"NLDI covered by DEM basin : "
    f"{nldi_coverage_percent:.3f}%"
)

print(
    f"DEM basin inside NLDI     : "
    f"{dem_inside_nldi_percent:.3f}%"
)

print(
    f"Jaccard / IoU             : "
    f"{jaccard:.5f}"
)


# =========================================================
# Longest flow path
# =========================================================

longest_path_shp = (
    interim_dir
    / f"USGS_{station_id}_longest_flowpath.shp"
)


# Remove stale shapefile if rerunning.

for suffix in [
    ".shp",
    ".shx",
    ".dbf",
    ".prj",
    ".cpg",
]:

    old_file = (
        longest_path_shp
        .with_suffix(
            suffix
        )
    )

    if old_file.exists():
        old_file.unlink()


print()
print("=" * 78)
print("LONGEST FLOW PATH")
print("=" * 78)


wbt.longest_flowpath(
    str(conditioned_dem),
    str(watershed_raster),
    str(longest_path_shp),
)


if not longest_path_shp.exists():

    raise SystemExit(
        "ERROR: Longest-flow-path vector not created."
    )


flowpath = gpd.read_file(
    longest_path_shp
)


if len(flowpath) == 0:

    raise SystemExit(
        "ERROR: Longest-flow-path output is empty."
    )


# If multiple records appear, retain the longest.

flowpath["geometry_length_m"] = (
    flowpath.geometry.length
)


flowpath = (
    flowpath
    .sort_values(
        "geometry_length_m",
        ascending=False,
    )
    .reset_index(drop=True)
)


primary_path = (
    flowpath.iloc[[0]]
    .copy()
)


path_geometry = (
    primary_path
    .geometry
    .iloc[0]
)


path_length_m = float(
    path_geometry.length
)


path_length_km = (
    path_length_m
    / 1000
)


# =========================================================
# Identify upstream/downstream orientation
# =========================================================

# Sample conditioned DEM at both endpoints.

coords = list(
    path_geometry.coords
)


endpoint_1 = coords[0]
endpoint_2 = coords[-1]


with rasterio.open(
    conditioned_dem
) as dem_src:

    z1 = float(
        list(
            dem_src.sample(
                [endpoint_1]
            )
        )[0][0]
    )

    z2 = float(
        list(
            dem_src.sample(
                [endpoint_2]
            )
        )[0][0]
    )


# Higher endpoint is treated as upstream.

if z1 >= z2:

    upstream_fraction_origin = 0.0

    upstream_point = Point(
        endpoint_1
    )

    downstream_point = Point(
        endpoint_2
    )

    upstream_elev = z1
    downstream_elev = z2

else:

    upstream_fraction_origin = 1.0

    upstream_point = Point(
        endpoint_2
    )

    downstream_point = Point(
        endpoint_1
    )

    upstream_elev = z2
    downstream_elev = z1


# =========================================================
# Sample 10% and 85% positions from upstream
# =========================================================

def point_from_upstream(
    fraction
):

    if upstream_fraction_origin == 0.0:

        distance = (
            path_length_m
            * fraction
        )

    else:

        distance = (
            path_length_m
            * (
                1.0
                - fraction
            )
        )


    return path_geometry.interpolate(
        distance
    )


point_10 = point_from_upstream(
    0.10
)

point_85 = point_from_upstream(
    0.85
)


with rasterio.open(
    conditioned_dem
) as dem_src:

    z10 = float(
        list(
            dem_src.sample(
                [
                    (
                        point_10.x,
                        point_10.y,
                    )
                ]
            )
        )[0][0]
    )

    z85 = float(
        list(
            dem_src.sample(
                [
                    (
                        point_85.x,
                        point_85.y,
                    )
                ]
            )
        )[0][0]
    )


distance_10_85_m = (
    path_length_m
    * 0.75
)


slope_10_85_m_per_m = (
    (
        z10
        - z85
    )
    / distance_10_85_m
)


slope_10_85_percent = (
    slope_10_85_m_per_m
    * 100
)


slope_10_85_m_per_km = (
    slope_10_85_m_per_m
    * 1000
)


# Conversion:
# 1 m/km = 5.279986876 ft/mi

slope_10_85_ft_per_mi = (
    slope_10_85_m_per_km
    * 5.279986876
)


overall_path_slope_percent = (
    (
        upstream_elev
        - downstream_elev
    )
    / path_length_m
    * 100
)


print(
    f"Longest path length       : "
    f"{path_length_km:.3f} km"
)

print(
    f"Upstream elevation        : "
    f"{upstream_elev:.2f} m"
)

print(
    f"Downstream elevation      : "
    f"{downstream_elev:.2f} m"
)

print(
    f"Overall path relief       : "
    f"{upstream_elev - downstream_elev:.2f} m"
)

print(
    f"Overall path slope        : "
    f"{overall_path_slope_percent:.4f}%"
)

print()
print(
    f"10% path elevation        : "
    f"{z10:.2f} m"
)

print(
    f"85% path elevation        : "
    f"{z85:.2f} m"
)

print(
    f"10-85 path distance       : "
    f"{distance_10_85_m / 1000:.3f} km"
)

print(
    f"10-85 slope               : "
    f"{slope_10_85_percent:.4f}%"
)

print(
    f"10-85 slope               : "
    f"{slope_10_85_m_per_km:.3f} m/km"
)

print(
    f"10-85 slope               : "
    f"{slope_10_85_ft_per_mi:.2f} ft/mi"
)


# =========================================================
# Save final flow path as GPKG
# =========================================================

flowpath_gpkg = (
    processed_dir
    / f"USGS_{station_id}_longest_flowpath.gpkg"
)


if flowpath_gpkg.exists():
    flowpath_gpkg.unlink()


primary_path.to_file(
    flowpath_gpkg,
    driver="GPKG",
)


# =========================================================
# Diagnostic map
# =========================================================

fig, ax = plt.subplots(
    figsize=(10, 11)
)


nldi.boundary.plot(
    ax=ax,
    linewidth=1.3,
    label="Accepted NLDI watershed",
)


primary_path.plot(
    ax=ax,
    linewidth=1.8,
    label="DEM longest flow path",
)


outlet_gdf.plot(
    ax=ax,
    marker="o",
    markersize=45,
    label="Locked DEM outlet",
)


ax.scatter(
    upstream_point.x,
    upstream_point.y,
    marker="^",
    s=50,
    label="Longest-path head",
)


ax.set_title(
    (
        "USGS 02361000 — accepted watershed "
        "and longest hydraulic flow path"
    )
)

ax.set_xlabel(
    "Easting (m, EPSG:5070)"
)

ax.set_ylabel(
    "Northing (m, EPSG:5070)"
)

ax.legend()


plt.tight_layout()


figure_file = (
    figure_dir
    / (
        f"USGS_{station_id}_"
        "longest_flowpath_QC.png"
    )
)


plt.savefig(
    figure_file,
    dpi=300,
    bbox_inches="tight",
)

plt.close()


# =========================================================
# Save summary
# =========================================================

summary = {

    "station":
        f"USGS-{station_id}",

    "locked_outlet": {

        "snap_radius_m":
            FINAL_RADIUS,

        "snap_distance_m":
            snap_distance,

        "x":
            outlet_x,

        "y":
            outlet_y,

        "flow_accumulation_cells":
            outlet_accum,

        "flow_accumulation_area_km2":
            outlet_area_km2,
    },

    "watershed": {

        "dem_watershed_area_km2":
            dem_area_km2,

        "official_usgs_area_km2":
            official_area_km2,

        "nldi_area_km2":
            nldi_area_km2,

        "intersection_area_km2":
            intersection_area_km2,

        "extra_dem_area_km2":
            extra_area_km2,

        "missing_nldi_area_km2":
            missing_area_km2,

        "nldi_coverage_percent":
            nldi_coverage_percent,

        "dem_inside_nldi_percent":
            dem_inside_nldi_percent,

        "jaccard_iou":
            jaccard,
    },

    "longest_flowpath": {

        "length_m":
            path_length_m,

        "length_km":
            path_length_km,

        "upstream_elevation_m":
            upstream_elev,

        "downstream_elevation_m":
            downstream_elev,

        "overall_slope_percent":
            overall_path_slope_percent,

        "elevation_at_10_percent_m":
            z10,

        "elevation_at_85_percent_m":
            z85,

        "slope_10_85_percent":
            slope_10_85_percent,

        "slope_10_85_m_per_km":
            slope_10_85_m_per_km,

        "slope_10_85_ft_per_mi":
            slope_10_85_ft_per_mi,
    },

    "scientific_status":
        (
            "outlet locked; DEM watershed and "
            "longest flow path derived; "
            "Clark Tc not yet estimated"
        ),
}


summary_file = (
    results_dir
    / (
        f"USGS_{station_id}_"
        "watershed_flowpath_summary.json"
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


print()
print("=" * 78)
print("FILES CREATED")
print("=" * 78)

print(outlet_gpkg)
print(watershed_raster)
print(flowpath_gpkg)
print(summary_file)
print(figure_file)

print()
print("=" * 78)
print("Stage 3D-2A4 COMPLETE")
print("=" * 78)

print()
print(
    "The snapped outlet is now locked."
)

print(
    "The DEM-derived watershed has been compared "
    "with the accepted NLDI watershed."
)

print(
    "The longest hydraulic flow path has been derived."
)

print(
    "Clark Tc has NOT yet been estimated."
)
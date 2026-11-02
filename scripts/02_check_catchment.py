"""
Stage 3A-2
Quality-control the downloaded NLDI catchment for USGS 02361000.

Checks:
1. File exists and loads correctly.
2. CRS is identified.
3. Geometry is valid.
4. Basin area is calculated independently using:
   a) geodesic area on the WGS84 ellipsoid
   b) projected area using CONUS Albers Equal Area (EPSG:5070)
5. Calculated area is compared with the official USGS drainage area.
6. A QC map and report are produced.

IMPORTANT:
The raw GeoJSON is never modified.
"""

from pathlib import Path
import json

import geopandas as gpd
import matplotlib.pyplot as plt
import yaml
from pyproj import Geod


# =========================================================
# Project paths
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CONFIG_FILE = PROJECT_ROOT / "config" / "project_config.yaml"


# =========================================================
# Read configuration
# =========================================================

with open(CONFIG_FILE, "r", encoding="utf-8") as file:
    config = yaml.safe_load(file)


station_id = config["catchment"]["usgs_station"]

official_area_sqmi = float(
    config["catchment"]["official_drainage_area_sqmi"]
)

official_area_km2 = float(
    config["catchment"]["official_drainage_area_km2"]
)


raw_file = (
    PROJECT_ROOT
    / config["paths"]["raw_catchment"]
    / f"USGS_{station_id}_NLDI_basin_raw.geojson"
)

interim_dir = (
    PROJECT_ROOT
    / config["paths"]["interim_catchment"]
)

results_dir = (
    PROJECT_ROOT
    / "results"
    / "tables"
)

figures_dir = (
    PROJECT_ROOT
    / "figures"
    / "maps"
)


interim_dir.mkdir(parents=True, exist_ok=True)
results_dir.mkdir(parents=True, exist_ok=True)
figures_dir.mkdir(parents=True, exist_ok=True)


# =========================================================
# Load raw basin
# =========================================================

print("=" * 65)
print("Stage 3A-2: Catchment geometry and area QC")
print("=" * 65)

print(f"USGS station       : {station_id}")
print(f"Raw basin file     : {raw_file}")


if not raw_file.exists():

    print()
    print("ERROR: Raw basin file does not exist.")
    print("Stage 3A-1 must be completed first.")

    raise SystemExit(1)


gdf = gpd.read_file(raw_file)


print()
print("Raw file loaded successfully.")

print(f"Number of features : {len(gdf)}")
print(f"CRS                : {gdf.crs}")


# =========================================================
# Basic geometry checks
# =========================================================

if len(gdf) == 0:

    print("ERROR: Catchment dataset contains no features.")

    raise SystemExit(1)


if gdf.crs is None:

    print()
    print("ERROR: No CRS is defined.")

    raise SystemExit(1)


geometry_types = sorted(
    gdf.geometry.geom_type.unique().tolist()
)

validity = gdf.geometry.is_valid


print(f"Geometry type(s)   : {geometry_types}")
print(f"All geometries valid: {bool(validity.all())}")


if not validity.all():

    print()
    print("WARNING: Invalid geometry detected.")
    print(
        "The geometry will NOT be automatically repaired."
    )


# =========================================================
# Convert to WGS84 if necessary
# =========================================================

gdf_wgs84 = gdf.to_crs("EPSG:4326")


# Combine features only for analysis.
# Raw data remain unchanged.

basin_geometry = gdf_wgs84.geometry.union_all()


print()
print("Geographic bounds (WGS84):")

minx, miny, maxx, maxy = basin_geometry.bounds

print(f"West  : {minx:.6f}")
print(f"South : {miny:.6f}")
print(f"East  : {maxx:.6f}")
print(f"North : {maxy:.6f}")


# =========================================================
# Method 1 — Geodesic area
# =========================================================

geod = Geod(ellps="WGS84")

geodesic_area_m2, perimeter_m = (
    geod.geometry_area_perimeter(
        basin_geometry
    )
)

geodesic_area_m2 = abs(geodesic_area_m2)

geodesic_area_km2 = (
    geodesic_area_m2 / 1_000_000
)

geodesic_area_sqmi = (
    geodesic_area_km2 / 2.589988110336
)


# =========================================================
# Method 2 — Equal-area projection
# =========================================================

# EPSG:5070:
# NAD83 / Conus Albers
#
# This is an equal-area projection appropriate for
# area calculations within the contiguous United States.

gdf_equal_area = gdf.to_crs("EPSG:5070")

projected_geometry = (
    gdf_equal_area.geometry.union_all()
)

projected_area_m2 = projected_geometry.area

projected_area_km2 = (
    projected_area_m2 / 1_000_000
)

projected_area_sqmi = (
    projected_area_km2 / 2.589988110336
)


# =========================================================
# Compare the two area calculations
# =========================================================

method_difference_percent = (

    abs(
        geodesic_area_km2
        - projected_area_km2
    )

    / geodesic_area_km2

    * 100
)


# =========================================================
# Compare against official USGS area
# =========================================================

geodesic_difference_km2 = (
    geodesic_area_km2
    - official_area_km2
)

geodesic_difference_percent = (
    geodesic_difference_km2
    / official_area_km2
    * 100
)


projected_difference_km2 = (
    projected_area_km2
    - official_area_km2
)

projected_difference_percent = (
    projected_difference_km2
    / official_area_km2
    * 100
)


# =========================================================
# Print results
# =========================================================

print()
print("=" * 65)
print("AREA RESULTS")
print("=" * 65)

print()
print("Official USGS drainage area:")
print(
    f"  {official_area_sqmi:.2f} mi²"
)
print(
    f"  {official_area_km2:.2f} km²"
)

print()
print("Method 1 — WGS84 geodesic area:")
print(
    f"  {geodesic_area_sqmi:.2f} mi²"
)
print(
    f"  {geodesic_area_km2:.2f} km²"
)

print()
print("Method 2 — EPSG:5070 equal-area:")
print(
    f"  {projected_area_sqmi:.2f} mi²"
)
print(
    f"  {projected_area_km2:.2f} km²"
)

print()
print(
    "Agreement between the two independent "
    "area calculations:"
)

print(
    f"  Difference = "
    f"{method_difference_percent:.4f}%"
)

print()
print("Difference from official USGS area:")

print(
    f"  Geodesic = "
    f"{geodesic_difference_km2:+.2f} km² "
    f"({geodesic_difference_percent:+.3f}%)"
)

print(
    f"  Projected = "
    f"{projected_difference_km2:+.2f} km² "
    f"({projected_difference_percent:+.3f}%)"
)


# =========================================================
# Save interim basin
# =========================================================

interim_file = (
    interim_dir
    / f"USGS_{station_id}_NLDI_basin_qc.gpkg"
)

gdf.to_file(
    interim_file,
    driver="GPKG",
)


# =========================================================
# Save QC report
# =========================================================

qc_report = {

    "station_id": station_id,

    "raw_file": raw_file.name,

    "crs": str(gdf.crs),

    "number_of_features": int(len(gdf)),

    "geometry_types": geometry_types,

    "all_geometries_valid": bool(
        validity.all()
    ),

    "bounds_wgs84": {
        "west": minx,
        "south": miny,
        "east": maxx,
        "north": maxy,
    },

    "official_usgs_area": {
        "sq_mi": official_area_sqmi,
        "km2": official_area_km2,
    },

    "geodesic_area": {
        "sq_mi": geodesic_area_sqmi,
        "km2": geodesic_area_km2,
    },

    "equal_area_projection": {
        "epsg": 5070,
        "sq_mi": projected_area_sqmi,
        "km2": projected_area_km2,
    },

    "area_method_difference_percent":
        method_difference_percent,

    "difference_from_usgs": {

        "geodesic_km2":
            geodesic_difference_km2,

        "geodesic_percent":
            geodesic_difference_percent,

        "projected_km2":
            projected_difference_km2,

        "projected_percent":
            projected_difference_percent,
    },

    "scientific_status":
        "pending manual QC decision",
}


report_file = (
    results_dir
    / f"USGS_{station_id}_catchment_qc.json"
)


with open(
    report_file,
    "w",
    encoding="utf-8",
) as file:

    json.dump(
        qc_report,
        file,
        indent=2,
    )


# =========================================================
# Create QC map
# =========================================================

fig, ax = plt.subplots(
    figsize=(8, 8)
)

gdf_wgs84.plot(
    ax=ax,
    edgecolor="black",
    facecolor="none",
    linewidth=1.2,
)

ax.set_title(
    f"USGS {station_id} — NLDI Upstream Basin"
)

ax.set_xlabel("Longitude")
ax.set_ylabel("Latitude")

ax.grid(
    True,
    linewidth=0.4,
)

plt.tight_layout()


map_file = (
    figures_dir
    / f"USGS_{station_id}_catchment_qc.png"
)

plt.savefig(
    map_file,
    dpi=300,
    bbox_inches="tight",
)

plt.close()


# =========================================================
# Final report
# =========================================================

print()
print("=" * 65)
print("FILES CREATED")
print("=" * 65)

print()
print("Interim basin:")
print(interim_file)

print()
print("QC report:")
print(report_file)

print()
print("QC map:")
print(map_file)

print()
print("=" * 65)
print("Stage 3A-2 ANALYSIS COMPLETE")
print("=" * 65)

print()
print(
    "Do not accept or reject the catchment yet."
)

print(
    "Review the area difference and map first."
)
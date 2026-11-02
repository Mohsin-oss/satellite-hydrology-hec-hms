"""
Stage 3D-2C1
Acquire and QC USDA-NRCS SSURGO Hydrologic Soil Groups (HSG)
for USGS 02361000.

This version includes robust WFS 1.1 / EPSG:4326
axis-order detection and correction.

It reuses already downloaded raw files where possible.

Outputs
-------
1. Raw SDA GML response.
2. Corrected SSURGO map-unit GeoPackage.
3. Raw HSG lookup table.
4. Catchment-clipped HSG polygons.
5. 30 m HSG raster aligned to NLCD.
6. HSG composition table.
7. QC metadata.

No Curve Number is calculated here.
"""

from pathlib import Path
import json
import time

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask, rasterize
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from shapely.geometry import box
from shapely.ops import transform as shapely_transform
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

ANALYSIS_CRS = (
    config
    .get("soils", {})
    .get(
        "analysis_crs",
        "EPSG:5070",
    )
)


# =========================================================
# Official NRCS services
# =========================================================

WFS_URL = (
    "https://SDMDataAccess.sc.egov.usda.gov/"
    "Spatial/SDMWGS84Geographic.wfs"
)

SDA_URL = (
    "https://SDMDataAccess.sc.egov.usda.gov/"
    "Tabular/post.rest"
)


# =========================================================
# Paths
# =========================================================

catchment_file = (
    PROJECT_ROOT
    / config["paths"]["interim_catchment"]
    / f"USGS_{station_id}_NLDI_basin_qc.gpkg"
)


nlcd_reference = (
    PROJECT_ROOT
    / config["paths"]["raw_landcover"]
    / f"USGS_{station_id}_NLCD2021_landcover_30m.tif"
)


raw_soils_path = (
    config["paths"]
    .get(
        "raw_soils",
        "data/raw/soils",
    )
)

interim_soils_path = (
    config["paths"]
    .get(
        "interim_soils",
        "data/interim/soils",
    )
)


raw_dir = (
    PROJECT_ROOT
    / raw_soils_path
)

interim_dir = (
    PROJECT_ROOT
    / interim_soils_path
)

results_dir = (
    PROJECT_ROOT
    / "results"
    / "tables"
)


raw_dir.mkdir(
    parents=True,
    exist_ok=True,
)

interim_dir.mkdir(
    parents=True,
    exist_ok=True,
)

results_dir.mkdir(
    parents=True,
    exist_ok=True,
)


# =========================================================
# Output files
# =========================================================

raw_gml_file = (
    raw_dir
    / (
        f"USGS_{station_id}_"
        "SSURGO_MapunitPoly_bbox_raw.gml"
    )
)


raw_spatial_file = (
    raw_dir
    / (
        f"USGS_{station_id}_"
        "SSURGO_MapunitPoly_bbox.gpkg"
    )
)


raw_table_file = (
    raw_dir
    / (
        f"USGS_{station_id}_"
        "SSURGO_HSG_DCD_raw.csv"
    )
)


clipped_file = (
    interim_dir
    / (
        f"USGS_{station_id}_"
        "SSURGO_HSG_DCD.gpkg"
    )
)


hsg_raster_file = (
    interim_dir
    / (
        f"USGS_{station_id}_"
        "SSURGO_HSG_DCD_30m.tif"
    )
)


summary_file = (
    results_dir
    / (
        f"USGS_{station_id}_"
        "SSURGO_HSG_summary.csv"
    )
)


metadata_file = (
    results_dir
    / (
        f"USGS_{station_id}_"
        "SSURGO_HSG_qc.json"
    )
)


# =========================================================
# HSG codes
# =========================================================

HSG_CODES = {
    "A": 1,
    "B": 2,
    "C": 3,
    "D": 4,
    "A/D": 5,
    "B/D": 6,
    "C/D": 7,
}


CODE_HSG = {
    value: key
    for key, value
    in HSG_CODES.items()
}


# =========================================================
# HTTP session
# =========================================================

session = requests.Session()

retry = Retry(
    total=5,
    connect=5,
    read=5,
    backoff_factor=1.5,
    status_forcelist=[
        429,
        500,
        502,
        503,
        504,
    ],
    allowed_methods=[
        "GET",
        "POST",
    ],
)


adapter = HTTPAdapter(
    max_retries=retry
)

session.mount(
    "https://",
    adapter,
)


# =========================================================
# Catchment
# =========================================================

print("=" * 78)
print(
    "Stage 3D-2C1: "
    "SSURGO Hydrologic Soil Group acquisition"
)
print("=" * 78)


catchment = gpd.read_file(
    catchment_file
)


catchment_5070 = (
    catchment
    .to_crs(
        ANALYSIS_CRS
    )
)


catchment_geometry = (
    catchment_5070
    .geometry
    .union_all()
)


catchment_area_km2 = (
    catchment_geometry.area
    / 1_000_000
)


catchment_wgs84 = (
    catchment
    .to_crs(
        "EPSG:4326"
    )
)


catchment_wgs84_geometry = (
    catchment_wgs84
    .geometry
    .union_all()
)


minx, miny, maxx, maxy = (
    catchment_wgs84.total_bounds
)


print(
    f"Accepted catchment area : "
    f"{catchment_area_km2:.2f} km²"
)

print(
    f"WGS84 query bounds      : "
    f"{minx:.6f}, {miny:.6f}, "
    f"{maxx:.6f}, {maxy:.6f}"
)


# =========================================================
# Download raw WFS response only if absent
# =========================================================

print()
print("=" * 78)
print("SSURGO SPATIAL QUERY")
print("=" * 78)


if raw_gml_file.exists():

    size_mb = (
        raw_gml_file.stat().st_size
        / 1024
        / 1024
    )

    print(
        "Raw GML already exists; "
        "reusing previous download."
    )

    print(
        f"Raw GML size    : "
        f"{size_mb:.1f} MB"
    )


else:

    filter_xml = (
        "<Filter>"
        "<BBOX>"
        "<PropertyName>Geometry</PropertyName>"
        '<Box srsName="EPSG:4326">'
        "<coordinates>"
        f"{minx},{miny} "
        f"{maxx},{maxy}"
        "</coordinates>"
        "</Box>"
        "</BBOX>"
        "</Filter>"
    )


    params = {

        "SERVICE":
            "WFS",

        "VERSION":
            "1.1.0",

        "REQUEST":
            "GetFeature",

        "TYPENAME":
            "MapunitPoly",

        "SRSNAME":
            "EPSG:4326",

        "OUTPUTFORMAT":
            "GML2",

        "MAXFEATURES":
            "250000",

        "FILTER":
            filter_xml,
    }


    response = session.get(
        WFS_URL,
        params=params,
        timeout=300,
    )


    print(
        f"HTTP status      : "
        f"{response.status_code}"
    )

    print(
        f"Response size    : "
        f"{len(response.content) / 1024:.1f} KB"
    )


    response.raise_for_status()


    preview = (
        response.text[:5000]
        .lower()
    )


    if (
        "serviceexception" in preview
        or
        "exceptionreport" in preview
    ):

        raise SystemExit(
            "ERROR: NRCS WFS returned "
            "a service exception."
        )


    with open(
        raw_gml_file,
        "wb",
    ) as file:

        file.write(
            response.content
        )


    print(
        f"Raw GML saved    : "
        f"{raw_gml_file}"
    )


# =========================================================
# Read WFS GML
# =========================================================

mapunits = gpd.read_file(
    raw_gml_file
)


if mapunits.empty:

    raise SystemExit(
        "ERROR: Raw SSURGO GML contains "
        "no features."
    )


if mapunits.crs is None:

    mapunits = mapunits.set_crs(
        "EPSG:4326"
    )


print(
    f"Returned polygons : "
    f"{len(mapunits):,}"
)

print(
    f"Reported CRS      : "
    f"{mapunits.crs}"
)

print(
    "Raw interpreted bounds:"
)

print(
    f"  xmin = "
    f"{mapunits.total_bounds[0]:.6f}"
)

print(
    f"  ymin = "
    f"{mapunits.total_bounds[1]:.6f}"
)

print(
    f"  xmax = "
    f"{mapunits.total_bounds[2]:.6f}"
)

print(
    f"  ymax = "
    f"{mapunits.total_bounds[3]:.6f}"
)


# =========================================================
# WFS 1.1 axis-order audit
# =========================================================

print()
print("=" * 78)
print("WFS AXIS-ORDER QC")
print("=" * 78)


catchment_bbox = box(
    minx,
    miny,
    maxx,
    maxy,
)


raw_bounds = (
    mapunits.total_bounds
)


raw_bbox = box(
    raw_bounds[0],
    raw_bounds[1],
    raw_bounds[2],
    raw_bounds[3],
)


raw_bbox_overlap = (
    raw_bbox.intersects(
        catchment_bbox
    )
)


# ---------------------------------------------------------
# Create an axis-swapped test geometry
# ---------------------------------------------------------

def swap_xy(
    geometry,
):

    if geometry is None:
        return None

    return shapely_transform(
        lambda x, y, z=None:
            (
                y,
                x,
            )
            if z is None
            else (
                y,
                x,
                z,
            ),
        geometry,
    )


swapped_test = mapunits.copy()


swapped_test[
    "geometry"
] = (
    swapped_test[
        "geometry"
    ]
    .apply(
        swap_xy
    )
)


swapped_bounds = (
    swapped_test
    .total_bounds
)


swapped_bbox = box(
    swapped_bounds[0],
    swapped_bounds[1],
    swapped_bounds[2],
    swapped_bounds[3],
)


swapped_bbox_overlap = (
    swapped_bbox.intersects(
        catchment_bbox
    )
)


print(
    f"Raw bounds overlap catchment     : "
    f"{raw_bbox_overlap}"
)

print(
    f"Swapped bounds overlap catchment : "
    f"{swapped_bbox_overlap}"
)


axis_swap_applied = False


# =========================================================
# Choose the interpretation that actually overlaps Alabama
# =========================================================

if (
    not raw_bbox_overlap
    and
    swapped_bbox_overlap
):

    print()
    print(
        "Detected reversed WFS/GML "
        "EPSG:4326 axis order."
    )

    print(
        "Applying X/Y coordinate swap."
    )


    mapunits = swapped_test

    mapunits = (
        mapunits
        .set_crs(
            "EPSG:4326",
            allow_override=True,
        )
    )

    axis_swap_applied = True


elif (
    raw_bbox_overlap
    and
    not swapped_bbox_overlap
):

    print(
        "Axis order is already correct."
    )


elif (
    raw_bbox_overlap
    and
    swapped_bbox_overlap
):

    print(
        "WARNING: Both raw and swapped bounding "
        "boxes overlap the query region."
    )

    print(
        "Using the interpretation with greater "
        "actual polygon/catchment intersection."
    )


    raw_copy = (
        mapunits
        .to_crs(
            "EPSG:4326"
        )
    )


    raw_intersection = (
        raw_copy
        .geometry
        .intersection(
            catchment_wgs84_geometry
        )
        .area
        .sum()
    )


    swapped_intersection = (
        swapped_test
        .geometry
        .intersection(
            catchment_wgs84_geometry
        )
        .area
        .sum()
    )


    if (
        swapped_intersection
        >
        raw_intersection
    ):

        mapunits = swapped_test

        mapunits = (
            mapunits
            .set_crs(
                "EPSG:4326",
                allow_override=True,
            )
        )

        axis_swap_applied = True


else:

    raise SystemExit(
        "ERROR: Neither the raw nor axis-swapped "
        "SSURGO geometry overlaps the catchment.\n"
        "This indicates a different WFS problem "
        "and should not be guessed."
    )


print()
print(
    f"Axis swap applied : "
    f"{axis_swap_applied}"
)

print(
    "Corrected bounds:"
)

print(
    f"  xmin = "
    f"{mapunits.total_bounds[0]:.6f}"
)

print(
    f"  ymin = "
    f"{mapunits.total_bounds[1]:.6f}"
)

print(
    f"  xmax = "
    f"{mapunits.total_bounds[2]:.6f}"
)

print(
    f"  ymax = "
    f"{mapunits.total_bounds[3]:.6f}"
)


# =========================================================
# Find mukey
# =========================================================

column_lookup = {
    str(column).lower():
        column
    for column
    in mapunits.columns
}


if "mukey" not in column_lookup:

    raise SystemExit(
        "ERROR: MapunitPoly does not contain mukey."
    )


mukey_column = (
    column_lookup[
        "mukey"
    ]
)


mapunits[
    "mukey"
] = (
    mapunits[
        mukey_column
    ]
    .astype(str)
    .str.strip()
    .str.replace(
        r"\.0$",
        "",
        regex=True,
    )
)


# =========================================================
# Remove exact duplicates
# =========================================================

mapunits = mapunits[
    mapunits.geometry.notna()
].copy()


mapunits = mapunits[
    ~mapunits.geometry.is_empty
].copy()


mapunits[
    "_wkb"
] = (
    mapunits
    .geometry
    .apply(
        lambda geom:
            geom.wkb_hex
    )
)


before = len(
    mapunits
)


mapunits = (
    mapunits
    .drop_duplicates(
        subset=[
            "mukey",
            "_wkb",
        ]
    )
    .drop(
        columns=[
            "_wkb"
        ]
    )
    .reset_index(
        drop=True
    )
)


print(
    f"Duplicate features removed : "
    f"{before - len(mapunits):,}"
)


unique_mukeys = sorted(
    mapunits[
        "mukey"
    ]
    .unique()
)


print(
    f"Unique map units           : "
    f"{len(unique_mukeys):,}"
)


# =========================================================
# Save corrected raw spatial data
# =========================================================

if raw_spatial_file.exists():

    raw_spatial_file.unlink()


mapunits.to_file(
    raw_spatial_file,
    driver="GPKG",
)


# =========================================================
# Tabular HSG table
# =========================================================

print()
print("=" * 78)
print("SSURGO TABULAR QUERY")
print("=" * 78)


if raw_table_file.exists():

    hsg_table = pd.read_csv(
        raw_table_file,
        dtype={
            "mukey": str,
        },
    )


    print(
        "Raw HSG table already exists; "
        "reusing previous query."
    )


else:

    def run_sda_query(
        sql,
    ):

        response = session.post(
            SDA_URL,
            data={
                "query":
                    sql,

                "format":
                    "JSON+COLUMNNAME",
            },
            timeout=300,
        )

        response.raise_for_status()

        data = response.json()

        table = (
            data.get("Table")
            or
            data.get("Table1")
        )


        if not table:

            return pd.DataFrame()


        return pd.DataFrame(
            table[1:],
            columns=table[0],
        )


    frames = []

    chunk_size = 400


    for start in range(
        0,
        len(unique_mukeys),
        chunk_size,
    ):

        chunk = unique_mukeys[
            start:
            start + chunk_size
        ]


        values = ",".join(
            f"'{value}'"
            for value in chunk
        )


        sql = f"""
        SELECT
            mu.mukey,
            mua.hydgrpdcd
        FROM mapunit AS mu
        LEFT JOIN muaggatt AS mua
            ON mu.mukey = mua.mukey
        WHERE mu.mukey IN ({values})
        """


        frame = run_sda_query(
            sql
        )


        if not frame.empty:

            frames.append(
                frame
            )


        print(
            f"Queried map units "
            f"{start + 1}–"
            f"{min(start + chunk_size, len(unique_mukeys))}"
        )


        time.sleep(
            0.25
        )


    hsg_table = (
        pd.concat(
            frames,
            ignore_index=True,
        )
    )


    hsg_table.to_csv(
        raw_table_file,
        index=False,
    )


# =========================================================
# Normalize table
# =========================================================

hsg_table.columns = [
    str(column).lower()
    for column
    in hsg_table.columns
]


hsg_table[
    "mukey"
] = (
    hsg_table[
        "mukey"
    ]
    .astype(str)
    .str.strip()
    .str.replace(
        r"\.0$",
        "",
        regex=True,
    )
)


hsg_table[
    "hydgrpdcd"
] = (
    hsg_table[
        "hydgrpdcd"
    ]
    .astype("string")
    .str.strip()
    .replace(
        {
            "":
                pd.NA,

            "None":
                pd.NA,

            "NULL":
                pd.NA,

            "<NA>":
                pd.NA,
        }
    )
)


hsg_table = (
    hsg_table
    .drop_duplicates(
        subset=[
            "mukey"
        ]
    )
)


print(
    f"Returned HSG rows : "
    f"{len(hsg_table):,}"
)

print(
    f"Rated map units   : "
    f"{hsg_table['hydgrpdcd'].notna().sum():,}"
)

print(
    f"Unrated map units : "
    f"{hsg_table['hydgrpdcd'].isna().sum():,}"
)


# =========================================================
# Join and project
# =========================================================

joined = mapunits.merge(
    hsg_table[
        [
            "mukey",
            "hydgrpdcd",
        ]
    ],
    on="mukey",
    how="left",
)


joined = (
    joined
    .to_crs(
        ANALYSIS_CRS
    )
)


# =========================================================
# Clip
# =========================================================

catchment_clip = (
    gpd.GeoDataFrame(
        geometry=[
            catchment_geometry
        ],
        crs=ANALYSIS_CRS,
    )
)


clipped = gpd.clip(
    joined,
    catchment_clip,
)


clipped = clipped[
    clipped.geometry.notna()
].copy()


clipped = clipped[
    ~clipped.geometry.is_empty
].copy()


if clipped.empty:

    raise SystemExit(
        "ERROR: SSURGO still does not overlap "
        "the accepted catchment after "
        "axis-order correction."
    )


clipped[
    "area_km2"
] = (
    clipped.geometry.area
    / 1_000_000
)


# =========================================================
# Save clipped polygons
# =========================================================

if clipped_file.exists():

    clipped_file.unlink()


clipped.to_file(
    clipped_file,
    driver="GPKG",
)


# =========================================================
# Coverage QC
# =========================================================

spatial_union = (
    clipped.geometry.union_all()
)


spatial_area_km2 = (
    spatial_union.area
    / 1_000_000
)


spatial_coverage_percent = (
    spatial_area_km2
    / catchment_area_km2
    * 100
)


rated = clipped[
    clipped[
        "hydgrpdcd"
    ].notna()
]


if len(rated):

    rated_area_km2 = (
        rated
        .geometry
        .union_all()
        .area
        / 1_000_000
    )

else:

    rated_area_km2 = 0.0


rated_coverage_percent = (
    rated_area_km2
    / catchment_area_km2
    * 100
)


print()
print("=" * 78)
print("COVERAGE QC")
print("=" * 78)

print(
    f"Catchment area          : "
    f"{catchment_area_km2:.2f} km²"
)

print(
    f"SSURGO polygon coverage : "
    f"{spatial_area_km2:.2f} km² "
    f"({spatial_coverage_percent:.3f}%)"
)

print(
    f"Rated HSG area          : "
    f"{rated_area_km2:.2f} km² "
    f"({rated_coverage_percent:.3f}%)"
)


if (
    spatial_coverage_percent
    <
    99.0
):

    raise SystemExit(
        "ERROR: SSURGO spatial coverage "
        "is below 99%."
    )


# =========================================================
# HSG composition
# =========================================================

clipped[
    "hsg"
] = (
    clipped[
        "hydgrpdcd"
    ]
    .fillna(
        "UNRATED"
    )
)


valid_classes = set(
    HSG_CODES.keys()
)


clipped.loc[
    ~clipped["hsg"].isin(
        list(valid_classes)
        +
        ["UNRATED"]
    ),
    "hsg",
] = "UNRATED"


summary = (
    clipped
    .groupby(
        "hsg"
    )[
        "area_km2"
    ]
    .sum()
    .reset_index()
)


summary[
    "percent_basin"
] = (
    summary[
        "area_km2"
    ]
    / catchment_area_km2
    * 100
)


summary = (
    summary
    .sort_values(
        "area_km2",
        ascending=False,
    )
    .reset_index(
        drop=True
    )
)


summary.to_csv(
    summary_file,
    index=False,
)


print()
print("=" * 78)
print("HSG COMPOSITION")
print("=" * 78)

print(
    summary.to_string(
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
# Rasterize on exact NLCD grid
# =========================================================

with rasterio.open(
    nlcd_reference
) as ref:

    ref_crs = ref.crs
    ref_transform = ref.transform
    ref_height = ref.height
    ref_width = ref.width
    profile = ref.profile.copy()


if (
    ref_crs.to_string()
    !=
    ANALYSIS_CRS
):

    raise SystemExit(
        "ERROR: NLCD reference CRS "
        "does not match analysis CRS."
    )


catchment_mask = geometry_mask(

    [
        catchment_geometry
        .__geo_interface__
    ],

    out_shape=(
        ref_height,
        ref_width,
    ),

    transform=ref_transform,

    invert=True,
)


# 255 outside watershed
# 0 unrated inside watershed

hsg_array = np.full(
    (
        ref_height,
        ref_width,
    ),
    255,
    dtype=np.uint8,
)


hsg_array[
    catchment_mask
] = 0


raster_shapes = []


for _, row in clipped.iterrows():

    hsg = row[
        "hydgrpdcd"
    ]


    if pd.isna(
        hsg
    ):

        continue


    hsg = str(
        hsg
    ).strip()


    code = HSG_CODES.get(
        hsg
    )


    if code is not None:

        raster_shapes.append(
            (
                row.geometry,
                code,
            )
        )


burned = rasterize(

    raster_shapes,

    out_shape=(
        ref_height,
        ref_width,
    ),

    transform=ref_transform,

    fill=0,

    dtype="uint8",

    all_touched=False,
)


valid_burn = (
    catchment_mask
    &
    (
        burned > 0
    )
)


hsg_array[
    valid_burn
] = burned[
    valid_burn
]


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
    hsg_raster_file,
    "w",
    **profile,
) as dst:

    dst.write(
        hsg_array,
        1,
    )


    dst.update_tags(
        SOURCE="USDA-NRCS SSURGO",
        ATTRIBUTE="muaggatt.hydgrpdcd",
        AGGREGATION="Dominant Condition",
        HSG_CODES=json.dumps(
            HSG_CODES
        ),
    )


# =========================================================
# Raster QC
# =========================================================

watershed_values = (
    hsg_array[
        catchment_mask
    ]
)


unique_codes, counts = np.unique(
    watershed_values,
    return_counts=True,
)


total_pixels = int(
    catchment_mask.sum()
)


rated_pixels = int(
    np.sum(
        (
            watershed_values >= 1
        )
        &
        (
            watershed_values <= 7
        )
    )
)


unrated_pixels = int(
    np.sum(
        watershed_values == 0
    )
)


raster_coverage_percent = (
    rated_pixels
    / total_pixels
    * 100
)


print()
print("=" * 78)
print("30 m HSG RASTER QC")
print("=" * 78)


for code, count in zip(
    unique_codes,
    counts,
):

    code = int(
        code
    )

    count = int(
        count
    )


    label = (
        "UNRATED"
        if code == 0
        else
        CODE_HSG.get(
            code,
            "UNKNOWN",
        )
    )


    print(
        f"{code:>2}  "
        f"{label:<10} "
        f"{count:>10,} pixels  "
        f"{count / total_pixels * 100:>7.3f}%"
    )


print()
print(
    f"Total watershed pixels : "
    f"{total_pixels:,}"
)

print(
    f"Rated raster pixels    : "
    f"{rated_pixels:,}"
)

print(
    f"Unrated raster pixels  : "
    f"{unrated_pixels:,}"
)

print(
    f"Raster HSG coverage    : "
    f"{raster_coverage_percent:.3f}%"
)


# =========================================================
# Metadata
# =========================================================

metadata = {

    "station":
        f"USGS-{station_id}",

    "source":
        "USDA-NRCS SSURGO",

    "wfs_endpoint":
        WFS_URL,

    "tabular_endpoint":
        SDA_URL,

    "axis_swap_applied":
        axis_swap_applied,

    "hsg_attribute":
        "muaggatt.hydgrpdcd",

    "aggregation":
        "Dominant Condition",

    "catchment_area_km2":
        catchment_area_km2,

    "spatial_coverage_percent":
        spatial_coverage_percent,

    "rated_polygon_coverage_percent":
        rated_coverage_percent,

    "rated_raster_coverage_percent":
        raster_coverage_percent,

    "dual_groups_preserved":
        True,

    "scientific_status":
        (
            "SSURGO HSG acquisition/QC complete; "
            "Curve Number not yet calculated"
        ),
}


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
# Final
# =========================================================

print()
print("=" * 78)
print("FILES CREATED")
print("=" * 78)

print(raw_gml_file)
print(raw_spatial_file)
print(raw_table_file)
print(clipped_file)
print(hsg_raster_file)
print(summary_file)
print(metadata_file)


print()
print("=" * 78)
print("Stage 3D-2C1 COMPLETE")
print("=" * 78)

print()
print(
    "SSURGO Hydrologic Soil Groups "
    "have been mapped."
)

print(
    "Dual groups remain unresolved intentionally."
)

print(
    "Missing HSG values have NOT been guessed."
)

print(
    "Curve Number has NOT yet been calculated."
)
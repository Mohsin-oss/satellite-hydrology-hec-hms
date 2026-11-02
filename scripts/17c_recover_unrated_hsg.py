"""
Stage 3D-2C3
Investigate the 11 SSURGO map units whose map-unit-level
hydrologic soil group (muaggatt.hydgrpdcd) is missing.

Purpose
-------
1. Identify unrated map units intersecting the watershed.
2. Query component-level SSURGO information:
       component.hydgrp
       component.comppct_r
3. Summarize how much of each map unit has rated components.
4. Calculate a diagnostic component-dominant HSG.

IMPORTANT
---------
This script does NOT automatically modify the HSG raster.

The component-derived HSG is diagnostic evidence only.
We will review it before deciding whether any missing
map-unit HSG values can be defensibly recovered.
"""

from pathlib import Path
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
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


# =========================================================
# Paths
# =========================================================

raw_hsg_table = (
    PROJECT_ROOT
    / raw_soils_path
    / (
        f"USGS_{station_id}_"
        "SSURGO_HSG_DCD_raw.csv"
    )
)


clipped_hsg_file = (
    PROJECT_ROOT
    / interim_soils_path
    / (
        f"USGS_{station_id}_"
        "SSURGO_HSG_DCD.gpkg"
    )
)


results_dir = (
    PROJECT_ROOT
    / "results"
    / "tables"
)


results_dir.mkdir(
    parents=True,
    exist_ok=True,
)


component_file = (
    results_dir
    / (
        f"USGS_{station_id}_"
        "SSURGO_unrated_components.csv"
    )
)


recovery_file = (
    results_dir
    / (
        f"USGS_{station_id}_"
        "SSURGO_unrated_HSG_recovery.csv"
    )
)


metadata_file = (
    results_dir
    / (
        f"USGS_{station_id}_"
        "SSURGO_unrated_HSG_recovery.json"
    )
)


# =========================================================
# Soil Data Access endpoint
# =========================================================

SDA_URL = (
    "https://SDMDataAccess.sc.egov.usda.gov/"
    "Tabular/post.rest"
)


# =========================================================
# Web session
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
        "POST",
    ],
)


session.mount(
    "https://",
    HTTPAdapter(
        max_retries=retry
    ),
)


# =========================================================
# Input validation
# =========================================================

print("=" * 78)
print("Stage 3D-2C3: Unrated SSURGO HSG component audit")
print("=" * 78)


for required_file in [
    raw_hsg_table,
    clipped_hsg_file,
]:

    if not required_file.exists():

        raise SystemExit(
            f"ERROR: Required file not found:\n"
            f"{required_file}"
        )


# =========================================================
# Identify unrated map units
# =========================================================

hsg_table = pd.read_csv(
    raw_hsg_table,
    dtype={
        "mukey": str,
    },
)


hsg_table.columns = [
    str(column).lower()
    for column
    in hsg_table.columns
]


hsg_table[
    "hydgrpdcd"
] = (
    hsg_table[
        "hydgrpdcd"
    ]
    .astype("string")
    .str.strip()
)


unrated_mukeys = (
    hsg_table.loc[
        hsg_table[
            "hydgrpdcd"
        ].isna(),
        "mukey",
    ]
    .astype(str)
    .unique()
    .tolist()
)


print()
print(
    f"Unrated map units found : "
    f"{len(unrated_mukeys)}"
)


if not unrated_mukeys:

    raise SystemExit(
        "No unrated map units remain."
    )


# =========================================================
# Area of each unrated map unit inside basin
# =========================================================

clipped = gpd.read_file(
    clipped_hsg_file
)


clipped[
    "mukey"
] = (
    clipped[
        "mukey"
    ]
    .astype(str)
)


clipped[
    "area_km2"
] = (
    clipped.geometry.area
    / 1_000_000
)


mapunit_area = (
    clipped[
        clipped[
            "mukey"
        ].isin(
            unrated_mukeys
        )
    ]
    .groupby(
        "mukey"
    )[
        "area_km2"
    ]
    .sum()
    .to_dict()
)


# =========================================================
# SDA query helper
# =========================================================

def run_sda_query(sql):

    response = session.post(
        SDA_URL,
        data={
            "query": sql,
            "format": "JSON+COLUMNNAME",
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


# =========================================================
# Query component-level HSG
# =========================================================

quoted = ",".join(
    f"'{value}'"
    for value
    in unrated_mukeys
)


sql = f"""
SELECT
    mu.mukey,
    mu.musym,
    mu.muname,

    co.cokey,
    co.compname,
    co.comppct_r,
    co.majcompflag,
    co.hydgrp

FROM mapunit AS mu

LEFT JOIN component AS co
    ON mu.mukey = co.mukey

WHERE mu.mukey IN ({quoted})

ORDER BY
    mu.mukey,
    co.comppct_r DESC
"""


print()
print("=" * 78)
print("COMPONENT QUERY")
print("=" * 78)


components = run_sda_query(
    sql
)


if components.empty:

    raise SystemExit(
        "ERROR: SDA returned no component records."
    )


components.columns = [
    str(column).lower()
    for column
    in components.columns
]


components[
    "mukey"
] = (
    components[
        "mukey"
    ]
    .astype(str)
)


components[
    "comppct_r"
] = pd.to_numeric(
    components[
        "comppct_r"
    ],
    errors="coerce",
)


components[
    "hydgrp"
] = (
    components[
        "hydgrp"
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


components.to_csv(
    component_file,
    index=False,
)


print(
    f"Component rows returned : "
    f"{len(components)}"
)

print(
    f"Components with HSG      : "
    f"{components['hydgrp'].notna().sum()}"
)

print(
    f"Components without HSG   : "
    f"{components['hydgrp'].isna().sum()}"
)


# =========================================================
# Build map-unit diagnostic summaries
# =========================================================

recovery_rows = []


for mukey in unrated_mukeys:

    subset = components[
        components[
            "mukey"
        ] == mukey
    ].copy()


    if subset.empty:

        recovery_rows.append({
            "mukey":
                mukey,

            "musym":
                None,

            "muname":
                None,

            "basin_area_km2":
                mapunit_area.get(
                    mukey,
                    np.nan,
                ),

            "component_count":
                0,

            "total_component_percent":
                0.0,

            "rated_component_percent":
                0.0,

            "unrated_component_percent":
                0.0,

            "dominant_component_hsg":
                None,

            "dominant_hsg_percent":
                0.0,

            "second_hsg_percent":
                0.0,

            "diagnostic_status":
                "NO_COMPONENT_DATA",
        })

        continue


    musym = subset[
        "musym"
    ].iloc[0]

    muname = subset[
        "muname"
    ].iloc[0]


    component_percent = (
        subset[
            "comppct_r"
        ]
        .fillna(
            0
        )
    )


    total_component_percent = float(
        component_percent.sum()
    )


    rated_subset = subset[
        subset[
            "hydgrp"
        ].notna()
    ].copy()


    rated_component_percent = float(
        rated_subset[
            "comppct_r"
        ]
        .fillna(
            0
        )
        .sum()
    )


    unrated_component_percent = (
        total_component_percent
        -
        rated_component_percent
    )


    # -----------------------------------------------------
    # Aggregate component percentages by HSG.
    # -----------------------------------------------------

    if rated_subset.empty:

        dominant_hsg = None
        dominant_percent = 0.0
        second_percent = 0.0

        status = (
            "NO_COMPONENT_HSG"
        )

    else:

        group_totals = (
            rated_subset
            .groupby(
                "hydgrp"
            )[
                "comppct_r"
            ]
            .sum()
            .sort_values(
                ascending=False
            )
        )


        dominant_hsg = (
            group_totals
            .index[0]
        )


        dominant_percent = float(
            group_totals
            .iloc[0]
        )


        if len(group_totals) > 1:

            second_percent = float(
                group_totals
                .iloc[1]
            )

        else:

            second_percent = 0.0


        # Diagnostic classifications only.
        #
        # No raster modification occurs here.

        if (
            rated_component_percent
            >= 75
            and
            dominant_percent
            >= 50
        ):

            status = (
                "STRONG_COMPONENT_EVIDENCE"
            )

        elif (
            rated_component_percent
            >= 50
        ):

            status = (
                "MODERATE_COMPONENT_EVIDENCE"
            )

        else:

            status = (
                "WEAK_COMPONENT_EVIDENCE"
            )


    recovery_rows.append({

        "mukey":
            mukey,

        "musym":
            musym,

        "muname":
            muname,

        "basin_area_km2":
            mapunit_area.get(
                mukey,
                np.nan,
            ),

        "component_count":
            len(subset),

        "total_component_percent":
            total_component_percent,

        "rated_component_percent":
            rated_component_percent,

        "unrated_component_percent":
            unrated_component_percent,

        "dominant_component_hsg":
            dominant_hsg,

        "dominant_hsg_percent":
            dominant_percent,

        "second_hsg_percent":
            second_percent,

        "diagnostic_status":
            status,
    })


recovery = pd.DataFrame(
    recovery_rows
)


recovery = (
    recovery
    .sort_values(
        "basin_area_km2",
        ascending=False,
    )
    .reset_index(
        drop=True
    )
)


recovery.to_csv(
    recovery_file,
    index=False,
)


# =========================================================
# Terminal report
# =========================================================

print()
print("=" * 78)
print("UNRATED MAP-UNIT RECOVERY AUDIT")
print("=" * 78)

print()


display_columns = [
    "mukey",
    "musym",
    "muname",
    "basin_area_km2",
    "rated_component_percent",
    "dominant_component_hsg",
    "dominant_hsg_percent",
    "diagnostic_status",
]


print(
    recovery[
        display_columns
    ]
    .to_string(
        index=False,
        formatters={
            "basin_area_km2":
                "{:.2f}".format,

            "rated_component_percent":
                "{:.1f}".format,

            "dominant_hsg_percent":
                "{:.1f}".format,
        },
    )
)


# =========================================================
# Basin-area summary by evidence category
# =========================================================

status_summary = (
    recovery
    .groupby(
        "diagnostic_status"
    )[
        "basin_area_km2"
    ]
    .sum()
    .reset_index()
)


print()
print("=" * 78)
print("EVIDENCE SUMMARY")
print("=" * 78)

print(
    status_summary.to_string(
        index=False,
        formatters={
            "basin_area_km2":
                "{:.2f}".format,
        },
    )
)


# =========================================================
# Metadata
# =========================================================

metadata = {

    "station":
        f"USGS-{station_id}",

    "unrated_mapunit_count":
        len(unrated_mukeys),

    "method":
        (
            "Diagnostic aggregation of "
            "SSURGO component.hydgrp "
            "using component.comppct_r"
        ),

    "automatic_imputation":
        False,

    "status_definition": {

        "STRONG_COMPONENT_EVIDENCE":
            (
                ">=75% of map unit component "
                "percentage has HSG ratings "
                "and dominant HSG >=50%"
            ),

        "MODERATE_COMPONENT_EVIDENCE":
            (
                ">=50% of component percentage "
                "has HSG ratings"
            ),

        "WEAK_COMPONENT_EVIDENCE":
            (
                "<50% of component percentage "
                "has HSG ratings"
            ),

        "NO_COMPONENT_HSG":
            (
                "Components exist but contain "
                "no HSG ratings"
            ),
    },

    "scientific_status":
        (
            "diagnostic only; unresolved map-unit "
            "HSGs have not yet been modified"
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


print()
print("=" * 78)
print("FILES CREATED")
print("=" * 78)

print(component_file)
print(recovery_file)
print(metadata_file)


print()
print("=" * 78)
print("Stage 3D-2C3 COMPLETE")
print("=" * 78)

print()
print(
    "No HSG raster values have been modified."
)

print(
    "No Curve Number has been calculated."
)
"""
Stage 3A-4
Quality-control raw USGS continuous discharge observations.

Station:
USGS 02361000

Parameter:
00060 = discharge

Objectives:
1. Read all raw USGS API pages.
2. Preserve raw observations unchanged.
3. Identify time-series IDs.
4. Check units.
5. Check timestamps.
6. Identify duplicate observations.
7. Identify missing/null values.
8. Determine actual sampling intervals.
9. Identify temporal gaps.
10. Summarize coverage by year.
11. Create an interim combined dataset and QC outputs.

IMPORTANT:
No gap filling, interpolation, resampling, or unit conversion
is performed in this script.
"""

from pathlib import Path
import json
from collections import Counter

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml


# =========================================================
# Project paths
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

raw_dir = (
    PROJECT_ROOT
    / config["paths"]["raw_discharge"]
)

interim_dir = (
    PROJECT_ROOT
    / config["paths"]["interim_discharge"]
)

results_dir = (
    PROJECT_ROOT
    / "results"
    / "tables"
)

figures_dir = (
    PROJECT_ROOT
    / "figures"
    / "hydrographs"
)


interim_dir.mkdir(parents=True, exist_ok=True)
results_dir.mkdir(parents=True, exist_ok=True)
figures_dir.mkdir(parents=True, exist_ok=True)


# =========================================================
# Locate raw files
# =========================================================

pattern = (
    f"USGS_{station_id}_00060_"
    "continuous_*_page*.geojson"
)

raw_files = sorted(
    raw_dir.glob(pattern)
)


print("=" * 72)
print("Stage 3A-4: USGS discharge quality control")
print("=" * 72)

print(f"Station            : USGS-{station_id}")
print(f"Raw directory      : {raw_dir}")
print(f"Raw API files found: {len(raw_files)}")


if not raw_files:
    raise SystemExit(
        "ERROR: No raw discharge files were found."
    )


# =========================================================
# Helper functions
# =========================================================

def first_available(dictionary, *keys):
    """Return first existing field among possible API names."""

    for key in keys:
        if key in dictionary:
            return dictionary[key]

    return None


def normalize_list_field(value):
    """Convert list/string/null metadata to readable text."""

    if value is None:
        return None

    if isinstance(value, list):
        return ";".join(str(x) for x in value)

    return str(value)


# =========================================================
# Read observations
# =========================================================

rows = []


for file_path in raw_files:

    with open(
        file_path,
        "r",
        encoding="utf-8",
    ) as file:

        data = json.load(file)


    features = data.get("features", [])


    for feature in features:

        props = feature.get(
            "properties",
            {},
        )


        # USGS documentation has used slightly different
        # spellings across API versions/documentation.
        # Supporting both prevents brittle parsing.

        time_series_id = first_available(
            props,
            "time_series_id",
            "timeseries_id",
        )

        approval_status = first_available(
            props,
            "approval_status",
            "approvals_status",
        )


        rows.append({

            "observation_id":
                feature.get("id"),

            "time_series_id":
                time_series_id,

            "monitoring_location_id":
                props.get(
                    "monitoring_location_id"
                ),

            "parameter_code":
                props.get(
                    "parameter_code"
                ),

            "time":
                props.get("time"),

            "value_raw":
                props.get("value"),

            "unit_of_measure":
                props.get(
                    "unit_of_measure"
                ),

            "approval_status":
                normalize_list_field(
                    approval_status
                ),

            "qualifier":
                normalize_list_field(
                    props.get("qualifier")
                ),

            "last_modified":
                props.get(
                    "last_modified"
                ),

            "source_file":
                file_path.name,
        })


# =========================================================
# Create dataframe
# =========================================================

df = pd.DataFrame(rows)


print()
print(f"Observations loaded : {len(df):,}")


# =========================================================
# Parse timestamps and values
# =========================================================

df["time_utc"] = pd.to_datetime(
    df["time"],
    utc=True,
    errors="coerce",
)


df["value_numeric"] = pd.to_numeric(
    df["value_raw"],
    errors="coerce",
)


# =========================================================
# Basic metadata checks
# =========================================================

print()
print("=" * 72)
print("BASIC METADATA")
print("=" * 72)


print()
print("Monitoring location IDs:")

print(
    df["monitoring_location_id"]
    .value_counts(
        dropna=False
    )
    .to_string()
)


print()
print("Parameter codes:")

print(
    df["parameter_code"]
    .value_counts(
        dropna=False
    )
    .to_string()
)


print()
print("Units:")

print(
    df["unit_of_measure"]
    .value_counts(
        dropna=False
    )
    .to_string()
)


print()
print("Time-series IDs:")

print(
    df["time_series_id"]
    .value_counts(
        dropna=False
    )
    .to_string()
)


print()
print("Approval status:")

print(
    df["approval_status"]
    .value_counts(
        dropna=False
    )
    .to_string()
)


print()
print("Qualifiers:")

print(
    df["qualifier"]
    .value_counts(
        dropna=False
    )
    .head(20)
    .to_string()
)


# =========================================================
# Invalid / missing values
# =========================================================

invalid_timestamp_count = (
    df["time_utc"]
    .isna()
    .sum()
)

missing_value_count = (
    df["value_numeric"]
    .isna()
    .sum()
)

negative_value_count = (
    (
        df["value_numeric"] < 0
    )
    .sum()
)


print()
print("=" * 72)
print("VALUE CHECKS")
print("=" * 72)

print(
    f"Invalid timestamps : "
    f"{invalid_timestamp_count:,}"
)

print(
    f"Missing/non-numeric values : "
    f"{missing_value_count:,}"
)

print(
    f"Negative discharge values  : "
    f"{negative_value_count:,}"
)


# =========================================================
# Duplicate checks
# =========================================================

duplicate_observation_ids = (
    df["observation_id"]
    .duplicated()
    .sum()
)


duplicate_series_times = (
    df.duplicated(
        subset=[
            "time_series_id",
            "time_utc",
        ],
        keep=False,
    )
)


duplicate_series_time_count = (
    duplicate_series_times.sum()
)


print()
print("=" * 72)
print("DUPLICATE CHECKS")
print("=" * 72)

print(
    f"Duplicate observation IDs      : "
    f"{duplicate_observation_ids:,}"
)

print(
    f"Rows sharing series + timestamp: "
    f"{duplicate_series_time_count:,}"
)


# =========================================================
# Clean subset ONLY for QC calculations
# =========================================================

valid_df = df[
    df["time_utc"].notna()
].copy()


valid_df = valid_df.sort_values(
    [
        "time_series_id",
        "time_utc",
    ]
)


valid_df["year"] = (
    valid_df["time_utc"]
    .dt.year
)


# =========================================================
# Sampling interval analysis
# =========================================================

valid_df["interval_minutes"] = (

    valid_df
    .groupby(
        "time_series_id",
        dropna=False,
    )["time_utc"]
    .diff()
    .dt.total_seconds()
    / 60
)


# Exclude zero/negative differences from interval summaries.

positive_intervals = valid_df[
    valid_df["interval_minutes"] > 0
].copy()


print()
print("=" * 72)
print("SAMPLING INTERVALS")
print("=" * 72)


interval_rows = []


for year in sorted(
    valid_df["year"]
    .dropna()
    .unique()
):

    year_intervals = (
        positive_intervals.loc[
            positive_intervals["year"] == year,
            "interval_minutes",
        ]
    )


    counts = Counter(
        year_intervals.round(3)
    )


    most_common = counts.most_common(8)


    print()
    print(f"{int(year)}:")

    if len(year_intervals) == 0:

        print("  No interval information.")

        continue


    median_interval = (
        year_intervals.median()
    )

    mode_interval = (
        year_intervals
        .round(3)
        .mode()
        .iloc[0]
    )


    print(
        f"  Median interval : "
        f"{median_interval:.2f} minutes"
    )

    print(
        f"  Modal interval  : "
        f"{mode_interval:.2f} minutes"
    )

    print(
        "  Most common intervals:"
    )


    for interval, count in most_common:

        print(
            f"    {interval:8.2f} min : "
            f"{count:,}"
        )


    interval_rows.append({

        "year":
            int(year),

        "median_interval_minutes":
            median_interval,

        "modal_interval_minutes":
            mode_interval,

        "interval_count":
            len(year_intervals),
    })


interval_summary = pd.DataFrame(
    interval_rows
)


# =========================================================
# Annual observation summary
# =========================================================

annual_rows = []


for year in sorted(
    valid_df["year"]
    .dropna()
    .unique()
):

    subset = valid_df[
        valid_df["year"] == year
    ]


    non_null = (
        subset["value_numeric"]
        .notna()
        .sum()
    )


    null_count = (
        subset["value_numeric"]
        .isna()
        .sum()
    )


    annual_rows.append({

        "year":
            int(year),

        "observations":
            len(subset),

        "valid_numeric_values":
            int(non_null),

        "missing_values":
            int(null_count),

        "first_timestamp":
            subset["time_utc"]
            .min()
            .isoformat(),

        "last_timestamp":
            subset["time_utc"]
            .max()
            .isoformat(),

        "time_series_count":
            subset[
                "time_series_id"
            ]
            .nunique(
                dropna=False
            ),
    })


annual_summary = pd.DataFrame(
    annual_rows
)


# Add cadence information

annual_summary = annual_summary.merge(
    interval_summary,
    on="year",
    how="left",
)


# =========================================================
# Gap analysis
# =========================================================

gap_rows = []


for series_id, series in (
    valid_df.groupby(
        "time_series_id",
        dropna=False,
    )
):

    series = series.sort_values(
        "time_utc"
    ).copy()


    for year, year_data in (
        series.groupby("year")
    ):

        intervals = (
            year_data["interval_minutes"]
            .dropna()
        )

        intervals = intervals[
            intervals > 0
        ]


        if intervals.empty:
            continue


        modal_interval = (
            intervals
            .round(3)
            .mode()
            .iloc[0]
        )


        # A gap is flagged when the interval is more
        # than 1.5 times the dominant cadence.
        #
        # This does NOT mean missing data will be filled.

        gap_threshold = (
            modal_interval * 1.5
        )


        gaps = year_data[
            year_data["interval_minutes"]
            > gap_threshold
        ]


        for _, row in gaps.iterrows():

            gap_rows.append({

                "time_series_id":
                    series_id,

                "year":
                    int(year),

                "gap_end":
                    row[
                        "time_utc"
                    ].isoformat(),

                "gap_minutes":
                    row[
                        "interval_minutes"
                    ],

                "dominant_interval_minutes":
                    modal_interval,
            })


gap_df = pd.DataFrame(
    gap_rows
)


# =========================================================
# Print annual summary
# =========================================================

print()
print("=" * 72)
print("ANNUAL COVERAGE SUMMARY")
print("=" * 72)

print()

display_columns = [
    "year",
    "observations",
    "valid_numeric_values",
    "missing_values",
    "time_series_count",
    "median_interval_minutes",
    "modal_interval_minutes",
]


print(
    annual_summary[
        display_columns
    ].to_string(
        index=False
    )
)


# =========================================================
# Print gap summary
# =========================================================

print()
print("=" * 72)
print("GAP SUMMARY")
print("=" * 72)


if gap_df.empty:

    print(
        "No intervals exceeding the "
        "year-specific gap threshold."
    )

else:

    gap_summary = (
        gap_df
        .groupby("year")
        .agg(
            flagged_gaps=(
                "gap_minutes",
                "count",
            ),

            largest_gap_minutes=(
                "gap_minutes",
                "max",
            ),
        )
        .reset_index()
    )


    print()
    print(
        gap_summary.to_string(
            index=False
        )
    )


# =========================================================
# Save interim combined observations
# =========================================================

interim_file = (
    interim_dir
    / (
        f"USGS_{station_id}_"
        "00060_continuous_combined_interim.csv"
    )
)


save_columns = [
    "observation_id",
    "time_series_id",
    "monitoring_location_id",
    "parameter_code",
    "time",
    "time_utc",
    "value_raw",
    "value_numeric",
    "unit_of_measure",
    "approval_status",
    "qualifier",
    "last_modified",
    "source_file",
]


df[
    save_columns
].to_csv(
    interim_file,
    index=False,
)


# =========================================================
# Save QC tables
# =========================================================

annual_file = (
    results_dir
    / (
        f"USGS_{station_id}_"
        "discharge_annual_qc.csv"
    )
)


annual_summary.to_csv(
    annual_file,
    index=False,
)


interval_file = (
    results_dir
    / (
        f"USGS_{station_id}_"
        "discharge_interval_qc.csv"
    )
)


interval_summary.to_csv(
    interval_file,
    index=False,
)


gap_file = (
    results_dir
    / (
        f"USGS_{station_id}_"
        "discharge_gap_qc.csv"
    )
)


gap_df.to_csv(
    gap_file,
    index=False,
)


# =========================================================
# QC JSON summary
# =========================================================

qc_summary = {

    "station":
        f"USGS-{station_id}",

    "parameter_code":
        "00060",

    "total_observations":
        int(len(df)),

    "invalid_timestamps":
        int(
            invalid_timestamp_count
        ),

    "missing_or_non_numeric_values":
        int(
            missing_value_count
        ),

    "negative_discharge_values":
        int(
            negative_value_count
        ),

    "duplicate_observation_ids":
        int(
            duplicate_observation_ids
        ),

    "duplicate_series_timestamp_rows":
        int(
            duplicate_series_time_count
        ),

    "time_series_ids":
        sorted(
            [
                str(x)
                for x in
                df[
                    "time_series_id"
                ]
                .dropna()
                .unique()
            ]
        ),

    "units":
        sorted(
            [
                str(x)
                for x in
                df[
                    "unit_of_measure"
                ]
                .dropna()
                .unique()
            ]
        ),

    "scientific_status":
        "pending Stage 3A-4 review",
}


qc_json_file = (
    results_dir
    / (
        f"USGS_{station_id}_"
        "discharge_qc_summary.json"
    )
)


with open(
    qc_json_file,
    "w",
    encoding="utf-8",
) as file:

    json.dump(
        qc_summary,
        file,
        indent=2,
    )


# =========================================================
# Overview hydrograph
# =========================================================

plot_df = valid_df[
    valid_df["value_numeric"]
    .notna()
].copy()


fig, ax = plt.subplots(
    figsize=(14, 5)
)


ax.plot(
    plot_df["time_utc"],
    plot_df["value_numeric"],
    linewidth=0.35,
)


unit_values = (
    plot_df[
        "unit_of_measure"
    ]
    .dropna()
    .unique()
)


if len(unit_values) == 1:

    ylabel = (
        f"Discharge "
        f"({unit_values[0]})"
    )

else:

    ylabel = "Discharge"


ax.set_title(
    f"USGS {station_id} — Raw Continuous Discharge"
)

ax.set_xlabel(
    "Time (UTC)"
)

ax.set_ylabel(
    ylabel
)

ax.grid(
    True,
    linewidth=0.3,
)


plt.tight_layout()


hydrograph_file = (
    figures_dir
    / (
        f"USGS_{station_id}_"
        "raw_discharge_overview.png"
    )
)


plt.savefig(
    hydrograph_file,
    dpi=300,
    bbox_inches="tight",
)

plt.close()


# =========================================================
# Observation-count figure
# =========================================================

fig, ax = plt.subplots(
    figsize=(10, 5)
)


ax.bar(
    annual_summary["year"].astype(str),
    annual_summary["observations"],
)


ax.set_title(
    f"USGS {station_id} — "
    "Continuous Discharge Observations by Year"
)

ax.set_xlabel(
    "Year"
)

ax.set_ylabel(
    "Number of observations"
)


plt.tight_layout()


count_figure = (
    figures_dir
    / (
        f"USGS_{station_id}_"
        "annual_observation_counts.png"
    )
)


plt.savefig(
    count_figure,
    dpi=300,
    bbox_inches="tight",
)

plt.close()


# =========================================================
# Final report
# =========================================================

print()
print("=" * 72)
print("FILES CREATED")
print("=" * 72)

print()
print("Combined interim observations:")
print(interim_file)

print()
print("Annual QC:")
print(annual_file)

print()
print("Sampling interval QC:")
print(interval_file)

print()
print("Gap QC:")
print(gap_file)

print()
print("QC summary:")
print(qc_json_file)

print()
print("Hydrograph:")
print(hydrograph_file)

print()
print("Observation-count figure:")
print(count_figure)


print()
print("=" * 72)
print("Stage 3A-4 ANALYSIS COMPLETE")
print("=" * 72)

print()
print(
    "No observations were resampled, "
    "interpolated, gap-filled, or converted."
)

print(
    "Review the QC results before accepting "
    "the discharge dataset."
)
"""
Stage 3B-3
Final quality control of basin-average GPM IMERG V07 precipitation.

Period:
2018-01-01 through 2024-12-31

Objectives
----------
1. Verify all 84 monthly extraction files exist.
2. Combine them without modifying monthly source files.
3. Verify the complete 30-minute UTC timeline.
4. Check missing timestamps and duplicates.
5. Verify all observations are permanent IMERG products.
6. Check calibrated, uncalibrated, and random-error fields.
7. Verify mm/hr -> 30-minute depth conversion.
8. Produce monthly and annual rainfall summaries.
9. Quantify calibrated-vs-uncalibrated differences.
10. Produce a combined interim precipitation dataset.

No interpolation, bias correction, event selection, or HEC-HMS
processing is performed here.
"""

from pathlib import Path
import calendar
import json
import re

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

precip_dir = (
    PROJECT_ROOT
    / config["paths"]["interim_precipitation"]
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

results_dir.mkdir(parents=True, exist_ok=True)
figures_dir.mkdir(parents=True, exist_ok=True)


START_YEAR = 2018
END_YEAR = 2024


# =========================================================
# Locate monthly files
# =========================================================

file_pattern = re.compile(
    rf"^IMERG_V07_USGS_{station_id}_"
    r"(\d{4})_(\d{2})\.csv$"
)

monthly_files = []

for path in precip_dir.glob("*.csv"):

    match = file_pattern.match(path.name)

    if match:

        monthly_files.append(
            (
                int(match.group(1)),
                int(match.group(2)),
                path,
            )
        )


monthly_files.sort(
    key=lambda x: (x[0], x[1])
)


print("=" * 76)
print("Stage 3B-3: Final IMERG precipitation QC")
print("=" * 76)

print(f"Station                  : USGS-{station_id}")
print(f"Monthly files discovered : {len(monthly_files)}")
print(f"Expected monthly files   : 84")


# =========================================================
# Verify month inventory
# =========================================================

expected_months = {
    (year, month)
    for year in range(
        START_YEAR,
        END_YEAR + 1,
    )
    for month in range(1, 13)
}

actual_months = {
    (year, month)
    for year, month, _
    in monthly_files
}

missing_months = sorted(
    expected_months
    - actual_months
)

unexpected_months = sorted(
    actual_months
    - expected_months
)


if missing_months:

    print()
    print("ERROR: Missing monthly files:")

    for year, month in missing_months:
        print(f"  {year}-{month:02d}")

    raise SystemExit(1)


if unexpected_months:

    print()
    print("WARNING: Unexpected monthly files:")

    for year, month in unexpected_months:
        print(f"  {year}-{month:02d}")


if len(monthly_files) != 84:

    raise SystemExit(
        "ERROR: Expected exactly 84 monthly files."
    )


print("Monthly file inventory      : PASS")


# =========================================================
# Read monthly datasets
# =========================================================

frames = []
monthly_inventory_rows = []


for year, month, path in monthly_files:

    month_df = pd.read_csv(
        path,
        low_memory=False,
    )


    month_df["time_utc"] = pd.to_datetime(
        month_df["time_utc"],
        utc=True,
        errors="coerce",
    )


    expected_count = (
        calendar.monthrange(
            year,
            month,
        )[1]
        * 48
    )


    monthly_inventory_rows.append({
        "year":
            year,

        "month":
            month,

        "file":
            path.name,

        "expected_rows":
            expected_count,

        "actual_rows":
            len(month_df),
    })


    frames.append(month_df)


df = pd.concat(
    frames,
    ignore_index=True,
)


df = (
    df.sort_values("time_utc")
    .reset_index(drop=True)
)


print()
print(f"Combined rows              : {len(df):,}")


# =========================================================
# Parse numeric fields
# =========================================================

numeric_columns = [
    "precipitation_mm_hr",
    "precipitation_mm_30min",
    "precipitation_uncal_mm_hr",
    "precipitation_uncal_mm_30min",
    "random_error_mm_hr",
]


for column in numeric_columns:

    df[column] = pd.to_numeric(
        df[column],
        errors="coerce",
    )


# =========================================================
# Expected complete 30-minute timeline
# =========================================================

expected_index = pd.date_range(
    start="2018-01-01 00:00:00",
    end="2024-12-31 23:30:00",
    freq="30min",
    tz="UTC",
)


expected_total = len(
    expected_index
)


observed_index = pd.DatetimeIndex(
    df["time_utc"]
    .dropna()
)


unique_observed_index = pd.DatetimeIndex(
    df["time_utc"]
    .dropna()
    .drop_duplicates()
)


missing_timestamps = (
    expected_index
    .difference(
        unique_observed_index
    )
)


unexpected_timestamps = (
    unique_observed_index
    .difference(
        expected_index
    )
)


# =========================================================
# Timestamp checks
# =========================================================

invalid_timestamp_count = int(
    df["time_utc"].isna().sum()
)


duplicate_timestamp_count = int(
    df["time_utc"]
    .duplicated()
    .sum()
)


on_grid_mask = (
    df["time_utc"].notna()
    &
    df["time_utc"].dt.minute.isin(
        [0, 30]
    )
    &
    (df["time_utc"].dt.second == 0)
)


off_grid_count = int(
    (
        df["time_utc"].notna()
        &
        ~on_grid_mask
    ).sum()
)


interval_minutes = (
    df["time_utc"]
    .diff()
    .dt.total_seconds()
    / 60
)


median_interval = float(
    interval_minutes
    .dropna()
    .median()
)


modal_interval = float(
    interval_minutes
    .dropna()
    .mode()
    .iloc[0]
)


# =========================================================
# Product status
# =========================================================

status_counts = (
    df["status"]
    .value_counts(
        dropna=False
    )
)


non_permanent_count = int(
    (
        df["status"] != "permanent"
    ).sum()
)


# =========================================================
# Missing numeric values
# =========================================================

missing_numeric = {
    column: int(
        df[column]
        .isna()
        .sum()
    )
    for column in numeric_columns
}


# =========================================================
# Negative rainfall values
# =========================================================

negative_calibrated = int(
    (
        df["precipitation_mm_hr"] < 0
    ).sum()
)


negative_uncalibrated = int(
    (
        df[
            "precipitation_uncal_mm_hr"
        ] < 0
    ).sum()
)


# =========================================================
# Verify rate -> depth conversion
# =========================================================

cal_depth_expected = (
    df["precipitation_mm_hr"]
    * 0.5
)


uncal_depth_expected = (
    df[
        "precipitation_uncal_mm_hr"
    ]
    * 0.5
)


cal_conversion_ok = np.isclose(
    df["precipitation_mm_30min"],
    cal_depth_expected,
    equal_nan=True,
    rtol=1e-9,
    atol=1e-12,
)


uncal_conversion_ok = np.isclose(
    df[
        "precipitation_uncal_mm_30min"
    ],
    uncal_depth_expected,
    equal_nan=True,
    rtol=1e-9,
    atol=1e-12,
)


cal_conversion_failures = int(
    (~cal_conversion_ok).sum()
)


uncal_conversion_failures = int(
    (~uncal_conversion_ok).sum()
)


# =========================================================
# Add calendar fields for QC summaries
# =========================================================

df["year"] = (
    df["time_utc"].dt.year
)

df["month"] = (
    df["time_utc"].dt.month
)


# =========================================================
# Monthly QC summary
# =========================================================

monthly_inventory_df = pd.DataFrame(
    monthly_inventory_rows
)


monthly_summary = (
    df.groupby(
        ["year", "month"],
        as_index=False,
    )
    .agg(
        observations=(
            "time_utc",
            "count",
        ),

        calibrated_total_mm=(
            "precipitation_mm_30min",
            "sum",
        ),

        uncalibrated_total_mm=(
            "precipitation_uncal_mm_30min",
            "sum",
        ),

        zero_calibrated_intervals=(
            "precipitation_mm_30min",
            lambda x: int(
                (x == 0).sum()
            ),
        ),

        max_30min_depth_mm=(
            "precipitation_mm_30min",
            "max",
        ),

        max_rate_mm_hr=(
            "precipitation_mm_hr",
            "max",
        ),

        mean_random_error_mm_hr=(
            "random_error_mm_hr",
            "mean",
        ),
    )
)


monthly_summary = monthly_summary.merge(
    monthly_inventory_df[
        [
            "year",
            "month",
            "expected_rows",
        ]
    ],
    on=[
        "year",
        "month",
    ],
    how="left",
)


monthly_summary[
    "completeness_percent"
] = (
    monthly_summary[
        "observations"
    ]
    /
    monthly_summary[
        "expected_rows"
    ]
    * 100
)


monthly_summary[
    "cal_minus_uncal_mm"
] = (
    monthly_summary[
        "calibrated_total_mm"
    ]
    -
    monthly_summary[
        "uncalibrated_total_mm"
    ]
)


monthly_summary[
    "zero_rain_percent"
] = (
    monthly_summary[
        "zero_calibrated_intervals"
    ]
    /
    monthly_summary[
        "observations"
    ]
    * 100
)


# =========================================================
# Annual QC summary
# =========================================================

annual_summary = (
    df.groupby(
        "year",
        as_index=False,
    )
    .agg(
        observations=(
            "time_utc",
            "count",
        ),

        calibrated_total_mm=(
            "precipitation_mm_30min",
            "sum",
        ),

        uncalibrated_total_mm=(
            "precipitation_uncal_mm_30min",
            "sum",
        ),

        zero_calibrated_intervals=(
            "precipitation_mm_30min",
            lambda x: int(
                (x == 0).sum()
            ),
        ),

        max_30min_depth_mm=(
            "precipitation_mm_30min",
            "max",
        ),

        max_rate_mm_hr=(
            "precipitation_mm_hr",
            "max",
        ),

        mean_random_error_mm_hr=(
            "random_error_mm_hr",
            "mean",
        ),
    )
)


annual_summary[
    "expected_observations"
] = annual_summary[
    "year"
].apply(
    lambda year:
        (
            366 if calendar.isleap(int(year))
            else 365
        )
        * 48
)


annual_summary[
    "completeness_percent"
] = (
    annual_summary[
        "observations"
    ]
    /
    annual_summary[
        "expected_observations"
    ]
    * 100
)


annual_summary[
    "cal_minus_uncal_mm"
] = (
    annual_summary[
        "calibrated_total_mm"
    ]
    -
    annual_summary[
        "uncalibrated_total_mm"
    ]
)


annual_summary[
    "cal_minus_uncal_percent"
] = (
    annual_summary[
        "cal_minus_uncal_mm"
    ]
    /
    annual_summary[
        "uncalibrated_total_mm"
    ]
    * 100
)


annual_summary[
    "zero_rain_percent"
] = (
    annual_summary[
        "zero_calibrated_intervals"
    ]
    /
    annual_summary[
        "observations"
    ]
    * 100
)


# =========================================================
# Maximum rainfall observation
# =========================================================

max_idx = (
    df[
        "precipitation_mm_30min"
    ]
    .idxmax()
)


max_row = df.loc[
    max_idx
]


# =========================================================
# Print temporal QC
# =========================================================

print()
print("=" * 76)
print("TEMPORAL COMPLETENESS")
print("=" * 76)

print(
    f"Expected observations      : "
    f"{expected_total:,}"
)

print(
    f"Actual observations        : "
    f"{len(df):,}"
)

print(
    f"Unique timestamps          : "
    f"{len(unique_observed_index):,}"
)

print(
    f"Missing timestamps         : "
    f"{len(missing_timestamps):,}"
)

print(
    f"Unexpected timestamps      : "
    f"{len(unexpected_timestamps):,}"
)

print(
    f"Duplicate timestamps       : "
    f"{duplicate_timestamp_count:,}"
)

print(
    f"Invalid timestamps         : "
    f"{invalid_timestamp_count:,}"
)

print(
    f"Off 30-minute grid         : "
    f"{off_grid_count:,}"
)

print(
    f"Median interval            : "
    f"{median_interval:.1f} min"
)

print(
    f"Modal interval             : "
    f"{modal_interval:.1f} min"
)


# =========================================================
# Print product status
# =========================================================

print()
print("=" * 76)
print("PRODUCT STATUS")
print("=" * 76)

print()
print(
    status_counts.to_string()
)

print()
print(
    f"Non-permanent observations : "
    f"{non_permanent_count:,}"
)


# =========================================================
# Print numerical checks
# =========================================================

print()
print("=" * 76)
print("NUMERICAL CHECKS")
print("=" * 76)

for column, count in missing_numeric.items():

    print(
        f"Missing {column:35s}: "
        f"{count:,}"
    )


print()
print(
    f"Negative calibrated rates     : "
    f"{negative_calibrated:,}"
)

print(
    f"Negative uncalibrated rates   : "
    f"{negative_uncalibrated:,}"
)

print(
    f"Calibrated conversion failures: "
    f"{cal_conversion_failures:,}"
)

print(
    f"Uncalibrated conversion failures: "
    f"{uncal_conversion_failures:,}"
)


# =========================================================
# Print annual rainfall summary
# =========================================================

print()
print("=" * 76)
print("ANNUAL IMERG SUMMARY")
print("=" * 76)

print()

display_columns = [
    "year",
    "observations",
    "expected_observations",
    "completeness_percent",
    "calibrated_total_mm",
    "uncalibrated_total_mm",
    "cal_minus_uncal_mm",
    "cal_minus_uncal_percent",
    "zero_rain_percent",
    "max_30min_depth_mm",
]


print(
    annual_summary[
        display_columns
    ]
    .to_string(
        index=False,
        formatters={
            "completeness_percent":
                "{:.3f}".format,

            "calibrated_total_mm":
                "{:.2f}".format,

            "uncalibrated_total_mm":
                "{:.2f}".format,

            "cal_minus_uncal_mm":
                "{:+.2f}".format,

            "cal_minus_uncal_percent":
                "{:+.2f}".format,

            "zero_rain_percent":
                "{:.2f}".format,

            "max_30min_depth_mm":
                "{:.2f}".format,
        },
    )
)


print()
print("Maximum calibrated 30-minute rainfall:")

print(
    f"  Time  : "
    f"{max_row['time_utc']}"
)

print(
    f"  Depth : "
    f"{max_row['precipitation_mm_30min']:.3f} mm"
)

print(
    f"  Rate  : "
    f"{max_row['precipitation_mm_hr']:.3f} mm/hr"
)


# =========================================================
# Save combined interim series
# =========================================================

combined_file = (
    precip_dir
    / (
        f"IMERG_V07_USGS_{station_id}_"
        "2018_2024_combined_interim.csv"
    )
)


save_columns = [
    "time_utc",
    "status",
    "precipitation_mm_hr",
    "precipitation_mm_30min",
    "precipitation_uncal_mm_hr",
    "precipitation_uncal_mm_30min",
    "random_error_mm_hr",
]


df[
    save_columns
].to_csv(
    combined_file,
    index=False,
)


# =========================================================
# Save QC tables
# =========================================================

monthly_qc_file = (
    results_dir
    / (
        f"IMERG_V07_USGS_{station_id}_"
        "monthly_qc_2018_2024.csv"
    )
)


annual_qc_file = (
    results_dir
    / (
        f"IMERG_V07_USGS_{station_id}_"
        "annual_qc_2018_2024.csv"
    )
)


monthly_summary.to_csv(
    monthly_qc_file,
    index=False,
)


annual_summary.to_csv(
    annual_qc_file,
    index=False,
)


# =========================================================
# QC JSON summary
# =========================================================

qc_summary = {

    "station":
        f"USGS-{station_id}",

    "period":
        "2018-01-01 to 2024-12-31",

    "monthly_files":
        len(monthly_files),

    "expected_observations":
        expected_total,

    "actual_observations":
        int(len(df)),

    "unique_timestamps":
        int(
            len(unique_observed_index)
        ),

    "missing_timestamps":
        int(
            len(missing_timestamps)
        ),

    "unexpected_timestamps":
        int(
            len(unexpected_timestamps)
        ),

    "duplicate_timestamps":
        duplicate_timestamp_count,

    "invalid_timestamps":
        invalid_timestamp_count,

    "off_grid_timestamps":
        off_grid_count,

    "median_interval_minutes":
        median_interval,

    "modal_interval_minutes":
        modal_interval,

    "non_permanent_observations":
        non_permanent_count,

    "missing_numeric":
        missing_numeric,

    "negative_calibrated_rates":
        negative_calibrated,

    "negative_uncalibrated_rates":
        negative_uncalibrated,

    "calibrated_rate_depth_conversion_failures":
        cal_conversion_failures,

    "uncalibrated_rate_depth_conversion_failures":
        uncal_conversion_failures,

    "maximum_calibrated_30min": {

        "time_utc":
            str(
                max_row[
                    "time_utc"
                ]
            ),

        "depth_mm":
            float(
                max_row[
                    "precipitation_mm_30min"
                ]
            ),

        "rate_mm_hr":
            float(
                max_row[
                    "precipitation_mm_hr"
                ]
            ),
    },

    "scientific_status":
        "pending final Stage 3B review",
}


summary_file = (
    results_dir
    / (
        f"IMERG_V07_USGS_{station_id}_"
        "stage3B3_summary.json"
    )
)


with open(
    summary_file,
    "w",
    encoding="utf-8",
) as file:

    json.dump(
        qc_summary,
        file,
        indent=2,
    )


# =========================================================
# Annual rainfall figure
# =========================================================

fig, ax = plt.subplots(
    figsize=(9, 5)
)


ax.bar(
    annual_summary[
        "year"
    ].astype(str),

    annual_summary[
        "calibrated_total_mm"
    ],
)


ax.set_xlabel(
    "Year"
)

ax.set_ylabel(
    "IMERG precipitation (mm)"
)

ax.set_title(
    "Annual Basin-Average GPM IMERG V07 Precipitation"
)


plt.tight_layout()


annual_figure = (
    figures_dir
    / (
        f"IMERG_V07_USGS_{station_id}_"
        "annual_precipitation_2018_2024.png"
    )
)


plt.savefig(
    annual_figure,
    dpi=300,
    bbox_inches="tight",
)

plt.close()


# =========================================================
# Daily rainfall overview
# =========================================================

daily_rainfall = (
    df.set_index(
        "time_utc"
    )[
        "precipitation_mm_30min"
    ]
    .resample("D")
    .sum()
)


fig, ax = plt.subplots(
    figsize=(14, 5)
)


ax.plot(
    daily_rainfall.index,
    daily_rainfall.values,
    linewidth=0.5,
)


ax.set_xlabel(
    "Time (UTC)"
)

ax.set_ylabel(
    "Daily IMERG precipitation (mm)"
)

ax.set_title(
    "Basin-Average GPM IMERG V07 Daily Precipitation"
)


plt.tight_layout()


daily_figure = (
    figures_dir
    / (
        f"IMERG_V07_USGS_{station_id}_"
        "daily_precipitation_overview.png"
    )
)


plt.savefig(
    daily_figure,
    dpi=300,
    bbox_inches="tight",
)

plt.close()


# =========================================================
# Final report
# =========================================================

print()
print("=" * 76)
print("FILES CREATED")
print("=" * 76)

print()
print("Combined interim rainfall:")
print(combined_file)

print()
print("Monthly QC:")
print(monthly_qc_file)

print()
print("Annual QC:")
print(annual_qc_file)

print()
print("QC summary:")
print(summary_file)

print()
print("Annual rainfall figure:")
print(annual_figure)

print()
print("Daily rainfall figure:")
print(daily_figure)


print()
print("=" * 76)
print("Stage 3B-3 ANALYSIS COMPLETE")
print("=" * 76)

print()
print(
    "No interpolation, bias correction, "
    "event extraction, or temporal resampling "
    "was performed."
)

print(
    "Review QC results before accepting "
    "the IMERG precipitation record."
)
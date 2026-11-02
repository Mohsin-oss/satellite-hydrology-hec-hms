"""
Stage 3C-1
Rainfall-event separation sensitivity analysis.

Purpose
-------
Identify candidate GPM IMERG rainfall events using several
minimum inter-event dry periods (IETDs).

This stage does NOT select final rainfall-runoff events.

IETDs tested:
- 6 hours
- 12 hours
- 24 hours

Rain/no-rain threshold:
0.1 mm/hr

Because IMERG is half-hourly, this corresponds to
0.05 mm per 30-minute interval.

No discharge data are used yet.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
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

with open(CONFIG_FILE, "r", encoding="utf-8") as file:
    config = yaml.safe_load(file)


station_id = config["catchment"]["usgs_station"]


precip_file = (
    PROJECT_ROOT
    / config["paths"]["interim_precipitation"]
    / (
        f"IMERG_V07_USGS_{station_id}_"
        "2018_2024_combined_interim.csv"
    )
)


results_dir = (
    PROJECT_ROOT
    / "results"
    / "event_catalog"
)

figures_dir = (
    PROJECT_ROOT
    / "figures"
    / "diagnostics"
)


results_dir.mkdir(parents=True, exist_ok=True)
figures_dir.mkdir(parents=True, exist_ok=True)


# =========================================================
# Event-definition parameters
# =========================================================

TIMESTEP_MINUTES = 30

WET_RATE_THRESHOLD_MM_HR = 0.1

WET_DEPTH_THRESHOLD_MM = (
    WET_RATE_THRESHOLD_MM_HR
    * TIMESTEP_MINUTES
    / 60
)


IETD_HOURS_LIST = [
    6,
    12,
    24,
]


SUMMARY_DEPTH_THRESHOLDS_MM = [
    1,
    5,
    10,
    20,
    50,
]


# =========================================================
# Load precipitation
# =========================================================

print("=" * 76)
print("Stage 3C-1: Rainfall-event separation sensitivity")
print("=" * 76)

print(f"Station       : USGS-{station_id}")
print(f"Rainfall file : {precip_file}")

if not precip_file.exists():

    raise SystemExit(
        "ERROR: Combined IMERG precipitation file not found."
    )


df = pd.read_csv(
    precip_file,
    low_memory=False,
)


df["time_utc"] = pd.to_datetime(
    df["time_utc"],
    utc=True,
    errors="coerce",
)


df["precipitation_mm_30min"] = pd.to_numeric(
    df["precipitation_mm_30min"],
    errors="coerce",
)


df["precipitation_mm_hr"] = pd.to_numeric(
    df["precipitation_mm_hr"],
    errors="coerce",
)


df[
    "precipitation_uncal_mm_30min"
] = pd.to_numeric(
    df[
        "precipitation_uncal_mm_30min"
    ],
    errors="coerce",
)


df = (
    df.sort_values("time_utc")
    .reset_index(drop=True)
)


# =========================================================
# Preconditions
# =========================================================

if df["time_utc"].isna().any():

    raise SystemExit(
        "ERROR: Invalid precipitation timestamps detected."
    )


if df["precipitation_mm_30min"].isna().any():

    raise SystemExit(
        "ERROR: Missing calibrated precipitation detected."
    )


if df["time_utc"].duplicated().any():

    raise SystemExit(
        "ERROR: Duplicate precipitation timestamps detected."
    )


print()
print(f"Observations                 : {len(df):,}")
print(
    f"Wet-rate threshold           : "
    f"{WET_RATE_THRESHOLD_MM_HR:.3f} mm/hr"
)

print(
    f"Equivalent 30-min threshold  : "
    f"{WET_DEPTH_THRESHOLD_MM:.3f} mm"
)


# =========================================================
# Wet/dry classification
# =========================================================

df["is_wet"] = (
    df["precipitation_mm_hr"]
    >= WET_RATE_THRESHOLD_MM_HR
)


print(
    f"Wet intervals                : "
    f"{df['is_wet'].sum():,}"
)

print(
    f"Dry intervals                : "
    f"{(~df['is_wet']).sum():,}"
)


# =========================================================
# Antecedent rainfall helper
# =========================================================

precip_series = (
    df.set_index("time_utc")[
        "precipitation_mm_30min"
    ]
)


def antecedent_rainfall(event_start, hours):
    """
    Sum precipitation immediately before event start.
    """

    window_start = (
        event_start
        - pd.Timedelta(hours=hours)
    )

    subset = precip_series.loc[
        (precip_series.index >= window_start)
        &
        (precip_series.index < event_start)
    ]

    return float(subset.sum())


# =========================================================
# Build event record
# =========================================================

def make_event(
    event_number,
    start_idx,
    end_idx,
    ietd_hours,
):

    subset = df.iloc[
        start_idx:end_idx + 1
    ].copy()


    start_time = (
        subset.iloc[0]["time_utc"]
    )

    end_time = (
        subset.iloc[-1]["time_utc"]
    )


    duration_hours = (
        (
            end_time
            - start_time
        ).total_seconds()
        / 3600
        + 0.5
    )


    wet_intervals = int(
        subset["is_wet"].sum()
    )


    rain_duration_hours = (
        wet_intervals
        * 0.5
    )


    total_mm = float(
        subset[
            "precipitation_mm_30min"
        ].sum()
    )


    uncal_total_mm = float(
        subset[
            "precipitation_uncal_mm_30min"
        ].sum()
    )


    max_depth_idx = (
        subset[
            "precipitation_mm_30min"
        ].idxmax()
    )


    peak_row = df.loc[
        max_depth_idx
    ]


    if uncal_total_mm != 0:

        cal_uncal_percent = (
            (
                total_mm
                - uncal_total_mm
            )
            /
            uncal_total_mm
            * 100
        )

    else:

        cal_uncal_percent = np.nan


    return {

        "event_id":
            (
                f"IETD{ietd_hours:02d}_"
                f"E{event_number:04d}"
            ),

        "ietd_hours":
            ietd_hours,

        "start_utc":
            start_time,

        "end_utc":
            end_time,

        "year":
            int(start_time.year),

        "duration_hours":
            duration_hours,

        "wet_intervals":
            wet_intervals,

        "rain_duration_hours":
            rain_duration_hours,

        "total_rainfall_mm":
            total_mm,

        "uncalibrated_total_mm":
            uncal_total_mm,

        "cal_minus_uncal_mm":
            total_mm
            - uncal_total_mm,

        "cal_minus_uncal_percent":
            cal_uncal_percent,

        "maximum_30min_depth_mm":
            float(
                peak_row[
                    "precipitation_mm_30min"
                ]
            ),

        "maximum_rate_mm_hr":
            float(
                peak_row[
                    "precipitation_mm_hr"
                ]
            ),

        "peak_rainfall_time_utc":
            peak_row[
                "time_utc"
            ],

        "antecedent_24h_mm":
            antecedent_rainfall(
                start_time,
                24,
            ),

        "antecedent_72h_mm":
            antecedent_rainfall(
                start_time,
                72,
            ),

        "antecedent_7day_mm":
            antecedent_rainfall(
                start_time,
                24 * 7,
            ),
    }


# =========================================================
# Event separation
# =========================================================

def identify_events(ietd_hours):
    """
    Separate rainfall events using a required consecutive
    dry period.

    Example:
    IETD = 6 h
    timestep = 30 min
    required dry intervals = 12

    An event closes only after 12 consecutive dry intervals.
    """

    required_dry_steps = int(
        ietd_hours
        * 60
        / TIMESTEP_MINUTES
    )


    events = []

    event_start_idx = None
    last_wet_idx = None
    dry_steps = 0

    event_number = 0


    for idx in range(len(df)):

        wet = bool(
            df.iloc[idx]["is_wet"]
        )


        if wet:

            if event_start_idx is None:

                event_start_idx = idx


            last_wet_idx = idx
            dry_steps = 0


        else:

            if event_start_idx is not None:

                dry_steps += 1


                if dry_steps >= required_dry_steps:

                    event_number += 1


                    events.append(
                        make_event(
                            event_number,
                            event_start_idx,
                            last_wet_idx,
                            ietd_hours,
                        )
                    )


                    event_start_idx = None
                    last_wet_idx = None
                    dry_steps = 0


    # Close an event still active at end of record.

    if (
        event_start_idx is not None
        and
        last_wet_idx is not None
    ):

        event_number += 1


        events.append(
            make_event(
                event_number,
                event_start_idx,
                last_wet_idx,
                ietd_hours,
            )
        )


    return pd.DataFrame(events)


# =========================================================
# Run IETD sensitivity analysis
# =========================================================

summary_rows = []

event_catalogs = {}


for ietd_hours in IETD_HOURS_LIST:

    print()
    print("=" * 76)
    print(
        f"IETD = {ietd_hours} hours"
    )
    print("=" * 76)


    events = identify_events(
        ietd_hours
    )


    event_catalogs[
        ietd_hours
    ] = events


    print(
        f"Events identified: "
        f"{len(events):,}"
    )


    if events.empty:
        continue


    summary = {

        "ietd_hours":
            ietd_hours,

        "number_of_events":
            len(events),

        "median_event_total_mm":
            events[
                "total_rainfall_mm"
            ].median(),

        "mean_event_total_mm":
            events[
                "total_rainfall_mm"
            ].mean(),

        "maximum_event_total_mm":
            events[
                "total_rainfall_mm"
            ].max(),

        "median_duration_hours":
            events[
                "duration_hours"
            ].median(),

        "maximum_duration_hours":
            events[
                "duration_hours"
            ].max(),
    }


    for threshold in (
        SUMMARY_DEPTH_THRESHOLDS_MM
    ):

        count = int(
            (
                events[
                    "total_rainfall_mm"
                ]
                >= threshold
            ).sum()
        )


        summary[
            f"events_ge_{threshold}mm"
        ] = count


    summary_rows.append(
        summary
    )


    print(
        f"Median event rainfall : "
        f"{summary['median_event_total_mm']:.2f} mm"
    )

    print(
        f"Maximum event rainfall: "
        f"{summary['maximum_event_total_mm']:.2f} mm"
    )


    for threshold in (
        SUMMARY_DEPTH_THRESHOLDS_MM
    ):

        print(
            f"Events >= {threshold:>2} mm    : "
            f"{summary[f'events_ge_{threshold}mm']:,}"
        )


    # -----------------------------------------------------
    # Save full event catalog
    # -----------------------------------------------------

    catalog_file = (
        results_dir
        / (
            f"IMERG_rainfall_events_"
            f"IETD_{ietd_hours:02d}h.csv"
        )
    )


    events.to_csv(
        catalog_file,
        index=False,
    )


    # -----------------------------------------------------
    # Save largest 25 events
    # -----------------------------------------------------

    largest_file = (
        results_dir
        / (
            f"IMERG_top25_events_"
            f"IETD_{ietd_hours:02d}h.csv"
        )
    )


    (
        events.sort_values(
            "total_rainfall_mm",
            ascending=False,
        )
        .head(25)
        .to_csv(
            largest_file,
            index=False,
        )
    )


# =========================================================
# Sensitivity summary
# =========================================================

summary_df = pd.DataFrame(
    summary_rows
)


summary_file = (
    results_dir
    / (
        "IMERG_event_separation_"
        "sensitivity_summary.csv"
    )
)


summary_df.to_csv(
    summary_file,
    index=False,
)


# =========================================================
# Annual counts
# =========================================================

annual_count_rows = []


for ietd_hours, events in (
    event_catalogs.items()
):

    counts = (
        events.groupby("year")
        .size()
    )


    for year, count in counts.items():

        annual_count_rows.append({

            "ietd_hours":
                ietd_hours,

            "year":
                int(year),

            "event_count":
                int(count),
        })


annual_counts = pd.DataFrame(
    annual_count_rows
)


annual_count_file = (
    results_dir
    / (
        "IMERG_event_counts_"
        "by_year_and_IETD.csv"
    )
)


annual_counts.to_csv(
    annual_count_file,
    index=False,
)


# =========================================================
# Print comparison
# =========================================================

print()
print("=" * 76)
print("IETD SENSITIVITY SUMMARY")
print("=" * 76)

print()

print(
    summary_df.to_string(
        index=False,
        formatters={
            "median_event_total_mm":
                "{:.2f}".format,

            "mean_event_total_mm":
                "{:.2f}".format,

            "maximum_event_total_mm":
                "{:.2f}".format,

            "median_duration_hours":
                "{:.2f}".format,

            "maximum_duration_hours":
                "{:.2f}".format,
        },
    )
)


# =========================================================
# Event-count sensitivity figure
# =========================================================

fig, ax = plt.subplots(
    figsize=(8, 5)
)


ax.plot(
    summary_df["ietd_hours"],
    summary_df["number_of_events"],
    marker="o",
)


ax.set_xlabel(
    "Minimum inter-event dry period (hours)"
)

ax.set_ylabel(
    "Number of rainfall events"
)

ax.set_title(
    "Sensitivity of IMERG Event Count to IETD"
)


plt.tight_layout()


figure_file = (
    figures_dir
    / (
        "IMERG_event_count_"
        "IETD_sensitivity.png"
    )
)


plt.savefig(
    figure_file,
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
print("Sensitivity summary:")
print(summary_file)

print()
print("Annual event counts:")
print(annual_count_file)

print()
print("IETD sensitivity figure:")
print(figure_file)

print()
print(
    "Individual event catalogs and top-25 tables "
    "were written to:"
)

print(results_dir)


print()
print("=" * 76)
print("Stage 3C-1 ANALYSIS COMPLETE")
print("=" * 76)

print()
print(
    "No final IETD has been selected."
)

print(
    "No rainfall events have yet been accepted "
    "for HEC-HMS calibration or validation."
)

print(
    "Next step: review event-separation sensitivity "
    "and then link candidate rainfall events to "
    "observed discharge."
)
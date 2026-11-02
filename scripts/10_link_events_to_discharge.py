"""
Stage 3C-2
Link 12-hour-IETD IMERG rainfall events to observed USGS discharge.

This is a screening stage.

Objectives
----------
1. Link every IETD-12 rainfall event with observed discharge.
2. Quantify discharge-data completeness around each event.
3. Identify discharge gaps and estimated observations.
4. Calculate pre-event discharge and post-event peak discharge.
5. Calculate rainfall-to-discharge timing metrics.
6. Identify potentially confounding subsequent rainfall.
7. Produce candidate-event tables for later scientific selection.

IMPORTANT
---------
No calibration is performed.
No discharge is interpolated.
No rainfall is altered.
No event is finally accepted or rejected here.
"""

from pathlib import Path
import json

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


# =========================================================
# Input files
# =========================================================

event_file = (
    PROJECT_ROOT
    / "results"
    / "event_catalog"
    / "IMERG_rainfall_events_IETD_12h.csv"
)


discharge_file = (
    PROJECT_ROOT
    / config["paths"]["interim_discharge"]
    / (
        f"USGS_{station_id}_"
        "00060_continuous_combined_interim.csv"
    )
)


# =========================================================
# Outputs
# =========================================================

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

results_dir.mkdir(
    parents=True,
    exist_ok=True,
)

figures_dir.mkdir(
    parents=True,
    exist_ok=True,
)


# =========================================================
# Screening parameters
# =========================================================

IETD_HOURS = 12

PRE_EVENT_HOURS = 24

BASEFLOW_WINDOW_HOURS = 6

POST_EVENT_RESPONSE_HOURS = 72

DISCHARGE_TIMESTEP_MINUTES = 15

CFS_TO_M3S = 0.028316846592


# =========================================================
# Load rainfall-event catalogue
# =========================================================

print("=" * 78)
print("Stage 3C-2: Link rainfall events to observed discharge")
print("=" * 78)

print(f"Rainfall event catalogue : {event_file}")
print(f"Discharge file           : {discharge_file}")


if not event_file.exists():

    raise SystemExit(
        "ERROR: IETD-12 rainfall event catalogue not found."
    )


if not discharge_file.exists():

    raise SystemExit(
        "ERROR: Combined discharge dataset not found."
    )


events = pd.read_csv(
    event_file,
    low_memory=False,
)


events["start_utc"] = pd.to_datetime(
    events["start_utc"],
    utc=True,
    errors="coerce",
)

events["end_utc"] = pd.to_datetime(
    events["end_utc"],
    utc=True,
    errors="coerce",
)

events[
    "peak_rainfall_time_utc"
] = pd.to_datetime(
    events[
        "peak_rainfall_time_utc"
    ],
    utc=True,
    errors="coerce",
)


events = (
    events
    .sort_values("start_utc")
    .reset_index(drop=True)
)


if events["start_utc"].isna().any():

    raise SystemExit(
        "ERROR: Invalid rainfall-event timestamps."
    )


print()
print(
    f"IETD-12 rainfall events : "
    f"{len(events):,}"
)


# =========================================================
# Next-event information
# =========================================================

events[
    "next_event_start_utc"
] = events[
    "start_utc"
].shift(-1)


events[
    "hours_to_next_event"
] = (
    (
        events[
            "next_event_start_utc"
        ]
        -
        events[
            "end_utc"
        ]
    )
    .dt.total_seconds()
    / 3600
)


# =========================================================
# Load discharge
# =========================================================

discharge = pd.read_csv(
    discharge_file,
    low_memory=False,
)


discharge["time_utc"] = pd.to_datetime(
    discharge["time_utc"],
    utc=True,
    errors="coerce",
)


discharge["value_numeric"] = pd.to_numeric(
    discharge["value_numeric"],
    errors="coerce",
)


if discharge["time_utc"].isna().any():

    raise SystemExit(
        "ERROR: Invalid discharge timestamps."
    )


if discharge["value_numeric"].isna().any():

    raise SystemExit(
        "ERROR: Missing discharge values."
    )


discharge[
    "discharge_m3_s"
] = (
    discharge[
        "value_numeric"
    ]
    * CFS_TO_M3S
)


discharge[
    "is_estimated"
] = (
    discharge[
        "qualifier"
    ]
    .fillna("")
    .astype(str)
    .str.contains(
        "ESTIMATED",
        case=False,
        regex=False,
    )
)


discharge = (
    discharge
    .sort_values("time_utc")
    .drop_duplicates(
        subset="time_utc"
    )
    .set_index("time_utc")
)


record_start = discharge.index.min()
record_end = discharge.index.max()


print(
    f"Discharge record          : "
    f"{record_start} to {record_end}"
)


# =========================================================
# Largest missing-run helper
# =========================================================

def largest_missing_run_minutes(
    missing_index,
    timestep_minutes=15,
):
    """
    Return duration represented by largest consecutive
    sequence of missing expected timestamps.
    """

    if len(missing_index) == 0:
        return 0


    missing_series = pd.Series(
        missing_index
    ).sort_values().reset_index(drop=True)


    differences = (
        missing_series.diff()
    )


    new_group = (
        differences
        != pd.Timedelta(
            minutes=timestep_minutes
        )
    )


    groups = new_group.cumsum()


    run_sizes = (
        missing_series
        .groupby(groups)
        .size()
    )


    return int(
        run_sizes.max()
        * timestep_minutes
    )


# =========================================================
# Process each event
# =========================================================

linked_rows = []


for idx, event in events.iterrows():

    start = event["start_utc"]
    end = event["end_utc"]

    rain_peak_time = (
        event[
            "peak_rainfall_time_utc"
        ]
    )


    # -----------------------------------------------------
    # Full screening window
    # -----------------------------------------------------

    window_start = (
        start
        - pd.Timedelta(
            hours=PRE_EVENT_HOURS
        )
    )


    window_end = (
        end
        + pd.Timedelta(
            hours=POST_EVENT_RESPONSE_HOURS
        )
    )


    window_within_record = (
        window_start >= record_start
        and
        window_end <= record_end
    )


    observed_window = discharge.loc[
        window_start:window_end
    ]


    expected_window = pd.date_range(
        start=window_start,
        end=window_end,
        freq="15min",
        tz="UTC",
    )


    observed_times = (
        observed_window.index
        .drop_duplicates()
    )


    matched_times = (
        expected_window.intersection(
            observed_times
        )
    )


    missing_times = (
        expected_window.difference(
            observed_times
        )
    )


    expected_count = len(
        expected_window
    )


    matched_count = len(
        matched_times
    )


    completeness_percent = (
        matched_count
        / expected_count
        * 100
        if expected_count > 0
        else np.nan
    )


    largest_gap_minutes = (
        largest_missing_run_minutes(
            missing_times
        )
    )


    # -----------------------------------------------------
    # Estimated discharge observations
    # -----------------------------------------------------

    estimated_count = int(
        observed_window[
            "is_estimated"
        ].sum()
    )


    estimated_percent = (
        estimated_count
        / len(observed_window)
        * 100
        if len(observed_window) > 0
        else np.nan
    )


    # -----------------------------------------------------
    # Pre-event baseline discharge
    # -----------------------------------------------------

    baseline_start = (
        start
        - pd.Timedelta(
            hours=BASEFLOW_WINDOW_HOURS
        )
    )


    baseline_end = (
        start
        - pd.Timedelta(
            minutes=15
        )
    )


    baseline = discharge.loc[
        baseline_start:baseline_end
    ]


    expected_baseline = int(
        BASEFLOW_WINDOW_HOURS
        * 60
        / DISCHARGE_TIMESTEP_MINUTES
    )


    baseline_completeness = (
        len(baseline)
        / expected_baseline
        * 100
    )


    if len(baseline) > 0:

        baseline_q = float(
            baseline[
                "discharge_m3_s"
            ].median()
        )

    else:

        baseline_q = np.nan


    # -----------------------------------------------------
    # Observed discharge response
    # -----------------------------------------------------

    response_end = (
        end
        + pd.Timedelta(
            hours=POST_EVENT_RESPONSE_HOURS
        )
    )


    response = discharge.loc[
        start:response_end
    ]


    if len(response) > 0:

        peak_idx = (
            response[
                "discharge_m3_s"
            ]
            .idxmax()
        )


        peak_q = float(
            response.loc[
                peak_idx,
                "discharge_m3_s"
            ]
        )


        peak_time = peak_idx


    else:

        peak_q = np.nan
        peak_time = pd.NaT


    # -----------------------------------------------------
    # Response metrics
    # -----------------------------------------------------

    if (
        np.isfinite(baseline_q)
        and baseline_q > 0
        and np.isfinite(peak_q)
    ):

        peak_minus_base = (
            peak_q
            - baseline_q
        )


        peak_ratio = (
            peak_q
            / baseline_q
        )


        peak_increase_percent = (
            peak_minus_base
            / baseline_q
            * 100
        )


    else:

        peak_minus_base = np.nan
        peak_ratio = np.nan
        peak_increase_percent = np.nan


    if pd.notna(peak_time):

        lag_start_to_peak_hours = (
            (
                peak_time
                - start
            ).total_seconds()
            / 3600
        )


        lag_end_to_peak_hours = (
            (
                peak_time
                - end
            ).total_seconds()
            / 3600
        )


        lag_rainpeak_to_qpeak_hours = (
            (
                peak_time
                - rain_peak_time
            ).total_seconds()
            / 3600
        )


    else:

        lag_start_to_peak_hours = np.nan
        lag_end_to_peak_hours = np.nan
        lag_rainpeak_to_qpeak_hours = np.nan


    # -----------------------------------------------------
    # Subsequent-rainfall confounding flag
    # -----------------------------------------------------

    hours_to_next = event[
        "hours_to_next_event"
    ]


    next_rain_within_72h = (
        pd.notna(hours_to_next)
        and
        hours_to_next
        <= POST_EVENT_RESPONSE_HOURS
    )


    # -----------------------------------------------------
    # Preliminary rainfall-size flag
    # -----------------------------------------------------

    rainfall_ge_10mm = (
        event[
            "total_rainfall_mm"
        ]
        >= 10
    )


    # -----------------------------------------------------
    # Save event diagnostics
    # -----------------------------------------------------

    linked_rows.append({

        "event_id":
            event[
                "event_id"
            ],

        "start_utc":
            start,

        "end_utc":
            end,

        "year":
            int(
                event["year"]
            ),

        "total_rainfall_mm":
            event[
                "total_rainfall_mm"
            ],

        "maximum_30min_depth_mm":
            event[
                "maximum_30min_depth_mm"
            ],

        "peak_rainfall_time_utc":
            rain_peak_time,

        "antecedent_24h_mm":
            event[
                "antecedent_24h_mm"
            ],

        "antecedent_72h_mm":
            event[
                "antecedent_72h_mm"
            ],

        "antecedent_7day_mm":
            event[
                "antecedent_7day_mm"
            ],

        "rainfall_ge_10mm":
            rainfall_ge_10mm,

        "window_start_utc":
            window_start,

        "window_end_utc":
            window_end,

        "window_within_discharge_record":
            window_within_record,

        "expected_discharge_slots":
            expected_count,

        "matched_discharge_slots":
            matched_count,

        "missing_discharge_slots":
            len(
                missing_times
            ),

        "discharge_completeness_percent":
            completeness_percent,

        "largest_discharge_gap_minutes":
            largest_gap_minutes,

        "estimated_discharge_observations":
            estimated_count,

        "estimated_discharge_percent":
            estimated_percent,

        "baseline_discharge_m3_s":
            baseline_q,

        "baseline_completeness_percent":
            baseline_completeness,

        "peak_discharge_m3_s":
            peak_q,

        "peak_discharge_time_utc":
            peak_time,

        "peak_minus_baseline_m3_s":
            peak_minus_base,

        "peak_to_baseline_ratio":
            peak_ratio,

        "peak_increase_percent":
            peak_increase_percent,

        "lag_event_start_to_qpeak_hours":
            lag_start_to_peak_hours,

        "lag_event_end_to_qpeak_hours":
            lag_end_to_peak_hours,

        "lag_rainpeak_to_qpeak_hours":
            lag_rainpeak_to_qpeak_hours,

        "hours_to_next_rain_event":
            hours_to_next,

        "next_rain_event_within_72h":
            next_rain_within_72h,
    })


# =========================================================
# Linked event table
# =========================================================

linked = pd.DataFrame(
    linked_rows
)


# =========================================================
# Basic screening subsets
# =========================================================

rain10 = linked[
    linked[
        "rainfall_ge_10mm"
    ]
].copy()


complete_windows = linked[
    linked[
        "missing_discharge_slots"
    ] == 0
].copy()


clean_rain10 = linked[
    (
        linked[
            "rainfall_ge_10mm"
        ]
    )
    &
    (
        linked[
            "missing_discharge_slots"
        ] == 0
    )
    &
    (
        linked[
            "estimated_discharge_observations"
        ] == 0
    )
    &
    (
        linked[
            "window_within_discharge_record"
        ]
    )
].copy()


# =========================================================
# Summary
# =========================================================

print()
print("=" * 78)
print("LINKAGE SUMMARY")
print("=" * 78)

print(
    f"All IETD-12 events                 : "
    f"{len(linked):,}"
)

print(
    f"Rainfall events >= 10 mm           : "
    f"{len(rain10):,}"
)

print(
    f"Events with complete discharge window: "
    f"{len(complete_windows):,}"
)

print(
    f">=10 mm + complete + no estimated  : "
    f"{len(clean_rain10):,}"
)


print()
print("=" * 78)
print("DISCHARGE RESPONSE SUMMARY — >=10 mm EVENTS")
print("=" * 78)


if not rain10.empty:

    print(
        f"Median rainfall             : "
        f"{rain10['total_rainfall_mm'].median():.2f} mm"
    )

    print(
        f"Median baseline discharge   : "
        f"{rain10['baseline_discharge_m3_s'].median():.2f} m3/s"
    )

    print(
        f"Median peak discharge       : "
        f"{rain10['peak_discharge_m3_s'].median():.2f} m3/s"
    )

    print(
        f"Median peak/base ratio      : "
        f"{rain10['peak_to_baseline_ratio'].median():.2f}"
    )

    print(
        f"Median start-to-peak lag    : "
        f"{rain10['lag_event_start_to_qpeak_hours'].median():.2f} h"
    )

    print(
        f"Median rainpeak-to-Qpeak lag: "
        f"{rain10['lag_rainpeak_to_qpeak_hours'].median():.2f} h"
    )


# =========================================================
# Distribution of discharge data quality
# =========================================================

print()
print("=" * 78)
print("DATA QUALITY — >=10 mm EVENTS")
print("=" * 78)


print(
    f"100% complete windows       : "
    f"{(
        rain10['discharge_completeness_percent'] == 100
    ).sum():,}"
)

print(
    f"Windows >=99% complete      : "
    f"{(
        rain10['discharge_completeness_percent'] >= 99
    ).sum():,}"
)

print(
    f"Windows with estimated Q    : "
    f"{(
        rain10['estimated_discharge_observations'] > 0
    ).sum():,}"
)

print(
    f"Next rain within 72 h       : "
    f"{(
        rain10['next_rain_event_within_72h']
    ).sum():,}"
)


# =========================================================
# Save tables
# =========================================================

linked_file = (
    results_dir
    / (
        "IMERG_USGS_"
        "IETD12_linked_events.csv"
    )
)


rain10_file = (
    results_dir
    / (
        "IMERG_USGS_"
        "IETD12_events_ge10mm.csv"
    )
)


clean_file = (
    results_dir
    / (
        "IMERG_USGS_"
        "IETD12_preliminary_clean_candidates.csv"
    )
)


linked.to_csv(
    linked_file,
    index=False,
)

rain10.to_csv(
    rain10_file,
    index=False,
)

clean_rain10.to_csv(
    clean_file,
    index=False,
)


# =========================================================
# Top events by rainfall
# =========================================================

top_rainfall_file = (
    results_dir
    / (
        "IMERG_USGS_"
        "IETD12_top30_by_rainfall.csv"
    )
)


(
    clean_rain10
    .sort_values(
        "total_rainfall_mm",
        ascending=False,
    )
    .head(30)
    .to_csv(
        top_rainfall_file,
        index=False,
    )
)


# =========================================================
# Top events by observed discharge increase
# =========================================================

top_response_file = (
    results_dir
    / (
        "IMERG_USGS_"
        "IETD12_top30_by_discharge_response.csv"
    )
)


(
    clean_rain10
    .sort_values(
        "peak_minus_baseline_m3_s",
        ascending=False,
    )
    .head(30)
    .to_csv(
        top_response_file,
        index=False,
    )
)


# =========================================================
# Diagnostic figure
# =========================================================

plot_df = clean_rain10[
    clean_rain10[
        "peak_minus_baseline_m3_s"
    ].notna()
].copy()


fig, ax = plt.subplots(
    figsize=(8, 6)
)


ax.scatter(
    plot_df[
        "total_rainfall_mm"
    ],

    plot_df[
        "peak_minus_baseline_m3_s"
    ],

    s=20,
)


ax.set_xlabel(
    "IMERG event rainfall (mm)"
)

ax.set_ylabel(
    "Observed peak rise above baseline (m³/s)"
)

ax.set_title(
    "Rainfall Amount vs Observed Discharge Response"
)


plt.tight_layout()


figure_file = (
    figures_dir
    / (
        "IMERG_USGS_"
        "rainfall_vs_discharge_response.png"
    )
)


plt.savefig(
    figure_file,
    dpi=300,
    bbox_inches="tight",
)

plt.close()


# =========================================================
# JSON summary
# =========================================================

summary = {

    "working_IETD_hours":
        IETD_HOURS,

    "screening_window": {
        "pre_event_hours":
            PRE_EVENT_HOURS,

        "post_event_hours":
            POST_EVENT_RESPONSE_HOURS,

        "baseline_hours":
            BASEFLOW_WINDOW_HOURS,
    },

    "all_events":
        int(
            len(linked)
        ),

    "events_ge_10mm":
        int(
            len(rain10)
        ),

    "complete_discharge_windows":
        int(
            len(
                complete_windows
            )
        ),

    "preliminary_clean_ge10mm_candidates":
        int(
            len(
                clean_rain10
            )
        ),

    "scientific_status":
        (
            "candidate-event linkage only; "
            "no final modelling events selected"
        ),
}


summary_file = (
    results_dir
    / (
        "IMERG_USGS_"
        "IETD12_linkage_summary.json"
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
print(linked_file)
print(rain10_file)
print(clean_file)
print(top_rainfall_file)
print(top_response_file)
print(summary_file)
print(figure_file)


print()
print("=" * 78)
print("Stage 3C-2 ANALYSIS COMPLETE")
print("=" * 78)

print()
print(
    "No final calibration or validation "
    "events have been selected."
)

print(
    "No discharge interpolation or rainfall "
    "modification was performed."
)
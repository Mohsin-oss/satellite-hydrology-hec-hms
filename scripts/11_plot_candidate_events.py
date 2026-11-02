"""
Stage 3C-3
Generate rainfall-discharge diagnostic plots for shortlisted events.

Purpose
-------
Visually inspect candidate events before selecting calibration and
validation events for HEC-HMS.

Shortlist criteria
------------------
Starting from Stage 3C-2 preliminary clean candidates:

1. Rainfall >= 10 mm
2. Complete discharge screening window
3. No ESTIMATED discharge observations
4. No subsequent rainfall event within 72 hours
5. Positive observed discharge rise above baseline
6. Discharge peak does not precede the IMERG rainfall peak

IMPORTANT
---------
This stage does NOT:
- calibrate HEC-HMS;
- modify rainfall;
- interpolate discharge;
- automatically accept/reject events;
- assign final calibration/validation events.

The diagnostic plots support manual scientific review.
"""

from pathlib import Path

import matplotlib.pyplot as plt
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

CFS_TO_M3S = 0.028316846592


# =========================================================
# Input files
# =========================================================

candidate_file = (
    PROJECT_ROOT
    / "results"
    / "event_catalog"
    / "IMERG_USGS_IETD12_preliminary_clean_candidates.csv"
)


rainfall_file = (
    PROJECT_ROOT
    / config["paths"]["interim_precipitation"]
    / (
        f"IMERG_V07_USGS_{station_id}_"
        "2018_2024_combined_interim.csv"
    )
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
# Output directories
# =========================================================

figure_dir = (
    PROJECT_ROOT
    / "figures"
    / "event_diagnostics"
)

results_dir = (
    PROJECT_ROOT
    / "results"
    / "event_catalog"
)


figure_dir.mkdir(
    parents=True,
    exist_ok=True,
)

results_dir.mkdir(
    parents=True,
    exist_ok=True,
)


# =========================================================
# Load candidate-event table
# =========================================================

print("=" * 78)
print("Stage 3C-3: Candidate-event visual diagnostics")
print("=" * 78)

print(f"Candidate file : {candidate_file}")
print(f"Rainfall file  : {rainfall_file}")
print(f"Discharge file : {discharge_file}")


for required_file in [
    candidate_file,
    rainfall_file,
    discharge_file,
]:

    if not required_file.exists():

        raise SystemExit(
            f"ERROR: Required file not found:\n{required_file}"
        )


candidates = pd.read_csv(
    candidate_file,
    low_memory=False,
)


# =========================================================
# Parse candidate timestamps
# =========================================================

datetime_columns = [
    "start_utc",
    "end_utc",
    "peak_rainfall_time_utc",
    "window_start_utc",
    "window_end_utc",
    "peak_discharge_time_utc",
]


for column in datetime_columns:

    candidates[column] = pd.to_datetime(
        candidates[column],
        utc=True,
        errors="coerce",
    )


# =========================================================
# Ensure boolean field is interpreted correctly
# =========================================================

if (
    candidates["next_rain_event_within_72h"].dtype
    != bool
):

    candidates[
        "next_rain_event_within_72h"
    ] = (
        candidates[
            "next_rain_event_within_72h"
        ]
        .astype(str)
        .str.lower()
        .map({
            "true": True,
            "false": False,
        })
    )


# =========================================================
# Derive diagnostic shortlist
# =========================================================

shortlist = candidates[
    (
        candidates[
            "next_rain_event_within_72h"
        ] == False
    )
    &
    (
        candidates[
            "peak_minus_baseline_m3_s"
        ] > 0
    )
    &
    (
        candidates[
            "lag_rainpeak_to_qpeak_hours"
        ] >= 0
    )
].copy()


shortlist = (
    shortlist
    .sort_values(
        [
            "year",
            "start_utc",
        ]
    )
    .reset_index(drop=True)
)


print()
print(
    f"Preliminary clean candidates : "
    f"{len(candidates)}"
)

print(
    f"Diagnostic shortlist         : "
    f"{len(shortlist)}"
)


# =========================================================
# Check expected shortlist size
# =========================================================

if len(shortlist) != 16:

    print()
    print(
        "WARNING: Expected 16 diagnostic events "
        "based on Stage 3C-2 review."
    )

    print(
        "The script will continue using the "
        "criteria-derived shortlist."
    )


# =========================================================
# Load IMERG rainfall
# =========================================================

rainfall = pd.read_csv(
    rainfall_file,
    low_memory=False,
)


rainfall["time_utc"] = pd.to_datetime(
    rainfall["time_utc"],
    utc=True,
    errors="coerce",
)


rainfall[
    "precipitation_mm_30min"
] = pd.to_numeric(
    rainfall[
        "precipitation_mm_30min"
    ],
    errors="coerce",
)


rainfall = (
    rainfall
    .sort_values("time_utc")
    .set_index("time_utc")
)


# =========================================================
# Load USGS discharge
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


discharge[
    "discharge_m3_s"
] = (
    discharge["value_numeric"]
    * CFS_TO_M3S
)


discharge = (
    discharge
    .sort_values("time_utc")
    .set_index("time_utc")
)


# =========================================================
# Review-table structure
# =========================================================

review_rows = []


# =========================================================
# Generate diagnostic plot for each event
# =========================================================

for _, event in shortlist.iterrows():

    event_id = event["event_id"]

    start = event["start_utc"]
    end = event["end_utc"]

    plot_start = event[
        "window_start_utc"
    ]

    plot_end = event[
        "window_end_utc"
    ]

    rain_peak_time = event[
        "peak_rainfall_time_utc"
    ]

    q_peak_time = event[
        "peak_discharge_time_utc"
    ]


    # -----------------------------------------------------
    # Extract rainfall and discharge windows
    # -----------------------------------------------------

    rainfall_window = rainfall.loc[
        plot_start:plot_end
    ].copy()


    discharge_window = discharge.loc[
        plot_start:plot_end
    ].copy()


    # -----------------------------------------------------
    # Verify data presence
    # -----------------------------------------------------

    if rainfall_window.empty:

        print(
            f"WARNING: No rainfall data for {event_id}"
        )

        continue


    if discharge_window.empty:

        print(
            f"WARNING: No discharge data for {event_id}"
        )

        continue


    # -----------------------------------------------------
    # Build figure
    # -----------------------------------------------------

    fig, (
        ax_rain,
        ax_q,
    ) = plt.subplots(
        2,
        1,
        figsize=(12, 8),
        sharex=True,
        gridspec_kw={
            "height_ratios": [
                1,
                2,
            ]
        },
    )


    # =====================================================
    # Rainfall hyetograph
    # =====================================================

    ax_rain.bar(
        rainfall_window.index,
        rainfall_window[
            "precipitation_mm_30min"
        ],
        width=0.018,
    )


    # Conventional hyetograph:
    # rainfall bars descend from top.

    ax_rain.invert_yaxis()


    ax_rain.set_ylabel(
        "IMERG rainfall\n(mm / 30 min)"
    )


    ax_rain.set_title(
        (
            f"{event_id} | "
            f"{int(event['year'])} | "
            f"P = {event['total_rainfall_mm']:.1f} mm | "
            f"Qpeak/Qbase = "
            f"{event['peak_to_baseline_ratio']:.2f}"
        )
    )


    # =====================================================
    # Discharge hydrograph
    # =====================================================

    ax_q.plot(
        discharge_window.index,
        discharge_window[
            "discharge_m3_s"
        ],
        linewidth=1.1,
    )


    ax_q.set_ylabel(
        "Observed discharge (m³/s)"
    )

    ax_q.set_xlabel(
        "Time (UTC)"
    )


    # =====================================================
    # Event start/end markers
    # =====================================================

    for ax in [
        ax_rain,
        ax_q,
    ]:

        ax.axvline(
            start,
            linestyle="--",
            linewidth=1.0,
            label="Rain event start",
        )

        ax.axvline(
            end,
            linestyle="--",
            linewidth=1.0,
            label="Rain event end",
        )


    # =====================================================
    # Rainfall peak
    # =====================================================

    ax_rain.axvline(
        rain_peak_time,
        linestyle=":",
        linewidth=1.2,
        label="Rainfall peak",
    )


    # =====================================================
    # Discharge peak
    # =====================================================

    ax_q.axvline(
        q_peak_time,
        linestyle=":",
        linewidth=1.2,
        label="Discharge peak",
    )


    ax_q.scatter(
        [
            q_peak_time
        ],
        [
            event[
                "peak_discharge_m3_s"
            ]
        ],
        s=35,
        zorder=5,
    )


    # =====================================================
    # Baseline discharge
    # =====================================================

    ax_q.axhline(
        event[
            "baseline_discharge_m3_s"
        ],
        linestyle="-.",
        linewidth=1.0,
        label="Pre-event baseline Q",
    )


    # =====================================================
    # Event-window shading
    # =====================================================

    ax_rain.axvspan(
        start,
        end,
        alpha=0.08,
    )

    ax_q.axvspan(
        start,
        end,
        alpha=0.08,
    )


    # =====================================================
    # Event summary text
    # =====================================================

    summary_text = (
        f"Rainfall = "
        f"{event['total_rainfall_mm']:.2f} mm\n"

        f"Antecedent 72 h = "
        f"{event['antecedent_72h_mm']:.2f} mm\n"

        f"Q baseline = "
        f"{event['baseline_discharge_m3_s']:.2f} m³/s\n"

        f"Q peak = "
        f"{event['peak_discharge_m3_s']:.2f} m³/s\n"

        f"Peak/base = "
        f"{event['peak_to_baseline_ratio']:.2f}\n"

        f"Rain peak → Q peak = "
        f"{event['lag_rainpeak_to_qpeak_hours']:.2f} h\n"

        f"Event end → Q peak = "
        f"{event['lag_event_end_to_qpeak_hours']:.2f} h"
    )


    ax_q.text(
        0.01,
        0.97,
        summary_text,
        transform=ax_q.transAxes,
        verticalalignment="top",
        fontsize=9,
        bbox={
            "boxstyle":
                "round",
            "alpha":
                0.15,
        },
    )


    # =====================================================
    # Grid and legends
    # =====================================================

    ax_rain.grid(
        True,
        linewidth=0.3,
    )

    ax_q.grid(
        True,
        linewidth=0.3,
    )


    ax_rain.legend(
        loc="upper right",
        fontsize=8,
    )

    ax_q.legend(
        loc="upper right",
        fontsize=8,
    )


    # =====================================================
    # Save plot
    # =====================================================

    plt.tight_layout()


    output_file = (
        figure_dir
        / f"{event_id}_diagnostic.png"
    )


    plt.savefig(
        output_file,
        dpi=300,
        bbox_inches="tight",
    )


    plt.close()


    # =====================================================
    # Populate review table
    # =====================================================

    # These fields deliberately remain blank.
    # They will be completed after visual scientific review.

    review_rows.append({

        "event_id":
            event_id,

        "year":
            int(event["year"]),

        "start_utc":
            start,

        "end_utc":
            end,

        "total_rainfall_mm":
            event[
                "total_rainfall_mm"
            ],

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

        "baseline_discharge_m3_s":
            event[
                "baseline_discharge_m3_s"
            ],

        "peak_discharge_m3_s":
            event[
                "peak_discharge_m3_s"
            ],

        "peak_to_baseline_ratio":
            event[
                "peak_to_baseline_ratio"
            ],

        "peak_increase_percent":
            event[
                "peak_increase_percent"
            ],

        "rainpeak_to_qpeak_hours":
            event[
                "lag_rainpeak_to_qpeak_hours"
            ],

        "event_end_to_qpeak_hours":
            event[
                "lag_event_end_to_qpeak_hours"
            ],

        "hours_to_next_rain_event":
            event[
                "hours_to_next_rain_event"
            ],

        "diagnostic_plot":
            output_file.name,

        # Manual review fields
        "hydrograph_response":
            "",

        "hydrograph_complexity":
            "",

        "recession_captured":
            "",

        "rainfall_pattern":
            "",

        "manual_decision":
            "",

        "manual_notes":
            "",
    })


    print(
        f"Created: {output_file.name}"
    )


# =========================================================
# Save review table
# =========================================================

review_df = pd.DataFrame(
    review_rows
)


review_file = (
    results_dir
    / (
        "IMERG_USGS_"
        "IETD12_event_visual_review.csv"
    )
)


review_df.to_csv(
    review_file,
    index=False,
)


# =========================================================
# Save concise shortlist table
# =========================================================

shortlist_file = (
    results_dir
    / (
        "IMERG_USGS_"
        "IETD12_diagnostic_shortlist.csv"
    )
)


shortlist.to_csv(
    shortlist_file,
    index=False,
)


# =========================================================
# Terminal summary
# =========================================================

print()
print("=" * 78)
print("DIAGNOSTIC SHORTLIST")
print("=" * 78)

print()


display_columns = [
    "event_id",
    "year",
    "total_rainfall_mm",
    "antecedent_72h_mm",
    "baseline_discharge_m3_s",
    "peak_discharge_m3_s",
    "peak_to_baseline_ratio",
    "lag_rainpeak_to_qpeak_hours",
    "lag_event_end_to_qpeak_hours",
]


print(
    shortlist[
        display_columns
    ]
    .to_string(
        index=False,
        formatters={
            "total_rainfall_mm":
                "{:.2f}".format,

            "antecedent_72h_mm":
                "{:.2f}".format,

            "baseline_discharge_m3_s":
                "{:.2f}".format,

            "peak_discharge_m3_s":
                "{:.2f}".format,

            "peak_to_baseline_ratio":
                "{:.2f}".format,

            "lag_rainpeak_to_qpeak_hours":
                "{:.2f}".format,

            "lag_event_end_to_qpeak_hours":
                "{:.2f}".format,
        },
    )
)


print()
print("=" * 78)
print("FILES CREATED")
print("=" * 78)

print()
print(f"Diagnostic plots:")
print(figure_dir)

print()
print(f"Review table:")
print(review_file)

print()
print(f"Diagnostic shortlist:")
print(shortlist_file)


print()
print("=" * 78)
print("Stage 3C-3 COMPLETE")
print("=" * 78)

print()
print(
    "No event has been automatically accepted "
    "or rejected."
)

print(
    "Next step: visually review the diagnostic "
    "hydrographs and classify events as "
    "ACCEPT / RESERVE / REJECT."
)
"""
Stage 3A-5
Finalize discharge eligibility for USGS 02361000.

Objectives
----------
1. Identify the operational transition from hourly to 15-minute data.
2. Measure true 15-minute completeness for 2018-2024.
3. Identify genuine missing 15-minute observations.
4. Identify observations carrying ESTIMATED qualifiers.
5. Determine whether the discharge record is suitable for
   event-based HEC-HMS modelling.

IMPORTANT
---------
No interpolation, gap filling, resampling, deletion, or
unit conversion occurs here.
"""

from pathlib import Path
import json

import matplotlib.pyplot as plt
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

interim_file = (
    PROJECT_ROOT
    / config["paths"]["interim_discharge"]
    / f"USGS_{station_id}_00060_continuous_combined_interim.csv"
)

results_dir = PROJECT_ROOT / "results" / "tables"
figures_dir = PROJECT_ROOT / "figures" / "hydrographs"

results_dir.mkdir(parents=True, exist_ok=True)
figures_dir.mkdir(parents=True, exist_ok=True)


# =========================================================
# Load interim observations
# =========================================================

print("=" * 74)
print("Stage 3A-5: Final discharge eligibility assessment")
print("=" * 74)

print(f"Station      : USGS-{station_id}")
print(f"Input file   : {interim_file}")

if not interim_file.exists():
    raise SystemExit(
        "ERROR: Combined interim discharge file not found."
    )

df = pd.read_csv(
    interim_file,
    low_memory=False,
)
df["time_utc"] = pd.to_datetime(
    df["time_utc"],
    utc=True,
    errors="coerce",
)

df["value_numeric"] = pd.to_numeric(
    df["value_numeric"],
    errors="coerce",
)

df = df.sort_values("time_utc").reset_index(drop=True)

print(f"Observations : {len(df):,}")


# =========================================================
# Calculate observation intervals
# =========================================================

df["interval_minutes"] = (
    df["time_utc"]
    .diff()
    .dt.total_seconds()
    / 60
)

df["date_utc"] = df["time_utc"].dt.date
df["year"] = df["time_utc"].dt.year


# =========================================================
# Daily cadence analysis
# =========================================================

daily_rows = []

for date, subset in df.groupby("date_utc"):

    intervals = subset["interval_minutes"].dropna()
    intervals = intervals[intervals > 0]

    if intervals.empty:
        continue

    rounded = intervals.round(3)

    modal_interval = rounded.mode().iloc[0]

    share_15 = (rounded == 15).mean()
    share_60 = (rounded == 60).mean()

    daily_rows.append({
        "date": str(date),
        "interval_count": len(intervals),
        "modal_interval_minutes": modal_interval,
        "share_15_minute": share_15,
        "share_60_minute": share_60,
    })

daily_cadence = pd.DataFrame(
    daily_rows,
    columns=[
        "date",
        "interval_count",
        "modal_interval_minutes",
        "share_15_minute",
        "share_60_minute",
    ],
)

daily_cadence["date"] = pd.to_datetime(
    daily_cadence["date"],
    utc=True,
)


# =========================================================
# Detect sustained transition to 15-minute reporting
# =========================================================

# A day qualifies as strongly 15-minute if:
#
# - at least 80 interval observations exist
# - >=80% of intervals are exactly 15 minutes
#
# We then require at least seven consecutive qualifying days
# before calling the change a sustained transition.

daily_cadence["strong_15min_day"] = (
    (daily_cadence["interval_count"] >= 80)
    &
    (daily_cadence["share_15_minute"] >= 0.80)
)


transition_date = None

qualified_dates = daily_cadence.loc[
    daily_cadence["strong_15min_day"],
    "date",
].sort_values()


if not qualified_dates.empty:

    run_start = None
    previous_date = None
    run_length = 0

    for current_date in qualified_dates:

        if (
            previous_date is not None
            and
            (current_date - previous_date).days == 1
        ):
            run_length += 1

        else:
            run_start = current_date
            run_length = 1

        if run_length >= 7:
            transition_date = run_start
            break

        previous_date = current_date


# Find first actual 15-minute observation interval
# on/after the sustained-transition date.

transition_timestamp = None

if transition_date is not None:

    transition_subset = df[
        df["time_utc"] >= transition_date
    ]

    transition_subset = transition_subset[
        transition_subset["interval_minutes"] == 15
    ]

    if not transition_subset.empty:

        transition_timestamp = (
            transition_subset.iloc[0]["time_utc"]
        )


# =========================================================
# Primary modelling period
# =========================================================

PRIMARY_START_YEAR = 2018
PRIMARY_END_YEAR = 2024


primary_df = df[
    (df["year"] >= PRIMARY_START_YEAR)
    &
    (df["year"] <= PRIMARY_END_YEAR)
].copy()


# =========================================================
# 15-minute grid completeness
# =========================================================

completeness_rows = []
all_gap_rows = []


for year in range(
    PRIMARY_START_YEAR,
    PRIMARY_END_YEAR + 1,
):

    year_df = primary_df[
        primary_df["year"] == year
    ].copy()


    expected_index = pd.date_range(
        start=f"{year}-01-01 00:00:00",
        end=f"{year}-12-31 23:45:00",
        freq="15min",
        tz="UTC",
    )


    observed_times = pd.DatetimeIndex(
        year_df["time_utc"]
        .dropna()
        .drop_duplicates()
    )


    # -----------------------------------------------------
    # Check whether observations fall on 15-minute grid
    # -----------------------------------------------------

    on_grid_mask = (
        (year_df["time_utc"].dt.minute % 15 == 0)
        &
        (year_df["time_utc"].dt.second == 0)
    )

    on_grid_count = int(on_grid_mask.sum())

    off_grid_count = int(
        (~on_grid_mask).sum()
    )


    observed_on_grid = pd.DatetimeIndex(
        year_df.loc[
            on_grid_mask,
            "time_utc",
        ]
        .drop_duplicates()
    )


    matched = expected_index.intersection(
        observed_on_grid
    )

    missing = expected_index.difference(
        observed_on_grid
    )


    expected_count = len(expected_index)
    matched_count = len(matched)
    missing_count = len(missing)

    completeness_percent = (
        matched_count
        / expected_count
        * 100
    )


    # -----------------------------------------------------
    # Estimated observations
    # -----------------------------------------------------

    qualifier_text = (
        year_df["qualifier"]
        .fillna("")
        .astype(str)
    )

    estimated_mask = qualifier_text.str.contains(
        "ESTIMATED",
        case=False,
        regex=False,
    )

    estimated_count = int(
        estimated_mask.sum()
    )

    estimated_percent = (
        estimated_count
        / len(year_df)
        * 100
        if len(year_df) > 0
        else 0
    )


    # -----------------------------------------------------
    # Group true missing timestamps into gap episodes
    # -----------------------------------------------------

    if len(missing) > 0:

        gap_group = 0
        previous_time = None

        current_group = []

        for missing_time in missing:

            if (
                previous_time is None
                or
                missing_time - previous_time
                == pd.Timedelta(minutes=15)
            ):
                current_group.append(
                    missing_time
                )

            else:

                gap_group += 1

                all_gap_rows.append({
                    "year": year,
                    "gap_id": gap_group,
                    "gap_start_utc":
                        current_group[0],
                    "gap_end_utc":
                        current_group[-1],
                    "missing_15min_slots":
                        len(current_group),
                    "missing_duration_minutes":
                        len(current_group) * 15,
                })

                current_group = [
                    missing_time
                ]

            previous_time = missing_time


        if current_group:

            gap_group += 1

            all_gap_rows.append({
                "year": year,
                "gap_id": gap_group,
                "gap_start_utc":
                    current_group[0],
                "gap_end_utc":
                    current_group[-1],
                "missing_15min_slots":
                    len(current_group),
                "missing_duration_minutes":
                    len(current_group) * 15,
            })


    completeness_rows.append({

        "year":
            year,

        "observations":
            len(year_df),

        "expected_15min_slots":
            expected_count,

        "matched_15min_slots":
            matched_count,

        "missing_15min_slots":
            missing_count,

        "completeness_percent":
            completeness_percent,

        "on_15min_grid":
            on_grid_count,

        "off_15min_grid":
            off_grid_count,

        "estimated_observations":
            estimated_count,

        "estimated_percent":
            estimated_percent,
    })


completeness_df = pd.DataFrame(
    completeness_rows
)

gap_df = pd.DataFrame(
    all_gap_rows
)


# =========================================================
# Estimated observations table
# =========================================================

qualifier_text = (
    primary_df["qualifier"]
    .fillna("")
    .astype(str)
)

estimated_primary = primary_df[
    qualifier_text.str.contains(
        "ESTIMATED",
        case=False,
        regex=False,
    )
].copy()


estimated_columns = [
    "time_utc",
    "value_numeric",
    "unit_of_measure",
    "qualifier",
    "approval_status",
]


# =========================================================
# Gap summary
# =========================================================

if not gap_df.empty:

    gap_summary = (
        gap_df.groupby("year")
        .agg(
            gap_episodes=(
                "gap_id",
                "count",
            ),
            missing_15min_slots=(
                "missing_15min_slots",
                "sum",
            ),
            largest_gap_minutes=(
                "missing_duration_minutes",
                "max",
            ),
        )
        .reset_index()
    )

else:

    gap_summary = pd.DataFrame(
        columns=[
            "year",
            "gap_episodes",
            "missing_15min_slots",
            "largest_gap_minutes",
        ]
    )


# =========================================================
# Print cadence transition
# =========================================================

print()
print("=" * 74)
print("CADENCE TRANSITION")
print("=" * 74)

if transition_date is None:

    print(
        "No sustained 15-minute transition "
        "could be identified."
    )

else:

    print(
        "First sustained 15-minute reporting date:"
    )

    print(
        f"  {transition_date.date()}"
    )

    if transition_timestamp is not None:

        print(
            "First 15-minute interval on/after "
            "transition:"
        )

        print(
            f"  {transition_timestamp}"
        )


# =========================================================
# Print completeness
# =========================================================

print()
print("=" * 74)
print("PRIMARY PERIOD COMPLETENESS — 2018-2024")
print("=" * 74)

print()

print(
    completeness_df.to_string(
        index=False,
        formatters={
            "completeness_percent":
                "{:.3f}".format,

            "estimated_percent":
                "{:.3f}".format,
        },
    )
)


# =========================================================
# Print true gap summary
# =========================================================

print()
print("=" * 74)
print("TRUE 15-MINUTE GAP SUMMARY")
print("=" * 74)

if gap_summary.empty:

    print(
        "No missing 15-minute timestamps detected."
    )

else:

    print()
    print(
        gap_summary.to_string(
            index=False
        )
    )


# =========================================================
# Largest individual gaps
# =========================================================

print()
print("=" * 74)
print("LARGEST GAP EPISODES")
print("=" * 74)

if gap_df.empty:

    print("No gaps.")

else:

    largest_gaps = (
        gap_df.sort_values(
            "missing_duration_minutes",
            ascending=False,
        )
        .head(15)
    )

    print()
    print(
        largest_gaps.to_string(
            index=False
        )
    )


# =========================================================
# Estimated observations
# =========================================================

print()
print("=" * 74)
print("ESTIMATED OBSERVATIONS — PRIMARY PERIOD")
print("=" * 74)

estimated_by_year = (
    completeness_df[
        [
            "year",
            "estimated_observations",
            "estimated_percent",
        ]
    ]
)

print()

print(
    estimated_by_year.to_string(
        index=False,
        formatters={
            "estimated_percent":
                "{:.3f}".format,
        },
    )
)


# =========================================================
# Overall primary-period statistics
# =========================================================

total_expected = int(
    completeness_df[
        "expected_15min_slots"
    ].sum()
)

total_matched = int(
    completeness_df[
        "matched_15min_slots"
    ].sum()
)

total_missing = int(
    completeness_df[
        "missing_15min_slots"
    ].sum()
)

overall_completeness = (
    total_matched
    / total_expected
    * 100
)

total_estimated = int(
    completeness_df[
        "estimated_observations"
    ].sum()
)

overall_estimated_percent = (
    total_estimated
    / len(primary_df)
    * 100
)


print()
print("=" * 74)
print("OVERALL 2018-2024")
print("=" * 74)

print(
    f"Expected 15-min slots : "
    f"{total_expected:,}"
)

print(
    f"Matched observations  : "
    f"{total_matched:,}"
)

print(
    f"Missing observations  : "
    f"{total_missing:,}"
)

print(
    f"Overall completeness  : "
    f"{overall_completeness:.3f}%"
)

print(
    f"Estimated observations: "
    f"{total_estimated:,}"
)

print(
    f"Estimated percentage  : "
    f"{overall_estimated_percent:.3f}%"
)


# =========================================================
# Save outputs
# =========================================================

daily_file = (
    results_dir
    / f"USGS_{station_id}_daily_cadence_qc.csv"
)

daily_cadence.to_csv(
    daily_file,
    index=False,
)


completeness_file = (
    results_dir
    / (
        f"USGS_{station_id}_"
        "discharge_completeness_2018_2024.csv"
    )
)

completeness_df.to_csv(
    completeness_file,
    index=False,
)


gap_file = (
    results_dir
    / (
        f"USGS_{station_id}_"
        "true_gap_episodes_2018_2024.csv"
    )
)

gap_df.to_csv(
    gap_file,
    index=False,
)


estimated_file = (
    results_dir
    / (
        f"USGS_{station_id}_"
        "estimated_observations_2018_2024.csv"
    )
)

estimated_primary[
    estimated_columns
].to_csv(
    estimated_file,
    index=False,
)


# =========================================================
# Final JSON summary
# =========================================================

summary = {

    "station":
        f"USGS-{station_id}",

    "primary_modelling_period":
        {
            "start":
                "2018-01-01",
            "end":
                "2024-12-31",
        },

    "detected_sustained_15min_transition_date":
        (
            str(
                transition_date.date()
            )
            if transition_date is not None
            else None
        ),

    "overall_primary_period": {

        "expected_15min_slots":
            total_expected,

        "matched_15min_slots":
            total_matched,

        "missing_15min_slots":
            total_missing,

        "completeness_percent":
            overall_completeness,

        "estimated_observations":
            total_estimated,

        "estimated_percent":
            overall_estimated_percent,
    },

    "scientific_status":
        "pending final Stage 3A review",
}


summary_file = (
    results_dir
    / (
        f"USGS_{station_id}_"
        "stage3A5_summary.json"
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
# Completeness figure
# =========================================================

fig, ax = plt.subplots(
    figsize=(9, 5)
)

ax.bar(
    completeness_df["year"].astype(str),
    completeness_df["completeness_percent"],
)

ax.set_xlabel("Year")
ax.set_ylabel("15-minute completeness (%)")

ax.set_title(
    f"USGS {station_id} — "
    "Discharge Completeness"
)

ax.set_ylim(
    90,
    100,
)

plt.tight_layout()


figure_file = (
    figures_dir
    / (
        f"USGS_{station_id}_"
        "discharge_completeness_2018_2024.png"
    )
)


plt.savefig(
    figure_file,
    dpi=300,
    bbox_inches="tight",
)

plt.close()


# =========================================================
# Final output
# =========================================================

print()
print("=" * 74)
print("FILES CREATED")
print("=" * 74)

print()
print(daily_file)
print(completeness_file)
print(gap_file)
print(estimated_file)
print(summary_file)
print(figure_file)

print()
print("=" * 74)
print("Stage 3A-5 ANALYSIS COMPLETE")
print("=" * 74)

print()
print(
    "No interpolation, resampling, deletion, "
    "gap filling, or unit conversion was performed."
)

print(
    "Review results before formally locking "
    "2018-2024 as the modelling period."
)
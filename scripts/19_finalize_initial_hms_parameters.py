"""
Stage 3D-2D2
Finalize the initial calibration-ready HEC-HMS parameter set.

No simulation or calibration is performed here.
"""

from pathlib import Path
import json
import yaml


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
) as f:
    config = yaml.safe_load(f)


station_id = config["catchment"]["usgs_station"]


# =========================================================
# Locked physical evidence
# =========================================================

basin_area_km2 = 1779.24

longest_flowpath_km = 111.007

slope_10_85_percent = 0.0788

initial_cn = 63.61

drained_dual_cn = 59.57


# =========================================================
# Initial Clark Tc
# =========================================================

# HEC-HMS recognizes travel time based on
# flow length / assumed velocity as an initial Tc method.
#
# Use 1.0 m/s as a transparent central starting value.
# Tc will subsequently be calibrated.

velocity_m_per_s = 1.0

flowpath_m = (
    longest_flowpath_km
    * 1000
)

tc_hours = (
    flowpath_m
    / velocity_m_per_s
    / 3600
)


# Physical velocity bracket used only to define
# sensible calibration bounds.

fast_velocity = 1.5
slow_velocity = 0.6

tc_fast = (
    flowpath_m
    / fast_velocity
    / 3600
)

tc_slow = (
    flowpath_m
    / slow_velocity
    / 3600
)


# =========================================================
# Initial Clark storage coefficient
# =========================================================

# No regional Alabama-specific Clark R regression
# is being imposed.
#
# Start R near Tc as a neutral calibration seed.

initial_R_hours = 30.0


# =========================================================
# Recession baseflow
# =========================================================

initial_recession_k = 0.95

ratio_to_peak = 0.20


# =========================================================
# Calibration bounds
# =========================================================

# Keep bounds broad but physically reasonable.
#
# These are calibration search bounds, not claims
# about actual basin parameters.

calibration_bounds = {

    "curve_number": {
        "minimum": 50.0,
        "initial": initial_cn,
        "maximum": 75.0,
    },

    "clark_tc_hours": {
        "minimum": 15.0,
        "initial": tc_hours,
        "maximum": 55.0,
    },

    "clark_r_hours": {
        "minimum": 10.0,
        "initial": initial_R_hours,
        "maximum": 70.0,
    },

    "recession_constant": {
        "minimum": 0.80,
        "initial": initial_recession_k,
        "maximum": 0.99,
    },
}


# =========================================================
# Parameter package
# =========================================================

parameters = {

    "station":
        f"USGS-{station_id}",

    "basin_area_km2":
        basin_area_km2,

    "loss": {

        "method":
            "SCS Curve Number",

        "initial_curve_number":
            initial_cn,

        "drained_dual_sensitivity_cn":
            drained_dual_cn,

        "directly_connected_impervious_percent":
            0.0,
    },

    "transform": {

        "method":
            "Clark Unit Hydrograph",

        "time_area_method":
            "Default",

        "longest_flowpath_km":
            longest_flowpath_km,

        "slope_10_85_percent":
            slope_10_85_percent,

        "initial_velocity_assumption_m_per_s":
            velocity_m_per_s,

        "initial_tc_hours":
            tc_hours,

        "initial_storage_coefficient_hours":
            initial_R_hours,

        "tc_velocity_bracket": {

            "velocity_1_5_m_s_tc_hours":
                tc_fast,

            "velocity_0_6_m_s_tc_hours":
                tc_slow,
        },
    },

    "baseflow": {

        "method":
            "Recession",

        "initial_discharge":
            "event-specific observed pre-event discharge",

        "initial_recession_constant":
            initial_recession_k,

        "threshold_type":
            "Ratio to Peak",

        "ratio_to_peak":
            ratio_to_peak,
    },

    "meteorology": {

        "method":
            "Specified Hyetograph",

        "forcing":
            "GPM IMERG Final Run V07 calibrated precipitation",

        "time_step_minutes":
            30,
    },

    "calibration_bounds":
        calibration_bounds,

    "calibration_parameters": [
        "curve_number",
        "clark_tc_hours",
        "clark_r_hours",
        "recession_constant",
    ],

    "fixed_during_primary_calibration": {

        "ratio_to_peak":
            ratio_to_peak,

        "directly_connected_impervious_percent":
            0.0,
    },

    "scientific_status":
        (
            "initial calibration-ready HEC-HMS "
            "parameter package; no parameters "
            "have yet been calibrated"
        ),
}


# =========================================================
# Save
# =========================================================

output_file = (
    PROJECT_ROOT
    / "results"
    / "tables"
    / f"USGS_{station_id}_HECHMS_initial_parameter_set.json"
)


output_file.parent.mkdir(
    parents=True,
    exist_ok=True,
)


with open(
    output_file,
    "w",
    encoding="utf-8",
) as f:

    json.dump(
        parameters,
        f,
        indent=2,
    )


# =========================================================
# Terminal report
# =========================================================

print("=" * 78)
print("Stage 3D-2D2: Initial HEC-HMS parameter set")
print("=" * 78)

print()
print("LOSS")
print("-" * 78)

print(
    f"SCS Curve Number       : "
    f"{initial_cn:.2f}"
)

print(
    f"DCIA                   : "
    f"0.00%"
)


print()
print("CLARK TRANSFORM")
print("-" * 78)

print(
    f"Longest flow path      : "
    f"{longest_flowpath_km:.3f} km"
)

print(
    f"10-85 slope            : "
    f"{slope_10_85_percent:.4f}%"
)

print(
    f"Velocity assumption    : "
    f"{velocity_m_per_s:.2f} m/s"
)

print(
    f"Initial Clark Tc       : "
    f"{tc_hours:.2f} h"
)

print(
    f"Initial Clark R        : "
    f"{initial_R_hours:.2f} h"
)


print()
print("BASEFLOW")
print("-" * 78)

print(
    f"Recession constant k   : "
    f"{initial_recession_k:.2f}"
)

print(
    f"Ratio to peak          : "
    f"{ratio_to_peak:.2f}"
)

print(
    "Initial discharge     : "
    "event-specific observed Q0"
)


print()
print("CALIBRATION BOUNDS")
print("-" * 78)

print(
    "CN                     : "
    "50.0 – 75.0"
)

print(
    "Clark Tc               : "
    "15.0 – 55.0 h"
)

print(
    "Clark R                : "
    "10.0 – 70.0 h"
)

print(
    "Recession k            : "
    "0.80 – 0.99"
)


print()
print("=" * 78)
print("FILE CREATED")
print("=" * 78)

print(output_file)


print()
print("=" * 78)
print("Stage 3D-2D2 COMPLETE")
print("=" * 78)

print()
print(
    "The basin is now parameterized sufficiently "
    "to construct the first HEC-HMS model."
)

print(
    "No calibration has been performed."
)
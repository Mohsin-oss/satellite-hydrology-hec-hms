"""
Stage 4A
Prepare E0015 automatically for HEC-HMS.

Key fix:
Instead of independently guessing one "start" column and one "end"
column, this script evaluates every plausible start/end pair on the
E0015 row and selects only a physically valid pair where end > start.

Outputs
-------
hec_hms/inputs/E0015/
    E0015_IMERG_30min.csv
    E0015_USGS_flow_30min.csv
    E0015_precip_values_only.txt
    E0015_flow_values_only.txt
    E0015_HECHMS_event_metadata.json
"""

from pathlib import Path
import json
import re
import warnings

import numpy as np
import pandas as pd


# ======================================================================
# SETTINGS
# ======================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

EVENT_NUMBER = 15
EVENT_ID = f"E{EVENT_NUMBER:04d}"

PRE_HOURS = 24
POST_HOURS = 72
Q0_HOURS = 6

warnings.filterwarnings(
    "ignore",
    category=pd.errors.DtypeWarning,
)


# ======================================================================
# GENERAL HELPERS
# ======================================================================

def normalize(value):

    return re.sub(
        r"[^a-z0-9]",
        "",
        str(value).lower(),
    )


def safe_read_csv(path, **kwargs):

    try:

        return pd.read_csv(
            path,
            low_memory=False,
            **kwargs,
        )

    except Exception:

        return None


def parse_datetime(value):

    return pd.to_datetime(
        value,
        utc=True,
        errors="coerce",
    )


# ======================================================================
# EVENT FILE PRIORITY
# ======================================================================

def event_file_priority(path):

    text = str(path).lower()

    score = 0

    if "ietd12" in text:
        score += 100

    if "event" in text:
        score += 80

    if "linkage" in text:
        score += 70

    if "candidate" in text:
        score += 40

    if "catalog" in text:
        score += 30

    if "review" in text:
        score += 20

    return score


# ======================================================================
# FIND E0015 ROW
# ======================================================================

def find_event_row(df):

    # --------------------------------------------------
    # Method 1:
    # literal E0015 anywhere in the row
    # --------------------------------------------------

    for idx, row in df.iterrows():

        values = (
            row
            .astype(str)
            .str.strip()
            .str.upper()
        )

        if (values == EVENT_ID).any():

            return idx, (
                "literal E0015"
            )


    # --------------------------------------------------
    # Method 2:
    # numeric event ID = 15
    # --------------------------------------------------

    for col in df.columns:

        name = normalize(col)

        if (
            "event" not in name
            and name not in [
                "id",
                "eventid",
                "eventno",
                "eventnumber",
                "eventindex",
            ]
        ):
            continue


        numeric = pd.to_numeric(
            df[col],
            errors="coerce",
        )


        matches = np.where(
            numeric.values
            ==
            EVENT_NUMBER
        )[0]


        if len(matches) > 0:

            return int(matches[0]), (
                f"numeric event 15 "
                f"in column {col}"
            )


    return None, None


# ======================================================================
# ROBUST START/END PAIR DETECTION
# ======================================================================

def start_score(column):

    name = normalize(column)

    if (
        "start" not in name
        and
        "begin" not in name
    ):
        return None


    score = 10


    if "event" in name:
        score += 50

    if "rain" in name:
        score += 45

    if "precip" in name:
        score += 45

    if "wet" in name:
        score += 25

    if "utc" in name:
        score += 10


    # Penalize expanded analysis windows.

    if "window" in name:
        score -= 40

    if "simulation" in name:
        score -= 50

    if "screen" in name:
        score -= 40

    if "pre" in name:
        score -= 30

    if "analysis" in name:
        score -= 20


    return score


def end_score(column):

    name = normalize(column)

    if (
        "end" not in name
        and
        "stop" not in name
    ):
        return None


    score = 10


    if "event" in name:
        score += 50

    if "rain" in name:
        score += 45

    if "precip" in name:
        score += 45

    if "wet" in name:
        score += 25

    if "utc" in name:
        score += 10


    if "window" in name:
        score -= 40

    if "simulation" in name:
        score -= 50

    if "screen" in name:
        score -= 40

    if "post" in name:
        score -= 30

    if "analysis" in name:
        score -= 20


    return score


def pair_similarity_bonus(
    start_col,
    end_col,
):

    s = normalize(
        start_col
    )

    e = normalize(
        end_col
    )

    bonus = 0


    # Reward matching conceptual families.

    for word in [
        "event",
        "rain",
        "precip",
        "wet",
        "storm",
    ]:

        if (
            word in s
            and
            word in e
        ):

            bonus += 30


    return bonus


def choose_valid_event_pair(
    row,
):

    start_candidates = []
    end_candidates = []


    for col in row.index:

        value = parse_datetime(
            row[col]
        )


        if pd.isna(
            value
        ):
            continue


        ss = start_score(
            col
        )

        es = end_score(
            col
        )


        if ss is not None:

            start_candidates.append(
                (
                    col,
                    value,
                    ss,
                )
            )


        if es is not None:

            end_candidates.append(
                (
                    col,
                    value,
                    es,
                )
            )


    valid_pairs = []


    for (
        start_col,
        start_time,
        ss,
    ) in start_candidates:


        for (
            end_col,
            end_time,
            es,
        ) in end_candidates:


            duration_hours = (
                end_time
                -
                start_time
            ).total_seconds() / 3600


            # ------------------------------------------
            # Hard physical filter
            # ------------------------------------------

            if duration_hours <= 0:
                continue


            if duration_hours > 200:
                continue


            score = (
                ss
                +
                es
                +
                pair_similarity_bonus(
                    start_col,
                    end_col,
                )
            )


            # Typical rainfall events should generally
            # be shorter than enormous screening windows.

            if duration_hours <= 72:
                score += 20


            if duration_hours <= 48:
                score += 10


            valid_pairs.append(
                {
                    "score":
                        score,

                    "start_col":
                        start_col,

                    "end_col":
                        end_col,

                    "start":
                        start_time,

                    "end":
                        end_time,

                    "duration_hours":
                        duration_hours,
                }
            )


    if not valid_pairs:

        return None, []


    valid_pairs = sorted(
        valid_pairs,
        key=lambda item:
            item["score"],
        reverse=True,
    )


    return (
        valid_pairs[0],
        valid_pairs,
    )


# ======================================================================
# TIME-SERIES COLUMN HELPERS
# ======================================================================

def detect_time_column(columns):

    scored = []


    for col in columns:

        name = normalize(
            col
        )

        score = 0


        if name == "timestamp":
            score += 100

        if name == "datetime":
            score += 100

        if "timestamp" in name:
            score += 80

        if "datetime" in name:
            score += 80

        if "utc" in name:
            score += 20

        if "time" in name:
            score += 20

        if "date" in name:
            score += 15


        if score > 0:

            scored.append(
                (
                    score,
                    col,
                )
            )


    if not scored:

        return None


    scored.sort(
        reverse=True
    )


    return scored[0][1]


# ======================================================================
# PRECIPITATION COLUMN
# ======================================================================

def detect_precip_column(columns):

    candidates = []


    for col in columns:

        name = normalize(
            col
        )

        score = 0
        kind = None


        # Preferred GPM IMERG V07 calibrated band.

        if name == "precipitation":

            score = 500
            kind = "rate"


        elif (
            "precipitation" in name
            and
            "uncal" not in name
        ):

            score = 250

            if (
                "depth" in name
                or name.endswith("mm")
            ):
                kind = "depth"

            else:
                kind = "rate"


        elif (
            "rain" in name
            and
            "uncal" not in name
        ):

            score = 100

            if "depth" in name:
                kind = "depth"

            elif (
                "rate" in name
                or "mmhr" in name
            ):
                kind = "rate"


        if kind is not None:

            if "uncal" in name:
                score -= 1000


            candidates.append(
                (
                    score,
                    col,
                    kind,
                )
            )


    if not candidates:

        return None, None


    candidates.sort(
        reverse=True
    )


    return (
        candidates[0][1],
        candidates[0][2],
    )


# ======================================================================
# FLOW COLUMN
# ======================================================================

def detect_flow_column(columns):

    candidates = []


    for col in columns:

        name = normalize(
            col
        )

        score = 0
        units = None


        if "discharge" in name:
            score += 100

        if "flow" in name:
            score += 70

        if name.startswith("q"):
            score += 30


        if (
            "m3s" in name
            or
            "cms" in name
        ):

            score += 100
            units = "m3s"


        elif (
            "cfs" in name
            or
            "ft3s" in name
        ):

            score += 90
            units = "cfs"


        if (
            score > 0
            and
            units is not None
        ):

            candidates.append(
                (
                    score,
                    col,
                    units,
                )
            )


    if not candidates:

        return None, None


    candidates.sort(
        reverse=True
    )


    return (
        candidates[0][1],
        candidates[0][2],
    )


# ======================================================================
# START
# ======================================================================

print("=" * 78)
print(
    "Stage 4A: Prepare E0015 for HEC-HMS"
)
print("=" * 78)

print()

print(
    f"Project root : "
    f"{PROJECT_ROOT}"
)

print(
    f"Target event : "
    f"{EVENT_ID}"
)


csv_files = list(
    PROJECT_ROOT.rglob(
        "*.csv"
    )
)


print(
    f"CSV files discovered : "
    f"{len(csv_files)}"
)


# ======================================================================
# FIND EVENT ROW
# ======================================================================

print()
print("=" * 78)
print(
    "EVENT CATALOGUE DISCOVERY"
)
print("=" * 78)


candidate_files = sorted(
    csv_files,
    key=event_file_priority,
    reverse=True,
)


selected_file = None
selected_row = None
selection_method = None
selected_pair = None
all_pairs = None


# ----------------------------------------------------------------------
# Primary:
# explicit event ID
# ----------------------------------------------------------------------

for csv_file in candidate_files:

    try:

        if (
            csv_file.stat().st_size
            >
            100 * 1024 * 1024
        ):
            continue

    except Exception:

        continue


    df = safe_read_csv(
        csv_file
    )


    if (
        df is None
        or
        df.empty
    ):
        continue


    row_index, method = (
        find_event_row(
            df
        )
    )


    if row_index is None:
        continue


    row = df.iloc[
        row_index
    ]


    pair, pairs = (
        choose_valid_event_pair(
            row
        )
    )


    if pair is None:
        continue


    selected_file = (
        csv_file
    )

    selected_row = (
        row
    )

    selection_method = (
        method
    )

    selected_pair = (
        pair
    )

    all_pairs = (
        pairs
    )

    break


# ----------------------------------------------------------------------
# Fallback:
# find ~886-event catalogue and use event row 15
# ----------------------------------------------------------------------

if selected_file is None:

    possible_catalogues = []


    for csv_file in candidate_files:

        try:

            if (
                csv_file.stat().st_size
                >
                100 * 1024 * 1024
            ):
                continue

        except Exception:

            continue


        df = safe_read_csv(
            csv_file
        )


        if df is None:
            continue


        if not (
            800
            <=
            len(df)
            <=
            950
        ):

            continue


        if (
            EVENT_NUMBER
            >
            len(df)
        ):

            continue


        row = df.iloc[
            EVENT_NUMBER
            -
            1
        ]


        pair, pairs = (
            choose_valid_event_pair(
                row
            )
        )


        if pair is None:
            continue


        score = (
            event_file_priority(
                csv_file
            )
            -
            abs(
                len(df)
                -
                886
            )
        )


        possible_catalogues.append(
            (
                score,
                csv_file,
                row,
                pair,
                pairs,
            )
        )


    if possible_catalogues:

        possible_catalogues.sort(
            key=lambda item:
                item[0],
            reverse=True,
        )


        (
            _,
            selected_file,
            selected_row,
            selected_pair,
            all_pairs,
        ) = possible_catalogues[0]


        selection_method = (
            "15th row of detected "
            "IETD-12 catalogue"
        )


# ======================================================================
# EVENT DISCOVERY FAILURE
# ======================================================================

if selected_file is None:

    raise SystemExit(
        "ERROR: Could not locate a usable "
        "E0015 event row."
    )


# ======================================================================
# SELECTED EVENT PAIR
# ======================================================================

rain_start = (
    selected_pair[
        "start"
    ]
)

rain_end = (
    selected_pair[
        "end"
    ]
)

duration_hours = (
    selected_pair[
        "duration_hours"
    ]
)


print(
    f"Catalogue       : "
    f"{selected_file}"
)

print(
    f"Selection       : "
    f"{selection_method}"
)


print()
print(
    "Top valid timestamp pairs:"
)

print(
    "-" * 78
)


for candidate in all_pairs[
    :5
]:

    print(
        f"{candidate['start_col']} "
        f"-> "
        f"{candidate['end_col']}"
    )

    print(
        f"    "
        f"{candidate['start']} "
        f"-> "
        f"{candidate['end']} "
        f"({candidate['duration_hours']:.2f} h, "
        f"score={candidate['score']})"
    )


print()
print(
    "SELECTED EVENT TIMESTAMPS"
)

print(
    "-" * 78
)

print(
    f"Start column   : "
    f"{selected_pair['start_col']}"
)

print(
    f"End column     : "
    f"{selected_pair['end_col']}"
)

print(
    f"Rain start     : "
    f"{rain_start}"
)

print(
    f"Rain end       : "
    f"{rain_end}"
)

print(
    f"Duration       : "
    f"{duration_hours:.2f} h"
)


# ======================================================================
# HEC-HMS WINDOW
# ======================================================================

simulation_start = (
    rain_start
    -
    pd.Timedelta(
        hours=PRE_HOURS
    )
).floor(
    "30min"
)


simulation_end = (
    rain_end
    +
    pd.Timedelta(
        hours=POST_HOURS
    )
).ceil(
    "30min"
)


print(
    f"Simulation     : "
    f"{simulation_start} "
    f"-> "
    f"{simulation_end}"
)


# ======================================================================
# FIND IMERG DATA
# ======================================================================

print()
print("=" * 78)
print(
    "IMERG DISCOVERY"
)
print("=" * 78)


rain_frames = []

rain_sources = []


for csv_file in csv_files:

    path_text = str(
        csv_file
    ).lower()


    if not any(
        keyword in path_text
        for keyword in [
            "imerg",
            "precipitation",
            "precip",
            "rainfall",
        ]
    ):

        continue


    header = safe_read_csv(
        csv_file,
        nrows=5,
    )


    if header is None:
        continue


    time_col = detect_time_column(
        header.columns
    )


    precip_col, precip_kind = (
        detect_precip_column(
            header.columns
        )
    )


    if (
        time_col is None
        or
        precip_col is None
    ):

        continue


    df = safe_read_csv(
        csv_file,
        usecols=[
            time_col,
            precip_col,
        ],
    )


    if (
        df is None
        or
        df.empty
    ):

        continue


    times = pd.to_datetime(
        df[
            time_col
        ],
        utc=True,
        errors="coerce",
    )


    values = pd.to_numeric(
        df[
            precip_col
        ],
        errors="coerce",
    )


    valid_time = (
        times.notna()
    )


    if not valid_time.any():
        continue


    if (
        times[
            valid_time
        ].max()
        <
        simulation_start
        or
        times[
            valid_time
        ].min()
        >
        simulation_end
    ):

        continue


    if precip_kind == "rate":

        # IMERG precipitation is mm/hour.
        # 30-minute depth = rate × 0.5 hour.

        depth_mm = (
            values
            *
            0.5
        )

    else:

        depth_mm = (
            values
        )


    temp = pd.DataFrame({

        "datetime":
            times,

        "precip_mm":
            depth_mm,
    })


    temp = temp[
        (
            temp[
                "datetime"
            ]
            >=
            simulation_start
        )
        &
        (
            temp[
                "datetime"
            ]
            <=
            simulation_end
        )
    ]


    if temp.empty:
        continue


    rain_frames.append(
        temp
    )


    rain_sources.append({

        "file":
            str(
                csv_file
            ),

        "time_column":
            time_col,

        "precipitation_column":
            precip_col,

        "type":
            precip_kind,
    })


if not rain_frames:

    raise SystemExit(
        "ERROR: Could not find IMERG "
        "data covering E0015."
    )


rainfall = pd.concat(
    rain_frames,
    ignore_index=True,
)


rainfall = (
    rainfall
    .dropna(
        subset=[
            "datetime"
        ]
    )
    .sort_values(
        "datetime"
    )
    .drop_duplicates(
        subset=[
            "datetime"
        ],
        keep="first",
    )
)


expected_rain_times = (
    pd.date_range(
        start=simulation_start,
        end=simulation_end,
        freq="30min",
        tz="UTC",
    )
)


rainfall = (
    rainfall
    .set_index(
        "datetime"
    )
    .reindex(
        expected_rain_times
    )
)


missing_rain = int(
    rainfall[
        "precip_mm"
    ]
    .isna()
    .sum()
)


if missing_rain > 0:

    raise SystemExit(
        f"ERROR: {missing_rain} "
        "IMERG steps are missing "
        "inside the simulation window."
    )


rainfall.index.name = (
    "datetime"
)


rainfall = (
    rainfall
    .reset_index()
)


event_rain_mask = (
    (
        rainfall[
            "datetime"
        ]
        >=
        rain_start
    )
    &
    (
        rainfall[
            "datetime"
        ]
        <=
        rain_end
    )
)


event_rainfall_mm = float(
    rainfall.loc[
        event_rain_mask,
        "precip_mm",
    ].sum()
)


window_rainfall_mm = float(
    rainfall[
        "precip_mm"
    ].sum()
)


print(
    f"IMERG files used : "
    f"{len(rain_sources)}"
)

print(
    f"Rain steps       : "
    f"{len(rainfall)}"
)

print(
    f"Missing rain     : "
    f"{missing_rain}"
)

print(
    f"Event rainfall   : "
    f"{event_rainfall_mm:.2f} mm"
)

print(
    f"Window rainfall  : "
    f"{window_rainfall_mm:.2f} mm"
)


# ======================================================================
# FIND USGS DISCHARGE
# ======================================================================

print()
print("=" * 78)
print(
    "USGS DISCHARGE DISCOVERY"
)
print("=" * 78)


flow_frames = []

flow_sources = []


q0_start = (
    rain_start
    -
    pd.Timedelta(
        hours=Q0_HOURS
    )
)


for csv_file in csv_files:

    path_text = str(
        csv_file
    ).lower()


    if not any(
        keyword in path_text
        for keyword in [
            "usgs",
            "discharge",
            "streamflow",
            "flow",
        ]
    ):

        continue


    header = safe_read_csv(
        csv_file,
        nrows=5,
    )


    if header is None:
        continue


    time_col = detect_time_column(
        header.columns
    )


    flow_col, flow_units = (
        detect_flow_column(
            header.columns
        )
    )


    if (
        time_col is None
        or
        flow_col is None
    ):

        continue


    df = safe_read_csv(
        csv_file,
        usecols=[
            time_col,
            flow_col,
        ],
    )


    if (
        df is None
        or
        df.empty
    ):

        continue


    times = pd.to_datetime(
        df[
            time_col
        ],
        utc=True,
        errors="coerce",
    )


    values = pd.to_numeric(
        df[
            flow_col
        ],
        errors="coerce",
    )


    valid_time = (
        times.notna()
    )


    if not valid_time.any():
        continue


    if (
        times[
            valid_time
        ].max()
        <
        q0_start
        or
        times[
            valid_time
        ].min()
        >
        simulation_end
    ):

        continue


    if flow_units == "cfs":

        values = (
            values
            *
            0.028316846592
        )


    temp = pd.DataFrame({

        "datetime":
            times,

        "flow_m3s":
            values,
    })


    temp = temp[
        (
            temp[
                "datetime"
            ]
            >=
            min(
                q0_start,
                simulation_start,
            )
        )
        &
        (
            temp[
                "datetime"
            ]
            <=
            simulation_end
        )
    ]


    if temp.empty:
        continue


    flow_frames.append(
        temp
    )


    flow_sources.append({

        "file":
            str(
                csv_file
            ),

        "time_column":
            time_col,

        "flow_column":
            flow_col,

        "original_units":
            flow_units,
    })


if not flow_frames:

    raise SystemExit(
        "ERROR: Could not find "
        "USGS discharge covering E0015."
    )


discharge = pd.concat(
    flow_frames,
    ignore_index=True,
)


discharge = (
    discharge
    .dropna(
        subset=[
            "datetime"
        ]
    )
    .sort_values(
        "datetime"
    )
    .drop_duplicates(
        subset=[
            "datetime"
        ],
        keep="first",
    )
)


# ======================================================================
# INITIAL FLOW Q0
# ======================================================================

q0_values = discharge[
    (
        discharge[
            "datetime"
        ]
        >=
        q0_start
    )
    &
    (
        discharge[
            "datetime"
        ]
        <
        rain_start
    )
][
    "flow_m3s"
].dropna()


if q0_values.empty:

    raise SystemExit(
        "ERROR: No observations were "
        "available for Q0."
    )


q0 = float(
    q0_values.median()
)


# ======================================================================
# EXACT 30-MIN FLOW
# ======================================================================

flow = discharge[
    (
        discharge[
            "datetime"
        ]
        >=
        simulation_start
    )
    &
    (
        discharge[
            "datetime"
        ]
        <=
        simulation_end
    )
].copy()


# No interpolation.

flow = flow[
    (
        flow[
            "datetime"
        ].dt.minute.isin(
            [
                0,
                30,
            ]
        )
    )
    &
    (
        flow[
            "datetime"
        ].dt.second
        ==
        0
    )
]


flow = (
    flow
    .drop_duplicates(
        subset=[
            "datetime"
        ]
    )
)


expected_flow_times = (
    pd.date_range(
        start=simulation_start,
        end=simulation_end,
        freq="30min",
        tz="UTC",
    )
)


flow = (
    flow
    .set_index(
        "datetime"
    )
    .reindex(
        expected_flow_times
    )
)


missing_flow = int(
    flow[
        "flow_m3s"
    ]
    .isna()
    .sum()
)


flow.index.name = (
    "datetime"
)


flow = (
    flow
    .reset_index()
)


print(
    f"USGS files used : "
    f"{len(flow_sources)}"
)

print(
    f"Initial Q0      : "
    f"{q0:.3f} m3/s"
)

print(
    f"Flow steps      : "
    f"{len(flow)}"
)

print(
    f"Missing flow    : "
    f"{missing_flow}"
)


# ======================================================================
# SAVE FILES
# ======================================================================

output_dir = (
    PROJECT_ROOT
    /
    "hec_hms"
    /
    "inputs"
    /
    EVENT_ID
)


output_dir.mkdir(
    parents=True,
    exist_ok=True,
)


rain_csv = (
    output_dir
    /
    f"{EVENT_ID}_IMERG_30min.csv"
)


flow_csv = (
    output_dir
    /
    f"{EVENT_ID}_USGS_flow_30min.csv"
)


rain_txt = (
    output_dir
    /
    f"{EVENT_ID}_precip_values_only.txt"
)


flow_txt = (
    output_dir
    /
    f"{EVENT_ID}_flow_values_only.txt"
)


metadata_file = (
    output_dir
    /
    f"{EVENT_ID}_HECHMS_event_metadata.json"
)


rainfall.to_csv(
    rain_csv,
    index=False,
)


flow.to_csv(
    flow_csv,
    index=False,
)


rainfall[
    "precip_mm"
].to_csv(
    rain_txt,
    index=False,
    header=False,
)


flow[
    "flow_m3s"
].to_csv(
    flow_txt,
    index=False,
    header=False,
    na_rep="",
)


metadata = {

    "event_id":
        EVENT_ID,

    "event_catalogue":
        str(
            selected_file
        ),

    "event_selection_method":
        selection_method,

    "event_start_column":
        selected_pair[
            "start_col"
        ],

    "event_end_column":
        selected_pair[
            "end_col"
        ],

    "rain_start_utc":
        str(
            rain_start
        ),

    "rain_end_utc":
        str(
            rain_end
        ),

    "event_duration_hours":
        duration_hours,

    "simulation_start_utc":
        str(
            simulation_start
        ),

    "simulation_end_utc":
        str(
            simulation_end
        ),

    "time_step_minutes":
        30,

    "event_rainfall_mm":
        event_rainfall_mm,

    "simulation_window_rainfall_mm":
        window_rainfall_mm,

    "initial_baseflow_q0_m3s":
        q0,

    "missing_precipitation_steps":
        missing_rain,

    "missing_flow_steps":
        missing_flow,

    "initial_hec_hms_parameters": {

        "area_km2":
            1779.24,

        "curve_number":
            63.61,

        "clark_tc_hours":
            30.84,

        "clark_r_hours":
            30.00,

        "recession_constant":
            0.95,

        "ratio_to_peak":
            0.20,

        "dcia_percent":
            0.0,
    },

    "imerg_sources":
        rain_sources,

    "usgs_sources":
        flow_sources,
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


# ======================================================================
# FINAL
# ======================================================================

print()
print("=" * 78)
print(
    "E0015 HEC-HMS EVENT PACKAGE"
)
print("=" * 78)

print(
    f"Rain start      : "
    f"{rain_start}"
)

print(
    f"Rain end        : "
    f"{rain_end}"
)

print(
    f"Duration        : "
    f"{duration_hours:.2f} h"
)

print(
    f"Simulation      : "
    f"{simulation_start} "
    f"-> "
    f"{simulation_end}"
)

print(
    f"Event rainfall  : "
    f"{event_rainfall_mm:.2f} mm"
)

print(
    f"Window rainfall : "
    f"{window_rainfall_mm:.2f} mm"
)

print(
    f"Initial Q0      : "
    f"{q0:.3f} m3/s"
)

print(
    f"Rain steps      : "
    f"{len(rainfall)}"
)

print(
    f"Missing rain    : "
    f"{missing_rain}"
)

print(
    f"Flow steps      : "
    f"{len(flow)}"
)

print(
    f"Missing flow    : "
    f"{missing_flow}"
)


print()
print("=" * 78)
print(
    "FILES CREATED"
)
print("=" * 78)

print(
    rain_csv
)

print(
    flow_csv
)

print(
    rain_txt
)

print(
    flow_txt
)

print(
    metadata_file
)


print()
print("=" * 78)
print(
    "Stage 4A COMPLETE"
)
print("=" * 78)

print()
print(
    "E0015 is ready for HEC-HMS."
)

print(
    "Observed discharge was not interpolated."
)
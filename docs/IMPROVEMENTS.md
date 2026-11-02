# Prioritized improvement suggestions

These are proposed future tests, not completed improvements or promises of success.
The current C072 baseline and its failed criteria should remain unchanged.

## 1. Independently audit rainfall — first priority

Compare basin-average event totals, intensity and timing with available quality-controlled
rain gauges and/or radar for the calibration events, especially E0010 and E0140.
Document spatial coverage, uncertainty and UTC/interval conventions. Assess whether
the rainfall discrepancy is large enough to explain the runoff-volume discrepancy.
Do not infer satellite error solely from streamflow, or treat the uncalibrated band
as rainfall truth. Any correction must be estimated on training data only.

## 2. Improve initial states and antecedent-flow treatment

Review antecedent rain, wetness indicators, hydrograph recession and previous storms.
Separate assumptions about background flow from soil moisture. Test one physically
justified state-aware loss/soil-storage approach or continuous simulation with a
declared warm-up period. Avoid independently fitted CN values for every event:
they can conceal a non-transferable model. Specify how states are initialized in
unseen events using information available before prediction.

## 3. Review event boundaries and delayed runoff

Investigate multi-storm sequences and the runoff tail. Predeclare any new window
definition for a new experiment, applying it consistently rather than extending
only poorly fitting events. Retain the original fixed-window scores for comparison.
Treat overlapping windows as dependent; do not sum their volumes or claim four
independent validation events.

## 4. Test spatial structure only if supported

Assess spatial rainfall, terrain and upstream records before adding subbasins or
reach routing. Compare a minimally subdivided model with the lumped baseline using
the same forcing and scoring rules. Resolve water-volume inconsistencies before
adding routing parameters merely to improve peak timing.

## 5. Use a bounded, falsifiable follow-up experiment

Freeze one change at a time, physical bounds, computational budget, objective,
stopping rules and an unchanged baseline comparison. Report volume, NSE, peak,
timing and hydrographs together; retain failures and boundary maxima. Use sensitivity
checks to assess compensation rather than automatically expanding the search.

## 6. Obtain genuinely unseen evaluation events

The current four held-out events have now been inspected and used for the forcing
sensitivity. They remain evidence for the original frozen baseline evaluation,
but cannot serve as fresh independent validation after redesign. Reserve a new
period/event set before future fitting, accounting for storm-window overlap.

## Smallest defensible next step

Conduct a data-only rainfall and antecedent-state audit of the strongest contrasting
calibration events before running more simulations. If independent evidence points
to rainfall bias, test a training-only forcing correction; if rainfall is consistent
but wetness/carryover is inadequately represented, test a state-aware formulation.
If evidence remains ambiguous, report that uncertainty rather than claiming a fix.

## Supporting method references

These primary references describe the methods; they do not prove the cause of this project's failure.

- [HEC SCS Curve Number loss model](https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/canopy-surface-infiltration-and-runoff-volume/infiltration/scs-curve-number-loss-model)
- [HEC recession baseflow model](https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/baseflow/recession-model)
- [HEC model calibration guidance](https://www.hec.usace.army.mil/confluence/hmsdocs/hmsrd/model-calibration-355276362.html)

# Why the model did not meet its targets

## What the evidence establishes

- Best tested shared vector C072: mean calibration NSE -0.479; held-out mean -0.220.
  All five project screening categories failed. This is not proof that every
  possible parameter vector would fail; the finite experiment stopped at its agreed cap.
- E0140 stormflow estimates were 9.405–12.212 mm under the two primary background
  assumptions, whereas the largest tested CN-bound rainfall excess was 1.729 mm.
  These are diagnostic background-separated estimates, not measured direct runoff.
- C072 simulated direct runoff was excessive in E0010/E0400 and deficient in the
  other four calibration events. A universal multiplier or CN increase would not
  address both directions of error.
- Routing/storage changes alter timing and the fraction leaving within the window;
  they cannot create rainfall excess. Only about 60–66% of generated excess left
  as direct runoff in the calibration windows. Windows were not changed after fitting.
- The E0140 simulated maximum occurred at the control start. Its -57-hour peak
  error is not a usable travel-time calibration target.
- R and recession k reached their upper search bounds. This may indicate parameter
  compensation, but does not by itself justify widening bounds.
- Fixed-parameter uncalibrated-IMERG substitution worsened the mean NSE in both
  groups. A change of product band alone did not solve the problem.

## Plausible explanations that remain unproven

| Hypothesis | Why it deserves investigation | What would distinguish it |
|---|---|---|
| Inadequate initial soil moisture/loss representation | One shared CN/Ia event model cannot reproduce contrasting runoff responses | Independent antecedent-wetness information and a state-aware model comparison |
| Carryover and delayed flow from preceding storms | E0140 has preceding rainfall and flow activity; Q0 is total observed flow, not independently measured groundwater flow | Longer antecedent records and alternative baseflow/state diagnostics |
| Event-dependent rainfall error or spatial averaging | Satellite basin means may miss storm variation; no gauge benchmark exists here | Independent gauge/radar totals, timing and spatial comparison |
| Lumped catchment and simplified routing | One subbasin represents 1779.24 km² | Spatial rainfall/terrain and upstream-flow evidence supporting subdivision |

Timestamp alignment, rainfall-depth conversion and sampled discharge were checked.
The automated GUI reproduction matched 55 statistics and 221 flow values. This
reduces concern about these specific implementation errors; it does not validate
all physical assumptions. Negative findings must remain in the published results.

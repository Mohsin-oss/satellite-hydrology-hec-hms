# Fixed C072 calibrated and uncalibrated IMERG comparison

Completed 2 November 2026. Ten new runs, one per existing event. No fitting.
Only the precipitation band changed. Prior original models, source data, results and final archive passed preservation checks.
This is paired sensitivity on already selected and now-seen events, not a fresh independent validation or independent rainfall-accuracy test.

| Event | Rain change % | Calibrated NSE | Uncalibrated NSE | NSE change |
|---|---:|---:|---:|---:|
| IETD12_E0010 | +22.51 | -0.6835 | -4.3414 | -3.6579 |
| IETD12_E0015 | -20.29 | 0.5717 | -0.7434 | -1.3150 |
| IETD12_E0136 | -17.00 | -0.3820 | -0.9414 | -0.5594 |
| IETD12_E0140 | -40.10 | -1.3038 | -1.4042 | -0.1003 |
| IETD12_E0177 | -10.35 | -0.7800 | -1.0995 | -0.3194 |
| IETD12_E0400 | -29.32 | -0.2975 | 0.3092 | +0.6067 |
| IETD12_E0659 | -23.22 | -0.1809 | -0.1809 | +0.0000 |
| IETD12_E0660 | -22.71 | -0.5186 | -1.0119 | -0.4933 |
| IETD12_E0679 | +11.04 | -0.8881 | -0.8216 | +0.0665 |
| IETD12_E0784 | -28.84 | 0.7085 | -0.6881 | -1.3966 |

Uncalibrated forcing improves NSE for E0400 and E0679, leaves E0659 unchanged and worsens seven events. The unchanged E0659 response reflects rainfall below the fixed initial abstraction for both products. E0010 receives more rain and its existing overprediction becomes larger. E0784 loses its previously positive NSE.

Calibration-event mean NSE: calibrated -0.479205; uncalibrated -1.370089.
Previously evaluated event mean NSE: calibrated -0.219775; uncalibrated -0.675604.
Three-group overlap sensitivity mean NSE: calibrated -0.176452; uncalibrated -0.702010.
The E0659/E0660 overlap remains unchanged. No pooled score or summed flow volume is reported.

The lower absolute mean timing error on the four evaluation events does not demonstrate acceptable timing or magnitude: E0679 changes from a boundary maximum to a weak simulated storm rise, with peak error still about -57.5%. All individual events must retain boundary-peak flags and magnitude errors.

Conclusion: the uncalibrated product does not rescue this fixed baseline. Retain the original calibrated C072 final-baseline decision and all negative findings. The proposed forcing comparison is complete, without choosing a new forcing or tuning against the evaluation events.

Full per-event NSE, modified KGE, both volume-bias definitions, peak/timing error, RMSE, rainfall, boundary flags and water-balance values are in paired_event_metrics.csv. Full means and mean absolute errors are in comparison_result.json and group_summary.csv. Numerical checks cover actual applied rainfall, observations, fresh outputs, NSE, volume and model parameters.

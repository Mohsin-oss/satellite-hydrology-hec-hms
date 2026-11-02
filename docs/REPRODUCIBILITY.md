# Reproducibility and execution boundaries

The full evidence archive is `Project_02_Reproducibility_Package.zip`, prepared
as a separate GitHub release asset. Until that asset is uploaded, obtain it from
the project owner; this repository does not imply that a release already exists.

SHA-256: `a7a733c9832232da58bd87ee6d72238f5d6d5ff47565f6aeed7c16bd6fc142db`

Extract it and, in the extracted folder containing `verify_package.py`, run:

```console
python verify_package.py
```

This standard-library-only verifier checks saved hashes and numerical metrics:
480 calibration, four held-out and ten forcing-comparison hydrographs. It performs
no simulations or downloads. The release recorded 6236 checked payload files.
The GitHub upload folder has a separate integrity manifest for its own files.

Fresh simulation is a different task. Install HEC-HMS 4.14 separately, review the
archived environment/commands and adapt original absolute Windows paths in a new
copy. Historical work scripts may execute at module scope: do not import them
to inspect them. The original requirements are unpinned analysis dependencies;
they are not a verified clean-environment lockfile. Earth Engine access and any
USGS credentials must be supplied independently, never committed.

Historical configuration snapshots may say `not_yet_locked` or RUN05. The confirmed
event split and final locked validation protocol in the evidence archive supersede
those strings. Calibration ranking used sampled-flow bias; validation's primary
volume metric uses trapezoidal integration. See the documented verifier correction.

No clean-machine HEC-HMS rerun or fresh cloud reacquisition is claimed.

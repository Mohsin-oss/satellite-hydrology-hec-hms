# Data sources, attribution and reuse

- Precipitation: NASA GPM IMERG Final Run V07, calibrated and uncalibrated bands,
  basin-mean half-hour series for 2018–2024; original extraction records are archived.
- Discharge: USGS station 02361000, parameter 00060. Exact half-hour values are
  converted from ft³/s to m³/s using 0.028316846592; no interpolation was used.
- Physical inputs: NLCD 2021 land cover, SSURGO hydrologic soil groups and 3DEP terrain.
- Simulation software: US Army Corps of Engineers HEC-HMS 4.14, installed separately.

The full processed rainfall and discharge series, QC and provenance are in the
evidence ZIP. Large raw rasters, software binaries, credentials and virtual
environments are excluded. Whole-period flow completeness was 98.5766%; only the
ten selected event windows were confirmed complete and free of estimated values.

This publication does not relicense third-party data or software. Consult the
source providers' terms and preserve attribution. No blanket open-source license
is asserted for this upload; the owner can select an appropriate code license later.
The evidence archive retains historical local Windows paths and run dates for
provenance. Its automated credential-pattern scan is not a guarantee of absence
of every possible secret.

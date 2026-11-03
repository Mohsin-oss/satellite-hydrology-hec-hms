# Runoff Lab — Satellite Hydrology & HEC-HMS Workspace

A reusable, browser-local dashboard for satellite precipitation–runoff projects in any basin. Explore the public Choctawhatchee case-study demo first, then make an editable copy or start a blank project for your own basin. Enter your station, datasets, event criteria, evidence and HEC-HMS readiness.

## Run

Open `index.html` in a browser, or serve this folder using Python 3:

```sh
python -m http.server 8080
```

Open https://mohsin-oss.github.io/satellite-hydrology-hec-hms/dashboard/ http://localhost:8080. No build step, dependency install, account or backend is required. For consistent browser storage, use a fixed HTTP origin instead of opening the file directly.

1. Explore the read-only demo, then choose **Make an editable copy** or **Start a blank project**. Enter the basin, provider, station, time zone, study period and units.
2. Register datasets with product versions, cadence, QA status and source references.
3. Set event criteria and record their rationale. Defaults are editable suggestions, not universal thresholds.
4. Add event summaries and independently assign selection decisions and calibration/validation roles.
5. Track scripts, outputs, figures and reports using references or public URLs.
6. Record verified evidence, assumptions and open questions separately.
7. Review HEC-HMS readiness and export a JSON backup.

Multiple projects are isolated in browser storage. Import adds a new project without replacing existing ones. Records can be edited or deleted. Export before clearing browser data or changing devices. Project records are not synchronized to GitHub or other visitors.

## Privacy and raw-data preservation

The bundled demo is a curated summary of the public Choctawhatchee case study: station details, source-reported dataset summaries, ten event windows and metrics, public artifact links, evidence and limitations. No local filesystem paths, raw archives, credentials or private hosting identifiers are included. The demo overview loads a published figure from GitHub; source links open public repository files. User-entered project records are not sent to a server. System fonts are used.

The dashboard cannot read, overwrite or execute local research files. Users enter metadata and references; raw time series and GIS datasets remain in their own research repositories. Do not put secrets or private filesystem paths into public exports. Each export contains the current project's user-entered records.

## Research scope

This is a workflow and evidence dashboard, not a rainfall downloader, GIS engine, event detector or HEC-HMS runner. Status labels and checklist marks are user assertions, not automatic quality checks or scientific validation.

Keep original downloads immutable. Record provider, product version, retrieval date, checksum, time zone, cadence and units. Store processing separately and version code and configurations. Preserve observation qualifiers and document missing-data treatment. Evaluate event windows, antecedent rainfall, baseflow, peaks, recession and overlapping rainfall. Keep calibration and independent validation roles separate.

IMERG, USGS and HEC-HMS are workflow concepts, not mandatory data providers or hard-coded model methods. Study areas outside the US may use local discharge and terrain sources.

## Demo and editable copies

New visitors open the read-only demo. Existing saved projects remain intact; select the demo from the project menu or use **Explore the demo**. The original example cannot be edited. Copies receive new project and record IDs, reset workflow/readiness checkboxes, reset dataset review status and event roles, and label copied evidence as unverified for the new study. Blank projects contain no case-study records. Exporting the demo also creates a copy with review claims reset. Import/export retains the existing schema and project isolation.

The example reports a completed experiment with failed calibration and held-out performance criteria. Preparation checkmarks do not imply model validity. Event dates are HEC-HMS control windows; provided rainfall is control-window depth. E0659/E0660 overlap is disclosed. Source-backed evidence summarizes the report rather than claiming a fresh simulator rerun.

## Files and checks

- `index.html`, `style.css`, `app.js`: static dashboard.
- `demo.js`: curated public case study and safe editable-copy creation.
- `model.js`: project model and import validation.
- `tests/model.test.cjs`: dependency-free validation tests.
- `.gitignore`: excludes common secrets, raw-data folders and workspace exports.

With Node.js available:

```sh
node --check app.js
node --test tests/model.test.cjs
```

## Hosting

Serve this folder with any static host. If the parent repository uses GitHub Pages from its root, this app is available under `/dashboard/`. Configure Pages in repository Settings → Pages if it is not already enabled. Uploading source alone does not enable Pages or change repository visibility.

## Limitations

Browser storage can be cleared or reach capacity; exports are the backup mechanism. Figure records link to references rather than uploading images. Files on another computer are not accessible to visitors. Scientific reproducibility still requires the original data, processing environment and analysis code. The parent repository's Apache 2.0 license applies to this dashboard.

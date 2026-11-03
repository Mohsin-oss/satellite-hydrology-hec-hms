/* Curated public case study. No local paths, credentials or raw data. */
(function(root){
 'use strict';
 const M=root.RunoffModel||(typeof require==='function'?require('./model.js'):null);
 const base='https://github.com/Mohsin-oss/satellite-hydrology-hec-hms/blob/main/';
 const report=base+'report/Project_02_Final_Report.md';
 function create(){
  const p=M.fresh();
  Object.assign(p,{id:'demo',name:'Choctawhatchee · public demo',basin:'Choctawhatchee River near Newton, Alabama',station:'02361000',provider:'USGS · parameter 00060',start:'2018-01-01',end:'2024-12-31',area:'1779.24',notes:'Published research case study, summarized from the repository report dated 2 November 2026. One lumped subbasin; SCS CN loss, Clark transform and recession baseflow. C072: CN 68, Ia 23.91 mm, Tc 18 h, R 70 h, daily recession k 0.99. Calibration and held-out acceptance criteria failed. This is not an operational flood model. Station-reported area 1776.73 km² differs from polygon-derived model area 1779.24 km².'});
  p.criteria={ietd:12,pre:24,post:72,baseline:6,minRain:10,note:'Case-study catalogue used IETD 12 h with a 24 h lead and 72 h tail. A 6 h baseline and 10 mm screening threshold were used during screening; these are not universal rules. Final six calibration and four held-out events were selected before fitting. Control windows were not resized after seeing the fit. The final stormflow audit distinguishes constant and recession background assumptions.'};
  for(let i=0;i<M.stages.length;i++)p.tasks[i]=true;
  for(let i=0;i<M.gates.length;i++)p.ready[i]=true;
  const dataset=(name,product,period,cadence,units,status,reference,notes)=>({id:M.id(),name,product,period,cadence,units,status,reference,notes});
  p.datasets=[
   dataset('Basin-average satellite precipitation','NASA GPM IMERG Final Run V07','2018–2024','30 minutes','mm per 30-minute interval','Accepted',report,'Source report records 122,736 expected half-hour intervals. Calibrated band was primary; uncalibrated band used in a fixed-parameter sensitivity experiment. Product calibration is not hydrologic calibration or independent proof of rainfall accuracy.'),
   dataset('Observed discharge','USGS 02361000 · parameter 00060','2015–2024 archive; 2018–2024 primary period','15-minute primary observations; exact half-hour model samples','ft³/s → m³/s using 0.028316846592','Accepted',base+'docs/DATA_SOURCES.md','Whole-period completeness 98.5766%; wider archive contains estimated values. Ten selected event windows separately passed completeness and estimated-value checks. Flow was sampled without interpolation.'),
   dataset('Terrain and accepted catchment','USGS 3DEP','Static physical input','10 m terrain in original preparation','m elevation; km² drainage area','Accepted',report,'Source report uses polygon-derived area 1779.24 km² and one lumped subbasin. Terrain preparation and outlet audits are documented by the project scripts; this dashboard does not rerun their checks.'),
   dataset('Land cover and soil groups','NLCD 2021 and USDA-NRCS SSURGO','NLCD 2021; SSURGO physical inputs','Physical parameterization','Land-cover classes and hydrologic soil groups','Accepted',report,'Used for physical starting information. Final C072 CN 68 is the tested calibration baseline, not a direct soil measurement. Dual-group and imperviousness assumptions must be reviewed for another catchment.')
  ];
  const rows=[
   ['E0010','Calibration','2018-02-09 15:00','2018-02-15 10:00','157.36','-0.6835127','49.8122'],
   ['E0015','Calibration','2018-03-05 05:30','2018-03-09 19:30','40.51','0.5716695','-12.3717'],
   ['E0136','Calibration','2018-12-18 22:00','2018-12-24 14:30','38.24','-0.3820064','-23.6375'],
   ['E0140','Calibration','2019-01-02 10:00','2019-01-07 17:30','29.92','-1.3038426','-31.1753'],
   ['E0177','Calibration','2019-04-24 10:00','2019-04-29 03:00','27.26','-0.7800466','-16.9814'],
   ['E0400','Calibration','2020-12-23 02:30','2020-12-27 23:00','65.21','-0.2974916','35.6517'],
   ['E0659','Validation','2023-01-24 04:30','2023-01-28 19:30','14.81','-0.1808817','-10.8916'],
   ['E0660','Validation','2023-01-28 04:00','2023-02-02 14:00','','-0.5186059','-45.4373'],
   ['E0679','Validation','2023-04-07 12:00','2023-04-11 19:30','','-0.8880975','-32.4907'],
   ['E0784','Validation','2024-02-03 04:30','2024-02-07 21:00','','0.7084857','-17.9131']
  ];
  p.events=rows.map(([id,role,start,end,rain,nse,bias])=>({id:M.id(),name:'IETD12_'+id,start:start+' UTC',end:end+' UTC',rain,peak:'',role,decision:'Selected',reference:base+'tables/ten_event_metrics.csv',notes:`Dates are HEC-HMS control-window boundaries, not rainfall onset/end. Rainfall, where provided, is the report's control-window depth in mm; blank values are not zero. C072 NSE ${nse}; trapezoidal volume bias ${bias}%. Selected means included in the experiment, not performance accepted.`+(id==='E0015'?' Focus example: the only calibration event with positive NSE; its performance does not establish multi-event transferability.':'')+(['E0659','E0660'].includes(id)?' These two held-out windows overlap by 15.5 h; they are not independent samples.':'')}));
  const artifact=(name,kind,path,notes)=>({id:M.id(),name,kind,reference:base+path,status:'Available',notes});
  p.artifacts=[
   artifact('Discharge quality control','Scripts','scripts/04_qc_discharge.py','Historical QA implementation; review dependencies and configuration before reuse.'),
   artifact('IMERG extraction','Scripts','scripts/07_extract_imerg.py','Historical acquisition script. The dashboard does not run cloud extraction.'),
   artifact('IMERG quality control','Scripts','scripts/08_qc_imerg.py','Review cadence, missing data and rate/depth conversion.'),
   artifact('Rainfall event separation','Scripts','scripts/09_identify_rainfall_events.py','Catalogue construction and inter-event separation.'),
   artifact('Link events to discharge','Scripts','scripts/10_link_events_to_discharge.py','Screening implementation; candidate status is distinct from final selection.'),
   artifact('DEM conditioning','Scripts','scripts/13_condition_dem.py','Terrain conditioning; preserve original terrain input.'),
   artifact('Physical curve number','Scripts','scripts/18_compute_curve_number.py','Physical starting value depends on soil and land-cover assumptions.'),
   artifact('Prepare first HEC-HMS event','Scripts','scripts/20_prepare_first_hms_event.py','Preparation example; do not reuse event settings without review.'),
   artifact('Ten-event baseline metrics','Outputs','tables/ten_event_metrics.csv','Six calibration and four held-out rows; NSE, modified KGE, bias and timing metrics.'),
   artifact('Paired forcing metrics','Outputs','tables/forcing_paired_event_metrics.csv','Same parameters, different IMERG band. Sensitivity, not another independent validation.'),
   artifact('Six-event stormflow audit','Outputs','tables/six_event_stormflow_audit.csv','Separates stormflow assumptions from directly observed total discharge.'),
   artifact('Calibration hydrographs','Figures','figures/calibration_hydrographs.png','C072 responses for six calibration events.'),
   artifact('Forcing comparison','Figures','figures/forcing_comparison_summary.png','Published paired forcing comparison.'),
   artifact('Final research report','Reports','report/Project_02_Final_Report.md','Complete experiment and limitations. Acceptance criteria failed.'),
   artifact('Reproducibility guide','Reports','docs/REPRODUCIBILITY.md','Distinguishes offline evidence checks from a clean-machine model rerun.'),
   artifact('Improvement plan','Reports','docs/IMPROVEMENTS.md','Prioritized future work; not completed results.')
  ];
  const evidence=(name,type,notes,reference=report)=>({id:M.id(),name,type,reference,notes,date:'2026-11-02'});
  p.evidence=[
   evidence('The frozen baseline experiment is complete','Verified evidence','Source-backed report statement: 80 shared parameter sets and 480 calibration simulations, then four fixed-parameter held-out runs. Dashboard review did not independently rerun the simulator.'),
   evidence('Calibration and held-out performance criteria failed','Verified evidence','Source-reported mean NSE: calibration −0.479; held-out −0.220. None of the four held-out events passed every project screen. Completed modelling is not validated forecasting.'),
   evidence('Input timing was audited','Verified evidence','Rain start labels were shifted +30 minutes to interval ends; observed flow sampled at exact half-hour times without interpolation. Numerical source-to-DSS and UTC-copy checks are documented in the report.'),
   evidence('Held-out windows have disclosed overlap','Verified evidence','E0659/E0660 share 15.5 h and 32 timestamps. Overlap-group mean NSE −0.176 is descriptive sensitivity, not proof of independence.'),
   evidence('One lumped subbasin and shared parameters','Assumption','The spatial representation and common CN/Clark/recession parameter vector are modelling choices. They may not transfer to another basin.'),
   evidence('Antecedent state or forcing may contribute to mismatch','Open question','Soil state, earlier-event carryover, rainfall errors and model structure are hypotheses. No independent rainfall reference identifies a unique cause.'),
   evidence('Fresh environment reproduction remains unverified','Open question','Offline evidence checks passed, but fresh cloud extraction and a clean-machine end-to-end simulator rerun have not been demonstrated.')
  ];
  return p;
 }
 function editableCopy(source){
  const p=M.validate(source);p.name='My copy · '+source.name;
  p.notes='COPIED EXAMPLE — replace basin-specific data and reverify all evidence before using this for your study.\n\n'+p.notes;
  p.tasks={};p.ready={};
  p.datasets.forEach(r=>{r.status='Not reviewed';r.notes='COPIED EXAMPLE — reverify for your study. '+r.notes});
  p.events.forEach(r=>{r.role='Unassigned';r.decision='Candidate';r.notes='COPIED EXAMPLE — not selected for your basin. '+r.notes});
  p.artifacts.forEach(r=>{r.status='Planned';r.notes='SOURCE DEMO REFERENCE — replace or adapt for your study. '+r.notes});
  p.evidence.forEach(r=>{r.type=r.type==='Open question'?'Open question':'Assumption';r.notes='SOURCE DEMO EXAMPLE — not verified for your study. '+r.notes});
  return p;
 }
 const api={create,editableCopy};root.RunoffDemo=api;if(typeof module!=='undefined')module.exports=api;
})(globalThis);

/* Shared browser/Node data model; no dependencies or network access. */
(function(root){
 'use strict';
 const stages=[['Acquire & preserve','Keep raw downloads immutable. Record provider, product, version, retrieval date and checksums.'],['Quality control','Review time zone, sampling cadence, units, duplicates, gaps, qualifiers and precipitation rate-to-depth conversion.'],['Link & select events','Choose an inter-event dry period; inspect antecedent rainfall, response windows, baseline, peaks and recession.'],['Rainfall–runoff analysis','Document lag, event volume, baseflow method and uncertainty. Keep calibration and validation roles separate.'],['Terrain integration','Review DEM coverage, CRS, conditioning, outlet snap, delineation, land cover and soil assumptions.'],['HEC-HMS preparation','Review forcing, observed flow, physical parameters, time controls, import checks and event roles.']];
 const gates=['Forcing units, interval and timestamp convention verified','Observed flow units and alignment verified','Event coverage, baseline and recession reviewed','Terrain, delineation and outlet evidence reviewed','Loss method and soil/land-cover assumptions documented','Transform and baseflow parameter basis documented','Calibration and independent validation roles assigned','HEC-HMS input import and control interval checked'];
 const id=()=>globalThis.crypto?.randomUUID?.()||Date.now().toString(36)+Math.random().toString(36).slice(2);
 function fresh(){return {id:id(),name:'Untitled watershed',basin:'',station:'',provider:'',start:'',end:'',area:'',timezone:'UTC',flowUnit:'m³/s',rainUnit:'mm',notes:'',criteria:{ietd:12,pre:24,post:72,baseline:6,minRain:10,note:'Suggested starting values only. Justify these for your basin and data resolution.'},tasks:{},ready:{},datasets:[],events:[],artifacts:[],evidence:[]}}
 function validate(p){
  if(!p||typeof p!=='object'||Array.isArray(p))throw Error('Project must be an object.');
  const out=fresh();
  for(const k of ['name','basin','station','provider','start','end','area','timezone','flowUnit','rainUnit','notes']){if(typeof p[k]!=='string'||p[k].length>20000)throw Error('Invalid project field: '+k);out[k]=p[k]}
  if(!out.name.trim())throw Error('A project name is required.');
  if(out.start&&out.end&&out.start>out.end)throw Error('Study end must follow study start.');
  if(!p.criteria||typeof p.criteria.note!=='string')throw Error('Missing criteria.');
  for(const k of ['ietd','pre','post','baseline','minRain']){if(typeof p.criteria[k]!=='number'||!Number.isFinite(p.criteria[k])||p.criteria[k]<0||p.criteria[k]>1000000)throw Error('Invalid criterion: '+k);out.criteria[k]=p.criteria[k]}
  out.criteria.note=p.criteria.note;
  for(const k of ['tasks','ready']){if(!p[k]||typeof p[k]!=='object'||Array.isArray(p[k]))throw Error('Invalid checklist.');out[k]={};for(let i=0;i<(k==='tasks'?stages.length:gates.length);i++)out[k][i]=p[k][i]===true}
  const fields={datasets:['name','product','period','cadence','units','status','reference','notes'],events:['name','start','end','rain','peak','role','decision','reference','notes'],artifacts:['name','kind','reference','status','notes'],evidence:['name','type','reference','notes','date']};
  for(const [k,keys] of Object.entries(fields)){if(!Array.isArray(p[k])||p[k].length>10000)throw Error('Invalid '+k);out[k]=p[k].map(r=>{if(!r||typeof r!=='object')throw Error('Invalid record.');const clean={id:id()};for(const field of keys){if(typeof r[field]!=='string'||r[field].length>20000)throw Error('Invalid '+k+' field: '+field);clean[field]=r[field]}return clean})}
  return out;
 }
 function unpack(text){const x=JSON.parse(text);if(x.schema!==1||x.application!=='runoff-lab')throw Error('Choose a Runoff Lab project export (schema 1).');return validate(x.project)}
 const model={stages,gates,id,fresh,validate,unpack};root.RunoffModel=model;if(typeof module!=='undefined')module.exports=model;
})(globalThis);

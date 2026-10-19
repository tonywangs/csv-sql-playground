import {ingest,project,restore,output} from './core.mjs';
const $=id=>document.getElementById(id);let doc,selected=new Set(),filter='',inspected=null,layer;
const map=L.map('map',{worldCopyJump:false}).setView([20,0],2);
const layers=new Map();
const tell=s=>$('message').textContent=s;
const safely=fn=>async(...args)=>{try{await fn(...args)}catch(e){tell(e.message)}};
function persist(){try{localStorage.setItem('geo-desk',JSON.stringify(project(doc,selected,filter)))}catch{tell('Browser storage unavailable. Save a project file to keep decisions.')}}
const matching=()=>doc.source.features.flatMap((f,i)=>JSON.stringify(f?.properties??{}).toLowerCase().includes(filter.toLowerCase())?[i]:[]);
function inspect(i){inspected=i;$('inspector').textContent=JSON.stringify({ordinal:i,issue:doc.issues[i],feature:doc.source.features[i]},null,2);$('include').disabled=!!doc.issues[i];}
function render(){
 const visible=matching();$('rows').replaceChildren();
 for(const i of visible){const f=doc.source.features[i],tr=document.createElement('tr');tr.tabIndex=0;tr.className=selected.has(i)?'selected':'';
 const td=document.createElement('td'),cb=document.createElement('input');cb.type='checkbox';cb.checked=selected.has(i);cb.disabled=!!doc.issues[i];cb.setAttribute('aria-label',`Include ordinal ${i}`);cb.onchange=()=>{cb.checked?selected.add(i):selected.delete(i);persist();render()};cb.onclick=e=>e.stopPropagation();td.append(cb);tr.append(td);
 for(const value of [i,f?.properties?.NAME||f?.properties?.name||f?.id||'(no ID)',doc.issues[i]||f?.geometry?.type||'Null geometry']){const cell=document.createElement('td');cell.textContent=value;tr.append(cell)}
 tr.onclick=()=>inspect(i);tr.onkeydown=e=>{if(e.key==='Enter')inspect(i)};$('rows').append(tr);
 }
 layers.forEach((l,i)=>{l.setStyle({color:selected.has(i)?'#ce691c':'#39726e',fillColor:selected.has(i)?'#eaa35d':'#8ab5a5',weight:selected.has(i)?2:1,fillOpacity:visible.includes(i)?.55:.1})});
 $('counts').textContent=`${doc.issues.length} total · ${visible.length} matches · ${selected.size} included · ${doc.issues.filter(Boolean).length} unsupported · ${doc.issues.filter(x=>!x).length-selected.size} excluded`;
}
async function open(bytes,name){const next=await ingest(bytes,name);doc=next;selected=new Set();filter='';inspected=null;$('inspector').textContent='Choose a feature.';let msg=`Loaded ${name}.`;
 let saved;try{saved=localStorage.getItem('geo-desk')}catch{msg+=' Browser storage unavailable; use project files.'}if(saved){try{({selected,filter}=restore(doc,JSON.parse(saved)));msg+=' Recovered saved decisions.'}catch{msg+=' Saved decisions belong to different source bytes and were not restored.'}}
 $('filter').value=filter;if(layer)map.removeLayer(layer);layers.clear();layer=L.featureGroup().addTo(map);
 doc.source.features.forEach((f,i)=>{if(doc.issues[i]||!f.geometry)return;const l=L.geoJSON(f,{pointToLayer:(_,p)=>L.circleMarker(p,{radius:5})}).addTo(layer);l.on('click',()=>inspect(i));layers.set(i,l)});
 if(layer.getBounds().isValid())map.fitBounds(layer.getBounds());render();tell(msg);
}
function download(name,text){const url=URL.createObjectURL(new Blob([text],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
$('source').onchange=safely(async e=>{const f=e.target.files[0];e.target.value='';if(f)await open(await f.arrayBuffer(),f.name)});
$('demo').onclick=safely(async()=>open(await(await fetch('../data/countries.geojson')).arrayBuffer(),'countries.geojson'));
$('filter').oninput=()=>{if(!doc)return;filter=$('filter').value;persist();render()};
for(const [id,add]of [['include-visible',true],['exclude-visible',false]])$(id).onclick=()=>{if(!doc)return;matching().forEach(i=>{if(!doc.issues[i])add?selected.add(i):selected.delete(i)});persist();render()};
for(const [id,add]of [['include',true],['exclude',false]])$(id).onclick=()=>{if(inspected===null||doc.issues[inspected])return;add?selected.add(inspected):selected.delete(inspected);persist();render()};
$('clear').onclick=()=>{if(doc){selected.clear();persist();render()}};
$('save').onclick=safely(()=>{if(!doc)throw Error('Open source first');download('selection.project.json',JSON.stringify(project(doc,selected,filter),null,2))});
$('restore').onchange=safely(async e=>{const file=e.target.files[0];e.target.value='';if(!file)return;if(!doc)throw Error('Open the original source before restoring a project');const state=restore(doc,JSON.parse(await file.text()));({selected,filter}=state);$('filter').value=filter;persist();render();tell('Project restored against matching source hash.')});
for(const id of ['export','manifest'])$(id).onclick=safely(async()=>{if(!doc)throw Error('Open source first');const out=await output(doc,selected,filter);download(id==='export'?'selection.geojson':'selection.manifest.json',id==='export'?out.geojson:JSON.stringify(out.manifest,null,2));tell('Exported current selection. Download both GeoJSON and manifest before changing decisions.')});

import {trace, report, escapeHTML as h} from './graph.js';
const $=id=>document.getElementById(id), storeKey='formula-map-project-v1';
let model=null, state={source:null,selected:null,notes:{}}, busy=false;
const status=s=>$('status').textContent=s;
function persist(){try{localStorage.setItem(storeKey,JSON.stringify(state));$('saved').textContent='Saved in this browser. Export JSON for a portable backup.';}catch{$('saved').textContent='Browser storage unavailable or full. Export JSON now to preserve your notes.';}}
function validateState(s){
 if(!s || !/^[0-9a-f]{64}$/.test(s.source?.sha256)||typeof s.selected!=='string'||!s.notes||typeof s.notes!=='object'||Array.isArray(s.notes))throw Error('Invalid project state');
 const notes=Object.create(null);
 if(Object.keys(s.notes).length>50000)throw Error('Too many annotations');
 for(const [k,v] of Object.entries(s.notes)){if(typeof v!=='string'||v.length>10000||k.length>400)throw Error('Invalid annotation');notes[k]=v;}
 return {source:{name:String(s.source.name).slice(0,255),sha256:s.source.sha256,bytes:s.source.bytes},selected:s.selected,notes};
}
try{const saved=localStorage.getItem(storeKey);if(saved){state=validateState(JSON.parse(saved));status('Saved review recovered. Reconnect '+state.source.name+' (matching SHA-256 required).');}}catch{status('Saved state could not be read. Import a project JSON backup.');}
function reset(){model=null;state={source:null,selected:null,notes:{}};try{localStorage.removeItem(storeKey);}catch{}$('workspace').hidden=true;$('source').textContent='';$('json').disabled=$('html').disabled=true;status('Ready for a new workbook. Export your current review before starting a new one.');}
$('reset').onclick=reset;
async function openWorkbook(blob,name){
 if(busy)return;busy=true;status('Inspecting workbook locally…');
 try{
  if(blob.size>10*1024*1024)throw Error('Workbook exceeds 10 MiB');
  const response=await fetch('/api/inspect',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Filename':encodeURIComponent(name)},body:blob});
  const m=await response.json();if(!response.ok)throw Error(m.error);
  if(state.source && state.source.sha256!==m.source.sha256)throw Error('Workbook hash mismatch. Your saved review is unchanged. Reconnect the original workbook, or export your review and choose Start new review.');
  model=m;state.source=m.source;
  if(!state.selected)state.selected=Object.values(m.cells).find(c=>c.kind==='formula')?.id||Object.keys(m.cells)[0];
  if(!state.selected)throw Error('Workbook has no stored cells');
  $('sheet').replaceChildren(...m.sheets.map(s=>new Option(s,s)));
  $('workspace').hidden=false;$('json').disabled=$('html').disabled=false;
  $('source').textContent=`${m.source.name} · ${m.source.bytes.toLocaleString()} bytes · SHA-256 ${m.source.sha256}`;
  $('coverage').textContent=`${m.coverage.supported||0} supported · ${m.coverage.partial||0} partially resolved · ${m.coverage.unsupported||0} unsupported formulas · ${m.coverage.literal||0} stored literal cells. “Supported” means dependency extraction within the documented subset, not a correct formula.`;
  $('unresolved').replaceChildren();
  for(const c of Object.values(m.cells).filter(c=>c.issues.length)){
   const row=document.createElement('p');row.append(cellButton(c.id),document.createTextNode(' '+c.issues.join('; ')));$('unresolved').append(row);
  }
  select(state.selected);status('Workbook connected. Browse cells or follow a dependency below.');
 }catch(e){status(e.message);}finally{busy=false;$('workbook').value='';}
}
$('workbook').onchange=e=>{if(e.target.files[0])openWorkbook(e.target.files[0],e.target.files[0].name);};
for(const b of document.querySelectorAll('[data-demo]'))b.onclick=async()=>{try{const r=await fetch('/demo/'+b.dataset.demo);if(!r.ok)throw Error('Demo unavailable');await openWorkbook(await r.blob(),b.dataset.demo);}catch(e){status(e.message);}};
$('project').onchange=async e=>{
 try{const f=e.target.files[0];if(!f)return;if(f.size>32*1024*1024)throw Error('Project exceeds 32 MiB');const p=JSON.parse(await f.text());const next=validateState(p.state);if(p.model?.source?.sha256!==next.source.sha256)throw Error('Inconsistent project source identity');model=null;state=next;persist();$('workspace').hidden=true;$('json').disabled=$('html').disabled=true;$('source').textContent='';status('Project loaded. Reconnect '+state.source.name+' to verify the workbook hash. Imported analysis is not trusted; it will be recomputed.');}catch(e){status(e.message);}finally{$('project').value='';}
};
function cellButton(id){const b=document.createElement('button');b.textContent=id;b.onclick=()=>select(id);return b;}
function select(id){
 const c=model.cells[id];
 // Blank referenced cells remain navigable.
 if(c){$('sheet').value=c.sheet;$('address').value=c.address;}
 else{const m=/^'((?:[^']|'')*)'!([A-Z]+[1-9][0-9]*)$/.exec(id);if(!m||!model.sheets.includes(m[1].replaceAll("''","'")))return; $('sheet').value=m[1].replaceAll("''","'");$('address').value=m[2];}
 state.selected=id;renderCells();renderDetail();persist();
}
function renderCells(){
 const query=$('filter').value.toLowerCase();const cells=Object.values(model.cells).filter(c=>c.sheet===$('sheet').value&&(!$('formulasOnly').checked||c.kind==='formula')&&[c.address,c.formula,c.value].join(' ').toLowerCase().includes(query));
 $('cellCount').textContent=`${cells.length} matching stored cells; showing first 500. Use an address to jump to any cell.`;
 $('cells').replaceChildren(...cells.slice(0,500).map(c=>{const b=cellButton(c.id);b.textContent=c.address+'  '+String(c.formula??c.value??'blank').slice(0,85);b.setAttribute('aria-current',String(c.id===state.selected));return b;}));
}
function renderDetail(){
 const c=model.cells[state.selected];
 $('detail').innerHTML=`<h2>${h(state.selected)}</h2><span class="badge">${h(c?.kind||'blank / not stored')}</span> <span class="badge">${h(c?.coverage||'literal')}</span><pre class="formula">${h(c?.formula??c?.value??'(blank)')}</pre>${c?.kind==='formula'?`<p>Cached result: <strong>${h(c.cached??'(not stored)')}</strong> · freshness unknown</p>`:''}${c?.formula_attributes?.t==='shared'?'<p>Shared formula expanded from its master; original attributes retained in export.</p>':''}${c?.issues?.length?`<p class="warning">Unresolved boundary: ${h(c.issues.join('; '))}</p>`:''}`;
 $('note').value=state.notes[state.selected]||'';renderTrace();
}
function renderTrace(){
 const t=trace(model,state.selected,$('direction').value,$('transitive').checked,model.limits.trace_nodes);
 $('traceStatus').textContent=`${t.nodes.length-1} reachable cells · ${t.edges.length} evidence edges. ${t.incomplete?'INCOMPLETE: unresolved formulas exist in this workbook or a resource limit was reached.':'Complete within the supported static-reference subset.'} ${t.limited?'Traversal limit reached.':''}`;
 $('traceStatus').className=t.incomplete?'warning':'';
 $('cycles').textContent=t.cycles.length?'Cycle back edges: '+t.cycles.map(c=>c.from+' → '+c.to).join('; '):'No cycle found in this trace.';
 const table=document.createElement('table');table.innerHTML='<thead><tr><th>Formula cell → precedent</th><th>Supporting formula / reference token</th></tr></thead>';
 for(const e of t.edges.slice(0,1000)){
  const row=document.createElement('tr'),a=document.createElement('td'),b=document.createElement('td');a.append(cellButton(e.source),document.createTextNode(' → '),cellButton(e.target));const code=document.createElement('code');code.textContent=e.formula+'\nToken: '+e.reference;b.append(code);row.append(a,b);table.append(row);
 }
 $('trace').replaceChildren(table);
 if(t.edges.length>1000){const p=document.createElement('p');p.textContent='Display limited to 1,000 edges. Export JSON or HTML for all extracted evidence.';$('trace').prepend(p);}
}
$('sheet').onchange=()=>{const c=Object.values(model.cells).find(c=>c.sheet===$('sheet').value);if(c)select(c.id);else renderCells();};
$('go').onsubmit=e=>{e.preventDefault();const a=$('address').value.toUpperCase().replaceAll('$','');if(!/^[A-Z]{1,3}[1-9][0-9]{0,6}$/.test(a)){status('Enter an A1 cell address.');return;}const col=a.match(/[A-Z]+/)[0].split('').reduce((n,c)=>n*26+c.charCodeAt(0)-64,0);if(col>16384||Number(a.match(/[0-9]+/)[0])>1048576){status('Address outside XLSX bounds.');return;}select("'"+$('sheet').value.replaceAll("'","''")+"'!"+a);};
$('filter').oninput=renderCells;$('formulasOnly').onchange=renderCells;
$('direction').onchange=renderTrace;$('transitive').onchange=renderTrace;
$('note').oninput=()=>{state.notes[state.selected]=$('note').value;persist();};
$('boundaries').onclick=()=>$('unresolved').hidden=!$('unresolved').hidden;
function download(text,name,type){const url=URL.createObjectURL(new Blob([text],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('json').onclick=()=>download(JSON.stringify({model,state},null,2),'formula-map-project.json','application/json');
$('html').onclick=()=>download(report(model,state),'formula-map-report.html','text/html');

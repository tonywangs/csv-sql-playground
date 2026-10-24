'use strict';
const $ = id => document.getElementById(id);
const storageKey = 'csv-pivot-desk-v1';
let source = null, result = null, pending = null, busy = false, dirty = false;
const message = text => { $('message').textContent = text; };
const configProject = () => ({version:1, source:result.source, config:result.config});
function persist() {
  try { localStorage.setItem(storageKey, JSON.stringify(configProject())); }
  catch { message('Summary is ready, but browser storage is unavailable. Save the project configuration to recover later.'); }
}
function setBusy(value) {
  busy = value;
  document.querySelectorAll('button, input, select').forEach(el => {el.disabled = value;});
}
function invalidate() {
  result = null;
  $('workspace').hidden = true;
  $('source-name').textContent = 'No source connected.';
}
function markDirty() {
  dirty = true;
  $('dirty').textContent = 'Configuration changed. Apply it to refresh the result and enable export.';
  $('export').disabled = true;
  $('save-project').disabled = true;
}
function options(id, headers, optional = false) {
  $(id).replaceChildren();
  if (optional) $(id).add(new Option('None', ''));
  for (const h of headers) $(id).add(new Option(h, h));
}
function controls() {
  const {headers, config:c} = result;
  options('row', headers); options('column', headers, true); options('value', headers, true); options('filter-column', headers, true);
  for (const k of ['row','column','value','aggregate']) $(k).value = c[k] ?? '';
  $('missing').value = JSON.stringify(c.missing);
  $('types').replaceChildren();
  for (const h of headers) {
    const label = document.createElement('label'); label.append(document.createTextNode(h));
    const select = document.createElement('select'); select.dataset.column = h; select.setAttribute('aria-label', `Type of ${h}`);
    select.add(new Option('Text','text')); select.add(new Option('Number','number')); select.value = c.types[h]; label.append(select); $('types').append(label);
  }
  if (c.filters.length > 1) throw new Error('The browser editor supports one filter. This project has multiple filters.');
  const f = c.filters[0];
  $('filter-column').value = f?.column ?? ''; $('filter-op').value = f?.op ?? 'eq'; $('filter-value').value = f?.value ?? '';
}
function readConfig() {
  return {types:Object.fromEntries([...$('types').querySelectorAll('select')].map(s => [s.dataset.column,s.value])),
    row:$('row').value, column:$('column').value || null, value:$('value').value || null, aggregate:$('aggregate').value,
    missing:JSON.parse($('missing').value), filters:$('filter-column').value ? [{column:$('filter-column').value,op:$('filter-op').value,value:$('filter-value').value}] : []};
}
function cell(row, text) { const td = document.createElement('td'); td.textContent = text; row.append(td); return td; }
function draw() {
  dirty = false; $('dirty').textContent = 'Results reflect the applied configuration. Group labels are preserved exactly, shown as JSON strings.';
  $('workspace').hidden = false;
  $('source-name').textContent = `${result.source.name} · ${result.source.bytes.toLocaleString()} bytes · SHA-256 ${result.source.sha256}`;
  $('recovery').textContent = '';
  $('stats').replaceChildren();
  for (const [key, value] of Object.entries(result.accounting)) {
    const box = document.createElement('div'); box.className = 'stat'; const n = document.createElement('strong'); n.textContent = value.toLocaleString(); box.append(n,document.createTextNode(key)); $('stats').append(box);
  }
  $('caption').textContent = `${result.config.aggregate.toUpperCase()}${result.config.value ? ' of ' + result.config.value : ''} by ${result.config.row}${result.config.column ? ' × ' + result.config.column : ''}`;
  const tbody = $('summary').querySelector('tbody'); tbody.replaceChildren();
  for (const [index,g] of [...result.groups,result.total].entries()) {
    const tr = document.createElement('tr');
    if (index === result.groups.length) tr.className = 'total';
    cell(tr, index === result.groups.length ? 'Grand total' : JSON.stringify(g.row) + (g.column === null ? '' : ' / ' + JSON.stringify(g.column)));
    for (const value of [g.value ?? 'Undefined',g.count,g.valid,g.missing,g.invalid]) cell(tr,value);
    const button = document.createElement('button'); button.textContent = 'Inspect'; button.setAttribute('aria-label',`Inspect ${index === result.groups.length ? 'grand total' : g.row + (g.column ? ' / '+g.column : '')}`);
    button.onclick = () => inspect(g.ordinals, 'Contributing source records', g); cell(tr,'').append(button); tbody.append(tr);
  }
}
function inspect(ordinals,title,group=null,rejected=false) {
  const table = $('records'); table.replaceChildren();
  const head = document.createElement('thead'), tr = document.createElement('tr');
  for (const h of ['Record ordinal','Status',...result.headers]) { const th=document.createElement('th'); th.textContent=h; tr.append(th); } head.append(tr); table.append(head);
  const body = document.createElement('tbody');
  const selected = new Set(ordinals);
  for (const r of (rejected ? result.rejected : result.records).filter(r => selected.has(r.ordinal))) {
    const row = document.createElement('tr'); cell(row,r.ordinal);
    cell(row,rejected ? r.reason : !group ? 'Filtered out' : group.valid_ordinals.includes(r.ordinal) ? 'Valid numeric contributor' : group.missing_ordinals.includes(r.ordinal) ? 'Missing numeric value' : group.invalid_ordinals.includes(r.ordinal) ? 'Invalid numeric value' : 'Count contributor');
    for (const v of r.values) cell(row,v); body.append(row);
  }
  table.append(body); $('drill-title').textContent = title; $('drill-note').textContent = `${ordinals.length} records. Ordinals count parsed records after the header, including quoted multiline fields as one record.`; $('drill').showModal();
}
async function api(path, payload) {
  const response = await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  if (!response.ok) { const body=await response.json(); throw new Error(body.error || 'Request failed'); }
  return response;
}
async function load(raw,name,demo=false) {
  invalidate(); source = null; message(''); setBusy(true);
  try {
    if(raw.byteLength > 2*1024*1024) throw new Error('CSV exceeds 2 MiB.');
    const data = btoa(Array.from(new Uint8Array(raw), b => String.fromCharCode(b)).join(''));
    const candidate = {data,name};
    if(pending && !demo) candidate.project = pending;
    let next = await (await api('/api/analyze',candidate)).json();
    if(demo) {
      const c = next.config; c.types.body_mass_g = 'number'; c.column='island'; c.value='body_mass_g'; c.aggregate='mean'; c.missing=['','NA'];
      next=await (await api('/api/analyze',{data,name,config:c})).json();
    }
    if(next.config.filters.length>1) throw new Error('The browser editor supports one filter.');
    source={data,name}; result=next; pending=null; controls(); draw(); persist();
  } catch(error) { message(error.message); }
  finally {setBusy(false);}
}
function download(blob,name) {
  const url=URL.createObjectURL(blob), a=document.createElement('a'); a.href=url; a.download=name; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
}
$('file').onchange=async e=>{const f=e.target.files[0]; if(f) await load(await f.arrayBuffer(),f.name); e.target.value='';};
$('demo').onclick=async()=>{try{await load(await (await fetch('/demo.csv')).arrayBuffer(),'penguins.csv',true);}catch(e){message(e.message);}};
$('project').onchange=async e=>{
  const f=e.target.files[0]; if(!f)return;
  try {
    if(f.size>100000)throw new Error('Project file exceeds 100 KB.');
    const p=JSON.parse(await f.text());
    if(p.version!==1 || !/^[0-9a-f]{64}$/.test(p.source?.sha256) || !p.config || !Array.isArray(p.config.filters) || p.config.filters.length>1)throw new Error('Unsupported project file.');
    pending=p; source=null; invalidate(); localStorage.setItem(storageKey,JSON.stringify(p));
    $('recovery').textContent=`Project loaded: reconnect ${p.source.name}. The exact source SHA-256 must match.`; message('');
  }catch(error){message(error.message);} e.target.value='';
};
$('config-form').oninput=markDirty;
$('config-form').onchange=markDirty;
$('config-form').onsubmit=async e=>{
  e.preventDefault(); if(busy || !source)return; message(''); setBusy(true);
  try {const next=await (await api('/api/analyze',{...source,config:readConfig(),expected_hash:result.source.sha256})).json(); result=next; draw(); persist();}
  catch(error){message(error.message);markDirty();}
  finally{setBusy(false);$('export').disabled=dirty;$('save-project').disabled=dirty;}
};
$('save-project').onclick=()=>{if(result&&!dirty)download(new Blob([JSON.stringify(configProject(),null,2)],{type:'application/json'}),'project.json');};
$('export').onclick=async()=>{
  if(!result || dirty)return; setBusy(true); message('');
  try {const response=await api('/api/export',{...source,project:configProject()});download(await response.blob(),'pivot-report.zip');}
  catch(error){message(error.message);}finally{setBusy(false);}
};
$('show-filtered').onclick=()=>inspect(result.filtered_ordinals,'Filtered records');
$('show-rejected').onclick=()=>inspect(result.rejected.map(r=>r.ordinal),'Rejected records',null,true);
$('close').onclick=()=>$('drill').close();
$('reset').onclick=()=>{source=null;pending=null;invalidate();try{localStorage.removeItem(storageKey);}catch{}$('recovery').textContent='';message('');};
try {pending=JSON.parse(localStorage.getItem(storageKey));if(pending)$('recovery').textContent=`Saved configuration found. Reconnect ${pending.source.name}; its SHA-256 must match. Or start a new demo.`;}catch{pending=null;}

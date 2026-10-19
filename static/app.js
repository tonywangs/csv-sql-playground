'use strict';
const $ = id => document.getElementById(id);
const KEY = 'jsonl-selection-desk-v1';
let project = {schema:1,source_sha256:null,name:'',filters:[],excluded_lines:[]};
let attached = false, offset = 0, total = 0, busy = false, token;
const notice = (text, error=false) => { $('notice').textContent=text; $('notice').className=error?'error':''; };
function validateProject(p) {
  if (!p || p.schema!==1 || !/^[a-f0-9]{64}$/.test(p.source_sha256) || typeof p.name!=='string' || p.name.length>1024 || !Array.isArray(p.filters) || p.filters.length>30 || !Array.isArray(p.excluded_lines) || p.excluded_lines.length>20000 || p.excluded_lines.some(n=>!Number.isSafeInteger(n)||n<1)) throw Error('Invalid project file');
  return {schema:1,source_sha256:p.source_sha256,name:p.name,filters:p.filters,excluded_lines:p.excluded_lines};
}
function persist() { try {localStorage.setItem(KEY,JSON.stringify(project));} catch {notice('Browser storage unavailable. Use Save project to retain this selection.',true);} }
function controls() { for(const id of ['add','clear','save','export']) $(id).disabled=!attached||busy; for(const id of ['demo','source','projectImport','view']) $(id).disabled=busy; $('prev').disabled=busy||!attached||offset===0; $('next').disabled=busy||!attached||offset+40>=total; }
async function api(url, body, binary=false) {
  const response = await fetch(url,{method:'POST',headers:{'X-Desk-Token':token,...(binary?{}:{'Content-Type':'application/json'})},body:binary?body:JSON.stringify(body)});
  if(!response.ok) throw Error((await response.json()).error);
  return response;
}
function renderFilters() {
  $('filters').replaceChildren();
  project.filters.forEach((f,i)=>{const row=document.createElement('div');row.className='filter';const text=document.createElement('code');text.textContent=`${f.path || '(root)'} ${f.op} ${f.value}`;const remove=document.createElement('button');remove.textContent='Remove';remove.disabled=busy||!attached;remove.onclick=()=>change(()=>project.filters.splice(i,1));row.append(text,remove);$('filters').append(row);});
}
// Format lexically: never JSON.parse source records (which could round numbers).
function pretty(text) {
  let out='',level=0,string=false,escape=false;
  for(const c of text.trim()) {
    if(string){out+=c;if(escape)escape=false;else if(c==='\\')escape=true;else if(c==='"')string=false;continue;}
    if(c==='"'){string=true;out+=c;} else if(c==='{'||c==='['){out+=c+'\n'+'  '.repeat(++level);} else if(c==='}'||c===']'){out+='\n'+'  '.repeat(Math.max(0,--level))+c;} else if(c===','){out+=',\n'+'  '.repeat(level);} else if(c===':'){out+=': ';} else if(!/\s/.test(c))out+=c;
  }
  return out;
}
async function query() {
  const data=await (await api('/api/query',{...project,offset,view:$('view').value})).json();
  if(!data.complete) throw Error('Processing incomplete; export unavailable');
  total=data.view_total;
  $('counts').replaceChildren();
  for(const [key,value] of Object.entries(data.counts)){const box=document.createElement('span'),n=document.createElement('strong');n.textContent=value;box.append(n,document.createTextNode(key));$('counts').append(box);}
  $('page').textContent=total?`${offset+1}–${Math.min(offset+40,total)} of ${total}`:'No matching lines';
  $('records').replaceChildren();
  for(const row of data.rows){const div=document.createElement('div');div.className='record';const check=document.createElement('input');check.type='checkbox';check.checked=!project.excluded_lines.includes(row.line);check.disabled=row.status==='error';check.setAttribute('aria-label',`Allow line ${row.line} if filters match`);check.onchange=()=>change(()=>{project.excluded_lines=project.excluded_lines.filter(n=>n!==row.line);if(!check.checked)project.excluded_lines.push(row.line);});const btn=document.createElement('button');const badge=document.createElement('span');badge.className='badge '+row.status;badge.textContent=`LINE ${row.line} · ${row.status.toUpperCase()} · ${row.type}`;const preview=document.createElement('code');preview.textContent=row.error||row.text;btn.append(badge,preview);btn.onclick=()=>{$('detailTitle').textContent=`Source line ${row.line} · ${row.status}`;$('detail').textContent=row.error?`${row.error}\n\n${row.text}`:pretty(row.text);};div.append(check,btn);$('records').append(div);}
  notice(`Processing complete. ${data.counts.included} included + ${data.counts.excluded} excluded + ${data.counts.errors} errors = ${data.counts.total} input lines. ${project.excluded_lines.length} manual exclusions.`);
  controls();renderFilters();
}
async function run(action) {if(busy)return;busy=true;controls();try{await action();}catch(e){notice(e.message,true);}finally{busy=false;controls();renderFilters();}}
async function change(mutate){await run(async()=>{const before=structuredClone(project);mutate();offset=0;try{await query();persist();}catch(e){project=before;throw e;}});}
async function attach(file,name) {
  await run(async()=>{
    attached=false; $('counts').textContent='Processing… export disabled';$('records').replaceChildren();$('detail').textContent='No record selected.';
    if(file.size>8*1024*1024)throw Error('File exceeds 8 MiB; processing incomplete. Previous selection remains saved.');
    const result=await (await api('/api/import',file,true)).json();
    if(project.source_sha256 && project.source_sha256!==result.source_sha256) {
      // A distinct file is a new selection; never apply saved decisions to it.
      project={schema:1,source_sha256:result.source_sha256,name,filters:[],excluded_lines:[]};
    } else { project.source_sha256=result.source_sha256;project.name=name; }
    offset=0;attached=true;
    $('sourceName').textContent=`${name} · ${result.source_bytes.toLocaleString()} bytes`;$('hash').textContent=`SHA-256 ${result.source_sha256}`;
    try{await query();persist();}catch(e){attached=false;throw e;}
  });
}
function download(blob,name){const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
$('source').onchange=()=>{const f=$('source').files[0];if(f)attach(f,f.name);$('source').value='';};
$('demo').onclick=async()=>{try{const r=await fetch('/demo.jsonl');if(!r.ok)throw Error('Demo unavailable');await attach(await r.blob(),'USGS · January 1, 2024');}catch(e){notice(e.message,true);}};
$('filterForm').onsubmit=e=>{e.preventDefault();if(!attached)return;change(()=>project.filters.push({path:$('path').value,op:$('op').value,value:$('value').value}));};
$('clear').onclick=()=>change(()=>{project.filters=[];project.excluded_lines=[];});
$('save').onclick=()=>download(new Blob([JSON.stringify(project,null,2)+'\n'],{type:'application/json'}),'selection.project.json');
$('export').onclick=()=>run(async()=>{const response=await api('/api/export',project);download(await response.blob(),'selection.zip');notice('Export ready: subset.jsonl + manifest.json. Original bytes and source order preserved.');});
$('projectImport').onchange=()=>run(async()=>{const file=$('projectImport').files[0];if(!file)return;if(file.size>1024*1024)throw Error('Project exceeds 1 MiB');const incoming=validateProject(JSON.parse(await file.text()));if(attached && incoming.source_sha256!==project.source_sha256)throw Error('Source hash mismatch. Project was not restored. Attach its matching source first.');const old=project;project=incoming;offset=0;try{if(attached)await query();else notice('Project loaded. Reattach the matching source to recover selection.');persist();}catch(e){project=old;throw e;}finally{$('projectImport').value='';}});
$('view').onchange=()=>run(async()=>{offset=0;if(attached)await query();});
$('prev').onclick=()=>run(async()=>{offset=Math.max(0,offset-40);await query();});
$('next').onclick=()=>run(async()=>{offset+=40;await query();});
(async()=>{try{token=(await (await fetch('/api/token')).json()).token;const saved=localStorage.getItem(KEY);if(saved){project=validateProject(JSON.parse(saved));notice(`Saved selection found for ${project.name}. Reattach the matching source or load its demo to recover.`);$('hash').textContent=`Expected SHA-256 ${project.source_sha256}`;}renderFilters();controls();}catch(e){notice(e.message,true);}})();

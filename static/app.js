'use strict';
const $=id=>document.getElementById(id);
let report=JSON.parse($('embedded-report').textContent), offline=Boolean(report), active=null, page=0, payload={demo:true}, identities=Object.create(null), busy=false;
const el=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
function message(text,error=false){$('message').textContent=text;$('message').className=error?'error':'';}
function lock(value){busy=value;for(const id of ['demo','compare-files','apply-identity','export-json','export-html'])$(id).disabled=value;}
async function run(){
 if(busy)return;lock(true);message('Comparing snapshots… Results are unavailable until the full comparison finishes.');$('workspace').hidden=true;
 try{
  const response=await fetch('/api/compare',{method:'POST',headers:{'Content-Type':'application/json','X-Desk-Token':'__TOKEN__'},body:JSON.stringify({...payload,identities})});
  const data=await response.json();if(!response.ok)throw Error(data.error);
  report=data;render();
 }catch(e){report=null;message('Comparison incomplete: '+e.message,true);}finally{lock(false);}
}
function render(){
 $('workspace').hidden=false;
 if(offline){$('setup').hidden=true;$('identity-panel').hidden=true;}
 message((offline?'Offline report. ':'')+(report.status==='complete'?'All supported user tables accounted for.':'Incomplete comparison: unsupported tables are listed below.'),report.status!=='complete');
 $('report-title').textContent=report.status==='complete'?'Comparison ready':'Comparison incomplete';
 $('sources').replaceChildren();
 for(const side of ['before','after']){
  const s=report[side];$('sources').append(el('p',`${side.toUpperCase()}: ${s.label} · ${s.bytes.toLocaleString()} bytes · SHA-256 ${s.sha256}`));
  if(s.provenance){
   $('sources').append(el('p',`${s.provenance.dataset} · revision ${s.provenance.revision} · ${s.provenance.revision_date} · ${s.provenance.license}`));
   for(const [name,source] of Object.entries(s.provenance.sources)){
    const p=el('p',`${name}: `),a=el('a',source.url);a.href=source.url;a.rel='noreferrer';p.append(a);$('sources').append(p);
   }
  }
  $('objects-'+side).textContent=side.toUpperCase()+'\n'+JSON.stringify(s.objects,null,2);
 }
 $('tables').replaceChildren();
 for(const [name,t] of Object.entries(report.tables)){
  const button=el('button',(name||'(empty table name)')+' · '+(t.status==='complete'?`${t.before_count} → ${t.after_count}`:'unsupported'));
  button.dataset.table=name;button.onclick=()=>selectTable(name);$('tables').append(button);
 }
 if(active===null||!Object.hasOwn(report.tables,active))active=Object.keys(report.tables)[0]??null;
 document.querySelector('.table-panel').hidden=active===null;
 if(active!==null)selectTable(active);
}
function selectTable(name){
 active=name;page=0;const t=report.tables[name];
 for(const b of $('tables').children)b.classList.toggle('selected',b.dataset.table===name);
 $('table-title').textContent=name||'(empty table name)';
 $('schema-before').textContent='BEFORE\n'+(t.before_schema||'(table absent)');$('schema-after').textContent='AFTER\n'+(t.after_schema||'(table absent)');
 $('identity').replaceChildren();
 for(const c of t.columns){const label=el('label'),input=el('input');input.type='checkbox';input.value=c.name;input.checked=t.identity.includes(c.name);label.append(input,document.createTextNode(' '+c.name));$('identity').append(label);}
 $('identity-description').textContent='Identity: '+(t.identity.length?t.identity.join(' + '):'none (exact multiset)')+(t.identity_valid===false?' · INVALID groups marked ambiguous':t.identity_valid===true?' · validated unique and non-NULL':'');
 $('warnings').textContent=t.warnings.join(' ');
 $('counts').replaceChildren();
 for(const [kind,count] of Object.entries(t.counts)){const c=el('div',undefined,'count');c.append(el('b',t.status==='complete'?count:'—'),el('span',kind.replace('_',' ')));$('counts').append(c);}
 $('accounting').textContent=t.status==='complete'?`Before ${t.before_count} = removed ${t.counts.removed} + changed ${t.counts.changed} + unchanged ${t.counts.unchanged} + ambiguous ${t.counts.ambiguous_before}. After ${t.after_count} = added ${t.counts.added} + changed ${t.counts.changed} + unchanged ${t.counts.unchanged} + ambiguous ${t.counts.ambiguous_after}.`:`Not compared. Known row counts: before ${t.before_count??'unknown'}, after ${t.after_count??'unknown'}. Counts above are unavailable, not zero.`;
 $('inspection').textContent='Select a record above to see typed values and source references.';renderRecords();
}
function valueText(v){if(!v)return '(absent)';if(v[0]==='null')return 'NULL';if(v[0]==='blob')return '0x'+v[1];return v[1];}
function renderRecords(){
 const t=report.tables[active],needle=$('search').value.toLowerCase(),kind=$('filter').value;
 const rows=t.records.filter(r=>(kind==='all'||r.kind===kind)&&(!needle||JSON.stringify(r).toLowerCase().includes(needle)));
 page=Math.min(page,Math.max(0,Math.ceil(rows.length/30)-1));$('records').replaceChildren();
 for(const r of rows.slice(page*30,page*30+30)){
  const button=el('button',undefined,'record');button.append(el('span',r.kind,'badge '+r.kind));
  const sample=(r.after[0]||r.before[0]).values.map(valueText).join(' · ');
  button.append(document.createTextNode(sample.slice(0,180)+(sample.length>180?'…':'')));
  if(r.kind==='ambiguous')button.append(el('small',`${r.before.length} before / ${r.after.length} after — no pairwise match asserted`));
  button.onclick=()=>inspect(r);$('records').append(button);
 }
 $('page-info').textContent=`${rows.length} matching record groups · Page ${page+1} of ${Math.max(1,Math.ceil(rows.length/30))}. Exports include every table and record, regardless of filters.`;
 $('previous').disabled=page===0;$('next').disabled=(page+1)*30>=rows.length;
}
function sourceRef(side,row){
 const snap=report[side];let ref=`${side}: ${snap.label} · table ${active} · scan ordinal ${row.ordinal} · SHA-256 ${snap.sha256}`;
 const source=snap.provenance?.sources[active];if(source)ref+=` · CSV data record ${row.ordinal} · ${source.url}`;
 return ref;
}
function inspect(r){
 const box=$('inspection');box.replaceChildren(el('p',r.kind==='ambiguous'?'Ambiguous group: all occurrences are shown independently. Their order does not imply matching.':'Typed values; highlighted cells differ. Scan ordinals locate rows in this snapshot only.'));
 const columns=report.tables[active].columns;
 if(r.kind==='ambiguous'){
  for(const side of ['before','after'])for(const row of r[side]){const details=el('details');details.append(el('summary',sourceRef(side,row)),el('pre',columns.map((c,i)=>`${c.name}: ${row.values[i][0]} ${valueText(row.values[i])}`).join('\n')));box.append(details);}
  return;
 }
 for(const side of ['before','after'])if(r[side][0])box.append(el('p',sourceRef(side,r[side][0])));
 const table=el('table'),head=el('tr');for(const name of ['Column','Before','After'])head.append(el('th',name));table.append(head);
 columns.forEach((c,i)=>{const tr=el('tr');tr.append(el('th',c.name));const b=r.before[0]?.values[i],a=r.after[0]?.values[i];for(const v of [b,a]){const td=el('td',valueText(v),JSON.stringify(a)!==JSON.stringify(b)?'different':'');if(v)td.append(el('small',v[0]));tr.append(td);}table.append(tr);});box.append(table);
}
function download(name,contents,type){const blob=new Blob([contents],{type});if(blob.size>10*1024*1024){message('Export exceeds 10 MiB; no file generated.',true);return;}const url=URL.createObjectURL(blob),a=el('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('demo').onclick=()=>{payload={demo:true};identities=Object.assign(Object.create(null),{countries:['id'],regions:['id']});active=null;run();};
$('compare-files').onclick=async()=>{
 if(!$('stable').checked){message('Confirm that the files are stable detached snapshots before comparing.',true);return;}
 const next={};
 try{for(const side of ['before','after']){const file=$(side+'-file').files[0];if(!file)throw Error('Choose both snapshot files');if(file.size>8*1024*1024)throw Error('Each database must be at most 8 MiB');const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(Error('File read failed'));reader.readAsDataURL(file);});next[side]={name:file.name,data};}payload=next;identities=Object.create(null);active=null;run();}catch(e){message(e.message,true);}
};
$('apply-identity').onclick=()=>{identities[active]=Array.from($('identity').querySelectorAll('input:checked'),i=>i.value);run();};
$('filter').onchange=$('search').oninput=()=>{page=0;if(report&&active!==null)renderRecords();};
$('previous').onclick=()=>{page--;renderRecords();};$('next').onclick=()=>{page++;renderRecords();};
$('export-json').onclick=()=>{if(report)download('snapshot-comparison.json',JSON.stringify(report,null,2),'application/json');};
$('export-html').onclick=()=>{
 if(!report)return;
 const doc=document.documentElement.cloneNode(true);
 doc.querySelector('#embedded-report').textContent=JSON.stringify(report).replace(/</g,'\\u003c').replace(/>/g,'\\u003e').replace(/&/g,'\\u0026');
 // Remove rendered data and duplicate DOM to keep the export compact; the embedded report restores it offline.
 for(const id of ['sources','tables','records','inspection','identity','counts'])doc.querySelector('#'+id).replaceChildren();
 for(const id of ['objects-before','objects-after','schema-before','schema-after'])doc.querySelector('#'+id).textContent='';
 doc.querySelector('#setup').remove();
 // Keep the setup element for script wiring, hidden and empty of selected filenames.
 const setup=document.createElement('section');setup.id='setup';setup.hidden=true;setup.innerHTML='<button id="demo"></button><button id="compare-files"></button><input id="stable"><input id="before-file"><input id="after-file">';doc.querySelector('main').prepend(setup);
 download('snapshot-comparison.html','<!doctype html>\n'+doc.outerHTML,'text/html');
};
if(report)render();

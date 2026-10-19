/* Graph analysis is deliberately separate from DOM and source parsing. */
export function trace(model, start, direction='precedents', transitive=true, limit=10000) {
  const adj = new Map();
  for (const e of model.edges) {
    const from = direction==='precedents' ? e.source : e.target;
    if (!adj.has(from)) adj.set(from,[]);
    adj.get(from).push(e);
  }
  const next = e => direction==='precedents' ? e.target : e.source;
  const seen = new Set([start]), edges=[], boundaries=[], cycles=[];
  const color = new Map([[start,1]]), stack=[{id:start, i:0}];
  let limited=false;
  while(stack.length) {
    const f=stack[stack.length-1], links=adj.get(f.id)||[];
    if(f.i===0 && model.cells[f.id]?.issues.length) boundaries.push(f.id);
    if(f.i>=links.length) {color.set(f.id,2);stack.pop();continue;}
    const e=links[f.i++], n=next(e);
    if (!seen.has(n) && seen.size>=limit) {limited=true;continue;}
    edges.push(e);
    if(color.get(n)===1) cycles.push({from:f.id,to:n});
    if(!seen.has(n)) {
      seen.add(n);
      if(transitive) {color.set(n,1);stack.push({id:n,i:0});}
      else if(model.cells[n]?.issues.length) boundaries.push(n);
    }
  }
  // Unknown incoming edges may originate anywhere, including array outputs.
  const unresolved=Object.values(model.cells).some(c=>c.issues.length);
  return {start,direction,transitive,nodes:[...seen],edges,boundaries:[...new Set(boundaries)],cycles,limited,incomplete:limited||unresolved};
}
export const escapeHTML = s => String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function report(model, state) {
  const h=escapeHTML, link=id=>`<a href="#${encodeURIComponent(id)}">${h(id)}</a>`;
  const rows=Object.values(model.cells).map(c=>`<tr id="${encodeURIComponent(c.id)}"><td>${h(c.id)}</td><td>${h(c.kind)}</td><td><code>${h(c.formula??c.value)}</code></td><td>${h(c.cached)}</td><td>${h(c.coverage)} ${h(c.issues.join('; '))}</td><td>${h(state.notes[c.id]||'')}</td></tr>`).join('');
  const edges=model.edges.map(e=>`<tr><td>${link(e.source)}</td><td>${link(e.target)}</td><td><code>${h(e.formula)}</code></td><td>${h(e.reference)}</td></tr>`).join('');
  const absent=[...new Set([...model.edges.map(e=>e.target),state.selected,...Object.keys(state.notes)].filter(id=>!model.cells[id]))].map(id=>`<p id="${encodeURIComponent(id)}">${h(id)} — blank / not stored in source worksheet. Annotation: ${h(state.notes[id]||'')}</p>`).join('');
  const t=trace(model,state.selected,'precedents',true,model.limits.trace_nodes);
  const json=JSON.stringify({model,state},null,2);
  return `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Formula Map — ${h(model.source.name)}</title><style>body{font:15px system-ui;margin:2rem;color:#182b2c}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd;padding:.5rem;text-align:left;overflow-wrap:anywhere}code{white-space:pre-wrap}a{color:#006759}pre{white-space:pre-wrap}tr:target{background:#fff0bd}</style><h1>Formula Map · offline review</h1><p>${h(model.source.name)} · ${model.source.bytes} bytes</p><p>SHA-256: <code>${h(model.source.sha256)}</code></p><p>Selected: ${link(state.selected)}</p><p>${h(model.warnings.join(' '))}</p><p>Coverage: ${h(JSON.stringify(model.coverage))}. ${t.incomplete?'INCOMPLETE: unresolved formulas exist or a traversal limit was reached.':'Complete within the documented static reference subset.'} This is not a calculation correctness guarantee.</p><h2>Selected transitive precedent trace</h2><p>Reached cells (visit order, not a dependency chain): ${t.nodes.map(link).join(', ')}</p><p>Cycle back edges: ${h(JSON.stringify(t.cycles))}. Boundaries: ${h(t.boundaries.join(', '))}. Limit reached: ${t.limited}.</p><h2>Cells, formulas, and review notes</h2><table><tr><th>Source cell</th><th>Kind</th><th>Literal / formula</th><th>Cached result (freshness unknown)</th><th>Coverage / boundary</th><th>Annotation</th></tr>${rows}</table>${absent}<h2>Dependency evidence (formula → precedent)</h2><table><tr><th>Formula cell</th><th>Precedent</th><th>Supporting formula</th><th>Reference token</th></tr>${edges}</table><h2>Portable project JSON</h2><p>Includes source metadata, formula attributes, defined names, limits, and annotations. Workbook bytes are not embedded. Reconnect the matching original workbook in Formula Map to resume editing.</p><details><summary>Full machine-readable record</summary><pre>${h(json)}</pre></details></html>`;
}

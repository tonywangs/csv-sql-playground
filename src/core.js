export const FORMAT = 'chart-point-desk/v1';
export const MAX_BYTES = 10 * 1024 * 1024;
export const MAX_POINTS = 10000;
const finite = n => typeof n === 'number' && Number.isFinite(n);
const insist = (ok, message) => { if (!ok) throw new Error(message); };
export function axisTransform(a, size = Infinity) {
  insist(a && ['linear', 'log10'].includes(a.scale), 'Choose linear or log10 axes.');
  insist(Array.isArray(a.anchors) && a.anchors.length === 2, 'Each axis needs two anchors.');
  const [p, q] = a.anchors;
  for (const t of [p,q]) {
    insist(t && finite(t.pixel) && t.pixel >= 0 && t.pixel < size, 'Anchor pixel must be inside the image.');
    insist(finite(t.value), 'Anchor values must be finite numbers.');
    insist(a.scale !== 'log10' || t.value > 0, 'Logarithmic anchor values must be positive.');
  }
  insist(Math.abs(p.pixel-q.pixel) >= 1, 'Axis anchors must be at least one pixel apart.');
  insist(p.value !== q.value, 'Axis anchor values must differ.');
  const f = a.scale === 'log10' ? Math.log10 : v => v;
  const slope = (f(q.value)-f(p.value))/(q.pixel-p.pixel);
  const intercept = f(p.value)-slope*p.pixel;
  insist(finite(slope) && slope !== 0 && finite(intercept), 'Calibration exceeds numeric limits.');
  return { scale:a.scale, slope, intercept, formula: a.scale === 'log10' ? 'value = 10 ** (slope * pixel + intercept)' : 'value = slope * pixel + intercept' };
}
export function axisValue(a, pixel) {
  const t = axisTransform(a), z=t.slope*pixel+t.intercept;
  const v = a.scale === 'log10' ? 10**z : z;
  insist(finite(v) && (a.scale !== 'log10' || v>0), 'Point exceeds the numeric range of this calibration.');
  return v;
}
export function values(state, point) {
  insist(state.calibration, 'Calibrate both axes first.');
  return {x:axisValue(state.calibration.x,point.px),y:axisValue(state.calibration.y,point.py)};
}
export function validateProject(s) {
  insist(s && s.format === FORMAT, 'Unsupported project format.');
  insist(s.image && /^[a-f0-9]{64}$/.test(s.image.sha256), 'Missing or invalid source-image SHA-256.');
  insist(typeof s.image.name === 'string' && s.image.name.length <= 500, 'Invalid image name.');
  for (const d of ['width','height']) insist(Number.isInteger(s.image[d]) && s.image[d]>0 && s.image[d]<=10000, 'Image dimensions must be 1–10,000 pixels.');
  insist(s.image.width*s.image.height<=25000000, 'Image exceeds 25 megapixels.');
  if (s.calibration !== null) {
    insist(s.calibration && typeof s.calibration==='object','Invalid calibration.');
    axisTransform(s.calibration.x,s.image.width); axisTransform(s.calibration.y,s.image.height);
  }
  insist(Array.isArray(s.series) && s.series.length>0 && s.series.length<=100,'Use 1–100 series.');
  const ids=new Set();
  for(const r of s.series) {
    insist(r && typeof r.id==='string' && r.id.length<=100 && !ids.has(r.id),'Invalid or duplicate series ID.'); ids.add(r.id);
    insist(typeof r.name==='string' && r.name.trim().length>0 && r.name.length<=200,'Series names must contain 1–200 characters.');
  }
  insist(ids.has(s.activeSeries),'Active series is missing.');
  insist(Array.isArray(s.points) && s.points.length<=MAX_POINTS,'At most 10,000 points are supported.');
  const pointIds=new Set();
  for(const r of s.points) {
    insist(r && typeof r.id==='string' && r.id.length<=100 && !pointIds.has(r.id),'Invalid or duplicate point ID.'); pointIds.add(r.id);
    insist(ids.has(r.series),'Point series is missing.');
    insist(finite(r.px) && finite(r.py) && r.px>=0 && r.py>=0 && r.px<s.image.width && r.py<s.image.height,'Point must be inside the source image.');
    if(s.calibration) values(s,r);
  }
  return s;
}
export function newProject(image) {
  return validateProject({format:FORMAT,image,calibration:null,series:[{id:'series-1',name:'Series 1'}],activeSeries:'series-1',points:[]});
}
export async function sha256(data) {
  const bytes = typeof data==='string' ? new TextEncoder().encode(data) : data;
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(b=>b.toString(16).padStart(2,'0')).join('');
}
export function parseProject(text) {
  insist(new TextEncoder().encode(text).length<=MAX_BYTES,'Project exceeds 10 MiB.');
  return validateProject(JSON.parse(text));
}
const csvCell = v => '"'+String(v).replaceAll('"','""')+'"';
export async function exportBundle(state) {
  validateProject(state); insist(state.calibration,'Calibrate both axes before exporting values.');
  const rows=['series,series_id,point_id,order,pixel_x,pixel_y,approximate_x,approximate_y'];
  const orders=new Map();
  for(const p of state.points) {
    const order=(orders.get(p.series)||0)+1; orders.set(p.series,order);
    const v=values(state,p), name=state.series.find(s=>s.id===p.series).name;
    rows.push([name,p.series,p.id,order,p.px,p.py,v.x,v.y].map(csvCell).join(','));
  }
  const csv=rows.join('\r\n')+'\r\n', project=JSON.stringify(state,null,2)+'\n';
  const manifest={format:'chart-point-desk-manifest/v1',approximate:true,
    warning:'Digitized estimates, not original measurements. Pixel-placement sensitivity is not statistical uncertainty.',
    image:state.image,coordinateSystem:'Source image pixels; origin top-left; x rightward; y downward; no image transformation.',
    calibration:state.calibration,transformations:{x:axisTransform(state.calibration.x),y:axisTransform(state.calibration.y)},
    series:state.series,points:state.points.map(p=>({...p,...values(state,p)})),
    outputs:{'points.csv':{sha256:await sha256(csv)},'project.json':{sha256:await sha256(project)}},
    csv:{encoding:'UTF-8',lineEnding:'CRLF',order:'Insertion order; order column is one-based within each series',labels:'Exact labels; spreadsheet users must import text columns as text to avoid formula interpretation.'}};
  return {csv,project,manifest:JSON.stringify(manifest,null,2)+'\n'};
}

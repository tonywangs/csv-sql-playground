export const hash=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),x=>x.toString(16).padStart(2,'0')).join('');
const fail=m=>{throw Error(m)};
export function reason(f){
 try{
 if(!f||f.type!=='Feature'||!('geometry'in f)||!('properties'in f)||f.properties!==null&&(typeof f.properties!=='object'||Array.isArray(f.properties)))fail('Malformed Feature');
 if('id'in f&&typeof f.id!=='string'&&typeof f.id!=='number')fail('Invalid ID');
 if(f.crs)fail('Legacy CRS is unsupported');
 const g=f.geometry;if(g===null)return null;
 if(!g||g.crs)fail('Invalid geometry or CRS');
 const pos=p=>{if(!Array.isArray(p)||p.length<2||p.length>3||!p.every(Number.isFinite)||Math.abs(p[0])>180||Math.abs(p[1])>90)fail('Invalid WGS84 position');};
 const line=(l,n=2)=>{if(!Array.isArray(l)||l.length<n)fail('Too few positions');l.forEach(pos);for(let i=1;i<l.length;i++)if(Math.abs(l[i][0]-l[i-1][0])>180)fail('Uncut antimeridian segment');};
 const ring=r=>{line(r,4);if(JSON.stringify(r[0])!==JSON.stringify(r.at(-1)))fail('Unclosed ring');};
 const many=(a,fn)=>{if(!Array.isArray(a)||!a.length)fail('Empty coordinates');a.forEach(fn);};
 const poly=p=>many(p,ring);
 switch(g.type){case 'Point':pos(g.coordinates);break;case 'MultiPoint':many(g.coordinates,pos);break;case 'LineString':line(g.coordinates);break;case 'MultiLineString':many(g.coordinates,x=>line(x));break;case 'Polygon':poly(g.coordinates);break;case 'MultiPolygon':many(g.coordinates,poly);break;default:fail('Unsupported geometry: '+g.type);}
 return null;
 }catch(e){return e.message;}
}
export async function ingest(bytes,name='source.geojson'){
 if(bytes.byteLength>8*1024*1024)fail('Limit: 8 MiB');
 const text=new TextDecoder('utf-8',{fatal:true}).decode(bytes);
 assertUniqueKeys(text);
 const source=JSON.parse(text,(k,v,ctx)=>{if(typeof v==='number'&&(!Number.isFinite(v)||Object.is(v,-0)||Number.isInteger(v)&&!Number.isSafeInteger(v)))fail('Unsafe JSON number');return v;});
 if(source.type!=='FeatureCollection'||!Array.isArray(source.features)||source.crs)fail('Expected RFC 7946 FeatureCollection without legacy CRS');
 if(source.features.length>2000)fail('Limit: 2,000 features');
 return {source,name,sourceHash:await hash(bytes),issues:source.features.map(reason)};
}
export function restore(doc,state){
 if(state.version!==1||state.sourceHash!==doc.sourceHash)fail('Source bytes changed or missing: decisions not restored');
 if(typeof state.filter!=='string'||!Array.isArray(state.selected)||state.selected.some(i=>!Number.isInteger(i)||i<0||i>=doc.issues.length||doc.issues[i]))fail('Invalid project decisions');
 return {selected:new Set(state.selected),filter:state.filter};
}
export function project(doc,selected,filter){return {version:1,sourceHash:doc.sourceHash,sourceName:doc.name,selected:[...selected].sort((a,b)=>a-b),filter};}
export async function output(doc,selected,filter){
 const ordinals=[...selected].sort((a,b)=>a-b);restore(doc,project(doc,selected,filter));
 const geojson=JSON.stringify({type:'FeatureCollection',features:ordinals.map(i=>doc.source.features[i])},null,2)+'\n';
 const unsupported=doc.issues.flatMap((reason,ordinal)=>reason?[{ordinal,reason}]:[]);
 const manifest={...project(doc,selected,filter),sourceCount:doc.issues.length,sourceOrdinals:ordinals,excluded:doc.issues.flatMap((r,i)=>!r&&!selected.has(i)?[i]:[]),unsupported,criteria:{filter,mode:'Explicit ordinal selection; filter does not itself select'},outputHash:await hash(new TextEncoder().encode(geojson))};
 return {geojson,manifest};
}

function assertUniqueKeys(text){
 // JSON.parse validates grammar; this lexical pass additionally rejects repeated object keys.
 const stack=[];
 for(const token of text.match(/"(?:\\.|[^"\\])*"|[{}\[\],:]|[^\s{}\[\],:]+/g)||[]){
  if(token==='{')stack.push({keys:new Set(),key:true});
  else if(token==='[')stack.push(null);
  else if(token==='}'||token===']')stack.pop();
  else if(token===','){if(stack.at(-1))stack.at(-1).key=true;}
  else if(token.startsWith('"')&&stack.at(-1)?.key){const frame=stack.at(-1),key=JSON.parse(token);if(frame.keys.has(key))fail('Duplicate JSON object key');frame.keys.add(key);frame.key=false;}
 }
}

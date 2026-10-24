import Ajv from 'ajv';
import {parseTree} from 'jsonc-parser';
export const DIALECT='http://json-schema.org/draft-07/schema#';
export const CONFIG={validator:'Ajv 8.17.1',dialect:DIALECT,formats:'annotation only',allErrors:true,coerceTypes:false,useDefaults:false,removeAdditional:false,maxBytes:1048576,maxResources:16,maxDepth:80,timeoutMs:5000,maxFindings:5000};
export const escapePointer=s=>s.replace(/~/g,'~0').replace(/\//g,'~1');
export function pointer(value,path){ if(path==='')return value; if(!path.startsWith('/'))throw Error('Not a JSON Pointer'); return path.slice(1).split('/').reduce((v,k)=>{k=k.replace(/~1/g,'/').replace(/~0/g,'~');if(v===null||typeof v!=='object'||!Object.hasOwn(v,k))throw Error('Missing pointer '+path);return v[k]},value); }
export function parse(text){
 if(new TextEncoder().encode(text).length>CONFIG.maxBytes)throw Error('resource-limit: file exceeds 1 MiB');
 const errors=[]; const tree=parseTree(text,errors,{allowTrailingComma:false,disallowComments:true});
 if(errors.length||!tree)throw Error('malformed-input: invalid JSON at byte/character offset '+(errors[0]?.offset??0));
 function walk(n,d){if(d>CONFIG.maxDepth)throw Error('resource-limit: nesting exceeds 80');if(n.type==='object'){const keys=new Set();for(const p of n.children||[]){const key=p.children[0].value;if(keys.has(key))throw Error('malformed-input: duplicate key '+key);keys.add(key)}}if(n.type==='number'&&(!Number.isFinite(n.value)||(Number.isInteger(n.value)&&!Number.isSafeInteger(n.value))))throw Error('unsupported: unsafe numeric precision');for(const c of n.children||[])walk(c,d+1)}walk(tree,0);
 return JSON.parse(text);
}
export async function sha(bytes){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('')}
export async function resource(name,bytes){if(bytes.byteLength>CONFIG.maxBytes)throw Error('resource-limit: file exceeds 1 MiB');let text;try{text=new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(bytes)}catch{throw Error('malformed-input: invalid UTF-8')}parse(text);return {name,text,hash:await sha(bytes)}}
export function validate(document,resources){
 const base={configuration:CONFIG,coverage:'incomplete',status:'interrupted',findings:[],document:{name:document.name,hash:document.hash},resources:resources.map(({name,hash})=>({name,hash}))};
 try {
 if(!resources.length||resources.length>CONFIG.maxResources)throw Error('resource-limit: import 1–16 schema resources');
 const data=parse(document.text),schemas=resources.map(r=>parse(r.text));
 const ajv=new Ajv({allErrors:true,verbose:true,strictSchema:true,strictTypes:false,strictTuples:false,strictRequired:false,allowUnionTypes:true,validateFormats:false,inlineRefs:false,loopRequired:100,loopEnum:100});
 const locations=new WeakMap();
 function index(v,p,r){if(v&&typeof v==='object'){locations.set(v,{resource:r,pointer:p});for(const [k,x] of Object.entries(v))index(x,p+'/'+escapePointer(k),r)}}
 function guard(v){
 if(!v||typeof v!=='object'||Array.isArray(v))return;
 if(v.$async)throw Error('unsupported: asynchronous schemas');
 if(v.$ref&&Object.keys(v).some(k=>!['$ref','$id','$schema','$comment','title','description','default','examples','definitions'].includes(k)))throw Error('unsupported: assertion siblings of $ref in draft-07');
 for(const k of ['definitions','properties','patternProperties','dependencies'])for(const child of Object.values(v[k]||{}))guard(child);
 for(const k of ['additionalProperties','additionalItems','contains','propertyNames','not','if','then','else'])guard(v[k]);
 for(const k of ['allOf','anyOf','oneOf'])for(const child of v[k]||[])guard(child);
 if(Array.isArray(v.items))v.items.forEach(guard);else guard(v.items);
 }
 for(let i=0;i<schemas.length;i++){
 const s=schemas[i];if(s&&s.$schema&&s.$schema!==DIALECT)throw Error('unsupported: only explicit draft-07 is supported');
 if(!ajv.validateSchema(s))throw Error('invalid-schema: '+ajv.errorsText());guard(s);index(s,'',i);
 }
 for(let i=0;i<schemas.length;i++)ajv.addSchema(schemas[i],`urn:desk:resource:${i}`);
 const fn=ajv.getSchema('urn:desk:resource:0');const ok=fn(data);
 base.status=ok?'valid':'invalid-document';base.coverage='complete';
 if((fn.errors||[]).length>CONFIG.maxFindings)throw Error('resource-limit: more than 5000 findings');
 base.findings=(fn.errors||[]).map((e,i)=>{
 let loc=locations.get(e.parentSchema);
 if(e.keyword==='false schema'){const p=decodeURIComponent(e.schemaPath.split('#').pop()).replace(/\/false schema$/,'');const matches=[];schemas.forEach((s,r)=>{try{if(pointer(s,p)===false)matches.push({resource:r,pointer:p})}catch{}});if(matches.length===1)loc=matches[0]}
 if(!loc)throw Error('unsupported: unable to locate schema rule');
 const sp=e.keyword==='false schema'?loc.pointer:loc.pointer+'/'+escapePointer(e.keyword);const rule=pointer(schemas[loc.resource],sp);const value=pointer(data,e.instancePath);
 return {id:String(i),documentPointer:e.instancePath,schemaResource:resources[loc.resource].name,schemaHash:resources[loc.resource].hash,schemaPointer:sp,keyword:e.keyword,message:e.message,params:e.params,value,rule,context:e.schemaPath};
 });return base;
 }catch(e){const msg=String(e.message||e);base.coverage='incomplete';base.findings=[];base.status=e.missingRef?'unresolved-reference':/invalid-schema|schema is invalid/.test(msg)?'invalid-schema':/resource-limit/.test(msg)?'resource-limit':/malformed-input/.test(msg)?'malformed-input':/unsupported|unknown keyword|strict mode/.test(msg)?'unsupported':/already exists|resolves to more than/.test(msg)?'duplicate-resource-id':'interrupted';base.error=msg;return base}
}
export function identity(document,resources){return JSON.stringify([document.hash,...resources.map(r=>[r.name,r.hash])])}
export function htmlReport(report){const esc=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');return '<!doctype html><html lang="en"><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><title>JSON Schema Review</title><style>body{font:16px system-ui;margin:3rem;max-width:1000px}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>JSON Schema Review</h1><p>Schema validity does not establish factual correctness. Input strings are inert text.</p><pre>'+esc(JSON.stringify(report,null,2))+'</pre></html>'}

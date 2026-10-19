import { chromium } from 'playwright';
import { parse } from 'csv-parse/sync';
import assert from 'node:assert/strict';
import { spawn, execFileSync } from 'node:child_process';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { createHash } from 'node:crypto';
import net from 'node:net';
const hash=b=>createHash('sha256').update(b).digest('hex');
const dir=await mkdtemp(join(tmpdir(),'csv-join-test-'));
const probe=net.createServer();await new Promise(r=>probe.listen(0,'127.0.0.1',r));const port=probe.address().port;await new Promise(r=>probe.close(r));
const server=spawn('python3',['app.py','--port',String(port)],{cwd:resolve('.'),stdio:['ignore','pipe','pipe']});
let browser;
try {
  await new Promise((resolve,reject)=>{server.stdout.once('data',resolve);server.once('error',reject);server.once('exit',code=>reject(Error('Server exited '+code)));});
  browser=await chromium.launch({headless:true,env:{...process.env,XDG_CONFIG_HOME:dir,XDG_CACHE_HOME:dir},...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{})});
  const page=await browser.newPage({viewport:{width:1440,height:1100}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const base=`http://127.0.0.1:${port}`;
  const ready=async()=>{await page.waitForFunction(()=>!document.querySelector('main').inert);};
  const click=async id=>{await page.locator('#'+id).click();await ready();};
  const save=async(id,name)=>{const download=page.waitForEvent('download');await page.locator('#'+id).click();const d=await download;const path=join(dir,name);await d.saveAs(path);return path;};
  const upload=async(side,name,text)=>{await page.locator('#'+side+'File').setInputFiles({name,mimeType:'text/csv',buffer:Buffer.from(text)});await ready();};
  const choose=async(id,value)=>{await page.locator('#'+id).selectOption(value);};
  const expectText=async(id,text)=>assert.ok((await page.locator('#'+id).innerText()).includes(text),`${id} must contain ${text}`);
  await page.goto(base);await click('demo');await expectText('leftInfo','300 records');await expectText('rightInfo','249 records');
  await click('inspect');await expectText('metrics','471');await expectText('metrics','0 / 171');
  await page.getByText('Unmatched and missing-key records',{exact:true}).click();assert.equal(await page.locator('#unmatched tbody tr').count(),171);
  await click('execute');await expectText('resultCount','471 output rows');
  const csvPath=await save('csv','joined.csv');const manifestPath=await save('manifest','manifest.json');const projectPath=await save('saveProject','project.json');
  const raw=await readFile(csvPath), manifest=JSON.parse(await readFile(manifestPath,'utf8'));assert.equal(hash(raw),manifest.output.sha256);
  const output=parse(raw,{bom:true});const l=parse(await readFile('data/airports.csv'),{bom:true});const r=parse(await readFile('data/countries.csv'),{bom:true});
  assert.equal(output.length,472);const expectedPairs=[];const seen=new Set();
  for(let i=1;i<l.length;i++){let matched=false;for(let j=1;j<r.length;j++)if(l[i][8]!==''&&l[i][8]===r[j][1]){expectedPairs.push([i,j]);seen.add(j);matched=true;}if(!matched)expectedPairs.push([i,null]);}
  for(let j=1;j<r.length;j++)if(!seen.has(j))expectedPairs.push([null,j]);
  assert.deepEqual(manifest.pairs,expectedPairs);
  expectedPairs.forEach(([a,b],i)=>assert.deepEqual(output[i+1],[a===null?'':String(a),b===null?'':String(b),...[1,3,8,10].map(c=>a===null?'':l[a][c]),...[1,2,3].map(c=>b===null?'':r[b][c])]));
  execFileSync('python3',['scripts/verify_export.py','data/airports.csv','data/countries.csv',csvPath,manifestPath],{stdio:'inherit'});
  if(process.env.JOIN_SCREENSHOT){await page.getByText('Unmatched and missing-key records',{exact:true}).click();await page.screenshot({path:process.env.JOIN_SCREENSHOT,fullPage:true});}
  // Reload recovery requires reselecting BOTH byte-identical original files.
  await page.reload();assert.equal(await page.locator('#restore').isDisabled(),true);assert.equal(await page.locator('#configuration').isVisible(),false);
  await page.locator('#leftFile').setInputFiles('data/airports.csv');await ready();assert.equal(await page.locator('#restore').isDisabled(),true);
  await page.locator('#rightFile').setInputFiles('data/countries.csv');await ready();assert.equal(await page.locator('#restore').isEnabled(),true);await click('restore');
  assert.equal(await page.locator('.left-key').inputValue(),'8');assert.equal(await page.locator('#join').inputValue(),'full');
  await click('inspect');await click('execute');const recovered=await save('csv','recovered.csv');assert.deepEqual(await readFile(recovered),raw);
  // Imported settings from disk, mismatching source bytes, then recovery.
  await click('discard');await page.locator('#projectFile').setInputFiles(projectPath);await ready();
  await upload('right','modified.csv',(await readFile('data/countries.csv','utf8')).replace('Afghanistan','Changed country'));
  assert.equal(await page.locator('#restore').isDisabled(),true);await expectText('recovery','matching SHA-256 hashes');
  await page.locator('#rightFile').setInputFiles('data/countries.csv');await ready();await click('restore');
  // Relationship validation with real duplicate country keys on left.
  await choose('relationship','one-to-one');await click('inspect');await expectText('validation','One-to-one');assert.equal(await page.locator('#execute').isDisabled(),true);
  // Synthetic control: 2 × 2 expansion plus unmatched records.
  await click('discard');await upload('left','control-left.csv','k,v\na,1\na,2\nb,3\n');await upload('right','control-right.csv','k,v\na,x\na,y\nz,z\n');
  await choose('relationship','many-to-one');await click('inspect');await expectText('validation','Many-to-one');
  await choose('relationship','unrestricted');await click('inspect');await expectText('validation','Acknowledge');assert.equal(await page.locator('#execute').isDisabled(),true);
  await page.locator('#ack').check();await page.locator('#limit').fill('5');await page.locator('#limit').blur();await page.locator('#ack').check();await click('inspect');await expectText('validation','exceeds output limit');
  await page.locator('#limit').fill('6');await page.locator('#limit').blur();await page.locator('#ack').check();await click('inspect');await click('execute');await expectText('resultCount','6 output rows');
  // Composite + missing + Unicode + multiline control, independent parser reopening.
  const left='k,c,v\n01,é,"hello\nworld"\n1,é,one\n01,é,combining\n,é,missing\n';const right='k,c,v\n01,é,match\n01,é,decomposed\n,é,missing\n';
  await upload('left','composite-left.csv',left);await upload('right','composite-right.csv',right);await page.locator('#limit').fill('100');await page.locator('#limit').blur();await click('addKey');await page.locator('.left-key').nth(1).selectOption('1');await page.locator('.right-key').nth(1).selectOption('1');
  await click('inspect');await expectText('metrics','5');await click('execute');const compositeCSV=await save('csv','composite.csv');const compositeManifest=await save('manifest','composite.json');
  assert.ok(parse(await readFile(compositeCSV)).some(row=>row.includes('hello\nworld')));await writeFile(join(dir,'left.csv'),left);await writeFile(join(dir,'right.csv'),right);execFileSync('python3',['scripts/verify_export.py',join(dir,'left.csv'),join(dir,'right.csv'),compositeCSV,compositeManifest],{stdio:'inherit'});
  // Invalid files cannot leave a stale export available.
  await upload('right','broken.csv','k,k\nx,y\n');await expectText('status','duplicate/empty headers');assert.equal(await page.locator('#result').isVisible(),false);assert.equal(await page.locator('#configuration').isVisible(),false);
  // Phone layout, no horizontal document overflow.
  await page.setViewportSize({width:390,height:844});await click('demo');await click('inspect');await click('execute');assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
  assert.deepEqual(errors,[]);
  console.log('PASS browser: real import, inspection, validation, export, independent parsing, reload/project recovery, hash mismatch, expansion/limit controls, composite/missing/Unicode/multiline, rejection, mobile layout.');
} finally {if(browser)await browser.close();server.kill();await rm(dir,{recursive:true,force:true});}

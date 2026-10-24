// Complete browser acceptance workflow; real USGS data, no external network.
const {chromium} = require('playwright');
const {spawn, spawnSync} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const root = path.resolve(__dirname,'..');
const tmp = fs.mkdtempSync(path.join(os.tmpdir(),'jsonl-browser-'));
const server = spawn('python3',['-u','desk.py','--port','0'],{cwd:root,stdio:['ignore','pipe','inherit']});
const address = new Promise((resolve,reject)=>{server.stdout.once('data',b=>resolve(b.toString().match(/http:\/\/127\.0\.0\.1:\d+/)[0]));server.once('error',reject);server.once('exit',()=>reject(Error('Server exited before start')));});
(async()=>{
 let browser;
 try {
  const url = await address;
  browser=await chromium.launch({headless:true});
  const context=await browser.newContext({viewport:{width:1440,height:1100},acceptDownloads:true});
  const page=await context.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const complete=()=>page.waitForFunction(()=>document.getElementById('notice').textContent.startsWith('Processing complete.')&&!document.getElementById('export').disabled);
  await page.goto(url);
  await page.getByRole('button',{name:'Load real earthquake demo'}).click();await complete();
  assert.match(await page.locator('#counts').innerText(),/111/);
  await page.locator('.record button').first().click();
  assert.match(await page.locator('#detail').innerText(),/"coordinates"/);
  await page.getByRole('button',{name:'Add filter',exact:true}).click();await complete();
  assert.match(await page.locator('#notice').innerText(),/13 included \+ 98 excluded \+ 0 errors = 111/);
  await page.selectOption('#view','included');await complete();
  assert.equal(await page.locator('.record').count(),13);
  await page.locator('.record button').first().click();
  // Save a visible real-data demo; kept outside project control records.
  fs.mkdirSync(path.join(root,'docs'),{recursive:true});
  await page.screenshot({path:path.join(root,'docs/demo.png'),fullPage:true});
  // Manually exclude one matching record, then recover the same selection.
  await page.locator('.record input').first().click();await complete();
  assert.match(await page.locator('#notice').innerText(),/12 included/);
  const savedEvent=page.waitForEvent('download');await page.click('#save');
  const saved=await savedEvent;await saved.saveAs(path.join(tmp,'project.json'));
  const project=JSON.parse(fs.readFileSync(path.join(tmp,'project.json')));
  assert.equal(project.excluded_lines.length,1);
  await page.reload();await page.waitForFunction(()=>document.getElementById('notice').textContent.includes('Saved selection found'));
  assert.equal(await page.locator('#export').isDisabled(),true);
  await page.setInputFiles('#source',path.join(root,'data/earthquakes.jsonl'));await complete();
  assert.match(await page.locator('#notice').innerText(),/12 included/);
  await page.click('#clear');await complete();assert.match(await page.locator('#notice').innerText(),/111 included/);
  await page.setInputFiles('#projectImport',path.join(tmp,'project.json'));await complete();
  assert.match(await page.locator('#notice').innerText(),/12 included/);
  const exportedEvent=page.waitForEvent('download');await page.click('#export');
  await (await exportedEvent).saveAs(path.join(tmp,'selection.zip'));
  let result=spawnSync('python3',['-m','zipfile','-e',path.join(tmp,'selection.zip'),tmp],{encoding:'utf8'});assert.equal(result.status,0,result.stderr);
  result=spawnSync('python3',['tools/verify_export.py','data/earthquakes.jsonl',path.join(tmp,'subset.jsonl'),path.join(tmp,'manifest.json')],{cwd:root,encoding:'utf8'});assert.equal(result.status,0,result.stderr);process.stdout.write(result.stdout);
  const source=fs.readFileSync(path.join(root,'data/earthquakes.jsonl'));
  const manifest=JSON.parse(fs.readFileSync(path.join(tmp,'manifest.json')));
  assert.equal(crypto.createHash('sha256').update(source).digest('hex'),manifest.source_sha256);
  // A second implementation in JavaScript verifies real-data selection directly.
  const lines=source.toString('utf8').trimEnd().split('\n');
  const expected=lines.flatMap((line,i)=>JSON.parse(line).properties.mag>=5&&!project.excluded_lines.includes(i+1)?[i+1]:[]);
  assert.deepEqual(manifest.source_lines,expected);
  assert.deepEqual(fs.readFileSync(path.join(tmp,'subset.jsonl')),Buffer.from(expected.map(n=>lines[n-1]+'\n').join('')));
  // Reopening subset starts a distinct source with no stale decisions.
  await page.setInputFiles('#source',path.join(tmp,'subset.jsonl'));await complete();
  assert.match(await page.locator('#notice').innerText(),/12 included \+ 0 excluded \+ 0 errors = 12/);
  // Wrong source must not restore a project.
  await page.setInputFiles('#projectImport',path.join(tmp,'project.json'));
  await page.waitForFunction(()=>document.getElementById('notice').textContent.includes('Source hash mismatch'));
  assert.equal(await page.locator('.filter').count(),0);
  // Fresh browser storage: import project first, then matching data.
  const fresh=await browser.newContext();const other=await fresh.newPage();await other.goto(url);
  await other.setInputFiles('#projectImport',path.join(tmp,'project.json'));
  await other.waitForFunction(()=>document.getElementById('notice').textContent.includes('Reattach the matching source'));
  await other.setInputFiles('#source',path.join(root,'data/earthquakes.jsonl'));
  await other.waitForFunction(()=>document.getElementById('notice').textContent.includes('12 included'));
  await fresh.close();
  // Error accounting and exact large integers through the actual browser.
  const control=Buffer.from('{"n":9007199254740993,"nested":[null,"雪"]}\r\n{"n":9007199254740992}\n{"n":1,"n":2}\n\n{bad}\n');
  await page.setInputFiles('#source',{name:'labeled-controls.jsonl',mimeType:'application/octet-stream',buffer:control});await complete();
  assert.match(await page.locator('#notice').innerText(),/2 included \+ 0 excluded \+ 3 errors = 5/);
  await page.locator('.record button').first().click();assert.match(await page.locator('#detail').innerText(),/9007199254740993/);
  await page.fill('#path','/n');await page.selectOption('#op','eq');await page.fill('#value','9007199254740993');await page.click('#add');await complete();
  assert.match(await page.locator('#notice').innerText(),/1 included \+ 1 excluded \+ 3 errors = 5/);
  await page.selectOption('#view','errors');await complete();assert.equal(await page.locator('.record').count(),3);
  // Failed oversized attachment cannot leave a previously exportable source enabled.
  await page.setInputFiles('#source',{name:'too-large.jsonl',mimeType:'application/octet-stream',buffer:Buffer.alloc(8388609,32)});
  await page.waitForFunction(()=>document.getElementById('notice').textContent.includes('processing incomplete'));
  assert.equal(await page.locator('#export').isDisabled(),true);
  assert.deepEqual(errors,[]);
  console.log('Browser PASS: import, nested inspection, typed filtering, exclusion, reload recovery, project roundtrip, hash rejection, export, independent byte audit, subset reopening, errors, precision, incomplete state');
 } finally {if(browser)await browser.close();server.kill();fs.rmSync(tmp,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});

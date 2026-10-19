'use strict';
// Real browser end-to-end check. No browser mocks or intercepted API responses.
const {chromium} = require('playwright');
const {spawn, execFileSync} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname,'..');
const artifacts = process.env.CSV_PIVOT_ARTIFACT_DIR || fs.mkdtempSync(path.join(os.tmpdir(),'csv-pivot-browser-'));
fs.mkdirSync(artifacts,{recursive:true});
const server = spawn('python3',['server.py','--port','0'],{cwd:root,stdio:['ignore','pipe','inherit']});
let browser;
const failures=[];
const pause = ms => new Promise(resolve=>setTimeout(resolve,ms));
async function ready(page) {await page.waitForFunction(()=>!document.getElementById('workspace').hidden && !document.getElementById('demo').disabled);}
async function apply(page) {await page.getByRole('button',{name:'Apply configuration',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('#config-form button').disabled);}
async function fileDownload(page,button,target) {const promise=page.waitForEvent('download');await page.getByRole('button',{name:button,exact:true}).click();const download=await promise;await download.saveAs(target);}
(async()=>{
  const url=await new Promise((resolve,reject)=>{let output='';server.stdout.on('data',chunk=>{output+=chunk;const match=output.match(/http:\/\/127\.0\.0\.1:\d+/);if(match)resolve(match[0]);});server.on('exit',code=>reject(new Error('Server exited '+code)));setTimeout(()=>reject(new Error('Server startup timeout')),10000).unref();});
  browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH}:{})});
  const context=await browser.newContext({acceptDownloads:true,viewport:{width:1440,height:1080}});
  const page=await context.newPage();page.on('pageerror',error=>failures.push(error.message));
  await page.goto(url);await page.getByRole('button',{name:'Try the penguins demo ↗',exact:true}).click();await ready(page);
  assert.match(await page.locator('#stats').innerText(),/344/);
  assert.equal(await page.locator('#summary tbody tr').count(),6);
  assert.match(await page.locator('#summary .total').innerText(),/4201\.754385964912/);
  await page.getByRole('button',{name:'Inspect grand total',exact:true}).click();
  assert.equal(await page.locator('#records tbody tr').count(),344);
  assert.equal(await page.locator('#records tbody tr').filter({hasText:'Missing numeric value'}).count(),2);
  await page.getByRole('button',{name:'Close',exact:true}).click();
  await page.screenshot({path:path.join(artifacts,'demo-desktop.png'),fullPage:true});
  // Export the untouched real demo and independently verify downloaded outputs.
  const demoZip=path.join(artifacts,'real-demo.zip');
  await fileDownload(page,'Export report bundle ↓',demoZip);
  const demoDir=path.join(artifacts,'real-demo');
  execFileSync('python3',['-m','zipfile','-e',demoZip,demoDir],{cwd:root});
  execFileSync('python3',['scripts/verify_report.py','data/penguins.csv',demoDir],{cwd:root,stdio:'inherit'});
  // Change grouping, value typing, aggregate and filter through browser controls.
  await page.locator('#row').selectOption('species');await page.locator('#column').selectOption('sex');
  await page.getByLabel('Type of bill_length_mm',{exact:true}).selectOption('number');
  await page.locator('#value').selectOption('bill_length_mm');await page.locator('#aggregate').selectOption('sum');
  await page.locator('#filter-column').selectOption('island');await page.locator('#filter-value').fill('Dream');
  assert.equal(await page.locator('#export').isDisabled(),true);await apply(page);
  assert.equal(await page.locator('#message').innerText(),'');
  assert.match(await page.locator('#summary .total').innerText(),/5476\.8/);
  assert.match(await page.locator('#stats').innerText(),/124/);
  await page.getByRole('button',{name:'Inspect filtered',exact:true}).click();
  assert.equal(await page.locator('#records tbody tr').count(),220);await page.getByRole('button',{name:'Close',exact:true}).click();
  // Invalid numeric config must not export stale results as the new result.
  await page.getByLabel('Type of bill_length_mm',{exact:true}).selectOption('text');await apply(page);
  assert.match(await page.locator('#message').innerText(),/explicitly numeric/);assert.equal(await page.locator('#export').isDisabled(),true);
  await page.getByLabel('Type of bill_length_mm',{exact:true}).selectOption('number');await apply(page);
  const saved=path.join(artifacts,'saved-project.json');await fileDownload(page,'Save project configuration ↓',saved);
  const before=JSON.parse(fs.readFileSync(saved,'utf8'));
  // Reload clears source bytes and requires a hash match before reconnection.
  await page.reload();assert.equal(await page.locator('#workspace').isHidden(),true);
  assert.match(await page.locator('#recovery').innerText(),/Saved configuration found/);
  await page.locator('#file').setInputFiles({name:'wrong.csv',mimeType:'text/csv',buffer:Buffer.from('a,b\nx,1\n')});
  await page.waitForFunction(()=>document.getElementById('message').textContent.includes('hash mismatch'));
  assert.equal(await page.locator('#workspace').isHidden(),true);
  await page.locator('#file').setInputFiles(path.join(root,'data/penguins.csv'));await ready(page);
  assert.equal(await page.locator('#column').inputValue(),'sex');assert.equal(await page.locator('#filter-value').inputValue(),'Dream');
  const filteredZip=path.join(artifacts,'filtered.zip');await fileDownload(page,'Export report bundle ↓',filteredZip);
  const filteredDir=path.join(artifacts,'filtered');execFileSync('python3',['-m','zipfile','-e',filteredZip,filteredDir],{cwd:root});
  execFileSync('python3',['scripts/verify_report.py','data/penguins.csv',filteredDir],{cwd:root,stdio:'inherit'});
  // Independent reopening: fresh context, no application storage or scripts in report.
  const fresh=await browser.newContext({acceptDownloads:true,javaScriptEnabled:false});
  const report=await fresh.newPage();await report.goto('file://'+path.join(filteredDir,'report.html'));
  assert.equal(await report.locator('script').count(),0);await report.locator('section details summary').first().click();
  assert.equal(await report.locator('section details').first().getAttribute('open'),'');
  assert.ok(await report.locator('section').first().locator('tbody tr').count()>0);
  await report.screenshot({path:path.join(artifacts,'portable-report.png'),fullPage:true});await fresh.close();
  const transfer=await browser.newContext({acceptDownloads:true});const restored=await transfer.newPage();
  restored.on('pageerror',error=>failures.push(error.message));await restored.goto(url);
  await restored.locator('#project').setInputFiles(saved);await restored.waitForFunction(()=>document.getElementById('recovery').textContent.includes('Project loaded'));
  await restored.locator('#file').setInputFiles(path.join(root,'data/penguins.csv'));await ready(restored);
  assert.equal(await restored.locator('#aggregate').inputValue(),before.config.aggregate);
  assert.equal(await restored.locator('#filter-value').inputValue(),'Dream');await transfer.close();
  // Local CSV controls: leading zeros, multiline field, invalid and rejected records.
  await page.getByRole('button',{name:'Clear workspace',exact:true}).click();
  const control=Buffer.from('id,value,note\n001,0,"hello\nworld"\n001,-2.5,雪\n002,,empty\n002,nope,invalid\nwrong,width\n');
  const controlSource=path.join(artifacts,'controls.csv');fs.writeFileSync(controlSource,control);
  await page.locator('#file').setInputFiles({name:'controls.csv',mimeType:'text/csv',buffer:control});await ready(page);
  await page.getByLabel('Type of value',{exact:true}).selectOption('number');await page.locator('#value').selectOption('value');await page.locator('#aggregate').selectOption('mean');await apply(page);
  assert.match(await page.locator('#summary tbody').innerText(),/"001"/);assert.match(await page.locator('#summary tbody').innerText(),/Undefined/);
  await page.getByRole('button',{name:'Inspect 001',exact:true}).click();assert.equal(await page.locator('#records tbody tr').count(),2);assert.match(await page.locator('#records tbody').innerText(),/hello\nworld/);await page.getByRole('button',{name:'Close',exact:true}).click();
  await page.getByRole('button',{name:'Inspect rejected',exact:true}).click();assert.match(await page.locator('#records tbody').innerText(),/field count/);await page.getByRole('button',{name:'Close',exact:true}).click();
  const controlsZip=path.join(artifacts,'controls.zip');await fileDownload(page,'Export report bundle ↓',controlsZip);
  const controlDir=path.join(artifacts,'controls');execFileSync('python3',['-m','zipfile','-e',controlsZip,controlDir],{cwd:root});execFileSync('python3',['scripts/verify_report.py',controlSource,controlDir],{cwd:root,stdio:'inherit'});
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(artifacts,'mobile.png'),fullPage:true});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
  assert.deepEqual(failures,[]);console.log('Browser workflow passed. Artifacts:',artifacts);
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.kill('SIGTERM');});

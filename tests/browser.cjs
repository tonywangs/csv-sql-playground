/* Run: NODE_PATH=/tmp/sqlite-desk-browser/node_modules PLAYWRIGHT_BROWSERS_PATH=/tmp/sqlite-desk-browsers node tests/browser.cjs */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const os=require('node:os');
const path=require('node:path');
const {spawn,spawnSync}=require('node:child_process');
(async()=>{
 const server=spawn('python3',['app.py','--port','0'],{cwd:path.resolve(__dirname,'..')});
 const url=await new Promise((resolve,reject)=>{server.stdout.on('data',data=>{const m=String(data).match(/http:\/\/127\.0\.0\.1:\d+/);if(m)resolve(m[0]);});server.on('error',reject);server.on('exit',c=>reject(Error('Server exited '+c)));});
 const folder=await fs.mkdtemp(path.join(os.tmpdir(),'desk-browser-'));
 let browser;
 try{
  browser=await chromium.launch({headless:true,args:['--no-sandbox']});
  const page=await browser.newPage({viewport:{width:1440,height:1100},acceptDownloads:true});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url);await page.getByRole('button',{name:'Open real-data demo'}).click();await page.getByRole('heading',{name:'Comparison ready'}).waitFor();
  await page.locator('#tables button').filter({hasText:'regions'}).click();
  await page.locator('#filter').selectOption('changed');
  assert.equal(await page.locator('#records button').count(),13);
  await page.locator('#search').fill('NC-01');assert.equal(await page.locator('#records button').count(),1);
  await page.locator('#records button').first().click();assert.match(await page.locator('#inspection').innerText(),/scan ordinal/);assert.match(await page.locator('#inspection').innerText(),/local_code/);
  await page.screenshot({path:process.env.DESK_SCREENSHOT||'demo/browser-demo.png',fullPage:true});
  const response=page.waitForResponse(r=>r.url().endsWith('/api/compare'));
  await page.locator('#identity input[value="id"]').uncheck();await page.locator('#identity input[value="code"]').check();await page.getByRole('button',{name:'Apply identity',exact:true}).click();
  const inspected=await (await response).json();await page.getByRole('heading',{name:'Comparison ready'}).waitFor();assert.deepEqual(inspected.tables.regions.identity,['code']);
  let downloadEvent=page.waitForEvent('download');await page.getByRole('button',{name:'Export JSON',exact:true}).click();let download=await downloadEvent;const jsonPath=path.join(folder,'report.json');await download.saveAs(jsonPath);
  const exported=JSON.parse(await fs.readFile(jsonPath,'utf8'));assert.deepEqual(exported,inspected);
  downloadEvent=page.waitForEvent('download');await page.getByRole('button',{name:'Export standalone HTML',exact:true}).click();download=await downloadEvent;const htmlPath=path.join(folder,'report.html');await download.saveAs(htmlPath);
  const offline=await browser.newContext({offline:true});const op=await offline.newPage();op.on('pageerror',e=>errors.push(e.message));const network=[];op.on('request',r=>{if(/^https?:/.test(r.url()))network.push(r.url());});
  await op.goto('file://'+htmlPath);await op.getByRole('heading',{name:'Comparison ready'}).waitFor();
  assert.deepEqual(JSON.parse(await op.locator('#embedded-report').textContent()),inspected);
  await op.locator('#tables button').filter({hasText:'regions'}).click();await op.locator('#filter').selectOption('changed');await op.locator('#search').fill('NC-01');await op.locator('#records button').first().click();assert.match(await op.locator('#inspection').innerText(),/local_code/);assert.equal(network.length,0);
  // Browser file upload starts with no assumed identity; then choose and validate id.
  await page.locator('#before-file').setInputFiles('demo/before.sqlite');await page.locator('#after-file').setInputFiles('demo/after.sqlite');await page.locator('#stable').check();
  await page.getByRole('button',{name:'Compare selected snapshots'}).click();await page.getByRole('heading',{name:'Comparison ready'}).waitFor();
  await page.locator('#tables button').filter({hasText:'regions'}).click();assert.match(await page.locator('#identity-description').innerText(),/none/);
  await page.locator('#identity input[value="id"]').check();await page.getByRole('button',{name:'Apply identity',exact:true}).click();await page.getByRole('heading',{name:'Comparison ready'}).waitFor();assert.match(await page.locator('#identity-description').innerText(),/validated/);
  // Unusable input must replace successful output with an incomplete error.
  await page.locator('#before-file').setInputFiles({name:'encrypted.sqlite',mimeType:'application/octet-stream',buffer:Buffer.from('not a database')});await page.getByRole('button',{name:'Compare selected snapshots'}).click();await page.locator('#message.error').waitFor();assert.match(await page.locator('#message').innerText(),/incomplete/);assert.equal(await page.locator('#workspace').isVisible(),false);
  // Legal JS-special table names must not silently discard selected identity.
  const controlPaths=['before-control.sqlite','after-control.sqlite'].map(n=>path.join(folder,n));
  const setup=spawnSync('python3',['-c',`import sqlite3,sys
for i,p in enumerate(sys.argv[1:]):
 c=sqlite3.connect(p)
 c.execute('CREATE TABLE ""(id)')
 c.execute('INSERT INTO "" VALUES (1)')
 c.execute('CREATE TABLE "__proto__"(id, value, payload)')
 c.execute('INSERT INTO "__proto__" VALUES(?,?,?)',(9007199254740993,bytes([i,255]),'</script><script>window.injected=true</script>'))
 c.commit();c.close()`,...controlPaths]);assert.equal(setup.status,0,String(setup.stderr));
  for(const [i,side] of ['before','after'].entries())await page.locator('#'+side+'-file').setInputFiles(controlPaths[i]);
  await page.getByRole('button',{name:'Compare selected snapshots'}).click();await page.getByRole('heading',{name:'Comparison ready'}).waitFor();
  assert.equal(await page.locator('#table-title').innerText(),'(empty table name)');
  await page.locator('#tables button').filter({hasText:'__proto__'}).click();
  await page.locator('#identity input[value="id"]').check();
  const specialResponse=page.waitForResponse(r=>r.url().endsWith('/api/compare'));
  await page.getByRole('button',{name:'Apply identity',exact:true}).click();
  const special=await (await specialResponse).json();assert.deepEqual(special.tables.__proto__.identity,['id']);assert.equal(special.tables.__proto__.counts.changed,1);
  await page.getByRole('heading',{name:'Comparison ready'}).waitFor();await page.locator('#search').fill('');await page.locator('#filter').selectOption('changed');await page.locator('#records button').first().click();
  assert.match(await page.locator('#inspection').innerText(),/9007199254740993/);assert.match(await page.locator('#inspection').innerText(),/0x00ff/);
  downloadEvent=page.waitForEvent('download');await page.getByRole('button',{name:'Export standalone HTML',exact:true}).click();download=await downloadEvent;const controlHTML=path.join(folder,'control.html');await download.saveAs(controlHTML);
  await op.goto('file://'+controlHTML);await op.getByRole('heading',{name:'Comparison ready'}).waitFor();await op.locator('#tables button').filter({hasText:'__proto__'}).click();await op.locator('#filter').selectOption('changed');await op.locator('#search').fill('');await op.locator('#records button').first().click();
  assert.equal(await op.evaluate(()=>window.injected),undefined);assert.match(await op.locator('#inspection').innerText(),/<script>/);
  assert.deepEqual(JSON.parse(await op.locator('#embedded-report').textContent()),special);
  const emptyPath=path.join(folder,'empty.sqlite');assert.equal(spawnSync('python3',['-c','import sqlite3,sys;c=sqlite3.connect(sys.argv[1]);c.execute("VACUUM");c.close()',emptyPath]).status,0);
  for(const side of ['before','after'])await page.locator('#'+side+'-file').setInputFiles(emptyPath);
  await page.getByRole('button',{name:'Compare selected snapshots'}).click();await page.getByRole('heading',{name:'Comparison ready'}).waitFor();await page.waitForFunction(()=>document.querySelectorAll('#tables button').length===0);assert.equal(await page.locator('.table-panel').isVisible(),false);assert.equal(await page.locator('#tables button').count(),0);
  assert.deepEqual(errors,[]);
  console.log('PASS browser: demo, tables, identities, search, inspection, exact JSON/HTML export, offline use, uploads, failed-input state, __proto__ table, BLOB/integer precision, HTML escaping, empty databases');
 }finally{if(browser)await browser.close();server.kill();await fs.rm(folder,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});

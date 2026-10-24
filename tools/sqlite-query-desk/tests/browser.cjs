/* Actual Chromium workflow; real geographic queries plus labeled edge controls. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const {spawn}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const crypto=require('node:crypto');
const root=path.resolve(__dirname,'..');
const output=path.join(root,'results');
const records=[];
const digest=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
let browser,server;
const errors=[];
async function main(){
 server=spawn('python3',['-m','desk.server','--port','0'],{cwd:root,stdio:['ignore','pipe','pipe']});
 const url=await new Promise((resolve,reject)=>{let text='';const timer=setTimeout(()=>reject(Error('Server startup timeout')),10000);server.stdout.on('data',d=>{text+=d;const match=text.match(/http:\/\/127\.0\.0\.1:\d+/);if(match){clearTimeout(timer);resolve(match[0]);}});server.on('exit',code=>reject(Error('Server exited '+code)));server.stderr.on('data',d=>process.stderr.write(d));});
 browser=await chromium.launch({headless:true});
 const context=await browser.newContext({viewport:{width:1440,height:1100},acceptDownloads:true});
 const page=await context.newPage();
 page.on('pageerror',e=>errors.push(e.message));
 const external=[];page.on('request',r=>{if(!r.url().startsWith(url))external.push(r.url());});
 const db=path.join(root,'demo/ourairports.sqlite');
 const before=digest(db);
 const record=(name,detail)=>{records.push({name,passed:true,...detail});console.log('PASS '+name);};
 const waitMessage=text=>page.waitForFunction(t=>document.querySelector('#message').textContent.includes(t),text,{timeout:15000});
 const run=async(status='COMPLETE')=>{await page.click('#run');await page.waitForFunction(()=>document.querySelector('#run').disabled);await page.waitForFunction(()=>!document.querySelector('#run').disabled,{},{timeout:15000});await waitMessage(status);};
 const download=async(button,target)=>{const event=page.waitForEvent('download');await page.click(button);const d=await event;await d.saveAs(path.join(output,target));};
 await page.goto(url);await page.click('#demo');await waitMessage('Snapshot connected');
 assert.equal(await page.locator('#schema summary').count(),2);
 await page.locator('#schema summary').filter({hasText:'countries'}).click();
 assert.match(await page.locator('#schema').innerText(),/continent/);
 record('real demo import and schema inspection');
 await page.click('button:has-text("Browse countries")');await run();
 assert.equal(await page.locator('tbody tr').count(),249);
 record('table browsing',{rows:249});
 // Re-select the untouched region join, edit its typed parameter, then restore CA.
 await page.selectOption('#saved','1');
 await page.fill('#parameters',JSON.stringify({country:{type:'text',value:'JP'}}));
 await run();assert.ok((await page.locator('tbody tr').count())>0);
 assert.match(await page.locator('tbody').innerText(),/Japan/);
 await page.fill('#parameters',JSON.stringify({country:{type:'text',value:'CA'}},null,2));
 await run();assert.equal(await page.locator('tbody tr').count(),14);
 await download('#export','browser-real-data.zip');
 await page.screenshot({path:path.join(output,'browser-workflow.png'),fullPage:true});
 record('SQL editing, typed filter and real join export',{rows:14,archive:'browser-real-data.zip'});
 await page.selectOption('#saved','2');await run();assert.equal(await page.locator('tbody tr').count(),7);
 record('real grouped aggregate',{rows:7});
 await page.selectOption('#saved','1');
 await download('#projectExport','browser-project.json');
 await page.reload();await waitMessage('Recovered saved queries');
 assert.equal(await page.inputValue('#saved'),'1');
 assert.equal(JSON.parse(await page.inputValue('#parameters')).country.value,'CA');
 assert.equal(await page.isDisabled('#run'),true);
 await page.click('#demo');await waitMessage('Snapshot connected');await run();
 record('reload recovers selected query, typed parameters and explicit reconnection');
 await page.evaluate(()=>localStorage.clear());await page.reload();
 await page.setInputFiles('#projectImport',path.join(output,'browser-project.json'));await waitMessage('Project recovered');
 assert.equal(await page.inputValue('#saved'),'1');assert.equal(await page.isDisabled('#run'),true);
 // Import actual bytes with the standalone confirmation, not only the demo route.
 await page.check('#stable');await page.setInputFiles('#database',db);await waitMessage('Snapshot connected');await run();
 assert.equal(await page.locator('tbody tr').count(),14);
 record('project transfer, file import and rerun');
 await page.fill('#rows','2');await run('TRUNCATED');
 assert.equal(await page.locator('tbody tr').count(),2);
 await page.click('#export');await waitMessage('Explicit partial-result acknowledgment required');
 await page.check('#partial');await download('#export','browser-partial.zip');
 record('row truncation and partial export acknowledgment',{rows:2});
 await page.fill('#rows','1000');await page.fill('#bytes','30');await run('TRUNCATED');
 record('byte truncation');
 await page.fill('#bytes','1048576');await page.fill('#sql','SELECT 1 AS empty WHERE 0');await page.fill('#parameters','{}');await run();
 await waitMessage('empty result');record('successful empty result');
 await page.fill('#sql',"SELECT 9223372036854775807 AS x, NULL AS x, X'00FF' AS payload");await run();
 assert.match(await page.locator('tbody').innerText(),/9223372036854775807/);
 assert.equal(await page.locator('thead th').allTextContents().then(a=>a.join(',')),'x,x,payload');
 assert.match(await page.locator('tbody').innerText(),/NULL/);assert.match(await page.locator('tbody').innerText(),/AP8=/);
 record('labeled controls: integer precision, NULL, duplicate columns and BLOB');
 for(const sql of ['SELCT 1','DELETE FROM countries',"ATTACH DATABASE ':memory:' AS outside",'PRAGMA query_only=OFF']){
  await page.fill('#sql',sql);await run('ERROR');assert.equal(await page.isDisabled('#export'),true);
 }
 record('labeled controls: malformed SQL, writes, attachment and pragma rejected');
 await page.fill('#sql','WITH RECURSIVE n(x) AS (VALUES(0) UNION ALL SELECT x+1 FROM n) SELECT sum(x) FROM n');
 await page.fill('#seconds','10');await page.click('#run');await waitMessage('RUNNING');for(const id of ['sql','parameters','rows','bytes','seconds','name'])assert.equal(await page.isDisabled('#'+id),true);await page.waitForTimeout(150);await page.click('#cancel');await waitMessage('INTERRUPTED');await waitMessage('cancelled');
 record('user cancellation and locked in-flight editor',{status:'interrupted'});
 await page.fill('#seconds','1');await run('INTERRUPTED');await waitMessage('time limit');record('execution time limit',{status:'interrupted'});
 // Changed source bytes require an explicit connection and invalidate results.
 const changed=fs.readFileSync(db);changed[60]^=1; // user_version header byte; valid database, different identity
 await page.setInputFiles('#database',{name:'changed-snapshot.sqlite',mimeType:'application/octet-stream',buffer:changed});await waitMessage('Different source bytes connected');assert.equal(await page.isDisabled('#export'),true);
 record('changed source identity invalidates results');
 const wal=Buffer.from(fs.readFileSync(db));wal[18]=2;wal[19]=2;
 await page.setInputFiles('#database',{name:'wal-control.sqlite',mimeType:'application/octet-stream',buffer:wal});await waitMessage('WAL or unsupported journal format');
 record('labeled WAL snapshot refused');
 // A backup larger than the import limit must not be offered as recoverable.
 await page.evaluate(()=>{const p=JSON.parse(localStorage.getItem('sqlite-query-desk.v1'));p.queries=Array.from({length:20},()=>({name:'Large control',sql:'SELECT 1 /*'+ 'x'.repeat(60000)+'*/',parameters:'{}',settings:{rows:1000,bytes:1048576,seconds:3}}));p.selected=0;localStorage.setItem('sqlite-query-desk.v1',JSON.stringify(p));});
 await page.reload();await waitMessage('Recovered saved queries');await page.click('#projectExport');await waitMessage('Project backup exceeds 1 MiB');
 record('oversized project export refused before producing an unrecoverable backup');
 assert.equal(digest(db),before);assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
 record('source bytes unchanged; no page errors or external requests',{sha256:before});
 // Reopen exported JSON independently of the original browser workspace.
 const backup=JSON.parse(fs.readFileSync(path.join(output,'browser-project.json')));
 assert.equal(backup.queries[1].parameters.includes('CA'),true);
 await context.close();
 fs.writeFileSync(path.join(output,'browser-evidence.json'),JSON.stringify({executed_at:new Date().toISOString(),browser:browser.version(),platform:process.platform,checks:records,source_before:before,source_after:digest(db),page_errors:errors,external_requests:external},null,2)+'\n');
}
main().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(server)server.kill('SIGTERM');});

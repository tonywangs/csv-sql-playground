#!/usr/bin/env node
// Optional test dependency: Playwright. The application itself is dependency-free.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');

(async () => {
 const browser = await chromium.launch({headless:true});
 const temp = fs.mkdtempSync(path.join(os.tmpdir(),'csv-browser-'));
 try {
  const context = await browser.newContext({offline:true,viewport:{width:1280,height:900}});
  const page = await context.newPage(), errors = [], external = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (!request.url().startsWith('file:')) external.push(request.url()); });
  await page.goto(pathToFileURL(path.join(root,'demo-output/comparison.html')).href);
  await page.locator('.event').first().waitFor();
  assert.match(await page.locator('#accounting').innerText(),/17,195 \/ 17,195 before · 17,394 \/ 17,394 after/);
  assert.equal(await page.locator('.event').count(),40);
  assert.match(await page.locator('#page-info').innerText(),/1–40 of 1,736/);
  await page.locator('#next').click();
  assert.match(await page.locator('#page-info').innerText(),/41–80/);
  await page.locator('#previous').click();
  assert.equal(await page.locator('#previous').isDisabled(),true);
  await page.locator('#status').selectOption('changed');
  assert.match(await page.locator('#page-info').innerText(),/of 1,407/);
  await page.locator('.event summary').first().click();
  await page.locator('.event-body').first().waitFor();
  assert.ok(await page.locator('td.different').count() >= 2);
  assert.match(await page.locator('.event-body').first().innerText(),/before\nrow \d+\nlines \d+–\d+/);
  await page.locator('#search').fill('Africa Western and Central');
  assert.ok(await page.locator('.event').count() > 0);
  await page.locator('#search').fill('this value does not exist 123xyz');
  assert.equal(await page.locator('.event').count(),0);
  assert.equal(await page.locator('#page-info').innerText(),'No matching groups');
  await page.locator('#search').fill('');
  await page.locator('#status').selectOption('removed');
  assert.match(await page.locator('#page-info').innerText(),/of 65/);
  await page.locator('#status').selectOption('added');
  assert.match(await page.locator('#page-info').innerText(),/of 264/);
  await page.locator('#status').selectOption('unchanged');
  assert.match(await page.locator('#page-info').innerText(),/of 15,723/);
  await page.locator('#status').selectOption('unresolved');
  assert.equal(await page.locator('.event').count(),0);
  await page.locator('#status').selectOption('changed');
  await page.locator('.event summary').first().click();
  await page.locator('.event-body').first().waitFor();
  if (process.argv[2]) {
   await page.setViewportSize({width:1280,height:1200});
   await page.screenshot({path:process.argv[2],fullPage:false});
  }
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),true);

  fs.writeFileSync(path.join(temp,'before.csv'),'id,v\na,x\na,y\n,missing\nb,"hello\nworld"\nc,</script><script>window.injected=true</script>\n');
  fs.writeFileSync(path.join(temp,'after.csv'),'id,v\na,x\na,z\n,missing\nb,new\nc,<img src=https://example.invalid/x onerror=window.injected=true>\n');
  execFileSync(process.env.PYTHON || 'python3',['-m','csv_reconcile_desk',path.join(temp,'before.csv'),path.join(temp,'after.csv'),'--key','id','--json',path.join(temp,'report.json'),'--html',path.join(temp,'report.html')],{cwd:root});
  await page.goto(pathToFileURL(path.join(temp,'report.html')).href);
  assert.equal(await page.locator('#unresolved-notice').isVisible(),true);
  await page.locator('#status').selectOption('unresolved');
  assert.equal(await page.locator('.event').count(),3);
  await page.locator('.event summary').first().click();
  await page.locator('.event-body').first().waitFor();
  assert.match(await page.locator('.event-body').first().innerText(),/no row-to-row pairing inferred/);
  assert.equal(await page.locator('.event-body tbody tr').count(),2);
  await page.locator('#duplicate-summary').click();
  await page.locator('#duplicate-list li').waitFor();
  assert.match(await page.locator('#duplicate-list').innerText(),/2 before \/ 2 after/);
  await page.locator('#status').selectOption('changed');
  for (const summary of await page.locator('.event summary').all()) await summary.click();
  await page.locator('.event-body').first().waitFor();
  assert.match(await page.locator('#events').innerText(),/lines 5–6/);
  assert.match(await page.locator('#events').innerText(),/<script>window.injected=true<\/script>/);
  assert.equal(await page.locator('#events img').count(),0);
  assert.equal(await page.evaluate(() => window.injected),undefined);
  assert.deepEqual(errors,[]);
  assert.deepEqual(external,[]);
  await context.close();
  console.log('Browser checks passed: offline file://, counts, filters, search, pagination, source references, mobile layout, duplicate ambiguity, multiline fields and inert HTML payloads.');
 } finally {
  await browser.close();
  fs.rmSync(temp,{recursive:true,force:true});
 }
})().catch(error => { console.error(error); process.exitCode=1; });

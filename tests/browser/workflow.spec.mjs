import {test,expect} from '@playwright/test';import fs from 'node:fs/promises';import {execFileSync} from 'node:child_process';
test('real source: linked inspection, selection, reload recovery, portable state, verified export and reopening',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));const external=[];page.on('request',r=>{if(!r.url().startsWith('http://127.0.0.1:8876/'))external.push(r.url())});
 await page.goto('http://127.0.0.1:8876/web/');await page.getByText('Load real country demo').click();await expect(page.locator('#counts')).toContainText('177 total');
 await page.locator('.leaflet-interactive').nth(1).click({force:true});await expect(page.locator('#inspector')).toContainText('ordinal');await page.locator('#include').click();await expect(page.locator('#counts')).toContainText('1 included');await page.locator('#clear').click();
 await page.locator('#filter').fill('France');await page.locator('#rows tr').first().click();await expect(page.locator('#inspector')).toContainText('France');await page.locator('#rows input').first().check();await page.getByText('Exclude matches',{exact:true}).click();await expect(page.locator('#counts')).toContainText('0 included');await page.getByText('Include matches',{exact:true}).click();const counts=await page.locator('#counts').textContent();expect(counts).not.toContain('0 included');
 const save=page.waitForEvent('download');await page.locator('#save').click();const project=await save;await project.saveAs('test-results/project.json');
 await page.reload();await page.getByText('Load real country demo').click();await expect(page.locator('#filter')).toHaveValue('France');await expect(page.locator('#counts')).toHaveText(counts);
 await page.locator('#clear').click();await page.locator('#restore').setInputFiles('test-results/project.json');await expect(page.locator('#counts')).toHaveText(counts);
 const d=page.waitForEvent('download');await page.locator('#export').click();await(await d).saveAs('test-results/selection.geojson');const m=page.waitForEvent('download');await page.locator('#manifest').click();await(await m).saveAs('test-results/selection.manifest.json');
 execFileSync('python3',['scripts/verify.py','data/countries.geojson','test-results/selection.geojson','test-results/selection.manifest.json']);
 await page.locator('#source').setInputFiles('test-results/selection.geojson');await expect(page.locator('#message')).toContainText('different source bytes');await page.locator('#restore').setInputFiles('test-results/project.json');await expect(page.locator('#message')).toContainText('Source bytes changed');
 await page.getByText('Load real country demo').click();await page.locator('#filter').fill('Europe');await page.getByText('Include matches',{exact:true}).click();await page.screenshot({path:'results/workbench.png',fullPage:true});expect(errors).toEqual([]);expect(external).toEqual([]);
});
test('independent Mapshaper rendering opens in browser',async({page})=>{await page.goto('http://127.0.0.1:8876/results/europe.svg');await expect(page.locator('svg')).toBeVisible();expect(await page.locator('path').count()).toBeGreaterThan(0);});
test('malformed and unsupported entries remain accounted for; storage denial permits import',async({page})=>{
 await page.addInitScript(()=>Object.defineProperty(window,'localStorage',{get(){throw Error('Denied')}}));await page.goto('http://127.0.0.1:8876/web/');
 const features=[null,{type:'Feature',geometry:null},{type:'Feature',properties:{name:'null geometry'},geometry:null},{type:'Feature',properties:{name:'unsupported'},geometry:{type:'GeometryCollection',geometries:[]}}];
 await page.locator('#source').setInputFiles({name:'controls.geojson',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({type:'FeatureCollection',features}))});
 await expect(page.locator('#counts')).toContainText('4 total');await expect(page.locator('#counts')).toContainText('3 unsupported');await expect(page.locator('#rows tr')).toHaveCount(4);await page.getByText('Include matches',{exact:true}).click();await expect(page.locator('#counts')).toContainText('1 included');
});

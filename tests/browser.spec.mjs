import {test,expect} from '@playwright/test';
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
const plan=JSON.parse(await fs.readFile('fixtures/reference-plan.json','utf8'));
const picks=JSON.parse(await fs.readFile('fixtures/selections.json','utf8')).charts;
const checksum=b=>createHash('sha256').update(b).digest('hex');
async function ready(page){await page.goto('/');await expect(page.locator('#status')).not.toContainText('Recovery failed');await page.waitForFunction(()=>document.querySelector('#persistence').textContent||document.querySelector('#status').textContent.startsWith('Ready'));}
async function calibrate(page,cal){for(const a of ['x','y']){await page.locator(`#${a}-scale`).selectOption(cal[a].scale);for(let i=0;i<2;i++){await page.locator(`#${a}${i}-pixel`).fill(String(cal[a].anchors[i].pixel));await page.locator(`#${a}${i}-value`).fill(String(cal[a].anchors[i].value));}}await page.locator('#axis-aligned').check();await page.getByRole('button',{name:'Apply calibration',exact:true}).click();await expect(page.locator('#status')).toContainText('Calibration applied');}
async function download(page,label,path){const wait=page.waitForEvent('download');await page.getByRole('link',{name:label,exact:true}).click();const d=await wait;await d.saveAs(path);return fs.readFile(path);}
for(const chart of plan.charts)test(`${chart.id}: complete real-input workflow`,async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort());
 page.on('dialog',d=>d.accept());await ready(page);
 await page.locator('#image-file').setInputFiles(`fixtures/owid/${chart.id}.png`);await expect(page.locator('#status')).toContainText('Image connected');
 await calibrate(page,chart.calibration);
 // Exercise interactive tick picking; it must use image coordinates at zoom.
 await page.locator('#zoom').selectOption('0.5');await page.locator('#pick-x0').click();
 await page.locator('#chart').click({position:{x:chart.calibration.x.anchors[0].pixel/2,y:100}});
 await expect(page.locator('#x0-pixel')).toHaveValue(chart.calibration.x.anchors[0].pixel.toFixed(3));
 await page.locator('#zoom').selectOption('1');
 await page.locator('#series-name').fill('World');await page.locator('#rename-series').click();
 for(const [x,y] of picks[chart.id])await page.locator('#chart').click({position:{x,y}});
 await expect(page.locator('#point-count')).toHaveText('5');
 await page.getByRole('button',{name:'Select point 1',exact:true}).click();
 const original=picks[chart.id][0];await page.locator('#point-x').fill(String(original[0]+4));await page.getByRole('button',{name:'Move point',exact:true}).click();await expect(page.locator('#point-x')).toHaveValue(String(original[0]+4));
 await page.locator('#undo').click();await page.getByRole('button',{name:'Select point 1',exact:true}).click();await expect(page.locator('#point-x')).toHaveValue(String(original[0]));
 await page.locator('#delete-point').click();await expect(page.locator('#point-count')).toHaveText('4');await page.locator('#undo').click();await expect(page.locator('#point-count')).toHaveText('5');
 // Named series creation is undoable and leaves all original selections intact.
 await page.locator('#series-name').fill('Second series');await page.locator('#add-series').click();await expect(page.locator('#series option')).toHaveCount(2);await page.locator('#undo').click();
 await expect(page.locator('#persistence')).toHaveText('Saved in this browser.');await page.reload();await expect(page.locator('#status')).toContainText('Recovered saved');await expect(page.locator('#point-count')).toHaveText('5');await expect(page.locator('#x0-pixel')).toHaveValue(String(chart.calibration.x.anchors[0].pixel));
 await page.locator('#export').click();
 await fs.mkdir('test-results/exports',{recursive:true});
 const csv=await download(page,'Download CSV',`test-results/exports/${chart.id}.csv`);
 const manifest=JSON.parse(await download(page,'Download manifest',`test-results/exports/${chart.id}.manifest.json`));
 const project=await download(page,'Download project',`test-results/exports/${chart.id}.project.json`);
 expect(checksum(csv)).toBe(manifest.outputs['points.csv'].sha256);expect(checksum(project)).toBe(manifest.outputs['project.json'].sha256);expect(manifest.image.sha256).toBe(chart.image_sha256);
 await page.locator('#project-file').setInputFiles(`test-results/exports/${chart.id}.project.json`);await expect(page.locator('#status')).toContainText('Project opened');await expect(page.locator('#chart')).toBeHidden();await expect(page.locator('#export')).toBeDisabled();
 const other=chart.id==='population'?'life-expectancy':'population';await page.locator('#image-file').setInputFiles(`fixtures/owid/${other}.png`);await expect(page.locator('#status')).toContainText('Image hash mismatch');await expect(page.locator('#chart')).toBeHidden();
 await page.locator('#image-file').setInputFiles(`fixtures/owid/${chart.id}.png`);await expect(page.locator('#status')).toContainText('Calibration and selections restored');await expect(page.locator('#point-count')).toHaveText('5');
 await page.getByRole('button',{name:'Select point 1',exact:true}).click();await expect(page.locator('#selection')).toContainText(String(original[0]));
 await page.screenshot({path:`test-results/${chart.id}-workbench.png`,fullPage:true});
 expect(errors).toEqual([]);
});
test('invalid calibration, drag at zoom, keyboard undo, and numeric limits',async({page})=>{
 page.on('dialog',d=>d.accept());await ready(page);await page.locator('#image-file').setInputFiles('fixtures/owid/population.png');await expect(page.locator('#status')).toContainText('Image connected');
 await calibrate(page,plan.charts[0].calibration);await page.locator('#x-scale').selectOption('log10');await page.locator('#x0-value').fill('0');await page.getByRole('button',{name:'Apply calibration',exact:true}).click();await expect(page.locator('#status')).toContainText('must be positive');
 await calibrate(page,plan.charts[0].calibration);await page.locator('#zoom').selectOption('0.5');await page.locator('#chart').click({position:{x:100,y:150}});await page.locator('#mode').selectOption('edit');
 const rect=await page.locator('#chart').boundingBox();await page.mouse.move(rect.x+100,rect.y+150);await page.mouse.down();await page.mouse.move(rect.x+110,rect.y+155);await page.mouse.up();await expect(page.locator('#point-x')).toHaveValue('220');await expect(page.locator('#point-y')).toHaveValue('310');
 await page.locator('#chart').press('ArrowRight');await expect(page.locator('#point-x')).toHaveValue('221');await page.locator('#undo').click();await page.getByRole('button',{name:'Select point 1',exact:true}).click();await expect(page.locator('#point-x')).toHaveValue('220');
 await page.locator('#point-x').fill('900');await page.getByRole('button',{name:'Move point',exact:true}).click();await expect(page.locator('#status')).toContainText('inside the source image');
 await page.locator('#point-x').fill('220');await page.locator('#export').click();await expect(page.getByRole('link',{name:'Download CSV',exact:true})).toBeVisible();await page.locator('#delete-point').click();await expect(page.getByRole('link',{name:'Download CSV',exact:true})).toHaveCount(0);
});
test('offline demos, rejected project input, and disconnected recovery',async({page})=>{
 const external=[];page.on('dialog',d=>d.accept());
 await page.route('**/*',route=>{if(new URL(route.request().url()).hostname!=='127.0.0.1'){external.push(route.request().url());return route.abort();}return route.continue();});
 await ready(page);await page.locator('#demo-population').click();await expect(page.locator('#status')).toContainText('Real published chart loaded');await expect(page.locator('#point-count')).toHaveText('5');
 await page.locator('#demo-life-expectancy').click();await expect(page.locator('#chart-title')).toHaveText('life-expectancy.png');await expect(page.locator('#point-count')).toHaveText('5');
 await page.locator('#project-file').setInputFiles({name:'bad.json',mimeType:'application/json',buffer:Buffer.from('{"format":"unknown"}')});await expect(page.locator('#status')).toContainText('Unsupported project format');await expect(page.locator('#chart-title')).toHaveText('life-expectancy.png');await expect(page.locator('#chart')).toBeVisible();
 await page.locator('#project-file').setInputFiles('samples/life-expectancy.project.json');await expect(page.locator('#status')).toContainText('Project opened');await expect(page.locator('#persistence')).toHaveText('Saved in this browser.');await page.reload();await expect(page.locator('#status')).toContainText('Recovered project');await expect(page.locator('#chart')).toBeHidden();
 await page.locator('#image-file').setInputFiles('fixtures/owid/life-expectancy.png');await expect(page.locator('#status')).toContainText('Calibration and selections restored');await expect(page.locator('#point-count')).toHaveText('5');expect(external).toEqual([]);
});

// Render publisher SVG as an image (external resources disabled), without cropping.
// Run with a separate empty output directory to compare; frozen originals stay unchanged.
import {chromium} from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
const output=process.argv[2];if(!output)throw Error('Usage: node scripts/rasterize.mjs OUTPUT_DIRECTORY');
await fs.mkdir(output,{recursive:true});
if((await fs.readdir(output)).length)throw Error('Output must be empty; frozen fixtures must not be overwritten.');
const browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:850,height:600},deviceScaleFactor:1});
await page.route('**/*',route=>route.abort());
const records=[];
for(const id of ['population','life-expectancy']){
 const source=await fs.readFile(`fixtures/owid/${id}.svg`);
 await page.setContent('<html><body style="margin:0;background:white"><img width="850" height="600" alt="Published chart"></body></html>');
 await page.locator('img').evaluate((img,base64)=>{img.src='data:image/svg+xml;base64,'+base64;return img.decode();},source.toString('base64'));
 const filename=path.join(output,`${id}.png`);await page.locator('img').screenshot({path:filename});
 const png=await fs.readFile(filename);records.push({file:`${id}.png`,sha256:createHash('sha256').update(png).digest('hex'),source:`${id}.svg`,sourceSha256:createHash('sha256').update(source).digest('hex'),width:850,height:600});
}
await fs.writeFile(path.join(output,'rasterization.json'),JSON.stringify({method:'Chromium SVG image rendering at intrinsic 850x600 CSS pixels, deviceScaleFactor=1, white background, no cropping. External fonts/resources disabled; system fallback fonts used. Original SVG bytes unchanged.',browser:browser.version(),files:records},null,2)+'\n');
await browser.close();console.log('Rasterized published charts into',output);

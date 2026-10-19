import fs from 'node:fs';import {resource,validate,htmlReport} from '../src/core.js';
const schema=await resource('vega-schema.json',fs.readFileSync('public/demo/vega-schema.json'));
const reports=[];
for(const n of ['bar-chart','pie-chart']){const doc=await resource(n+'.json',fs.readFileSync('public/demo/'+n+'.json'));reports.push(validate(doc,[schema]))}
let d=JSON.parse(fs.readFileSync('public/demo/bar-chart.json'));d.width='deliberately invalid';d.marks[0].type='not-a-vega-mark';fs.writeFileSync('public/demo/CONTROL-invalid-bar.json',JSON.stringify(d,null,2));const doc=await resource('CONTROL-invalid-bar.json',fs.readFileSync('public/demo/CONTROL-invalid-bar.json'));reports.push(validate(doc,[schema]));
fs.writeFileSync('results/sample-reports.json',JSON.stringify(reports,null,2)+'\n');fs.writeFileSync('public/demo/sample-report.html',htmlReport(reports[2]));

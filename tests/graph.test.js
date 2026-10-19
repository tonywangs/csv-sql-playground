import test from 'node:test';
import assert from 'node:assert/strict';
import {trace,report} from '../static/graph.js';
const cells=Object.fromEntries(['A','B','C','D'].map(id=>[id,{id,issues:[],kind:'formula',formula:'=B',coverage:'supported'}]));
const edges=[{source:'A',target:'B',formula:'=B',reference:'B'},{source:'B',target:'C',formula:'=C',reference:'C'},{source:'C',target:'A',formula:'=A',reference:'A'},{source:'D',target:'B',formula:'=B',reference:'B'}];
const model={cells,edges,limits:{trace_nodes:10000},source:{name:'test',bytes:0,sha256:'a'},coverage:{supported:4},warnings:[]};
test('transitive precedents and cycle',()=>{const t=trace(model,'A');assert.deepEqual(t.nodes,['A','B','C']);assert.deepEqual(t.cycles,[{from:'C',to:'A'}]);assert.equal(t.incomplete,false);});
test('direct and reverse navigation',()=>{assert.deepEqual(trace(model,'A','precedents',false).nodes,['A','B']);assert.deepEqual(new Set(trace(model,'B','dependents').nodes),new Set(['A','B','C','D']));});
test('limit and disconnected unknown boundary are incomplete',()=>{assert.equal(trace(model,'A','precedents',true,2).limited,true);const m=structuredClone(model);m.cells.D.issues=['INDIRECT'];assert.equal(trace(m,'A').incomplete,true);});
test('report escapes hostile workbook and note strings',()=>{const html=report({...model,source:{...model.source,name:'<script>alert(1)</script>'}},{selected:'A',notes:{A:'<img src=x onerror=alert(1)>'}});assert.ok(!html.includes('<script>'));assert.ok(!html.includes('<img'));assert.ok(html.includes('&lt;img'));assert.ok(html.includes('Supporting formula'));});

test('offline report preserves notes and anchors for selected blank cells',()=>{const html=report(model,{selected:'Z99',notes:{Z99:'Check this missing input'}});assert.ok(html.includes('id="Z99"'));assert.ok(html.includes('Annotation: Check this missing input'));});

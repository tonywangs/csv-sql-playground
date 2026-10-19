import {axisValue,axisTransform} from '../src/core.js';
const axis=(p,v,q,w,scale='linear')=>({scale,anchors:[{pixel:p,value:v},{pixel:q,value:w}]});
const cases=[
 {name:'linear',axis:axis(50,10,450,90),pixel:250,expected:50,valid:true},
 {name:'reversed linear',axis:axis(100,100,300,0),pixel:150,expected:75,valid:true},
 {name:'logarithmic',axis:axis(100,1,500,10000,'log10'),pixel:300,expected:100,valid:true},
 {name:'reversed logarithmic',axis:axis(500,1,100,10000,'log10'),pixel:400,expected:10,valid:true},
 {name:'equal pixels',axis:axis(50,1,50,2),valid:false},
 {name:'equal values',axis:axis(50,2,250,2),valid:false},
 {name:'nonpositive log',axis:axis(50,0,250,10,'log10'),valid:false},
 {name:'negative log',axis:axis(50,-1,250,10,'log10'),valid:false},
 {name:'outside image',axis:axis(-1,1,250,10),valid:false},
 {name:'unsupported scale',axis:axis(50,1,250,10,'symlog'),valid:false}
];
console.log(JSON.stringify(cases.map(c=>{try{axisTransform(c.axis,1000);return {...c,rejected:false,...(c.valid?{result:axisValue(c.axis,c.pixel)}:{})};}catch(e){return {...c,rejected:true,error:e.message};}})));

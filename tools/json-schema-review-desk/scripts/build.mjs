import {build} from 'esbuild';
await build({entryPoints:['src/app.js','src/worker.js'],bundle:true,outdir:'public',format:'esm',minify:true});

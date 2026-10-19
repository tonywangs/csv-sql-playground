import {validate} from './core.js';
self.onmessage=e=>self.postMessage(validate(e.data.document,e.data.resources));

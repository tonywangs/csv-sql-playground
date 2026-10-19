import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./tests',testMatch:'browser.spec.mjs',workers:1,timeout:60000,use:{baseURL:'http://127.0.0.1:8000',viewport:{width:1600,height:1200},headless:true},webServer:{command:'python3 scripts/serve.py',url:'http://127.0.0.1:8000',reuseExistingServer:false},reporter:'list'});

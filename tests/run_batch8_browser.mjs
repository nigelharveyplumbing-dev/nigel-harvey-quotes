// Actual mixed catalogue: published shower/project, private radiator draft.
import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';
import { createRequire } from 'node:module';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { spawn } from 'node:child_process';
import net from 'node:net';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
const require=createRequire(import.meta.url);
let playwright;
try {playwright=require('playwright')}catch{playwright=require(join(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES,'playwright'))}
const {chromium}=playwright;
const executablePath=process.env.STAGE6_CHROMIUM_EXECUTABLE||chromium.executablePath();
assert(existsSync(executablePath),'Preinstalled Chromium required');
const directory=dirname(fileURLToPath(import.meta.url));
const socket=net.createServer();await new Promise(r=>socket.listen(0,'127.0.0.1',r));
const port=socket.address().port;await new Promise(r=>socket.close(r));
const origin=`http://127.0.0.1:${port}`;
const credentials={username:randomBytes(16).toString('hex'),password:randomBytes(24).toString('hex')};
const server=spawn(process.env.STAGE6_TEST_PYTHON||'python',['-B',join(directory,'batch8_browser_server.py')],{cwd:dirname(directory),env:{...process.env,STAGE6_TEST_USERNAME:credentials.username,STAGE6_TEST_PASSWORD:credentials.password,STAGE6_TEST_PORT:String(port)},stdio:['ignore','pipe','pipe']});
let errors='';server.stderr.on('data',data=>errors+=data);
const draft='/advice/radiators-cold-heating-unevenly';
const pages=[['home','/'],['guildford','/plumber-guildford'],['woking','/plumber-woking'],['farnham-leak','/leak-repair-farnham'],['radiator-draft',draft]];
const evidence=process.env.BATCH8_EVIDENCE_DIR?resolve(process.env.BATCH8_EVIDENCE_DIR):process.env.ADVICE_EVIDENCE_DIR?resolve(process.env.ADVICE_EVIDENCE_DIR,'batch8'):null;
if(evidence)mkdirSync(evidence,{recursive:true});
const diagnostics={pageErrors:[],externalRequests:[],layouts:[],draftAnonymous:404,changedPageCount:4};
let browser;
try{
 for(let i=0;i<100;i++){
  if(server.exitCode!==null)throw Error(errors.slice(-2000));
  try{if((await fetch(origin)).status===200)break}catch{}
  if(i===99)throw Error('Server did not start');await new Promise(r=>setTimeout(r,100));
 }
 browser=await chromium.launch({executablePath,headless:true,args:['--no-sandbox']});
 const anonymous=await browser.newContext();
 assert.equal((await anonymous.request.get(origin+draft)).status(),404);
 assert.equal((await anonymous.request.get(origin+'/app')).status(),401);
 assert(!(await(await anonymous.request.get(origin+'/advice')).text()).includes(draft));
 const sitemap=await(await anonymous.request.get(origin+'/sitemap.xml')).text();
 assert.equal((sitemap.match(/<loc>/g)||[]).length,76);assert(!sitemap.includes(draft));
 const auth=Buffer.from(`${credentials.username}:${credentials.password}`).toString('base64');
 const context=await browser.newContext({httpCredentials:credentials,extraHTTPHeaders:{Authorization:`Basic ${auth}`}});
 await context.addInitScript(()=>localStorage.setItem('nhp_analytics_choice_v1','rejected'));
 await context.route('**/*',route=>{if(new URL(route.request().url()).origin===origin)return route.continue();diagnostics.externalRequests.push(route.request().url());return route.abort()});
 const page=await context.newPage();page.on('pageerror',e=>diagnostics.pageErrors.push(e.message));
 for(const [device,width,height] of [['desktop',1440,1000],['mobile',390,844]]){
  await page.setViewportSize({width,height});
  for(const [name,path] of pages){
   const response=await page.goto(origin+path);assert.equal(response.status(),200);await page.waitForLoadState('networkidle');
   assert.equal(await page.locator('main h1').count(),1);
   assert.equal(await page.locator('link[rel=canonical]').getAttribute('href'),'https://www.nigelharveyplumbing.co.uk'+path);
   const layout=await page.evaluate(()=>({width:innerWidth,document:document.documentElement.scrollWidth}));
   assert(layout.document<=width,`${name} ${device} overflow`);diagnostics.layouts.push({name,device,...layout});
   if(path===draft){assert.match(response.headers()['x-robots-tag'],/noindex/);assert.equal(response.headers()['cache-control'],'private, no-store');assert.equal(await page.locator('#public-analytics').getAttribute('data-send-to-google'),'false')}
   else assert(!response.headers()['x-robots-tag']);
   for(const s of await page.locator('script[type="application/ld+json"]').all())JSON.parse(await s.textContent());
   const hrefs=await page.locator('main a[href^="/"]').evaluateAll(links=>links.map(l=>l.getAttribute('href').split('#')[0]));
   for(const href of new Set(hrefs))assert.equal((await context.request.get(origin+href)).status(),200,href);
   const quote=page.locator('main a').filter({hasText:'enquiry form'});
   if(path==='/plumber-guildford'){
    const href=await quote.getAttribute('href');assert(href.includes('landing_page=%2Fplumber-guildford'));
   }
   await page.evaluate(()=>scrollTo(0,0));
   if(evidence){
    await page.screenshot({path:join(evidence,`${name}-${device}-top.png`)});
    await page.screenshot({path:join(evidence,`${name}-${device}.png`),fullPage:true});
    if(device==='desktop'){
     const pictures=await page.locator('img[src^="/"]').evaluateAll(images=>images.map(i=>i.getAttribute('src')));
     const embedded={};for(const src of new Set(pictures)){const r=await context.request.get(origin+src);if(r.ok())embedded[src]=`data:${r.headers()['content-type']};base64,${(await r.body()).toString('base64')}`}
     const html=await page.evaluate(embedded=>{const doc=document.documentElement.cloneNode(true);for(const s of doc.querySelectorAll('script:not([type="application/ld+json"])'))s.remove();doc.querySelector('#analytics-consent')?.remove();for(const img of doc.querySelectorAll('img')){if(embedded[img.getAttribute('src')])img.setAttribute('src',embedded[img.getAttribute('src')]);img.removeAttribute('srcset')}return '<!doctype html>\n'+doc.outerHTML},embedded);
     writeFileSync(join(evidence,`${name}-owner-preview.html`),html);
    }
   }
  }
 }
 assert.deepEqual(diagnostics.pageErrors,[]);assert.deepEqual(diagnostics.externalRequests,[]);
 if(evidence)writeFileSync(join(evidence,'batch8-browser-validation.json'),JSON.stringify(diagnostics,null,2)+'\n');
 console.log(JSON.stringify({result:'PASS',diagnostics},null,2));
}finally{if(browser)await browser.close();server.kill('SIGTERM')}

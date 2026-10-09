// Private advice browser checks and optional review evidence. Loopback only.
import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';
import { createRequire } from 'node:module';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import net from 'node:net';
import { spawn } from 'node:child_process';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
let playwright;
try { playwright = require('playwright'); }
catch { playwright = require(join(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES, 'playwright')); }
const { chromium } = playwright;
const executablePath = process.env.STAGE6_CHROMIUM_EXECUTABLE || chromium.executablePath();
assert(existsSync(executablePath), 'Preinstalled Chromium required');
const directory = dirname(fileURLToPath(import.meta.url));
const socket = net.createServer();
await new Promise(resolve => socket.listen(0, '127.0.0.1', resolve));
const port = socket.address().port;
await new Promise(resolve => socket.close(resolve));
const origin = `http://127.0.0.1:${port}`;
const credentials = { username: randomBytes(16).toString('hex'), password: randomBytes(24).toString('hex') };
const stage = process.env.ADVICE_TEST_STAGING === '1';
const published = process.env.ADVICE_TEST_PUBLISHED === '1';
const server = spawn(process.env.STAGE6_TEST_PYTHON || 'python', ['-B', join(directory, 'advice_browser_server.py')], {
 cwd: dirname(directory), env: { ...process.env, STAGE6_TEST_USERNAME: credentials.username,
 STAGE6_TEST_PASSWORD: credentials.password, STAGE6_TEST_PORT: String(port) }, stdio: ['ignore','pipe','pipe'] });
let errors=''; server.stderr.on('data',data=>errors+=data);
let browser;
const diagnostics={pageErrors:[],externalRequests:[],badResponses:[],layouts:[],mode:stage?'isolated-local-staging':'isolated-local-preview'};
try {
 for(let attempt=0;attempt<100;attempt++) {
  if(server.exitCode!==null) throw new Error(errors.slice(-2000));
  try { if((await fetch(origin)).status===(stage?401:200)) break; } catch {}
  if(attempt===99) throw new Error('Server did not start');
  await new Promise(resolve=>setTimeout(resolve,100));
 }
 browser=await chromium.launch({executablePath,headless:true,args:['--no-sandbox']});
 const anonymous=await browser.newContext();
 const path='/advice/shower-replacement-waterproofing-rebuild';
 for(const privatePath of ['/advice',path]) assert.equal((await anonymous.request.get(origin+privatePath)).status(),stage?401:published?200:404);
 assert.equal((await anonymous.request.get(origin+'/app')).status(),401);
 const context=await browser.newContext({httpCredentials:credentials,extraHTTPHeaders:{Authorization:`Basic ${Buffer.from(`${credentials.username}:${credentials.password}`).toString('base64')}`}});
 await context.addInitScript(()=>localStorage.setItem('nhp_analytics_choice_v1','rejected'));
 await context.route('**/*',route=>{if(new URL(route.request().url()).origin===origin)return route.continue();diagnostics.externalRequests.push(route.request().url());return route.abort();});
 const page=await context.newPage();page.on('pageerror',e=>diagnostics.pageErrors.push(e.message));
 page.on('response',r=>{if(r.status()>=400)diagnostics.badResponses.push({url:r.url(),status:r.status()});});
 const evidence=published && process.env.ADVICE_EVIDENCE_DIR?resolve(process.env.ADVICE_EVIDENCE_DIR):null;
 if(evidence)mkdirSync(evidence,{recursive:true});
 for(const [name,width,height] of [['desktop',1440,1000],['mobile',390,844]]) {
  await page.setViewportSize({width,height});const response=await page.goto(origin+path);assert.equal(response.status(),200);
  await page.waitForLoadState('networkidle');
  if(stage || !published) {assert.match(response.headers()['x-robots-tag'],/noindex/);assert.equal(response.headers()['cache-control'],'private, no-store');}
  else {assert(!response.headers()['x-robots-tag']);assert.equal(response.headers()['cache-control'],'no-cache');}
  assert.equal(await page.locator('main h1').count(),1);
  assert.match(await page.locator('main h1').textContent(),/complete shower replacement/);
  assert.equal(await page.locator('#public-analytics').getAttribute('data-send-to-google'),stage || !published?'false':'true');
  const layout=await page.evaluate(()=>({width:innerWidth,document:document.documentElement.scrollWidth,h2:document.querySelectorAll('main h2').length}));
  assert(layout.document<=width);diagnostics.layouts.push({name,...layout,overflow:false});
  const canonical=await page.locator('link[rel=canonical]').getAttribute('href');assert.equal(canonical,(stage?origin:'https://www.nigelharveyplumbing.co.uk')+path);
  for(const link of await page.locator('main a[href^="/"]').all()) {
   const href=(await link.getAttribute('href')).split('#')[0];assert.equal((await context.request.get(origin+href)).status(),200,href);
  }
  const schema=JSON.parse(await page.locator('script[type="application/ld+json"]').textContent());const article=schema['@graph'].find(x=>x['@type']==='Article');assert.equal(Boolean(article.datePublished),published);
  assert.equal(await page.locator('main img').count(),0);
  await page.evaluate(()=>scrollTo(0,0));
  if(evidence) {
   await page.screenshot({path:join(evidence,`advice-${name}-top.png`)});
   await page.screenshot({path:join(evidence,`advice-${name}.png`),fullPage:true});
   if(name==='desktop') {
    const html=await page.evaluate(()=>{const doc=document.documentElement.cloneNode(true);for(const s of doc.querySelectorAll('script:not([type="application/ld+json"])'))s.remove();doc.querySelector('#analytics-consent')?.remove();return '<!DOCTYPE html>\n'+doc.outerHTML;});
    writeFileSync(join(evidence,'Shower-Replacement-Owner-Preview.html'),html);
   }
  }
 }
 assert.equal((await(await context.request.get(origin+'/sitemap.xml')).text()).includes('/advice'),published);
 assert.equal((await context.request.get(origin+'/advice')).status(),200);
 assert.equal((await context.request.get(origin+'/projects/ensuite-renovation-merrow-guildford')).status(),200);
 assert.deepEqual(diagnostics.pageErrors,[]);assert.deepEqual(diagnostics.externalRequests,[]);assert.deepEqual(diagnostics.badResponses,[]);
 if(evidence)writeFileSync(join(evidence,'advice-browser-validation.json'),JSON.stringify(diagnostics,null,2)+'\n');
 console.log(JSON.stringify({result:'PASS',diagnostics},null,2));
} finally {if(browser)await browser.close();server.kill('SIGTERM');}

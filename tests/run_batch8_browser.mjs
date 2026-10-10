// Actual mixed catalogue: published shower/project, private radiator draft.
import assert from 'node:assert/strict';
import { randomBytes, createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { spawn } from 'node:child_process';
import net from 'node:net';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { bounded, stopServer } from './batch8_browser_support.mjs';
const require=createRequire(import.meta.url);
let playwright;
try {playwright=require('playwright')}catch{playwright=require(join(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES,'playwright'))}
const {chromium}=playwright;
const executablePath=process.env.STAGE6_CHROMIUM_EXECUTABLE||chromium.executablePath();
assert(existsSync(executablePath),'Preinstalled Chromium required');
const directory=dirname(fileURLToPath(import.meta.url));
const privateFile=process.env.PLUMBING_ADVICE_PRIVATE_DRAFTS;
assert(!(process.env.CI && privateFile),'Private owner content must not be loaded in public CI');
if(process.env.BATCH8_REQUIRE_PRIVATE_DRAFT==='1')assert(privateFile && !resolve(privateFile).includes('/tests/fixtures/'),'Complete private catalogue required');
const ownerRecords=privateFile?JSON.parse(readFileSync(privateFile,'utf8')):null;
const ownerArticle=ownerRecords?.find(a=>a.slug==='radiators-cold-heating-unevenly');
if(privateFile)assert(ownerArticle?.status==='draft' && !ownerArticle.approved_at && !ownerArticle.published_at,'Owner article must remain a private draft');
const socket=net.createServer();await new Promise(r=>socket.listen(0,'127.0.0.1',r));
const port=socket.address().port;await new Promise(r=>socket.close(r));
const origin=`http://127.0.0.1:${port}`;
const credentials={username:randomBytes(16).toString('hex'),password:randomBytes(24).toString('hex')};
const legacyProbe=process.argv.includes('--legacy-probe');
const faultImageDecode=process.argv.includes('--fault-image-decode');
const server=spawn(process.env.STAGE6_TEST_PYTHON||'python',['-B',join(directory,'batch8_browser_server.py')],{cwd:dirname(directory),env:{...process.env,STAGE6_TEST_USERNAME:credentials.username,STAGE6_TEST_PASSWORD:credentials.password,STAGE6_TEST_PORT:String(port)},stdio:['ignore','pipe','pipe']});
let serverErrorBytes=0, serverSpawnError;
server.on('error',error=>{serverSpawnError=error.code});
server.stderr.on('data',data=>serverErrorBytes+=data.length);if(!legacyProbe)server.stdout.resume();
const draft='/advice/radiators-cold-heating-unevenly';
const pages=[['home','/'],['guildford','/plumber-guildford'],['woking','/plumber-woking'],['farnham-leak','/leak-repair-farnham'],['radiator-draft',draft]];
const evidence=process.env.BATCH8_EVIDENCE_DIR?resolve(process.env.BATCH8_EVIDENCE_DIR):process.env.ADVICE_EVIDENCE_DIR?resolve(process.env.ADVICE_EVIDENCE_DIR,'batch8'):null;
if(evidence)mkdirSync(evidence,{recursive:true});
const diagnostics={pageErrors:[],consoleErrors:[],externalRequests:[],layouts:[],images:[],draftAnonymous:404,changedPageCount:4,
 draftContentMode:ownerArticle?'complete_private_owner_wording':'labelled_synthetic_fixture',
 privateCatalogueSha256:privateFile?createHash('sha256').update(readFileSync(privateFile)).digest('hex'):null};
const devices=[['desktop',1440,1000],['mobile',390,844]];
const probeArgs=process.argv.slice(2).filter(x=>!['--legacy-probe','--fault-image-decode'].includes(x));
const probe=probeArgs[0]==='--probe'?{page:probeArgs[1],device:probeArgs[2]}:null;
assert(probe?probeArgs.length===3:probeArgs.length===0,'Usage: run_batch8_browser.mjs [--probe page device] [diagnostic flag]');
if(probe)assert(pages.some(p=>p[0]===probe.page)&&devices.some(d=>d[0]===probe.device),'Unknown probe target');
diagnostics.scope=legacyProbe?'legacy_standalone_diagnostic':probe?'isolated_probe':'complete_batch8_workflow';
diagnostics.progress=[];
let browser, browserServer, activePhase='startup', failure;
const progress=event=>{
 event.serverStdoutBufferedBytes=server.stdout.readableLength;
 diagnostics.progress.push(event);if(diagnostics.progress.length>250)diagnostics.progress.shift();
 console.log('[batch8] '+JSON.stringify(event));
 if(evidence)writeFileSync(join(evidence,'batch8-progress.json'),JSON.stringify({scope:diagnostics.scope,progress:diagnostics.progress},null,2)+'\n');
};
const phase=(name,operation,ms=15000)=>{activePhase=name;return bounded(name,operation,ms,progress)};
const forceOwnedCleanup=()=>Promise.all([stopServer(server),...(browserServer?[stopServer(browserServer.process())]:[])]);
const watchdog=setTimeout(async()=>{
 progress({phase:activePhase,state:'harness_deadline',milliseconds:180000});
 try{await forceOwnedCleanup()}finally{process.exit(1)}
},180000);
try{

 await phase('server-ready',async()=>{for(let i=0;i<100;i++){
  if(serverSpawnError)throw Error(`Disposable server spawn failed: ${serverSpawnError}`);
  if(server.exitCode!==null)throw Error(`Disposable server exited; stderr bytes=${serverErrorBytes}`);
  try{if((await fetch(origin,{signal:AbortSignal.timeout(1000)})).status===200)break}catch{}
  if(i===99)throw Error('Server did not start');await new Promise(r=>setTimeout(r,100));
 }},12000);
 if(legacyProbe)browser=await phase('browser-launch',()=>chromium.launch({executablePath,headless:true,args:['--no-sandbox'],timeout:10000}));
 else{
  browserServer=await phase('browser-launch',()=>chromium.launchServer({executablePath,headless:true,args:['--no-sandbox'],timeout:10000}));
  browser=await phase('browser-connect',()=>chromium.connect(browserServer.wsEndpoint(),{timeout:10000}));
 }
 await phase('privacy-checks',async()=>{
 const anonymous=await browser.newContext();anonymous.setDefaultTimeout(10000);
 for(const suffix of ['', '?preview=1','?utm_source=google']){
  const hidden=await anonymous.request.get(origin+draft+suffix);assert.equal(hidden.status(),404);
  assert.match(hidden.headers()['x-robots-tag'],/noindex/);assert.equal(hidden.headers()['cache-control'],'private, no-store');
 }
 assert.equal((await anonymous.request.get(origin+'/app')).status(),401);
 assert.equal((await anonymous.request.get(origin+'/api/customers')).status(),401);
 assert.equal((await anonymous.request.get(origin+draft,{headers:{Authorization:'Basic ZmFrZTpmYWtl'}})).status(),404);
 assert(!(await(await anonymous.request.get(origin+'/advice')).text()).includes(draft));
 const sitemap=await(await anonymous.request.get(origin+'/sitemap.xml')).text();
 assert.equal((sitemap.match(/<loc>/g)||[]).length,76);assert(!sitemap.includes(draft));
 await anonymous.close();
 });
 const auth=Buffer.from(`${credentials.username}:${credentials.password}`).toString('base64');
 const context=await phase('context-create',()=>browser.newContext({httpCredentials:credentials,extraHTTPHeaders:{Authorization:`Basic ${auth}`}}));
 context.setDefaultTimeout(10000);context.setDefaultNavigationTimeout(15000);
 await context.addInitScript(()=>localStorage.setItem('nhp_analytics_choice_v1',location.pathname==='/advice/radiators-cold-heating-unevenly'?'accepted':'rejected'));
 if(faultImageDecode)await context.addInitScript(()=>HTMLImageElement.prototype.decode=()=>new Promise(()=>{}));
 await context.route('**/*',route=>{if(new URL(route.request().url()).origin===origin)return route.continue();diagnostics.externalRequests.push(route.request().url());return route.abort()});
 const page=await context.newPage();page.on('pageerror',e=>diagnostics.pageErrors.push(e.message));
 page.on('console',m=>{if(m.type()==='error')diagnostics.consoleErrors.push(m.text().replace(/data:image[^\s]+/g,'[inline image]').slice(0,300))});
 for(const [device,width,height] of devices){
  if(probe&&probe.device!==device)continue;
  await page.setViewportSize({width,height});
  for(const [name,path] of pages){
   if(probe&&probe.page!==name)continue;
   const step=(label,op,ms)=>phase(`${device}/${name}/${label}`,op,ms);
   const response=await step('navigation',()=>page.goto(origin+path,{timeout:15000}));assert.equal(response.status(),200);
   await step('network-idle',()=>page.waitForLoadState('networkidle',{timeout:10000}));
   await step('layout-and-branding',async()=>{
   assert.equal(await page.locator('main h1').count(),1);
   assert.equal(await page.locator('link[rel=canonical]').getAttribute('href'),'https://www.nigelharveyplumbing.co.uk'+path);
   const layout=await page.evaluate(()=>({width:innerWidth,document:document.documentElement.scrollWidth}));
   assert(layout.document<=width,`${name} ${device} overflow`);diagnostics.layouts.push({name,device,...layout});
   const brand=await page.locator('header .brand').evaluate(b=>({text:b.textContent,width:b.getBoundingClientRect().width}));
   assert(brand.text.includes('Nigel Harvey') && brand.width<=width,'Existing public wordmark must remain readable');
   diagnostics.layouts.at(-1).branding=brand.text.replace(/\s+/g,' ').trim();
   });
   const images=await step('image-decoding',()=>page.locator('img').evaluateAll(async images=>Promise.all(images.map(async i=>{
    let decodeError=null;try{await i.decode()}catch(e){decodeError=e.name}
    return {alt:i.alt,sourceKind:i.src.startsWith('data:')?'inline':'local',complete:i.complete,naturalWidth:i.naturalWidth,naturalHeight:i.naturalHeight,decodeError};
   }))),8000);
   diagnostics.images.push({name,device,images});
   await step('metadata-and-content',async()=>{
   if(path===draft){assert.match(response.headers()['x-robots-tag'],/noindex/);assert.equal(response.headers()['cache-control'],'private, no-store');assert.equal(await page.locator('#public-analytics').getAttribute('data-send-to-google'),'false')}
   else assert(!response.headers()['x-robots-tag']);
   const graphs=[];for(const s of await page.locator('script[type="application/ld+json"]').all())graphs.push(JSON.parse(await s.textContent()));
   if(path===draft){
    const a=graphs.flatMap(g=>g['@graph']||[g]).find(g=>g['@type']==='Article');
    assert(a && a.author.name==='Nigel Harvey');assert(!a.datePublished && !a.dateModified);
    assert.equal(await page.locator('nav a[href^="/advice/radiators-cold"]').count(),0);
    assert.equal(await page.locator('main img').count(),0);
    if(ownerArticle){
     assert.equal(await page.locator('main h1').textContent(),ownerArticle.title);
     const text=await page.locator('main').innerText();
     const normalize=s=>s.replace(/\s+/g,' ').trim();
     for(const p of [ownerArticle.summary,ownerArticle.author_note,...ownerArticle.sections.flatMap(s=>[s.heading,...s.paragraphs]),...ownerArticle.safety,...ownerArticle.faqs.flatMap(f=>[f.question,f.answer])])assert(normalize(text).includes(normalize(p)),'Complete private wording must be rendered');
     const external=await page.locator('main a[href^="https://"]').evaluateAll(links=>links.map(l=>({href:l.href,rel:l.rel})));
     assert.deepEqual(external.map(x=>x.href),ownerArticle.sources);assert(external.every(x=>x.rel.includes('noopener')&&x.rel.includes('noreferrer')));
     diagnostics.externalSourceLinks=external.map(x=>x.href);
    }
    const readability=await page.locator('main .advice-story p:not(.kicker):not(.project-byline)').evaluateAll(ps=>ps.map(p=>({font:parseFloat(getComputedStyle(p).fontSize),line:parseFloat(getComputedStyle(p).lineHeight)})));
    assert(readability.every(p=>p.font>=14 && p.line>p.font));
    diagnostics.layouts.at(-1).paragraphs=readability.length;
   }
   });
   await step('internal-links',async()=>{
   const hrefs=await page.locator('main a[href^="/"]').evaluateAll(links=>links.map(l=>l.getAttribute('href').split('#')[0]));
   for(const href of new Set(hrefs))assert.equal((await context.request.get(origin+href,{timeout:10000})).status(),200,href);
   const quote=page.locator('main a').filter({hasText:'enquiry form'});
   if(path==='/plumber-guildford'){
    const href=await quote.getAttribute('href');assert(href.includes('landing_page=%2Fplumber-guildford'));
   }
   if(path===draft){
    const href=await page.locator('main a.btn').getAttribute('href');assert(href.startsWith('/request-quote'));
    assert.equal((await context.request.get(origin+href,{timeout:10000})).status(),200);
   }
   });
   await step('scroll-top',()=>page.evaluate(()=>scrollTo(0,0)));
   if(evidence){
    await step('viewport-screenshot',()=>page.screenshot({path:join(evidence,`${name}-${device}-top.png`),timeout:15000}));
    await step('full-page-screenshot',()=>page.screenshot({path:join(evidence,`${name}-${device}.png`),fullPage:true,timeout:15000}));
    if(device==='desktop')await step('owner-html-capture',async()=>{
     const pictures=await page.locator('img[src^="/"]').evaluateAll(images=>images.map(i=>i.getAttribute('src')));
     const embedded={};for(const src of new Set(pictures)){const r=await context.request.get(origin+src,{timeout:10000});if(r.ok())embedded[src]=`data:${r.headers()['content-type']};base64,${(await r.body()).toString('base64')}`}
     const html=await page.evaluate(embedded=>{const doc=document.documentElement.cloneNode(true);for(const s of doc.querySelectorAll('script:not([type="application/ld+json"])'))s.remove();doc.querySelector('#analytics-consent')?.remove();for(const img of doc.querySelectorAll('img')){if(embedded[img.getAttribute('src')])img.setAttribute('src',embedded[img.getAttribute('src')]);img.removeAttribute('srcset')}return '<!doctype html>\n'+doc.outerHTML},embedded);
     writeFileSync(join(evidence,`${name}-owner-preview.html`),html);
    });
   }
   await step('enquiry-navigation',async()=>{
   const enquiry=path===draft?page.locator('main a.btn'):page.locator('main a[href^="/request-quote"]').first();
   const enquiryHref=await enquiry.getAttribute('href');await enquiry.click({timeout:10000});await page.waitForURL('**/request-quote**',{timeout:10000});
   assert(await page.locator('#lead_postcode').isVisible(),'Enquiry form postcode input must be usable');
   diagnostics.layouts.at(-1).enquiryDestination=enquiryHref;
   });
  }
 }
 if(evidence)writeFileSync(join(evidence,'batch8-browser-validation.json'),JSON.stringify(diagnostics,null,2)+'\n');
 assert.deepEqual(diagnostics.pageErrors,[]);assert.deepEqual(diagnostics.externalRequests,[]);
 assert(!diagnostics.images.some(p=>p.images.some(i=>i.decodeError||!i.naturalWidth)), 'All page images must decode before screenshots');
}catch(error){
 failure={phase:activePhase,errorType:error.name};
 diagnostics.failure=failure;process.exitCode=1;
 console.error('[batch8] Failure '+JSON.stringify(failure));
}finally{
 clearTimeout(watchdog);
 try{if(browser)await phase('cleanup-browser',async()=>{await browser.close();if(browserServer)await browserServer.close()},5000);
  diagnostics.browserProcessTerminated=browserServer?browserServer.process().exitCode!==null||browserServer.process().signalCode!==null:!browser?.isConnected()} 
 catch(error){diagnostics.cleanupForced=true;await forceOwnedCleanup();failure??={phase:'cleanup-browser',errorType:error.name};process.exitCode=1}
 try{diagnostics.serverCleanup=await phase('cleanup-server',()=>stopServer(server),7000)}
 catch(error){await forceOwnedCleanup();failure??={phase:'cleanup-server',errorType:error.name};process.exitCode=1}
 if(evidence)writeFileSync(join(evidence,'batch8-browser-validation.json'),JSON.stringify(diagnostics,null,2)+'\n');
 console.log(JSON.stringify({result:failure?'FAIL':legacyProbe?'DIAGNOSTIC_PASS':probe?'PROBE_PASS':'PASS',diagnostics},null,2));
}


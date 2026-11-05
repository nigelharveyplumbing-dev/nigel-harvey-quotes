// Full 82-route staging matrix; never submits forms or follows contact actions.
import assert from 'node:assert/strict';
import {randomBytes} from 'node:crypto';
import {createRequire} from 'node:module';
import {mkdirSync,writeFileSync} from 'node:fs';
import {spawn} from 'node:child_process';
import net from 'node:net';
import {dirname,join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {stopServer} from './batch8_browser_support.mjs';
const require=createRequire(import.meta.url);
let playwright;
try{playwright=require('playwright')}catch{playwright=require(join(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES,'playwright'))}
const directory=dirname(fileURLToPath(import.meta.url));
const remote=process.env.NHP_SEO_STAGING_URL;
let server,origin,credentials;
if(remote){
 origin=remote.replace(/\/$/,'');
 assert(new URL(origin).hostname.endsWith('.onrender.com'),'Hosted staging only');
 credentials={username:process.env.NHP_SEO_STAGING_USERNAME,password:process.env.NHP_SEO_STAGING_PASSWORD};
 assert(credentials.username&&credentials.password,'Staging credentials required');
}else{
 const socket=net.createServer();await new Promise(r=>socket.listen(0,'127.0.0.1',r));
 const port=socket.address().port;await new Promise(r=>socket.close(r));
 origin=`http://127.0.0.1:${port}`;
 credentials={username:randomBytes(16).toString('hex'),password:randomBytes(24).toString('hex')};
 server=spawn(process.env.STAGE6_TEST_PYTHON||'python',['-B',join(directory,'full_site_browser_server.py')],{
  cwd:dirname(directory),env:{...process.env,STAGE6_TEST_PORT:String(port),STAGE6_TEST_USERNAME:credentials.username,STAGE6_TEST_PASSWORD:credentials.password},stdio:['ignore','pipe','pipe']});
 server.stdout.resume();server.stderr.resume();
}
const evidence=resolve(process.env.FULL_SITE_EVIDENCE_DIR||'/tmp/nhp-full-site-evidence');mkdirSync(evidence,{recursive:true});
const diagnostics={origin,viewports:[],pages:[],pageErrors:[],failures:[],externalRequests:[]};
let browser;
const auth='Basic '+Buffer.from(credentials.username+':'+credentials.password).toString('base64');
try{
 for(let i=0;i<100;i++){
  try{if((await fetch(origin,{headers:{Authorization:auth}})).ok)break}catch{}
  if(server?.exitCode!==null&&server?.exitCode!==undefined)throw Error('Staging server exited');
  if(i===99)throw Error('Staging server did not start');
  await new Promise(r=>setTimeout(r,100));
 }
 assert.equal((await fetch(origin)).status,401,'Staging must require authentication');
 const sitemap=await fetch(origin+'/sitemap.xml',{headers:{Authorization:auth}});
 assert.equal(sitemap.status,200);
 assert.match(sitemap.headers.get('x-robots-tag'),/noindex/);
 const urls=[...(await sitemap.text()).matchAll(/<loc>(.*?)<\/loc>/g)].map(x=>x[1]);
 assert.equal(urls.length,82);assert.equal(new Set(urls).size,82);
 assert(urls.every(u=>new URL(u).origin===origin),'Staging sitemap origin');
 const paths=urls.map(u=>new URL(u).pathname);
 browser=await playwright.chromium.launch({headless:true,...(process.env.STAGE6_CHROMIUM_EXECUTABLE?{executablePath:process.env.STAGE6_CHROMIUM_EXECUTABLE}:{})});
 for(const [device,width,height] of [['mobile-320',320,800],['mobile-375',375,900],['tablet',768,1024],['desktop',1440,1000]]){
  const context=await browser.newContext({viewport:{width,height},httpCredentials:credentials});
  await context.addInitScript(()=>localStorage.setItem('nhp_analytics_choice_v1','rejected'));
  await context.route('**/*',route=>{
   if(new URL(route.request().url()).origin===origin)return route.continue();
   diagnostics.externalRequests.push(route.request().url());return route.abort();
  });
  const page=await context.newPage();page.on('pageerror',e=>diagnostics.pageErrors.push({device,error:e.message}));
  for(const path of paths){
   const response=await page.goto(origin+path,{waitUntil:'load'});
   await page.evaluate(()=>document.fonts.ready);
   await page.evaluate(async()=>{
    // Below-the-fold project photographs are lazy-loaded in the real page.
    // Request them explicitly before a full-page capture and bound decoding,
    // so an offscreen image cannot stall the entire 328-case matrix.
    const images=[...document.images];for(const img of images)img.loading='eager';
    let timeout;
    try{await Promise.race([
     Promise.all(images.map(img=>img.decode().catch(()=>{}))),
     new Promise((_,reject)=>{timeout=setTimeout(()=>reject(Error('Image decode deadline')),15000)}),
    ])}finally{clearTimeout(timeout)}
   });
   const headers=await response.allHeaders();
   const layout=await page.evaluate(()=>({
    ctaContrast:[...document.querySelectorAll('.cta p')].map(x=>{
     const rgb=c=>c.match(/[\d.]+/g).slice(0,3).map(Number);
     const luminance=c=>rgb(c).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
     let background=x;while(background.parentElement&&getComputedStyle(background).backgroundColor==='rgba(0, 0, 0, 0)')background=background.parentElement;
     const fg=luminance(getComputedStyle(x).color),bg=luminance(getComputedStyle(background).backgroundColor);
     return {text:x.textContent,ratio:(Math.max(fg,bg)+.05)/(Math.min(fg,bg)+.05)};
    }),
    overflow:document.documentElement.scrollWidth>innerWidth,
    canonical:[...document.querySelectorAll('link[rel="canonical"]')].map(x=>x.href),
    h1:document.querySelectorAll('h1').length,title:document.title,
    description:document.querySelector('meta[name="description"]')?.content,
    logos:document.querySelectorAll('header .brand-logo').length,
    brokenImages:[...document.images].filter(x=>!x.complete||!x.naturalWidth).map(x=>x.getAttribute('src')),
    analyticsSend:document.querySelector('#public-analytics')?.dataset.sendToGoogle,
    quoteLinks:document.querySelectorAll('a[href^="/request-quote"]').length,
    phoneLinks:document.querySelectorAll('a[href^="tel:"]').length,
    clippedHeadings:[...document.querySelectorAll('h1,h2,h3')].filter(x=>{
     const r=x.getBoundingClientRect();return r.width>0&&(r.left< -1||r.right>innerWidth+1);
    }).map(x=>x.textContent),
   }));
   const row={device,path,status:response.status(),noindex:headers['x-robots-tag'],revision:headers['x-preview-commit'],...layout};
   diagnostics.pages.push(row);
   const problems=[];
   if(row.status!==200)problems.push('HTTP');
   if(!/noindex/.test(row.noindex||''))problems.push('staging noindex');
   if(row.overflow||row.clippedHeadings.length)problems.push('layout overflow');
   if(row.ctaContrast.some(x=>x.ratio<4.5))problems.push('contact banner contrast');
   if(row.canonical.length!==1||row.canonical[0]!==origin+path)problems.push('canonical');
   if(row.h1!==1||!row.title||!row.description)problems.push('metadata/heading');
   if(row.logos!==1||row.brokenImages.length)problems.push('logo/images');
   if(row.analyticsSend!=='false')problems.push('staging analytics');
   if(!row.quoteLinks||!row.phoneLinks)problems.push('contact routes');
   if(problems.length)diagnostics.failures.push({device,path,problems});
   await page.screenshot({path:join(evidence,`${device}-${path==='/'?'home':path.slice(1).replaceAll('/','_')}.png`),fullPage:true});
  }
  diagnostics.viewports.push({device,width,height,pages:paths.length});await context.close();
 }
 assert.deepEqual(diagnostics.pageErrors,[]);assert.deepEqual(diagnostics.failures,[]);
 diagnostics.result='PASS';console.log(JSON.stringify({result:'PASS',pages:82,responsiveChecks:diagnostics.pages.length,origin}));
}finally{
 writeFileSync(join(evidence,'full-site-validation.json'),JSON.stringify(diagnostics,null,2));
 if(browser)await browser.close();if(server)await stopServer(server);
}

// Public Google badge layout and accessibility checks. Synthetic reviews only.
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
const socket=net.createServer();await new Promise(r=>socket.listen(0,'127.0.0.1',r));
const port=socket.address().port;await new Promise(r=>socket.close(r));
const origin=`http://127.0.0.1:${port}`;
const credentials={username:randomBytes(16).toString('hex'),password:randomBytes(24).toString('hex')};
const server=spawn(process.env.STAGE6_TEST_PYTHON||'python',['-B',join(directory,'public_reviews_browser_server.py')],{cwd:dirname(directory),env:{...process.env,STAGE6_TEST_USERNAME:credentials.username,STAGE6_TEST_PASSWORD:credentials.password,STAGE6_TEST_PORT:String(port)},stdio:['ignore','pipe','pipe']});
let serverError='';server.stderr.on('data',d=>serverError+=d);server.stdout.resume();
const evidence=resolve(process.env.PUBLIC_REVIEWS_EVIDENCE_DIR||'/tmp/nhp-public-review-evidence');mkdirSync(evidence,{recursive:true});
const pages=[['home','/'],['local-service','/leak-repair-guildford'],['service','/heating-repairs-surrey'],['surrey','/plumber-woking'],['london','/plumber-wimbledon'],['advice','/advice/shower-replacement-waterproofing-rebuild'],['project','/projects/ensuite-renovation-merrow-guildford'],['enquiry','/request-quote']];
const diagnostics={fixture:'Synthetic Google response: 4.6 / 23; not production data',layouts:[],pageErrors:[]};
let browser;
try{
 for(let i=0;i<100;i++){
  if(server.exitCode!==null)throw Error(serverError.slice(-1000));
  try{if((await fetch(origin)).ok)break}catch{}
  if(i===99)throw Error('Public review test server did not start');
  await new Promise(r=>setTimeout(r,100));
 }
 browser=await playwright.chromium.launch({headless:true,...(process.env.STAGE6_CHROMIUM_EXECUTABLE?{executablePath:process.env.STAGE6_CHROMIUM_EXECUTABLE}:{})});
 for(const [device,width,height] of [['desktop',1440,1000],['tablet',768,1024],['mobile',375,900],['small-mobile',320,800]]){
  const context=await browser.newContext({viewport:{width,height},httpCredentials:credentials});
  await context.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
  const page=await context.newPage();page.on('pageerror',e=>diagnostics.pageErrors.push(e.message));
  for(const [name,path] of pages){
   const response=await page.goto(origin+path,{waitUntil:'networkidle'});assert.equal(response.status(),200,path);
   const decline=page.getByRole('button',{name:'Decline',exact:true});if(await decline.isVisible())await decline.click();
   await page.mouse.move(0,0); // Measure the normal badge, independently of the previous page's pointer.
   const layout=await page.evaluate(()=>{
    const badge=document.querySelector('.hero-review-badge');const link=badge?.querySelector('a');
    const actions=badge?.parentElement.querySelector('.actions,.nav-actions');
    const rect=badge?.getBoundingClientRect();const buttonRect=actions?.getBoundingClientRect();
    return {overflow:document.documentElement.scrollWidth>innerWidth,badges:document.querySelectorAll('.hero-review-badge').length,cards:document.querySelectorAll('.google-review-card').length,headerLogos:document.querySelectorAll('header .brand-logo').length,heroLogos:document.querySelectorAll('.hero img.logo').length,href:link?.getAttribute('href'),text:link?.textContent,background:link?getComputedStyle(link).backgroundColor:null,color:link?getComputedStyle(link).color:null,starColor:link?.querySelector('.stars')?getComputedStyle(link.querySelector('.stars')).color:null,underline:link?getComputedStyle(link).textDecorationLine:null,badgeWidth:link?.getBoundingClientRect().width,beforeActions:rect&&buttonRect?rect.bottom<=buttonRect.top:null};
   });
   diagnostics.layouts.push({device,path,...layout});assert.equal(layout.overflow,false,`${device} ${path}: overflow`);
   assert.equal(layout.headerLogos,1,path);assert.equal(layout.heroLogos,0,path);
   if(name==='home'){assert.equal(layout.cards,5);assert.equal(layout.badges,0)}
   else if(name==='enquiry'){assert.equal(layout.badges,0)}
   else{
    assert.equal(layout.badges,1,path);assert.equal(layout.cards,0,path);assert.equal(layout.href,'/#reviews');assert.match(layout.text,/4\.6/);assert.match(layout.text,/23 Google reviews/);
    assert.equal(layout.background,'rgb(255, 255, 255)');assert.equal(layout.color,'rgb(7, 85, 135)');assert.equal(layout.starColor,'rgb(169, 97, 5)');assert.equal(layout.underline,'none');assert(layout.badgeWidth<=width);
    if(layout.beforeActions!==null)assert.equal(layout.beforeActions,true,path);
    const link=page.locator('.hero-review-badge a');await link.focus();
    assert(await link.evaluate(el=>el===document.activeElement));
   }
   await page.screenshot({path:join(evidence,`${name}-${device}.png`),fullPage:false});
  }
  await context.close();
 }
 assert.deepEqual(diagnostics.pageErrors,[]);diagnostics.result='PASS';
 console.log(JSON.stringify({result:'PASS',responsiveChecks:diagnostics.layouts.length,fixture:diagnostics.fixture}));
}finally{
 writeFileSync(join(evidence,'public-review-validation.json'),JSON.stringify(diagnostics,null,2));
 if(browser)await browser.close();await stopServer(server);
}

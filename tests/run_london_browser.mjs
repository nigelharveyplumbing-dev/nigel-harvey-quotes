// Six owner-confirmed area pages, isolated data and blocked outbound traffic.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {randomBytes} from 'node:crypto';
import {spawn} from 'node:child_process';
import net from 'node:net';
import {join,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
const require=createRequire(import.meta.url);
const {chromium}=require(join(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES,'playwright'));
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const probe=net.createServer();await new Promise(r=>probe.listen(0,'127.0.0.1',r));const port=probe.address().port;await new Promise(r=>probe.close(r));
const origin=`http://127.0.0.1:${port}`;
const server=spawn(process.env.STAGE6_TEST_PYTHON||'python',['-B','tests/batch8_browser_server.py'],{cwd:root,env:{...process.env,STAGE6_TEST_PORT:String(port),STAGE6_TEST_USERNAME:randomBytes(12).toString('hex'),STAGE6_TEST_PASSWORD:randomBytes(18).toString('hex')},stdio:['ignore','ignore','pipe']});server.stderr.resume();
let browser;const errors=[],external=[];const deadline=setTimeout(()=>{server.kill('SIGKILL');process.exitCode=1;browser?.close();},120000);
try {
 for(let i=0;i<100;i++){try{if((await fetch(origin)).status===200)break;}catch{}if(i===99)throw Error('Disposable server did not start');await new Promise(r=>setTimeout(r,100));}
 browser=await chromium.launch({headless:true,executablePath:process.env.STAGE6_CHROMIUM_EXECUTABLE,args:['--no-sandbox']});
 const context=await browser.newContext();await context.addInitScript(()=>localStorage.setItem('nhp_analytics_choice_v1','rejected'));
 await context.route('**/*',route=>{if(new URL(route.request().url()).origin===origin)return route.continue();external.push(route.request().url());return route.abort();});
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 let layouts=0;
 for(const [width,height] of [[1440,1000],[390,844],[320,740]]){
  await page.setViewportSize({width,height});
  await page.goto(origin);for(const slug of ['richmond','kingston','wimbledon','putney','merton','morden'])assert.equal(await page.locator(`#areas a[href="/plumber-${slug}"]`).count(),1);
  for(const slug of ['richmond','kingston','wimbledon','putney','merton','morden']){
   const response=await page.goto(origin+'/plumber-'+slug);assert.equal(response.status(),200);await page.waitForLoadState('networkidle');
   assert.equal(await page.locator('main h1').count(),1);
   assert((await page.evaluate(()=>document.documentElement.scrollWidth))<=width,`${slug} overflow at ${width}`);
   const text=await page.locator('main').innerText();assert.match(text,/based in Guildford/);assert.match(text,/subject to availability/);
   const href=await page.locator('main a[href^="/request-quote"]').first().getAttribute('href');assert.equal(new URL(href,origin).searchParams.get('landing_page'),'/plumber-'+slug);
   await page.locator('main a[href^="/request-quote"]').first().click();await page.waitForURL('**/request-quote**');assert(await page.locator('#lead_postcode').isVisible());layouts++;
  }
 }
 assert.deepEqual(errors,[]);assert.deepEqual(external,[]);console.log(`South West London browser PASS: ${layouts} layouts; six homepage links; enquiry attribution; zero submissions, errors or external requests.`);
}finally{clearTimeout(deadline);if(browser)await browser.close();server.kill('SIGTERM');await new Promise(r=>server.exitCode!==null?r():server.once('exit',r));}

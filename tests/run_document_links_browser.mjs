// Enabled-mode desktop/mobile UI, downloads and scoped customer media.
// All records and credentials are synthetic; no WhatsApp/email is sent.
import assert from 'node:assert/strict';
import {randomBytes} from 'node:crypto';
import {createRequire} from 'node:module';
import {existsSync, mkdirSync, readFileSync, writeFileSync} from 'node:fs';
import {spawn} from 'node:child_process';
import net from 'node:net';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {bounded, stopServer} from './batch8_browser_support.mjs';

const require = createRequire(import.meta.url);
let playwright;
try {playwright = require('playwright');}
catch {playwright = require(join(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES, 'playwright'));}
const executablePath = process.env.STAGE6_CHROMIUM_EXECUTABLE || playwright.chromium.executablePath();
assert(existsSync(executablePath), 'Preinstalled Chromium required');
const directory = dirname(fileURLToPath(import.meta.url));
const evidence = process.env.DOCUMENT_LINK_EVIDENCE_DIR ? resolve(process.env.DOCUMENT_LINK_EVIDENCE_DIR) : null;
if (evidence) mkdirSync(evidence, {recursive:true});
const report = {synthetic_only:true, browser:'Chromium', mode:'secure', cases:[], external_requests:0};
let browser, server, failure;
const cleanup = async () => {
  if (browser) {await browser.close(); browser = null;}
  if (server) {await stopServer(server); server = null;}
};
const deadline = setTimeout(async () => {try {await cleanup();} finally {process.exit(1);}}, 240000);
for (const signal of ['SIGTERM','SIGINT']) process.once(signal, async () => {await cleanup(); process.exit(1);});
const phase = (label, action) => bounded(label, action, 40000);
const picture = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO2X6a8AAAAASUVORK5CYII=', 'base64');

try {
  browser = await playwright.chromium.launch({headless:true, executablePath});
  for (const policy of ['customer','staging']) {
    const socket = net.createServer();
    await new Promise(resolve => socket.listen(0, '127.0.0.1', resolve));
    const port = socket.address().port;
    await new Promise(resolve => socket.close(resolve));
    const origin = `http://127.0.0.1:${port}`;
    const credentials = {username:randomBytes(16).toString('hex'), password:randomBytes(24).toString('hex')};
    server = spawn(process.env.STAGE6_TEST_PYTHON || 'python', ['-B', join(directory,'document_links_browser_server.py')], {
      cwd:dirname(directory), env:{...process.env, STAGE6_TEST_USERNAME:credentials.username,
        STAGE6_TEST_PASSWORD:credentials.password, STAGE6_TEST_PORT:String(port), DOCUMENT_LINK_TEST_POLICY:policy},
      stdio:['ignore','pipe','pipe'],
    });
    let serverErrorBytes = 0;
    server.stdout.resume(); server.stderr.on('data', chunk => {serverErrorBytes += chunk.length;});
    await phase(`${policy}-startup`, async () => {
      for (let n = 0; n < 100; n++) {
        assert.equal(server.exitCode, null, `Isolated server exited (${serverErrorBytes} diagnostic bytes)`);
        try {if ([200,401].includes((await fetch(origin + '/app')).status)) return;} catch {}
        await new Promise(resolve => setTimeout(resolve,100));
      }
      throw new Error('Isolated server did not become ready');
    });
    for (const [device,width,height] of [['desktop',1440,1000], ['mobile',390,844]]) {
      await phase(`${policy}-${device}`, async () => {
        const name = `Fictional ${policy} ${device} Customer`;
        const errors = [], external = [];
        const context = await browser.newContext({httpCredentials:credentials, acceptDownloads:true,
          viewport:{width,height}, isMobile:device === 'mobile', hasTouch:device === 'mobile'});
        const anonymous = await browser.newContext({viewport:{width,height}, acceptDownloads:true});
        const guard = async route => {
          const url = new URL(route.request().url());
          if (url.origin === origin) return route.continue();
          external.push(url.origin); return route.abort('blockedbyclient');
        };
        await context.route('**/*', guard); await anonymous.route('**/*', guard);
        const page = await context.newPage();
        page.on('pageerror', error => errors.push(error.name));
        assert.equal((await anonymous.request.get(origin+'/app')).status(),401);
        assert.equal((await page.goto(origin+'/app')).status(),200);
        await page.getByRole('button',{name:'Quotes',exact:true}).click();
        await page.locator('#customer_name').fill(name);
        await page.locator('#customer_address').fill('1 Fictional Test Lane');
        await page.locator('#customer_phone').fill('07000000000');
        await page.locator('#job').fill('FICTIONAL TEST ONLY - valve replacement');
        await page.locator('#labour').fill('120');
        const quoteResponse = page.waitForResponse(r => r.url() === origin+'/api/quote' && r.request().method() === 'POST');
        await page.getByRole('button',{name:'Generate Quote',exact:true}).click();
        const quote = await (await quoteResponse).json();
        assert.match(quote.share_pdf_path, /^\/share\/quote\/[\w-]{43}\/pdf$/);
        const quoteMessage = new URL(await page.locator('#whatsappBtn').getAttribute('href')).searchParams.get('text');
        assert(quoteMessage.includes(origin + quote.share_pdf_path));
        assert(!quoteMessage.includes('/api/quotes/'));
        if (evidence) await page.screenshot({path:join(evidence,`${policy}-${device}-quote.png`), fullPage:true});
        const conversion = page.waitForResponse(r => r.url() === `${origin}/api/quotes/${quote.id}/to-invoice`);
        await page.locator('#historyList .history-item').filter({hasText:name})
          .getByRole('button',{name:'To Invoice',exact:true}).click();
        const invoice = await (await conversion).json();
        assert.match(invoice.share_path, /^\/share\/invoice\/[\w-]{43}$/);
        const row = page.locator('#invoiceList .history-item').filter({hasText:invoice.invoice_number});
        await row.getByRole('button',{name:'Preview Invoice',exact:true}).click();
        await page.locator('#invoicePhotoFiles').setInputFiles({name:'fictional.png',mimeType:'image/png',buffer:picture});
        const photoResponse = page.waitForResponse(r => r.url() === `${origin}/api/invoices/${invoice.id}/photos` && r.request().method() === 'POST');
        await page.getByRole('button',{name:'Add Photos to Invoice',exact:true}).click();
        const photo = (await (await photoResponse).json()).photos[0];
        await page.locator('#invoicePhotoGallery img').first().waitFor();
        const invoiceMessage = new URL(await page.locator('#invoiceWhatsappBtn').getAttribute('href')).searchParams.get('text');
        assert(invoiceMessage.includes(origin + invoice.share_path));
        assert(!invoiceMessage.includes(`${origin}/invoice/`));
        assert.equal(await page.locator('#invoiceOpenBtn').getAttribute('href'),origin + invoice.share_path);
        if (evidence) await page.screenshot({path:join(evidence,`${policy}-${device}-owner-invoice.png`),fullPage:true});

        // Exercise the actual email UI while intercepting its request locally.
        // SMTP remains disabled and blocked in the disposable application.
        let emailPayload;
        const emailEndpoint = `${origin}/api/invoices/${invoice.id}/send-email`;
        await page.route(emailEndpoint, async route => {
          emailPayload = route.request().postDataJSON();
          await route.fulfill({status:200,contentType:'application/json',body:'{"ok":true}'});
        });
        const promptHandler = dialog => dialog.accept(dialog.message().startsWith('Send invoice')
          ? 'fictional@example.test' : 'FICTIONAL TEST ONLY');
        page.on('dialog',promptHandler);
        await page.getByRole('button',{name:'Email Invoice PDF',exact:true}).click();
        await page.getByText('Invoice email sent successfully.',{exact:true}).waitFor();
        page.off('dialog',promptHandler);
        assert.deepEqual(emailPayload,{to_email:'fictional@example.test',message:'FICTIONAL TEST ONLY'});
        await page.unroute(emailEndpoint);

        const customerContext = policy === 'customer' ? anonymous : context;
        const customer = await customerContext.newPage();
        customer.on('pageerror', error => errors.push(error.name));
        if (policy === 'staging') {
          for (const suffix of ['', '/pdf','/payment-qr',`/photos/${photo.id}`])
            assert.equal((await anonymous.request.get(origin+invoice.share_path+suffix)).status(),401);
          assert.equal((await anonymous.request.get(origin+quote.share_pdf_path)).status(),401);
        }
        const response = await customer.goto(origin+invoice.share_path);
        assert.equal(response.status(),200);
        for (const [header, value] of [['cache-control','no-store'],['referrer-policy','no-referrer']])
          assert.equal(response.headers()[header],value);
        await customer.getByText(name,{exact:false}).waitFor();
        for (const image of await customer.locator('img').all()) {
          await image.scrollIntoViewIfNeeded();
          assert(await image.evaluate(i => i.complete && i.naturalWidth > 0),'Customer image failed');
        }
        assert(await customer.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1), 'Customer invoice overflows viewport');
        assert.equal(await customer.getByRole('link',{name:'Download PDF',exact:true}).getAttribute('href'),invoice.share_path+'/pdf');
        if (evidence) await customer.screenshot({path:join(evidence,`${policy}-${device}-customer-invoice.png`),fullPage:true});
        const downloadEvent = customer.waitForEvent('download');
        await customer.getByRole('link',{name:'Download PDF',exact:true}).click();
        const download = await downloadEvent;
        assert.equal(download.suggestedFilename(),invoice.invoice_number+'.pdf');
        assert.equal(readFileSync(await download.path()).subarray(0,4).toString(),'%PDF');
        const quoteDownloadPage = await customerContext.newPage();
        const quoteDownloadEvent = quoteDownloadPage.waitForEvent('download');
        await quoteDownloadPage.goto(origin+quote.share_pdf_path).catch(error => assert.match(error.message,/Download is starting|net::ERR_ABORTED/));
        const quoteDownload = await quoteDownloadEvent;
        assert.equal(readFileSync(await quoteDownload.path()).subarray(0,4).toString(),'%PDF');
        for (const path of [`/invoice/${invoice.id}`,`/api/invoices/${invoice.id}/pdf`,`/api/quotes/${quote.id}/pdf`])
          assert.equal((await anonymous.request.get(origin+path)).status(),401);
        assert.equal((await anonymous.request.get(`${origin}/api/invoices/${invoice.id}`)).status(),401);
        assert.equal((await customerContext.request.get(origin+invoice.share_path+'/photos/999999')).status(),404);
        const endpoint = `${origin}/api/document-links/invoice/${invoice.id}`;
        const replacement = (await (await context.request.post(endpoint)).json()).path;
        assert.equal((await customerContext.request.get(origin+invoice.share_path)).status(),404);
        assert.equal((await customer.goto(origin+replacement)).status(),200);
        assert.equal((await context.request.delete(endpoint)).status(),200);
        assert.equal((await customerContext.request.get(origin+replacement)).status(),404);
        assert.deepEqual(errors,[]); assert.deepEqual(external,[]);
        report.cases.push({policy,device,viewport:[width,height],result:'PASS',
          quote_ui:true,invoice_ui:true,whatsapp_links:true,email_ui_intercepted:true,
          pdf_downloads:true,images:true,no_horizontal_overflow:true,legacy_staff_only:true,
          rotation_and_revocation:true,anonymous_customer:policy === 'customer',
          staging_auth:policy === 'staging',page_errors:0,external_requests:0});
        await context.close(); await anonymous.close();
        console.log(`Document links ${policy} ${device}: PASS`);
      });
    }
    await stopServer(server); server = null;
  }
} catch (error) {
  failure = error; report.failure = error.name;
} finally {
  clearTimeout(deadline); await cleanup();
  report.result = failure ? 'FAIL' : 'PASS';
  if (evidence) writeFileSync(join(evidence,'document-links-browser.json'),JSON.stringify(report,null,2)+'\n');
}
if (failure) throw failure;
console.log('Secure document-link browser matrix: PASS (four desktop/mobile policy cases; no messages sent)');

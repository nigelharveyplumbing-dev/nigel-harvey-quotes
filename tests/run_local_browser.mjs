// Stage 6 UI checks. Requires a preinstalled Playwright Chromium executable.
// The child server first copies the application into a temporary directory and
// rejects every non-loopback socket, HTTP request and SMTP connection.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { randomBytes } from 'node:crypto';
import { existsSync } from 'node:fs';
import net from 'node:net';
import { spawn } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const packageDirectory = process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES;
let playwright;
try {
  playwright = require('playwright');
} catch {
  if (!packageDirectory) throw new Error('Install Playwright in the test environment first');
  playwright = require(join(packageDirectory, 'playwright'));
}
const { chromium } = playwright;
const executablePath = process.env.STAGE6_CHROMIUM_EXECUTABLE || chromium.executablePath();
if (!existsSync(executablePath)) {
  console.error('BROWSER INCOMPLETE: preinstalled Playwright Chromium is required; no download is performed.');
  process.exit(2);
}

const directory = dirname(fileURLToPath(import.meta.url));
const credentials = {
  username: `local-${randomBytes(12).toString('hex')}`,
  password: randomBytes(32).toString('hex'),
};
const serverSocket = net.createServer();
await new Promise((resolve, reject) => serverSocket.listen(0, '127.0.0.1', resolve).on('error', reject));
const port = serverSocket.address().port;
await new Promise(resolve => serverSocket.close(resolve));
const origin = `http://127.0.0.1:${port}`;
const python = process.env.STAGE6_TEST_PYTHON || 'python';
const server = spawn(python, ['-B', join(directory, 'local_browser_server.py')], {
  cwd: dirname(directory),
  env: {
    ...process.env,
    PYTHONDONTWRITEBYTECODE: '1',
    STAGE6_TEST_USERNAME: credentials.username,
    STAGE6_TEST_PASSWORD: credentials.password,
    STAGE6_TEST_PORT: String(port),
  },
  stdio: ['ignore', 'pipe', 'pipe'],
});
let serverErrors = '';
server.stderr.on('data', chunk => { serverErrors += chunk.toString(); });
const browserDiagnostics = {
  consoleErrors: [], pageErrors: [], failedRequests: [], failedResponses: [],
  blockedExternalRequests: [], apiRequests: [],
};
let browser;

async function waitForServer() {
  for (let attempt = 0; attempt < 80; attempt += 1) {
    if (server.exitCode !== null) throw new Error(`Test server stopped: ${serverErrors.slice(-1500)}`);
    try {
      const response = await fetch(`${origin}/`);
      if (response.ok) return;
    } catch { /* A loopback server can take a moment to start. */ }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Test server did not start: ${serverErrors.slice(-1500)}`);
}

async function localRoute(route) {
  const url = new URL(route.request().url());
  if (url.origin !== origin) {
    browserDiagnostics.blockedExternalRequests.push(url.origin);
    await route.abort('blockedbyclient');
  } else {
    await route.continue();
  }
}

try {
  await waitForServer();
  browser = await chromium.launch({ headless: true, executablePath });

  const anonymous = await browser.newContext();
  await anonymous.route('**/*', localRoute);
  const challengePage = await anonymous.newPage();
  // Chromium can surface a refused Basic Auth navigation as a network error.
  // Verify the HTTP challenge separately and accept only that exact error.
  async function expectAuthChallenge(page) {
    try {
      const response = await page.goto(`${origin}/app`);
      assert.equal(response.status(), 401);
    } catch (error) {
      assert.match(error.message, /net::ERR_INVALID_AUTH_CREDENTIALS/);
    }
  }
  const challenge = await anonymous.request.get(`${origin}/app`);
  assert.equal(challenge.status(), 401);
  assert.match(challenge.headers()['www-authenticate'] || '', /Basic/i);
  await expectAuthChallenge(challengePage);
  assert.equal((await anonymous.request.get(`${origin}/api/dashboard`)).status(), 401);

  const wrong = await browser.newContext({ httpCredentials: {
    username: credentials.username, password: `${credentials.password}-incorrect`,
  } });
  await wrong.route('**/*', localRoute);
  assert.equal((await wrong.request.get(`${origin}/app`)).status(), 401);
  await expectAuthChallenge(await wrong.newPage());

  const context = await browser.newContext({
    httpCredentials: credentials,
    acceptDownloads: true,
  });
  await context.route('**/*', localRoute);
  const page = await context.newPage();
  page.on('dialog', dialog => dialog.accept()); // Only synthetic delete confirmations.
  page.on('pageerror', error => browserDiagnostics.pageErrors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') browserDiagnostics.consoleErrors.push(message.text());
  });
  page.on('requestfailed', request => browserDiagnostics.failedRequests.push({
    url: request.url(), failure: request.failure()?.errorText || '',
  }));
  page.on('request', request => {
    if (request.url().startsWith(`${origin}/api/`)) {
      browserDiagnostics.apiRequests.push(`${request.method()} ${new URL(request.url()).pathname}`);
    }
  });
  page.on('response', response => {
    if (response.status() >= 400) {
      browserDiagnostics.failedResponses.push(`${response.status()} ${new URL(response.url()).pathname}`);
    }
  });

  assert.equal((await page.goto(`${origin}/app`)).status(), 200);
  await page.locator('#dashboardGrid .dashboard-item').first().waitFor();
  assert.equal(await page.locator('#dashboardTab.active').count(), 1);
  assert.equal((await context.request.get(`${origin}/api/dashboard`)).status(), 200);
  assert.ok(browserDiagnostics.apiRequests.includes('GET /api/dashboard'));

  // Use the actual form and JavaScript for quote creation, editing and conversion.
  await page.getByRole('button', { name: 'Quotes', exact: true }).click();
  await page.locator('#customer_name').fill('Synthetic Browser Customer');
  await page.locator('#customer_address').fill('1 Test Lane');
  await page.locator('#customer_phone').fill('07000000000');
  await page.locator('#job').fill('Replace synthetic valve');
  await page.locator('#labour').fill('100.10');
  await page.getByRole('button', { name: '+ Blank Material Row' }).click();
  await page.locator('.material-row .m-name').last().fill('Synthetic valve');
  await page.locator('.material-row .m-qty').last().fill('2');
  await page.locator('.material-row .m-manual').last().fill('10');
  // Exercise the comparison with synthetic public prices; no merchant request
  // leaves the browser or the disposable server.
  const comparisonRow = page.locator('.material-row').last();
  await comparisonRow.locator('.m-url').fill('https://www.cityplumbing.co.uk/p/synthetic-valve/p/123456');
  await comparisonRow.getByLabel('Other merchant product URL', {exact:false}).fill('https://www.toolstation.com/synthetic-valve/p12345');
  await page.route('**/api/best-trade-prices?**', route => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({
      note: 'Public prices; delivery not included.', merchants: [], results: [{
        name: 'Synthetic valve', supplier: 'Toolstation',
        url: 'https://www.toolstation.com/synthetic-valve/p12345',
        price_provenance: 'public_live', price: 8, price_inc_vat: 9.6,
        vat_basis: 'ex_vat', pack_quantity: 1, availability: 'in_stock',
        is_best_price: true, comparison_group: 1,
        comparison_reason: 'Same manufacturer product and pack',
      }, {name: 'Synthetic valve', supplier: 'Screwfix', price: 1,
        price_provenance: 'manual', vat_basis: 'unknown', is_best_price: false}],
    }),
  }));
  await comparisonRow.getByRole('button', { name: /Best Trade Price/ }).click();
  assert.ok(browserDiagnostics.apiRequests.includes('GET /api/best-trade-prices'));
  await comparisonRow.getByText(/BEST PRICE/).waitFor();
  assert.equal(await comparisonRow.locator('.m-manual').inputValue(), '10');
  assert.equal(await comparisonRow.locator('.m-qty').inputValue(), '2');
  assert.equal(await page.locator('#materials_handling_percent').inputValue(), '25');
  assert.equal(await comparisonRow.getByRole('button', { name: 'Use this product and price' }).count(), 1);
  await comparisonRow.getByRole('button', { name: 'Use this product and price' }).click();
  assert.equal(await comparisonRow.locator('.m-manual').inputValue(), '9.60');
  assert.equal(await comparisonRow.locator('.m-supplier').inputValue(), 'Toolstation');
  assert.equal((await page.evaluate(() => collectFormPayload())).materials.at(-1).selected_comparison_price, 9.6);
  await comparisonRow.getByRole('button', {name:'Update price', exact:true}).click();
  await comparisonRow.getByRole('button', {name:'Use this product and price'}).click();
  assert.equal((await page.evaluate(() => collectFormPayload())).materials.at(-1).selected_comparison_price, 9.6);
  assert.equal(await comparisonRow.locator('.m-qty').inputValue(), '2');
  assert.equal(await page.locator('#materials_handling_percent').inputValue(), '25');
  // Restore the original synthetic material before the existing quote checks.
  await comparisonRow.locator('.m-url').fill('');
  await comparisonRow.locator('.m-manual').fill('10');
  await comparisonRow.locator('.m-supplier').selectOption('');
  await page.unroute('**/api/best-trade-prices?**');
  const createdRequest = page.waitForResponse(response => response.url() === `${origin}/api/quote`
    && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Generate Quote' }).click();
  const created = await createdRequest;
  assert.equal(created.status(), 200);
  const quote = await created.json();
  assert.ok(browserDiagnostics.apiRequests.includes('POST /api/quote'));
  assert.equal(quote.result.total_price, 125.10);
  await page.locator('#historyList').getByText('Synthetic Browser Customer').waitFor();
  assert.match(await page.locator('#whatsappBtn').getAttribute('href'), /^https:\/\/wa\.me\//);

  await page.locator('#historyList .history-item').filter({ hasText: 'Synthetic Browser Customer' })
    .getByRole('button', { name: 'Edit', exact: true }).click();
  await page.locator('#labour').fill('120.20');
  const editRequest = page.waitForResponse(response => response.url() === `${origin}/api/quotes/${quote.id}`
    && response.request().method() === 'PUT');
  await page.getByRole('button', { name: /Update Quote|Generate Quote/ }).click();
  assert.equal((await editRequest).status(), 200);

  await page.getByRole('button', { name: 'Customers', exact: true }).click();
  await page.locator('#customerSearch').fill('Synthetic Browser Customer');
  const customer = page.locator('#customerList .history-item').filter({ hasText: 'Synthetic Browser Customer' });
  await customer.waitFor();
  await customer.getByRole('button', { name: 'View History' }).click();
  await customer.getByText('Replace synthetic valve').first().waitFor();

  await page.getByRole('button', { name: 'Quotes', exact: true }).click();
  const conversionRequest = page.waitForResponse(response => response.url() === `${origin}/api/quotes/${quote.id}/to-invoice`);
  await page.locator('#historyList .history-item').filter({ hasText: 'Synthetic Browser Customer' })
    .getByRole('button', { name: 'To Invoice' }).click();
  const conversion = await conversionRequest;
  assert.equal(conversion.status(), 200);
  const invoice = await conversion.json();
  await page.locator('#invoiceList').getByText(invoice.invoice_number).waitFor();
  await page.locator('#invoiceList .history-item').filter({ hasText: invoice.invoice_number })
    .getByRole('button', { name: 'Edit Invoice / Job Ref' }).click();
  await page.locator('#edit_invoice_job_reference').fill('LOCAL-BROWSER-1');
  const invoiceEdit = page.waitForResponse(response => response.url() === `${origin}/api/invoices/${invoice.id}`
    && response.request().method() === 'PUT');
  await page.getByRole('button', { name: 'Save Invoice Changes' }).click();
  assert.equal((await invoiceEdit).status(), 200);
  const invoiceRow = page.locator('#invoiceList .history-item').filter({ hasText: invoice.invoice_number });
  await invoiceRow.getByRole('button', { name: 'Mark Paid' }).click();
  await page.locator('#invoiceList').getByText('Paid', { exact: true }).first().waitFor();

  // A synthetic image goes through the browser file input and normal upload UI.
  await invoiceRow.getByRole('button', { name: 'Preview Invoice', exact: true }).click();
  const paymentDisplay = await page.locator('#i_payment_link_box').innerText();
  assert.ok(paymentDisplay.includes('Test Bank'));
  assert.ok(paymentDisplay.includes('Synthetic Test Account'));
  assert.deepEqual(await page.evaluate(() => ({
    bank: window.CURRENT_INVOICE_PAYMENT_DETAILS.bank,
    accountName: window.CURRENT_INVOICE_PAYMENT_DETAILS.accountName,
    sortCode: window.CURRENT_INVOICE_PAYMENT_DETAILS.sortCode,
    accountNumber: window.CURRENT_INVOICE_PAYMENT_DETAILS.accountNumber,
  })), {
    bank: 'Test Bank', accountName: 'Synthetic Test Account',
    sortCode: '00-00-00', accountNumber: '00000000',
  });
  await page.locator('#invoicePhotoFiles').setInputFiles({
    name: 'synthetic.png', mimeType: 'image/png',
    buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO2X6a8AAAAASUVORK5CYII=', 'base64'),
  });
  await page.getByRole('button', { name: 'Add Photos to Invoice' }).click();
  await page.locator('#invoicePhotoGallery img').first().waitFor();
  const invoicePdf = await context.request.get(`${origin}/api/invoices/${invoice.id}/pdf`);
  assert.equal(invoicePdf.status(), 200);
  assert.equal(invoicePdf.headers()['content-disposition'], `attachment; filename="${invoice.invoice_number}.pdf"`);
  assert.equal((await invoicePdf.body()).subarray(0, 4).toString(), '%PDF');
  assert.equal((await anonymous.request.get(`${origin}/api/invoices/${invoice.id}/pdf`)).status(), 200);
  assert.equal((await anonymous.request.get(`${origin}/api/quotes/${quote.id}/pdf`)).status(), 200);
  assert.equal((await anonymous.request.get(`${origin}/invoice/${invoice.id}`)).status(), 200);
  const whatsappHref = await page.locator('#invoiceWhatsappBtn').getAttribute('href');
  assert.match(whatsappHref, /^https:\/\/wa\.me\//);
  assert.ok(decodeURIComponent(whatsappHref).includes(`${origin}/invoice/${invoice.id}`));
  // Never click a WhatsApp link or send email.
  await page.locator('#invoicePhotoGallery button').first().click();
  await page.locator('#invoicePhotoGallery img').first().waitFor({ state: 'detached' });

  const lead = await anonymous.request.post(`${origin}/api/leads`, {
    data: { name: 'Synthetic Lead', description: 'Test tap' },
  });
  assert.equal(lead.status(), 200);
  await page.getByRole('button', { name: 'Leads', exact: true }).click();
  await page.locator('#leadList').getByText('Synthetic Lead').waitFor();
  await page.getByRole('button', { name: 'Material Database' }).click();
  await page.locator('#materialDbSearch').fill('Synthetic valve');
  await page.locator('#materialDbList').getByText('Synthetic valve').waitFor();

  for (const path of ['/', '/plumber-guildford', '/request-quote', '/robots.txt', '/sitemap.xml']) {
    assert.equal((await anonymous.request.get(`${origin}${path}`)).status(), 200);
  }
  assert.equal((await anonymous.request.get(`${origin}/api/quotes`)).status(), 401);
  assert.equal((await anonymous.request.get(`${origin}/api/invoices`)).status(), 401);
  assert.equal((await anonymous.request.get(`${origin}/api/material-prices`)).status(), 401);

  // City captures: actual mobile preview/save/select/create/reopen/edit UI.
  // Product identity is real; prices are deliberately sanitized.
  await page.getByRole('button', { name: 'Quotes', exact: true }).click();
  await page.getByRole('button', { name: 'Start Fresh Quote', exact: true }).click();
  await page.setViewportSize({width:390,height:844});
  await page.locator('#customer_name').fill('Synthetic City Capture Customer');
  await page.locator('#job').fill('Synthetic account-price persistence check');
  await page.locator('#labour').fill('0');
  await page.locator('#include_callout_charge').uncheck();
  await page.locator('#include_travel_charge').uncheck();
  await page.getByRole('button', { name: '+ Blank Material Row' }).click();
  let cityRow = page.locator('.material-row').last();
  const productName = 'Wednesbury Plain Copper Tube 15mm × 3m X015L-3';
  await cityRow.locator('.m-name').fill(productName);
  await cityRow.locator('.m-qty').fill('2');
  await cityRow.locator('.m-supplier').selectOption('Selco');
  await cityRow.locator('.m-manual').fill('20');
  await cityRow.getByRole('button', {name:'City account prices — add / update / choose'}).click();
  await cityRow.getByText('Add or update a checked City price', {exact:true}).click();
  await cityRow.locator('.city-code').fill('313813');
  await cityRow.locator('.city-name').fill(productName);
  await cityRow.locator('.city-price').fill('6.00');
  await cityRow.getByText('Optional manufacturer identifiers shown by City', {exact:true}).click();
  await cityRow.locator('.city-brand').fill('Wednesbury');
  await cityRow.locator('.city-mpn').fill('X015L-3');
  await cityRow.getByRole('button', {name:'Preview checked price',exact:true}).click();
  await cityRow.locator('.city-preview').getByText(/nothing saved yet/).waitFor();
  assert.equal((await (await context.request.get(origin + '/api/city-account-prices')).json()).results.length,0);
  assert.equal(await cityRow.locator('.m-supplier').inputValue(),'Selco');
  assert.equal(await cityRow.locator('.m-manual').inputValue(),'20');
  await cityRow.getByRole('button', {name:'Save confirmed owner capture',exact:true}).click();
  await cityRow.locator('.city-saved-results .city-account-card').waitFor();
  let savedCapture = (await (await context.request.get(origin + '/api/city-account-prices')).json()).results[0];
  assert.equal(savedCapture.price,'6.00');
  assert.equal(savedCapture.price_inc_vat,'7.20');
  assert.equal(savedCapture.availability,'unknown');
  assert.equal(savedCapture.is_best_price,false);
  assert.match(await cityRow.locator('.city-saved-results').innerText(),/£6.00 ex VAT · £7.20 inc VAT/);
  assert.ok(!(await cityRow.locator('.city-saved-results').innerText()).includes('BEST PRICE'));
  await cityRow.getByRole('button', {name:'Preview checked price',exact:true}).click();
  await cityRow.getByRole('button', {name:'Save confirmed owner capture',exact:true}).click();
  await cityRow.locator('.city-preview').getByText(/Identical capture already saved; age unchanged/).waitFor();

  // Public network prices are isolated fixtures; the saved account card was
  // obtained through the real authenticated capture endpoint above.
  const publicOffers = ['City Plumbing','Toolstation','Selco'].map((supplier,index) => ({
    name:productName,supplier,sku:supplier==='City Plumbing'?'313813':'synthetic-sku',
    brand:'Wednesbury',mpn:'X015L-3',pack_quantity:1,
    price:9+index,price_inc_vat:10.8+index*1.2,vat_basis:'ex_vat',
    availability:'in_stock',price_provenance:'public_live',
    url:supplier==='City Plumbing'?'https://www.cityplumbing.co.uk/p/tube/p/313813':
      supplier==='Toolstation'?'https://www.toolstation.com/tube/p12345':'https://www.selcobw.com/tube',
    is_best_price:index===0,comparison_group:1,checked_at:new Date().toISOString()
  }));
  const comparedCapture = {...savedCapture,cheapest_observed:true,
    public_comparisons:publicOffers.map(p => ({supplier:p.supplier,price_inc_vat:p.price_inc_vat,
      saving_using_account:(p.price_inc_vat-7.2).toFixed(2)}))};
  await page.route('**/api/best-trade-prices?**', route => route.fulfill({
    status:200,contentType:'application/json',body:JSON.stringify({
      results:publicOffers,account_results:[comparedCapture],
      merchants:[{supplier:'Screwfix',status:'unavailable'}],note:'Synthetic offline public comparison'
    })
  }));
  await cityRow.getByRole('button', {name:/Best Trade Price/}).click();
  const accountCard=cityRow.locator('.trade-price-results .city-account-card');
  await accountCard.waitFor();
  assert.match(await accountCard.innerText(),/CHEAPEST OBSERVED — CACHED ACCOUNT PRICE/);
  assert.match(await accountCard.innerText(),/£3.60 less/);
  assert.ok(!(await accountCard.innerText()).includes('BEST PRICE'));
  assert.equal(await cityRow.locator('.m-supplier').inputValue(),'Selco');
  await accountCard.getByRole('button',{name:'Use cached City account price'}).click();
  assert.equal(await cityRow.locator('.m-manual').inputValue(),'20');
  await accountCard.locator('.city-cached-confirm').check();
  await accountCard.getByRole('button',{name:'Use cached City account price'}).click();
  assert.equal(await cityRow.locator('.m-supplier').inputValue(),'City Plumbing');
  assert.equal(await cityRow.locator('.m-manual').inputValue(),'7.20');
  assert.equal(await cityRow.locator('.m-url').inputValue(),'');
  assert.equal(await cityRow.locator('.m-qty').inputValue(),'2');
  assert.equal(await page.locator('#materials_handling_percent').inputValue(),'25');
  let selectedPayload=await page.evaluate(() => collectFormPayload());
  assert.equal(selectedPayload.materials.at(-1).selected_account_price.source_type,'account_cached');
  assert.equal(selectedPayload.materials.at(-1).selected_comparison_price,undefined);
  await page.unroute('**/api/best-trade-prices?**');
  const cityCreate=page.waitForResponse(r=>r.url()===origin+'/api/quote' && r.request().method()==='POST');
  await page.getByRole('button',{name:'Generate Quote',exact:true}).click();
  const cityCreateResponse=await cityCreate;
  assert.equal(cityCreateResponse.status(),200);
  const cityQuote=await cityCreateResponse.json();
  assert.equal(cityQuote.result.total_price,18);
  assert.equal(cityQuote.result.internal_handling_percent,25);
  assert.equal(cityQuote.result.material_lines.at(-1).full_unit_price,7.2);
  assert.equal(cityQuote.result.material_lines.at(-1).price_source,'account_cached');
  await page.locator('#historyList .history-item').filter({hasText:'Synthetic City Capture Customer'})
    .getByRole('button',{name:'Edit',exact:true}).click();
  cityRow=page.locator('.material-row').last();
  await cityRow.locator('.material-live-status').getByText(/City Plumbing account price — cached/).waitFor();
  assert.equal(Number(await cityRow.locator('.m-manual').inputValue()),7.2);
  assert.equal(await cityRow.locator('.m-qty').inputValue(),'2');
  assert.equal(await page.locator('#materials_handling_percent').inputValue(),'25');
  const lookupsBefore=browserDiagnostics.apiRequests.filter(r=>r.includes('/api/live-product-refresh')).length;
  await cityRow.getByRole('button',{name:'Update price',exact:true}).click();
  assert.equal(Number(await cityRow.locator('.m-manual').inputValue()),7.2);
  assert.equal(browserDiagnostics.apiRequests.filter(r=>r.includes('/api/live-product-refresh')).length,lookupsBefore);
  await cityRow.getByRole('button',{name:'Update City 313813',exact:true}).click();
  await cityRow.locator('.city-price').fill('9.00');
  await cityRow.getByRole('button',{name:'Preview checked price',exact:true}).click();
  await cityRow.getByRole('button',{name:'Save confirmed owner capture',exact:true}).click();
  await cityRow.locator('.city-preview').getByText(/Owner capture saved/).waitFor();
  assert.equal(Number(await cityRow.locator('.m-manual').inputValue()),7.2);
  await cityRow.locator('.m-qty').fill('3');
  const cityEdit=page.waitForResponse(r=>r.url()===origin+'/api/quotes/'+cityQuote.id && r.request().method()==='PUT');
  await page.getByRole('button',{name:/Update Quote|Generate Quote/}).click();
  const editedCity=await cityEdit;
  assert.equal(editedCity.status(),200);
  const editedResult=await editedCity.json();
  assert.equal(editedResult.result.total_price,27);
  assert.equal(editedResult.result.material_lines.at(-1).full_unit_price,7.2);
  assert.equal(editedResult.request.materials.at(-1).selected_account_price.price,'6.00');
  assert.equal(editedResult.request.materials.at(-1).quantity,3);
  assert.equal(editedResult.request.materials_handling_percent,25);
  // Reference-only stale captures are rendered but cannot be selected.
  const staleDate=new Date(Date.now()-8*86400000).toISOString().slice(0,10);
  assert.equal((await context.request.post(origin+'/api/city-account-prices',{data:{records:[{
    city_code:'119745',product_name:'Wednesbury Plain Copper Tube 22mm × 3m X022L-3',
    brand:'Wednesbury',mpn:'X022L-3',ex_vat_price:'6.00',selling_unit:'each',
    pack_quantity:1,checked_at:staleDate
  }]}})).status(),200);
  await cityRow.getByRole('button',{name:'City account prices — add / update / choose'}).click();
  const staleCard=cityRow.locator('.city-saved-results .city-account-card').filter({hasText:'119745'});
  await staleCard.waitFor();
  assert.match(await staleCard.innerText(),/STALE/);
  assert.equal(await staleCard.getByRole('button',{name:'Use cached City account price'}).count(),0);
  await page.setViewportSize({width:1280,height:900});

  // Delete the saved quote through its visible UI and verify the private API.
  await page.getByRole('button', { name: 'Quotes', exact: true }).click();
  await page.locator('#historyList .history-item').filter({ hasText: 'Synthetic Browser Customer' })
    .getByRole('button', { name: 'Delete', exact: true }).click();
  await page.locator('#historyList').getByText('Synthetic Browser Customer').waitFor({ state: 'detached' });
  assert.equal((await context.request.get(`${origin}/api/quotes/${quote.id}`)).status(), 404);

  assert.deepEqual(browserDiagnostics.pageErrors, [], 'Fatal browser JavaScript error');
  console.log(JSON.stringify({ result: 'PASS', diagnostics: browserDiagnostics }, null, 2));
} catch (error) {
  console.error(JSON.stringify({ result: 'FAIL', error: error.message,
    diagnostics: browserDiagnostics, serverErrors: serverErrors.slice(-1500) }, null, 2));
  process.exitCode = 1;
} finally {
  if (browser) await browser.close();
  server.kill('SIGTERM');
}

const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../static/app.js'), 'utf8');
const code = source.slice(source.indexOf('function tradePriceLabel('), source.indexOf('function renderMaterialSearchResults('));
const fields = {'.m-name':{value:'Acme Valve V15'}, '.m-url':{value:''}, '.m-manual':{value:'50'},
  '.m-supplier':{value:'City Plumbing'}, '.m-qty':{value:'3'}, '.trade-price-results':{textContent:'',innerHTML:''}};
const row = {dataset:{}, querySelector: selector => fields[selector]};
const button = {disabled:false, closest: () => row};
const live = {name:'Acme Valve V15',supplier:'Toolstation',url:'https://www.toolstation.com/valve/p12345',
  price_provenance:'public_live', price_inc_vat:12, price:10, vat_basis:'ex_vat', pack_quantity:1,
  availability:'in_stock', checked_at:'2026-10-05T15:00:00+00:00',is_best_price:true,comparison_group:1};
let response = {note:'Public prices, confirm before ordering.', results:[live,
  {...live,name:'Manual <script>alert(1)</script>',price_provenance:'manual',price_inc_vat:null,is_best_price:false}],merchants:[]};
let resolveFetch;
const notices = [];
const handling = {value:'25'};
const context = {URL, URLSearchParams, fetch:async () => ({ok:true,json:async () => response}),
  pounds:x => '£' + Number(x).toFixed(2), escapeHtml:x => String(x).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;'),
  showNotice:x => notices.push(x),updateMaterialLiveBadge:() => {},handling};
vm.createContext(context);
vm.runInContext(code, context);
(async () => {
  await context.compareMaterialTradePrices(button);
  assert.equal(fields['.m-manual'].value, '50');
  assert.equal(fields['.m-supplier'].value, 'City Plumbing');
  assert.equal(fields['.m-qty'].value, '3');
  assert.equal(handling.value, '25');
  assert.match(fields['.trade-price-results'].innerHTML, /BEST PRICE/);
  assert.match(fields['.trade-price-results'].innerHTML, /Live public price/);
  assert.match(fields['.trade-price-results'].innerHTML, /Manual price/);
  assert.ok(!fields['.trade-price-results'].innerHTML.includes('<script>'));
  assert.equal((fields['.trade-price-results'].innerHTML.match(/Use this product and price/g) || []).length, 1);
  context.useComparedTradePrice(button, 1);
  assert.equal(fields['.m-manual'].value, '50');
  context.useComparedTradePrice(button, 0);
  assert.equal(fields['.m-manual'].value, '12.00');
  assert.equal(fields['.m-supplier'].value, 'Toolstation');
  assert.equal(fields['.m-qty'].value, '3');
  assert.equal(handling.value, '25');
  assert.equal(context.safeTradeProductUrl('javascript:alert(1)'), '');
  assert.equal(context.safeTradeProductUrl('https://u:p@example.com/'), '');
  fields['.m-name'].value = 'Acme Valve V15';
  fields['.m-url'].value = '';
  context.fetch = () => new Promise(resolve => {resolveFetch = resolve;});
  const pending = context.compareMaterialTradePrices(button);
  fields['.m-name'].value = 'Different valve';
  resolveFetch({ok:true,json:async () => response});
  await pending;
  assert.match(fields['.trade-price-results'].textContent, /Material changed/);
  assert.equal(button.disabled, false);
  context.useComparedTradePrice(button, 0);
  assert.equal(fields['.m-name'].value, 'Different valve');
  context.fetch = async () => ({ok:false,json:async () => ({detail:'Authentication required'})});
  await context.compareMaterialTradePrices(button);
  assert.equal(fields['.trade-price-results'].textContent, 'Authentication required');
  assert.equal(button.disabled, false);
  console.log('Trade comparison UI: PASS');
})().catch(error => {console.error(error);process.exitCode=1;});

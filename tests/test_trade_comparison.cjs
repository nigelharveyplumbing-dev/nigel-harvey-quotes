const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../static/app.js'), 'utf8');
const code = source.slice(source.indexOf('function tradePriceLabel('), source.indexOf('function renderMaterialSearchResults('));
const fields = {'.m-name':{value:'Acme Valve V15'}, '.m-url':{value:''}, '.m-manual':{value:'50'},
  '.m-compare-url':{value:''},
  '.m-supplier':{value:'City Plumbing'}, '.m-qty':{value:'3'}, '.trade-price-results':{textContent:'',innerHTML:''}};
const row = {dataset:{}, querySelector: selector => fields[selector]};
const button = {disabled:false, closest: () => row};
const live = {name:'Acme Valve V15',supplier:'Toolstation',url:'https://www.toolstation.com/valve/p12345',
  price_provenance:'public_live', price_inc_vat:12, price:10, vat_basis:'ex_vat', pack_quantity:1,
  availability:'in_stock', checked_at:'2026-10-05T15:00:00+00:00',is_best_price:true,comparison_group:1};
let response = {note:'Public prices, confirm before ordering.', results:[live,
  {...live,name:'Manual <script>alert(1)</script>',price_provenance:'manual',price_inc_vat:null,is_best_price:false}],merchants:[]};
let resolveFetch;
let lastRequest;
const notices = [];
const handling = {value:'25'};
const context = {URL, URLSearchParams, fetch:async url => {lastRequest=url; return {ok:true,json:async () => response};},
  pounds:x => '£' + Number(x).toFixed(2), escapeHtml:x => String(x).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;'),
  showNotice:x => notices.push(x),updateMaterialLiveBadge:() => {},handling};
vm.createContext(context);
vm.runInContext(fs.readFileSync(require('node:path').join(__dirname, '../static/city_account_prices.js'), 'utf8'), context);
vm.runInContext(code, context);
(async () => {
  fields['.m-url'].value = 'https://www.cityplumbing.co.uk/p/valve/p/123456';
  fields['.m-compare-url'].value = live.url;
  await context.compareMaterialTradePrices(button);
  assert.equal(new URL(lastRequest, 'https://app.example').searchParams.get('compare_url'), live.url);
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
  assert.equal(context.selectedComparisonPrice(row), 12);
  fields['.m-qty'].value = '7';
  assert.equal(context.selectedComparisonPrice(row), 12);
  fields['.m-manual'].value = '13';
  assert.equal(context.selectedComparisonPrice(row), null);
  fields['.m-manual'].value = '12';
  fields['.m-url'].value = 'https://www.toolstation.com/other/p12346';
  assert.equal(context.selectedComparisonPrice(row), null);
  assert.equal(context.safeTradeProductUrl('https://u:p@example.com/'), '');
  fields['.m-name'].value = 'Acme Valve V15';
  fields['.m-url'].value = '';
  fields['.m-compare-url'].value = '';
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
  // Cached account selection is a separate, explicit source. Sanitized price.
  const cached = {name:'Wednesbury Plain Copper Tube 15mm × 3m X015L-3',supplier_sku:'313813',
    price:'6.00',price_inc_vat:'7.20',pack_quantity:1,selling_unit:'each',
    source_type:'account_cached',freshness:'current',checked_at:new Date().toISOString(),
    checked_precision:'time',selectable:true,cheapest_observed:true,stock_note:'<script>note</script>'};
  cached.selection = {...cached};
  let acknowledged = false;
  const cachedButton = {closest:selector => selector === '.material-row' ? row :
    {querySelector:() => ({checked:acknowledged})}};
  const cards = context.cityAccountCards([cached], 'chooseSavedCityAccountPrice');
  assert.match(cards,/City Plumbing account price — cached/);
  assert.match(cards,/CHEAPEST OBSERVED — CACHED ACCOUNT PRICE/);
  assert.ok(!cards.includes('BEST PRICE') && !cards.includes('<script>'));
  fields['.m-qty'].value = '3';
  context.selectCityAccountPrice(row,cached,cachedButton);
  assert.equal(context.selectedAccountPrice(row),null);
  acknowledged = true;
  context.selectCityAccountPrice(row,cached,cachedButton);
  assert.equal(fields['.m-supplier'].value,'City Plumbing');
  assert.equal(fields['.m-manual'].value,'7.20');
  assert.equal(fields['.m-url'].value,'');
  assert.equal(fields['.m-qty'].value,'3');
  assert.equal(handling.value,'25');
  assert.equal(context.selectedAccountPrice(row).supplier_sku,'313813');
  assert.equal(context.selectedComparisonPrice(row),null);
  fields['.m-qty'].value='9';
  assert.equal(context.selectedAccountPrice(row).price_inc_vat,'7.20');
  fields['.m-supplier'].value='Selco';
  assert.equal(context.selectedAccountPrice(row),null);
  fields['.m-supplier'].value='City Plumbing';
  fields['.m-url'].value='https://www.cityplumbing.co.uk/p/other/p/119745';
  assert.equal(context.selectedAccountPrice(row),null);
  fields['.m-url'].value='';
  const stale={...cached,checked_at:new Date(Date.now()-8*86400000).toISOString(),freshness:'stale',selectable:false};
  assert.match(context.cityAccountCards([stale],'chooseSavedCityAccountPrice'),/STALE/);
  assert.ok(!context.cityAccountCards([stale],'chooseSavedCityAccountPrice').includes('Use cached City account price'));
  row.selectedCityAccount=null;
  context.selectCityAccountPrice(row,stale,cachedButton);
  assert.equal(context.selectedAccountPrice(row),null);
  // A card opened before expiry cannot be selected after seven days elapse.
  context.selectCityAccountPrice(row,{...stale,freshness:'current',selectable:true},cachedButton);
  assert.equal(context.selectedAccountPrice(row),null);
  console.log('Trade comparison UI: PASS');
})().catch(error => {console.error(error);process.exitCode=1;});

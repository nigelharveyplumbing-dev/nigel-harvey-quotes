// City owner captures: private app storage only; no City credentials or requests.
function selectedAccountPrice(row) {
  const held = row.selectedCityAccount;
  if (!held || held.name !== row.querySelector('.m-name').value ||
      !['City Plumbing','PTS'].includes(row.querySelector('.m-supplier').value) ||
      held.selectedSupplier !== row.querySelector('.m-supplier').value ||
      held.selectedUrl !== row.querySelector('.m-url').value ||
      Number(held.snapshot.price_inc_vat) !== Number(row.querySelector('.m-manual').value)) return null;
  return held.snapshot;
}

function rememberAccountPrice(row, snapshot) {
  row.selectedTradePrice = null;
  row.selectedCityAccount = {name:row.querySelector('.m-name').value,
    selectedSupplier:row.querySelector('.m-supplier').value,
    selectedUrl:row.querySelector('.m-url').value, snapshot:JSON.parse(JSON.stringify(snapshot))};
}

function cityCaptureCurrent(item) {
  const age = Date.now() - new Date(item.checked_at).getTime();
  return Number.isFinite(age) && age >= 0 && age < 7 * 86400000 && item.freshness !== 'stale';
}

function cityCaptureAge(item) {
  const date = new Date(item.checked_at);
  const stale = item.freshness === 'stale' || Date.now() - date.getTime() >= 7 * 86400000;
  const label = item.checked_precision === 'date'
    ? date.toLocaleDateString('en-GB', {timeZone:'Europe/London'}) + ' (date only)'
    : date.toLocaleString('en-GB', {timeZone:'Europe/London'});
  return `${label} · ${Math.max(0, Math.floor((Date.now()-date.getTime())/86400000))} day(s) old${stale ? ' · STALE — refresh or reconfirm with City' : ''}`;
}

function cityAccountCards(items, action) {
  return items.map((item, index) => `<div class="city-account-card" style="margin-top:8px;padding:12px;border:1px solid #d97706;border-radius:8px;">
    <strong>City Plumbing account price — cached</strong><br>
    <strong>${escapeHtml(item.name)}</strong><br>
    <span class="small">City code ${escapeHtml(item.supplier_sku)} · ${escapeHtml(item.selling_unit)} · pack ${Number(item.pack_quantity)}<br>
    ${pounds(item.price)} ex VAT · ${pounds(item.price_inc_vat)} inc VAT (20%)<br>
    Owner-captured in City app · ${escapeHtml(cityCaptureAge(item))}<br>
    ${item.imported_at ? 'Saved to this app: ' + escapeHtml(new Date(item.imported_at).toLocaleString('en-GB', {timeZone:'Europe/London'})) + '<br>' : ''}
    Current stock unconfirmed${item.stock_note ? ' · capture note: ' + escapeHtml(item.stock_note) : ''}
    ${item.mpn ? '<br>MPN/model ' + escapeHtml(item.mpn) : '<br>MPN/GTIN not supplied — cross-merchant identity may be unconfirmed'}
    ${item.cheapest_observed ? '<br><strong>CHEAPEST OBSERVED — CACHED ACCOUNT PRICE (not live)</strong>' : ''}
    ${(item.public_comparisons || []).map(p => '<br>Exact ' + escapeHtml(p.supplier) + ' public product: ' + pounds(p.price_inc_vat) + ' inc VAT · ' + (Number(p.saving_using_account) >= 0 ? pounds(p.saving_using_account) + ' less using cached account price' : pounds(-Number(p.saving_using_account)) + ' more using cached account price')).join('')}
    </span>
    ${item.selectable && cityCaptureCurrent(item) && item.source_type === 'account_cached' ? `<label class="check-row"><input class="city-cached-confirm" type="checkbox">I confirm this cached price for the quote; current stock is unconfirmed.</label><button type="button" class="btn-light" onclick="${action}(this, ${index})">Use cached City account price</button>` : '<p class="small">Reference only — refresh the checked price before selecting.</p>'}
  </div>`).join('');
}

function selectCityAccountPrice(row, item, button) {
  if (!item || !item.selectable || !cityCaptureCurrent(item) || item.source_type !== 'account_cached' || item.freshness !== 'current' ||
      !button.closest('.city-account-card').querySelector('.city-cached-confirm')?.checked) {
    showNotice('Confirm the cached price and stock uncertainty before choosing it.'); return;
  }
  // Selection is an explicit action: supplier changes only here, quantity never does.
  row.querySelector('.m-name').value = item.name;
  row.querySelector('.m-supplier').value = 'City Plumbing';
  row.querySelector('.m-url').value = '';
  row.querySelector('.m-manual').value = Number(item.price_inc_vat).toFixed(2);
  rememberAccountPrice(row, item.selection);
  row.dataset.liveProduct = '';
  row.dataset.sku = item.supplier_sku;
  row.dataset.checkedAt = item.checked_at;
  row.tradeComparisonToken = null;
  row.querySelector('.trade-price-results').textContent = 'Selected cached City account price is held for this quote. Quantity is unchanged. Public price lookup will not replace it.';
  updateMaterialLiveBadge(row);
  showNotice('Cached City account price selected; review quantity and calculate the quote.');
}

function useComparedCityAccountPrice(button, index) {
  const row = button.closest('.material-row');
  const input = row.tradeComparisonInput;
  if (!input || row.querySelector('.m-name').value.trim() !== input.query ||
      row.querySelector('.m-url').value.trim() !== input.productUrl ||
      (row.querySelector('.m-compare-url')?.value.trim() || '') !== input.comparisonUrl) {
    showNotice('Material changed. Compare again before choosing a price.'); return;
  }
  selectCityAccountPrice(row, row.cityComparedResults?.[index], button);
}

function chooseSavedCityAccountPrice(button, index) {
  const row = button.closest('.material-row');
  selectCityAccountPrice(row, row.citySavedResults?.[index], button);
}

async function openCityAccountPrices(button) {
  const row = button.closest('.material-row');
  const panel = row.querySelector('.city-account-panel');
  panel.innerHTML = `<details open><summary>City account prices — owner-captured, cached</summary>
    <p class="small">No City login needed here. Recheck prices in your City app, then save them below. Existing quotes keep their selected price.</p>
    <label>Find by City code or product<input class="city-find" type="search" placeholder="City code or product"></label>
    <button type="button" class="btn-light" onclick="loadCityAccountPrices(this)">Find saved account prices</button>
    <details><summary>Add or update a checked City price</summary>
      <label>City product code<input class="city-code" inputmode="numeric" maxlength="6" placeholder="313813"></label>
      <label>Product name<input class="city-name" placeholder="Exact City product description"></label>
      <label>Price (£ ex VAT)<input class="city-price" type="number" inputmode="decimal" step="0.01" min="0.01"></label>
      <label>Selling unit<select class="city-unit"><option value="each">Each</option><option value="pack">Pack</option></select></label>
      <label>Items in selling pack<input class="city-pack" type="number" min="1" step="1" value="1"></label>
      <label>Checked date/time (UK time)<input class="city-checked" type="datetime-local"></label>
      <label>Optional stock note (point-in-time only)<input class="city-stock" maxlength="500"></label>
      <details><summary>Optional manufacturer identifiers shown by City</summary>
        <label>Brand/manufacturer<input class="city-brand"></label>
        <label>MPN/product model<input class="city-mpn"></label>
        <label>GTIN, if shown<input class="city-gtin" inputmode="numeric"></label>
      </details>
      <button type="button" class="btn-light" onclick="previewCityAccountUpdate(this)">Preview checked price</button>
    </details>
    <label>Initial owner-capture JSON file<input class="city-capture-file" type="file" accept="application/json,.json"></label>
    <button type="button" class="btn-light" onclick="previewCityCaptureFile(this)">Preview owner capture file</button>
    <div class="city-preview" aria-live="polite"></div>
    <div class="city-saved-results" aria-live="polite"></div>
  </details>`;
  panel.querySelector('.city-find').value = '';
  const now = new Date();
  const london = new Intl.DateTimeFormat('sv-SE', {timeZone:'Europe/London',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(now);
  panel.querySelector('.city-checked').value = london.replace(' ', 'T');
  await loadCityAccountPrices(button);
}

async function loadCityAccountPrices(button) {
  const row = button.closest('.material-row');
  const panel = row.querySelector('.city-account-panel');
  const box = panel.querySelector('.city-saved-results');
  try {
    const response = await fetch('/api/city-account-prices?q=' + encodeURIComponent(panel.querySelector('.city-find').value.trim()));
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Could not load account prices');
    row.citySavedResults = data.results || [];
    box.innerHTML = cityAccountCards(row.citySavedResults, 'chooseSavedCityAccountPrice') || '<p>No saved captures. Add a checked price or preview the initial owner file.</p>';
    box.innerHTML += row.citySavedResults.map((_, index) => `<button type="button" class="btn-light" onclick="editCityAccountCapture(this, ${index})">Update City ${escapeHtml(row.citySavedResults[index].supplier_sku)}</button>`).join('');
  } catch (error) { box.textContent = error.message; }
}

function editCityAccountCapture(button, index) {
  const row = button.closest('.material-row'), panel = row.querySelector('.city-account-panel'), item = row.citySavedResults?.[index];
  if (!item) return;
  const fields = {code:item.supplier_sku,name:item.name,price:item.price,unit:item.selling_unit,
    pack:item.pack_quantity,brand:item.brand,mpn:item.mpn,gtin:item.gtin,stock:''};
  for (const [field,value] of Object.entries(fields)) panel.querySelector('.city-' + field).value = value || '';
  panel.querySelector('.city-code').closest('details').open = true;
  panel.querySelector('.city-checked').focus();
  showNotice('Recheck in the City app before saving. The new checked time must reflect your actual check.');
}

async function previewCityAccountUpdate(button) {
  const row = button.closest('.material-row'), panel = row.querySelector('.city-account-panel');
  const field = key => panel.querySelector('.city-' + key).value.trim();
  // Explicit owner-local time. Send timezone offset for the selected UK date,
  // including DST; do not reinterpret it in the browser's own timezone.
  const local = field('checked');
  const guess = new Date(local + 'Z');
  if (!local || !Number.isFinite(guess.getTime())) { showNotice('Enter the actual checked date/time.'); return; }
  const parts = new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/London',timeZoneName:'shortOffset'}).formatToParts(guess);
  const offset = parts.find(p=>p.type==='timeZoneName')?.value === 'GMT+1' ? '+01:00' : '+00:00';
  const record = {city_code:field('code'),product_name:field('name'),ex_vat_price:field('price'),
    selling_unit:field('unit'),pack_quantity:Number(field('pack')),checked_at:local + ':00' + offset,
    brand:field('brand'),mpn:field('mpn'),gtin:field('gtin'),stock_note:field('stock')};
  await previewCityPayload(row, {records:[record]});
}

async function previewCityCaptureFile(button) {
  const row = button.closest('.material-row');
  const file = row.querySelector('.city-capture-file').files[0];
  if (!file || file.size > 1024 * 1024) { showNotice('Choose an owner-capture JSON file under 1 MB.'); return; }
  try { await previewCityPayload(row, JSON.parse(await file.text())); }
  catch { showNotice('Invalid capture JSON file. Nothing saved.'); }
}

async function previewCityPayload(row, payload) {
  const box = row.querySelector('.city-preview');
  row.cityPendingCapture = null;
  try {
    const response = await fetch('/api/city-account-prices/preview', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Invalid capture');
    row.cityPendingCapture = payload;
    box.innerHTML = `<p><strong>Preview ${data.results.length} capture(s) — nothing saved yet</strong></p>` +
      data.results.map(item=>`<p>${escapeHtml(item.name)} · City ${escapeHtml(item.supplier_sku)} · ${escapeHtml(item.selling_unit)} / ${Number(item.pack_quantity)} · ${pounds(item.price)} ex VAT → ${pounds(item.price_inc_vat)} inc VAT<br>${escapeHtml(cityCaptureAge(item))}</p>`).join('') +
      '<button type="button" class="btn-light" onclick="saveCityAccountCapture(this)">Save confirmed owner capture</button>';
  } catch(error) { box.textContent = error.message + ' — nothing saved.'; }
}

async function saveCityAccountCapture(button) {
  const row = button.closest('.material-row'), payload = row.cityPendingCapture;
  if (!payload) return;
  button.disabled = true;
  try {
    const response = await fetch('/api/city-account-prices', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Could not save captures');
    row.cityPendingCapture = null;
    // Reload while the clicked button is still attached to its material row.
    await loadCityAccountPrices(button);
    row.querySelector('.city-preview').textContent = `${data.status === 'duplicate' ? 'Identical capture already saved; age unchanged.' : 'Owner capture saved.'} ${data.rows} City products retained. Quote selection unchanged.`;
  } catch(error) { row.querySelector('.city-preview').textContent = error.message; button.disabled = false; }
}

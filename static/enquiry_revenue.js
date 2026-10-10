/* Owner-only revenue workspace. Included only in the authenticated app. */
const revenueState = { options: null, origin: null, invoice: null, entity: null, pending: new Map() };
function revenueEsc(value) { return escapeHtml(String(value ?? '')); }
function revenueMoney(pence) { return new Intl.NumberFormat('en-GB',{style:'currency',currency:'GBP'}).format((pence || 0)/100); }
function revenueOptions(items,current='') { return items.map(x=>`<option ${x===current?'selected':''}>${revenueEsc(x)}</option>`).join(''); }
function revenueDate() { return new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/London',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date()).split('/').reverse().join('-'); }
async function revenueFetch(path,payload) {
  const response = await fetch('/api/revenue/'+path,payload ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)} : {});
  const data=await response.json();
  if (!response.ok) throw new Error(data.detail || 'Unable to load revenue information');
  return data;
}
async function revenueRun(operation) {
  const status=document.getElementById('revenueStatus');status.textContent='Working…';
  try { await operation();status.textContent='Saved / loaded. No email has been sent.'; }
  catch(error) { status.textContent=error.message; }
}
function revenueKey(scope,payload) {
  const signature=JSON.stringify(payload),old=revenueState.pending.get(scope);
  if (old?.signature===signature) return old.key;
  const key=crypto.randomUUID();revenueState.pending.set(scope,{signature,key});return key;
}
function revenueValue(id) { return document.getElementById(id).value.trim(); }
async function loadRevenue() {
  revenueState.options=await revenueFetch('options');
  const section=document.getElementById('revenueWorkspace');
  section.hidden=!revenueState.options.active;
  document.getElementById('revenueActivation').textContent=revenueState.options.active ? 'Tracking migration active. GBP amounts; UK receipt dates. Synthetic tests excluded.' : 'Tracking is inactive. A separately approved migration is required. Existing business records are unchanged.';
  if (!revenueState.options.active) return;
  const selected=Object.fromEntries(['revenueOriginSelect','revenueInvoiceSelect','revenueEntitySelect','revenueStageQuote','revenueStageJob','revenueRevisionCurrent','revenueRevisionPrevious'].map(id=>[id,document.getElementById(id).value]));
  revenueState.origin=null;revenueState.invoice=null;revenueState.entity=null;
  for (const id of ['revenueOriginal','revenuePaymentHistory','revenueWorkflowHistory']) document.getElementById(id).textContent='Load the selected record before changing it.';
  const [leads,quotes,jobs,invoices,customers]=await Promise.all(['/api/leads','/api/quotes','/api/jobs','/api/invoices','/api/customers'].map(async path=>(await fetch(path)).json()));
  revenueState.records={leads,quotes,jobs,invoices,customers};
  document.getElementById('revenueOriginSelect').innerHTML=[...new Map([...leads,...quotes,...invoices,...jobs].filter(x=>x.origin_id).map(x=>[x.origin_id,x])).entries()].map(([id,x])=>`<option value="${id}">Origin #${id} · ${revenueEsc(x.source_category || x.invoice_number || x.job || 'Review source')}</option>`).join('');
  document.getElementById('revenueInvoiceSelect').innerHTML=invoices.map(x=>`<option value="${x.id}">${revenueEsc(x.invoice_number)} · balance ${revenueMoney(Math.round(x.balance_due*100))}</option>`).join('');
  document.getElementById('revenueEntitySelect').innerHTML=[...quotes.map(x=>`<option value="quote/${x.id}">Quote #${x.id} · ${revenueEsc(x.status || 'unclassified')}</option>`),...jobs.map(x=>`<option value="job/${x.id}">Job #${x.id} · ${revenueEsc(x.status)}</option>`)].join('');
  document.getElementById('revenueStageQuote').innerHTML=quotes.map(x=>`<option value="${x.id}">Quote #${x.id}</option>`).join('');
  document.getElementById('revenueStageJob').innerHTML='<option value="">No job link</option>'+jobs.map(x=>`<option value="${x.id}">Job #${x.id} / quote #${x.quote_id}</option>`).join('');
  for (const id of ['revenueRevisionCurrent','revenueRevisionPrevious']) document.getElementById(id).innerHTML='<option value="">Choose a quote explicitly</option>'+quotes.map(x=>`<option value="${x.id}">Quote #${x.id} · origin #${x.origin_id} · ${revenueEsc(x.status)}</option>`).join('');
  for (const [id,value] of Object.entries(selected)) if (Array.from(document.getElementById(id).options).some(x=>x.value===value)) document.getElementById(id).value=value;
  await revenueReport();
}
async function revenueReport() {
  const report=await revenueFetch('report?'+new URLSearchParams({start:revenueValue('revenueStart'),end:revenueValue('revenueEnd')}));
  document.getElementById('revenueDashboard').innerHTML=`<p>Enquiry cohort: ${revenueEsc(report.start)}–${revenueEsc(report.end)}. Current balances as at ${revenueEsc(report.as_of)}. Synthetic origins excluded: ${report.synthetic_origins_excluded}.</p><div style="overflow:auto"><table><thead><tr>${['Original source','Enquiries','Quoted','Accepted jobs','Completed','Quote-decision win rate (won / lost)','Enquiry win rate (won / lost)','Cash in dates','Cohort all recorded paid','Undated legacy','Current outstanding'].map(x=>`<th>${x}</th>`).join('')}</tr></thead><tbody>${Object.entries(report.by_source).map(([source,x])=>`<tr><td>${revenueEsc(source)}</td><td>${x.enquiries}</td><td>${x.quoted_enquiries} (${x.quoted_percent ?? '—'}%)</td><td>${x.accepted_enquiries} (${x.accepted_percent ?? '—'}%)</td><td>${x.completed_enquiries}</td><td>${x.won_quotes} / ${x.lost_quotes} (${x.quote_win_percent ?? '—'}%)</td><td>${x.won_enquiries} / ${x.lost_enquiries} (${x.enquiry_win_percent ?? '—'}%)</td>${['cash_pence','cohort_paid_pence','legacy_undated_pence','outstanding_pence'].map(k=>`<td>${revenueMoney(x[k])}</td>`).join('')}</tr>`).join('')}</tbody></table></div><p>Dated cash: ${revenueMoney(report.totals.cash_pence)}. Refunds reduce cash on their actual date. Reversals cancel erroneous entries on their original dates. Cohort paid includes all recorded later receipts and undated balances; it is not period cash or profit. Won / lost excludes explicitly superseded quote revisions. Enquiry win rate counts each enquiry with a current won/lost quote once; any won quote wins, otherwise it is lost. Pending, expired and unclassified quotes do not create decisions; superseded quotes and synthetic tests are excluded. Standalone quotes have no enquiry denominator. Unknown remains visible.</p>`;
}
async function revenueOrigin() {
  const origin=await revenueFetch('origins/'+revenueValue('revenueOriginSelect'));revenueState.origin=origin;
  document.getElementById('revenueOriginal').innerHTML=`<h3>Origin #${origin.id}</h3><p><strong>${revenueEsc(origin.source)}</strong> · original contact ${revenueEsc(origin.contact_channel)} · ${revenueEsc(origin.kind)} · revision ${origin.revision}</p><p>Captured source: ${revenueEsc(origin.captured_source)}. Method: ${revenueEsc(origin.method)}. Captured confidence: ${revenueEsc(origin.confidence)}. Capture time: ${revenueEsc(origin.captured_at)}. Test reference: ${revenueEsc(origin.test_reference || 'None')}.</p><pre style="white-space:pre-wrap;overflow-wrap:anywhere">${revenueEsc(JSON.stringify(origin.evidence,null,2))}</pre><h4>Append-only corrections</h4>${origin.history.map(x=>`<p>${revenueEsc(x.recorded_at)} · ${revenueEsc(x.actor)} · ${revenueEsc(x.old_source)} → ${revenueEsc(x.new_source)} · ${revenueEsc(x.old_kind)} → ${revenueEsc(x.new_kind)} · ${revenueEsc(x.old_channel)} → ${revenueEsc(x.new_channel)} · ${revenueEsc(x.reason)}</p>`).join('') || '<p>No corrections.</p>'}<h4>Later interactions</h4>${(origin.interactions || []).map(x=>`<p>${revenueEsc(x.occurred_at)} · ${revenueEsc(x.channel)} · ${revenueEsc(x.note)}</p>`).join('') || '<p>None recorded.</p>'}`;
  document.getElementById('revenueSource').innerHTML=revenueOptions(revenueState.options.sources,origin.source);
  document.getElementById('revenueCorrectionChannel').innerHTML=revenueOptions(revenueState.options.channels,origin.contact_channel);
  document.getElementById('revenueKind').innerHTML=revenueOptions(revenueState.options.kinds,origin.kind);
  document.getElementById('revenueTestReference').value=origin.test_reference;
  document.getElementById('revenueInteractionChannel').innerHTML=revenueOptions(revenueState.options.channels);
}
async function revenueCorrect() {
  if (!revenueState.origin) throw new Error('Load an original source first');
  await revenueFetch(`origins/${revenueState.origin.id}/corrections`,{source:revenueValue('revenueSource'),kind:revenueValue('revenueKind'),channel:revenueValue('revenueCorrectionChannel'),test_reference:revenueValue('revenueTestReference'),reason:revenueValue('revenueCorrectionReason'),expected_revision:revenueState.origin.revision});
  await revenueOrigin();await revenueReport();
}
async function revenueInteraction() {
  if (!revenueState.origin) throw new Error('Load an original source first');
  await revenueFetch(`origins/${revenueState.origin.id}/interactions`,{channel:revenueValue('revenueInteractionChannel'),note:revenueValue('revenueInteractionNote')});await revenueOrigin();
}
async function revenueInvoice() {
  const data=await revenueFetch('invoices/'+revenueValue('revenueInvoiceSelect')+'/payments');revenueState.invoice=data;
  document.getElementById('revenuePaymentHistory').innerHTML=`<h3>${revenueEsc(data.invoice.invoice_number)}</h3><p>Recorded paid ${revenueMoney(Math.round(data.invoice.amount_paid*100))} · outstanding ${revenueMoney(Math.round(data.invoice.balance_due*100))} · undated legacy ${revenueMoney(data.undated_balance_pence)} · excess credit ${revenueMoney(data.overpayment_credit_pence)}</p>${data.entries.map(x=>`<p>#${x.id} · ${revenueEsc(x.received_on || 'Undated legacy')} · ${revenueMoney(x.amount_pence)} · ${revenueEsc(x.entry_type)} · ${revenueEsc(x.method)} · ${revenueEsc(x.reference)} · ${revenueEsc(x.reason)} · recorded ${revenueEsc(x.recorded_at)}</p>`).join('') || '<p>No payments.</p>'}`;
  document.getElementById('revenuePaymentTarget').innerHTML='<option value="">Choose for a correction / reversal</option>'+data.entries.filter(x=>x.entry_type!=='reversal' && !data.entries.some(r=>r.entry_type==='reversal' && r.related_entry_id===x.id)).map(x=>`<option value="${x.id}">#${x.id} · ${revenueMoney(x.amount_pence)} · ${revenueEsc(x.received_on || 'Undated legacy')}</option>`).join('');
  document.getElementById('revenuePaymentMethod').innerHTML=revenueOptions(revenueState.options.methods);
}
async function revenuePayment() {
  if (!revenueState.invoice) throw new Error('Load an invoice first');
  const iid=revenueState.invoice.invoice.id;
  const payload={action:revenueValue('revenuePaymentAction'),amount:revenueValue('revenuePaymentAmount') || '0',received_on:revenueValue('revenuePaymentDate'),method:revenueValue('revenuePaymentMethod'),reference:revenueValue('revenuePaymentReference'),reason:revenueValue('revenuePaymentReason'),related_entry_id:Number(revenueValue('revenuePaymentTarget')) || null};
  payload.operation_key=revenueKey('payment/'+iid,payload);
  await revenueFetch(`invoices/${iid}/payments`,payload);revenueState.pending.delete('payment/'+iid);await revenueInvoice();await revenueReport();
  document.getElementById('revenueInvoiceSelect').selectedOptions[0].textContent=revenueState.invoice.invoice.invoice_number+' · balance '+revenueMoney(Math.round(revenueState.invoice.invoice.balance_due*100));
  if (CURRENT_INVOICE_ID===iid) renderInvoiceCard(await (await fetch('/api/invoices/'+iid)).json(),false);
  document.getElementById('revenuePaymentAmount').value='';document.getElementById('revenuePaymentReason').value='';
}
async function revenueWorkflow() {
  const entity=revenueValue('revenueEntitySelect');revenueState.entity=entity;
  const data=await revenueFetch('workflow/'+entity);
  const [type,id]=entity.split('/');
  const item=revenueState.records[type==='quote'?'quotes':'jobs'].find(x=>String(x.id)===id);
  document.getElementById('revenueOutcome').innerHTML=revenueOptions(type==='quote'?['pending','won','lost','expired']:['awaiting_schedule','accepted','scheduled','in_progress','completed','cancelled'],item?.status);
  const invoices=type==='job'?revenueState.records.invoices.filter(x=>x.job_id===Number(id) || x.id===item?.invoice_id):revenueState.records.invoices.filter(x=>x.quote_id===Number(id));
  document.getElementById('revenueWorkflowHistory').innerHTML=`<p>Current ${revenueEsc(type)} status: ${revenueEsc(item?.status)}. Quote won is distinct from job acceptance. ${invoices.map(x=>`Invoice ${revenueEsc(x.invoice_number)}: balance ${revenueMoney(Math.round(x.balance_due*100))}`).join('; ')}</p>${data.history.map(x=>`<p>${revenueEsc(x.occurred_at)} · ${x.event_kind==='quote_revision'?'Explicit revision of quote #'+revenueEsc(x.to_status):revenueEsc(x.from_status)+' → '+revenueEsc(x.to_status)} · ${revenueEsc(x.reason)} · ${revenueEsc(x.actor)}</p>`).join('') || '<p>No recorded milestones. Historical status is not a dated event.</p>'}`;
}
async function revenueMilestone() {
  if (!revenueState.entity) throw new Error('Load a quote or job first');
  const entity=revenueState.entity,payload={status:revenueValue('revenueOutcome'),reason:revenueValue('revenueOutcomeReason')};payload.operation_key=revenueKey('workflow/'+entity,payload);
  await revenueFetch('workflow/'+entity,payload);revenueState.pending.delete('workflow/'+entity);await loadRevenue();await revenueWorkflow();await loadHistory();
}
async function revenueStageInvoice() {
  const qid=revenueValue('revenueStageQuote'),payload={job_id:Number(revenueValue('revenueStageJob')) || null};payload.operation_key=revenueKey('stage-invoice/'+qid,payload);
  await revenueFetch(`quotes/${qid}/stage-invoice`,payload);revenueState.pending.delete('stage-invoice/'+qid);await loadRevenue();
}
async function revenueExport() {
  const response=await fetch('/api/revenue/export?'+new URLSearchParams({start:revenueValue('revenueStart'),end:revenueValue('revenueEnd')}));
  if (!response.ok) { const error=await response.json();throw new Error(error.detail || 'Export failed'); }
  const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');
  link.href=url;link.download='source-revenue-aggregate.csv';document.body.appendChild(link);link.click();link.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function revenueRevision() {
  if (!document.getElementById('revenueRevisionConfirmed').checked) throw new Error('Confirm these are genuine revisions of the same work');
  const quote=Number(revenueValue('revenueRevisionCurrent')),previous=Number(revenueValue('revenueRevisionPrevious')),reason=revenueValue('revenueRevisionReason');
  if (!quote || !previous || !reason) throw new Error('Choose both quotes and give a revision reason');
  if (!confirm(`Record quote #${quote} as a replacement revision of quote #${previous}? This permanent link excludes the earlier quote from current decision rates; it does not cancel invoices or change payments.`)) return;
  const payload={supersedes_quote_id:previous,confirmed_same_scope:true,reason};payload.operation_key=revenueKey('revision/'+quote,payload);
  await revenueFetch(`quotes/${quote}/revision`,payload);revenueState.pending.delete('revision/'+quote);
  document.getElementById('revenueRevisionConfirmed').checked=false;document.getElementById('revenueRevisionReason').value='';
  await loadRevenue();document.getElementById('revenueEntitySelect').value='quote/'+quote;await revenueWorkflow();
  document.getElementById('revenueWorkflowHistory').closest('details').open=true;
}
async function revenueReview() {
  const data=await revenueFetch('review');document.getElementById('revenueHistorical').innerHTML=Object.entries(data).map(([name,x])=>`<h4>${revenueEsc(name.replaceAll('_',' '))}: ${x.count}</h4><pre style="white-space:pre-wrap">${revenueEsc(JSON.stringify(x.records,null,2))}</pre>`).join('')+'<p>No records are merged or reclassified automatically. Corrections require explicit owner evidence and a reason. Genuine historical receipt dates are entered by correcting the undated ledger entry.</p>';
}
function revenueInit() {
  const button=document.createElement('button');button.className='btn-light';button.textContent='Source & revenue';button.type='button';button.onclick=()=>{showTab('revenueTab');revenueRun(loadRevenue);};document.querySelector('.tabs').append(button);
  const panel=document.createElement('section');panel.id='revenueTab';panel.className='tab-panel';
  const field=(id,label,type='text')=>`<label for="${id}">${label}</label><input id="${id}" type="${type}">`;
  const select=(id,label,options='')=>`<label for="${id}">${label}</label><select id="${id}">${options}</select>`;
  const action=(label,handler,id='')=>`<button type="button" class="btn-blue" ${id?`id="${id}"`:''} onclick="revenueRun(${handler})">${label}</button>`;
  panel.innerHTML=`<h2>Source-to-revenue</h2><p id="revenueActivation"></p><p id="revenueStatus" role="status" aria-live="polite"></p><div id="revenueWorkspace" hidden><h3>Reporting period</h3><div class="row">${field('revenueStart','Enquiry / cash start','date')}${field('revenueEnd','Enquiry / cash end','date')}</div>${action('Refresh report','revenueReport')}${action('Download aggregate CSV','revenueExport')}<p class="small">CSV contains source totals only. GBP money columns are integer pence; blank rates mean no decided records. No customer details or payment references.</p><div id="revenueDashboard"></div><details open><summary>Original source and correction history</summary>${select('revenueOriginSelect','Enquiry origin')}${action('Load original source','revenueOrigin')}<div id="revenueOriginal"></div>${select('revenueSource','Corrected original source')}${select('revenueCorrectionChannel','Corrected original contact channel')}${select('revenueKind','Record classification')}${field('revenueTestReference','Synthetic test reference (required for tests)')}${field('revenueCorrectionReason','Correction reason (required)')}${action('Append source correction','revenueCorrect')}${select('revenueInteractionChannel','Later contact channel')}${field('revenueInteractionNote','Later interaction note')}${action('Record interaction','revenueInteraction')}</details><details><summary>Quote outcomes and job milestones</summary>${select('revenueEntitySelect','Quote / job')}${action('Load milestone history','revenueWorkflow')}<div id="revenueWorkflowHistory"></div>${select('revenueOutcome','New outcome / progress')}${field('revenueOutcomeReason','Reason (required for loss, cancellation or reopening)')}${action('Record milestone','revenueMilestone')}${select('revenueStageQuote','Quote for an additional invoice')}${select('revenueStageJob','Explicit job link')}${action('Create additional stage / final invoice','revenueStageInvoice')}<p>An additional invoice starts with the quote snapshot. Edit its actual stage amount before sharing; do not issue duplicate full-value invoices.</p></details><details><summary>Record payment and history</summary>${select('revenueInvoiceSelect','Invoice')}${action('Load payment history','revenueInvoice')}<div id="revenuePaymentHistory"></div><p>Use Refund for money actually returned on its receipt date. Reversal cancels an erroneous record on its original date; it does not record a cash refund.</p>${select('revenuePaymentAction','Action',revenueOptions(['receipt','refund','reversal','correction']))}${field('revenuePaymentAmount','GBP amount (positive, two decimals maximum)','text')}${field('revenuePaymentDate','Genuine UK receipt / refund date','date')}${select('revenuePaymentMethod','Payment method')}${select('revenuePaymentTarget','Entry to correct / reverse')}${field('revenuePaymentReference','Private payment reference (optional)')}${field('revenuePaymentReason','Refund / reversal / correction reason')}${action('Record payment entry','revenuePayment','revenueSavePayment')}</details><details><summary>Link genuine quote revisions</summary><p>Use only for a replacement version of the same work. Separate jobs and additional scope remain independent quotes. Links are recorded permanently with your reason.</p>${select('revenueRevisionCurrent','Newer replacement quote')}${select('revenueRevisionPrevious','Earlier quote being replaced')}${field('revenueRevisionReason','Why is this a revision of the same work?')}<label><input id="revenueRevisionConfirmed" type="checkbox"> I confirm these quotes describe the same work, not separate jobs or additional scope.</label>${action('Confirm revision link','revenueRevision')}<p>Reload the newer quote in milestone history to inspect the recorded link, actor, time and reason.</p></details><details><summary>Historical-data review</summary>${action('Load bounded review (up to 50 IDs per check)','revenueReview')}<div id="revenueHistorical"></div></details></div>`;
  document.querySelector('#dashboardTab').before(panel);
  const today=new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/London'}).format(new Date());
  document.getElementById('revenueStart').value=today.slice(0,7)+'-01';document.getElementById('revenueEnd').value=today;document.getElementById('revenuePaymentDate').value=today;
  document.getElementById('revenueOriginSelect').onchange=()=>{revenueState.origin=null;};
  document.getElementById('revenueInvoiceSelect').onchange=()=>{revenueState.invoice=null;};
  document.getElementById('revenueEntitySelect').onchange=()=>{revenueState.entity=null;};
  // New manual enquiries retain Unknown unless Nigel chooses a source.
  const quick=document.getElementById('quickSource');
  if (quick) { const wrap=document.createElement('div');wrap.id='revenueQuickFields';wrap.innerHTML=select('quickChannel','Contact channel',revenueOptions(['Unknown','Phone','WhatsApp','Email','Directory message','In person','Other']))+select('quickKind','Record classification',revenueOptions(['unconfirmed','genuine','synthetic']))+field('quickTestReference','Synthetic test reference')+field('quickCustomerId','Existing customer ID (only when explicitly confirmed)','number');quick.after(wrap); }
  // Ledger-backed balances can only be changed through the dated payment screen.
  const originalInvoices=loadInvoices;
  loadInvoices=async function(){ await originalInvoices();const options=await revenueFetch('options');if(!options.active)return;document.querySelectorAll('#invoiceList input[id^="paid_"]').forEach(input=>{input.disabled=true;const row=input.parentElement;const button=row.querySelector('button');button.textContent='Dated payment / history';button.onclick=()=>{showTab('revenueTab');revenueRun(async()=>{await loadRevenue();document.getElementById('revenueInvoiceSelect').value=input.id.slice(5);await revenueInvoice();document.getElementById('revenuePaymentHistory').closest('details').open=true;});};});document.querySelectorAll('#invoiceList button[onclick^="markInvoice"]').forEach(x=>x.hidden=true);document.getElementById('edit_invoice_amount_paid').readOnly=true; };
}
revenueInit();
// Explicit returning-customer selection and stable quote save keys.
const revenueOriginalPayload = collectFormPayload;
collectFormPayload = function () {
  const payload=revenueOriginalPayload();
  payload.customer_id=Number(document.getElementById('revenueQuoteCustomer')?.value) || null;
  payload.submission_key=revenueKey('quote-save',payload);
  return payload;
};
const revenueCustomer=document.createElement('div');
revenueCustomer.innerHTML='<label for="revenueQuoteCustomer">Existing customer ID (only when explicitly confirmed)</label><input id="revenueQuoteCustomer" type="number" min="1"><p class="small">Leave blank for a new customer. No name or telephone matching is used after tracking activation.</p>';
document.getElementById('customer_name').before(revenueCustomer);
const revenueOriginalFill=fillFormFromRequest;
fillFormFromRequest=function(request,quoteId=null){revenueOriginalFill(request,quoteId);document.getElementById('revenueQuoteCustomer').value=request.customer_id || '';};
const revenueOriginalReset=resetQuoteFormState;
resetQuoteFormState=function(){revenueOriginalReset();document.getElementById('revenueQuoteCustomer').value='';revenueState.pending.delete('quote-save');};
const revenueOriginalLeads=loadLeads;
loadLeads=async function(){await revenueOriginalLeads();const options=await revenueFetch('options');if(!options.active)return;document.querySelectorAll('#leadList select[id^="lead_source_"]').forEach(x=>{x.disabled=true;const button=document.createElement('button');button.type='button';button.className='btn-light';button.textContent='Original source / corrections';button.onclick=()=>{const lead=SAVED_LEADS.find(l=>l.id===Number(x.id.slice(12)));showTab('revenueTab');revenueRun(async()=>{await loadRevenue();document.getElementById('revenueOriginSelect').value=lead.origin_id;await revenueOrigin();});};x.after(button);});};

const revenueOriginalPost=b7Post;
b7Post=function(url,data,method){if(/^\/api\/jobs(?:\/|$)/.test(url))data={...data,operation_key:revenueKey('job/'+url,data)};return revenueOriginalPost(url,data,method);};

// The legacy watermark has inline display:flex; .hidden alone cannot suppress it.
const revenueOriginalInvoiceCard=renderInvoiceCard;
renderInvoiceCard=function(data,...args){revenueOriginalInvoiceCard(data,...args);const watermark=document.getElementById('invoicePaidWatermark');watermark.style.display=watermark.classList.contains('hidden')?'none':'flex';};

if (document.getElementById('jobStatus')) { const option=document.createElement('option');option.value='accepted';option.textContent='Accepted';document.getElementById('jobStatus').append(option); }

const revenueLegacyNotice=document.createElement('p');
revenueLegacyNotice.className='small';
revenueLegacyNotice.textContent='These legacy summaries use quote estimates and invoice paid balances, may include synthetic tests, and do not use original-source corrections. Use Source & revenue for dated cash, enquiry cohorts and audited source reporting.';
document.getElementById('dashboardTab').querySelector('h2').after(revenueLegacyNotice);

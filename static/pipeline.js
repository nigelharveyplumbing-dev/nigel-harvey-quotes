/* Batch 7 private workflow: no automatic messages or calendar writes. */
const B7_STAGES = [
  ['new_enquiry', 'New enquiries'],
  ['visit_booked', 'Site visits / quote next'],
  ['quote_pending', 'Quotes awaiting decision'],
  ['won_unscheduled', 'Won / awaiting schedule'],
  ['scheduled', 'Scheduled jobs'],
  ['in_progress', 'In progress'],
  ['completed_uninvoiced', 'Completed / invoice next'],
  ['invoiced_unpaid', 'Invoiced / awaiting payment'],
  ['paid', 'Paid'],
  ['closed_lost_expired', 'Closed / lost or expired']
];
let b7QuickKey = '';
let b7Appointments = [];
let b7Jobs = [];
let b7WeekOffset = 0;
const B7_WORK_TYPES = ['Leak / repair','Tap','Toilet / cistern','Shower','Bathroom plumbing',
  'Radiator / TRV','Outside tap','Pipework','Power/heating-system flush','Cylinder / tank','Other'];

function b7AdditionalHtml(id, selected, primary) {
  const values = Array.isArray(selected) ? selected : [];
  return '<details class="work-type-more"><summary>Additional work types' +
    (values.length ? ': ' + values.map(escapeHtml).join(', ') + ' (edit)' : ' (select all that apply)') +
    '</summary>' +
    '<div class="work-type-grid">' + B7_WORK_TYPES.filter(value => value !== primary).map(value =>
      '<label class="work-type-chip"><input type="checkbox" value="' + escapeHtml(value) + '" ' +
      (values.includes(value) ? 'checked' : '') + '> ' + escapeHtml(value) + '</label>').join('') + '</div></details>';
}
function b7SelectedAdditional(id, primary) {
  const node = document.getElementById(id);
  return node && node.querySelectorAll ? Array.from(node.querySelectorAll('input:checked'))
    .map(input => input.value).filter(value => value !== primary) : [];
}
function b7SetAdditional(id, selected, primary) {
  document.getElementById(id).innerHTML = b7AdditionalHtml(id, selected, primary);
}
function b7ChangePrimary(id, selectId) {
  b7SetAdditional(id, b7SelectedAdditional(id, b7Value(selectId)), b7Value(selectId));
}

function b7Value(id) { return document.getElementById(id).value.trim(); }
function b7Number(id) { return Number(b7Value(id)) || null; }
async function b7Request(url, options) {
  const response = await fetch(url, options || {});
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Request failed');
  return payload;
}
function b7Post(url, data, method) {
  return b7Request(url, { method:method || 'POST',
    headers:{'Content-Type':'application/json'}, body:JSON.stringify(data) });
}

async function previewQuickLead() {
  try {
    const data = await b7Post('/api/quick-add/preview', {message:b7Value('quickMessage')});
    document.getElementById('quickNext').classList.add('hidden');
    b7QuickKey = crypto.randomUUID();
    ['Name','Phone','Email','Description'].forEach(key => {
      document.getElementById('quick' + key).value = data[key.toLowerCase()] || '';
    });
    document.getElementById('quickAddress').value = data.address || data.postcode || '';
    document.getElementById('quickVisitStart').value = data.visit_starts_at || '';
    document.getElementById('quickVisitEnd').value = data.visit_ends_at || '';
    document.getElementById('quickSource').value = '';
    const types = data.suggested_work_types || [];
    document.getElementById('quickWork').value = types[0] || '';
    b7SetAdditional('quickAdditional', types.slice(1), types[0] || '');
    document.getElementById('quickVisitStatus').value = 'confirmed';
    document.getElementById('quickFollowUp').value = '';
    document.getElementById('quickProvisionalFollow').classList.add('hidden');
    document.getElementById('quickHint').innerText = data.hint;
    document.getElementById('quickPreview').classList.remove('hidden');
    document.getElementById('quickPreview').scrollIntoView({behavior:'smooth', block:'start'});
  } catch (error) { alert(error.message); }
}

async function saveQuickLead() {
  const button = document.getElementById('quickSave');
  if (!b7QuickKey || button.disabled) return;
  const data = {
    idempotency_key:b7QuickKey,
    name:b7Value('quickName'), phone:b7Value('quickPhone'),
    email:b7Value('quickEmail'), address:b7Value('quickAddress'),
    description:b7Value('quickDescription'), source_category:b7Value('quickSource'),
    work_type:b7Value('quickWork'),
    additional_work_types:b7SelectedAdditional('quickAdditional', b7Value('quickWork')),
    visit_starts_at:b7Value('quickVisitStart'),
    visit_ends_at:b7Value('quickVisitEnd'), visit_status:b7Value('quickVisitStatus'),
    provisional_follow_up:b7Value('quickVisitStatus') === 'provisional' ? b7Value('quickFollowUp') : ''
  };
  button.disabled = true;
  try {
    const result = await b7Post('/api/quick-add/confirm', data);
    b7QuickKey = '';
    document.getElementById('quickPreview').classList.add('hidden');
    document.getElementById('quickMessage').value = '';
    await loadLeads();
    showQuickNextActions(result);
    showNotice((result.already_created ? 'Existing lead returned' : 'Lead saved') +
      ' #' + result.lead.id + (result.appointment_id ? ' with site visit' : '') + '.');
  } catch (error) { alert(error.message); }
  finally { button.disabled = false; }
}

function showQuickNextActions(result) {
  const leadId = Number(result.lead.id);
  const visitId = Number(result.appointment_id) || 0;
  const box = document.getElementById('quickNext');
  box.innerHTML = '<strong>Lead #' + leadId + ' saved' +
    (result.lead.name ? ' · ' + escapeHtml(result.lead.name) : '') + '</strong>' +
    '<p class="small">' + (visitId ?
      'Quote survey booked, not the plumbing job. Open the visit in Diary; Add to Google Calendar creates a draft you review before saving.' :
      'Next, book a site visit or start a quote when ready. No appointment or quote was created.') + '</p>' +
    '<div class="history-actions quick-next-actions">' +
    '<button type="button" class="btn-light" onclick="openPipelineLead(' + leadId + ')">Open Lead</button>' +
    (visitId ? '<button type="button" class="btn-blue" onclick="openQuickVisit(' + visitId + ')">View Visit in Diary</button>' :
      '<button type="button" class="btn-blue" onclick="bookVisitForLead(' + leadId + ')">Book Site Visit</button>') +
    '<button type="button" class="btn-light" onclick="quoteFromDiaryLead(' + leadId + ')">Start Quote</button></div>';
  box.classList.remove('hidden');
  box.scrollIntoView({behavior:'smooth', block:'start'});
}

async function openQuickVisit(appointmentId) {
  showTab('diaryTab');
  await loadDiary();
  const visit = b7Appointments.find(a => a.id === appointmentId);
  if (!visit) return;
  const monday = day => new Date(day.getFullYear(), day.getMonth(),
    day.getDate() - ((day.getDay() + 6) % 7));
  const date = new Date(visit.starts_at.slice(0,10) + 'T12:00:00');
  b7WeekOffset = Math.round((monday(date) - monday(new Date())) / 86400000);
  renderDiary();
  document.getElementById('diary_appointment_' + appointmentId)?.scrollIntoView({behavior:'smooth', block:'center'});
}

async function loadPipeline() {
  const board = document.getElementById('pipelineBoard');
  try {
    const results = await Promise.all([b7Request('/api/pipeline'), b7Request('/api/jobs')]);
    const data = results[0];
    b7Jobs = results[1];
    board.innerHTML = B7_STAGES.map(pair => {
      const items = data.stages[pair[0]] || [];
      return '<section class="pipeline-stage"><h3>' + pair[1] + ' (' + items.length + ')</h3>' +
        (items.map(card => '<div class="history-item"><strong>' + escapeHtml(card.name) + '</strong>' +
          (card.lead_id ? ' · Lead #' + Number(card.lead_id) : '') +
          (card.quote_ids.length ? ' · Quote #' + card.quote_ids.map(Number).join(', #') : '') +
          (card.job_ids.length ? ' · Job #' + card.job_ids.map(Number).join(', #') : '') +
          '<div class="small">' + escapeHtml(card.description) + '</div>' +
          '<div class="history-actions">' +
          (card.visit_completed ? '<div class="small">Visit completed · prepare quote</div>' : '') +
          (card.lead_id ? '<button type="button" class="btn-light" onclick="bookVisitForLead(' + Number(card.lead_id) + ')">Book visit</button>' : '') +
          (card.lead_id ? '<button type="button" class="btn-light" onclick="openPipelineLead(' + Number(card.lead_id) + ')">Open lead</button>' : '') +
          (card.lead_id ? '<button type="button" class="btn-light" onclick="quoteFromDiaryLead(' + Number(card.lead_id) + ')">Start quote</button>' : '') +
          (card.job_ids.length ? '<button type="button" class="btn-light" onclick="editPipelineJob(' + Number(card.job_ids[0]) + ')">Update job</button>' : '') +
          (card.lead_id && card.job_ids.length ? '<button type="button" class="btn-light" onclick="bookJobForLead(' + Number(card.lead_id) + ',' + Number(card.job_ids[0]) + ')">Book job dates</button>' : '') +
          '</div></div>').join('') || '<p class="small">None</p>') + '</section>';
    }).join('');
  } catch (error) { board.innerText = 'Could not load pipeline: ' + error.message; }
}

function jobFromQuote(id) {
  const quote = (typeof SAVED_QUOTES !== 'undefined' ? SAVED_QUOTES : []).find(x => x.id === id);
  showTab('pipelineTab');
  document.getElementById('jobEditor').open = true;
  document.getElementById('jobEditId').value = '';
  document.getElementById('jobLeadId').value = '';
  document.getElementById('jobQuoteId').value = '';
  document.getElementById('jobInvoiceId').value = '';
  document.getElementById('jobTitle').value = '';
  document.getElementById('jobNotes').value = '';
  document.getElementById('jobStatus').value = 'awaiting_schedule';
  if (quote) {
    document.getElementById('jobLeadId').value = quote.lead_id || '';
    document.getElementById('jobQuoteId').value = quote.id;
    document.getElementById('jobTitle').value = quote.job || 'Plumbing work';
  }
}
function editPipelineJob(id) {
  const job = b7Jobs.find(x => x.id === id);
  if (!job) return;
  document.getElementById('jobEditor').open = true;
  ['EditId','LeadId','QuoteId','InvoiceId','Title','Status','Notes'].forEach((key, index) => {
    document.getElementById('job' + key).value =
      [job.id, job.lead_id, job.quote_id, job.invoice_id, job.title, job.status, job.notes][index] || '';
  });
  document.getElementById('jobEditId').scrollIntoView({behavior:'smooth', block:'center'});
}
async function savePipelineJob() {
  const id = b7Number('jobEditId');
  const data = {lead_id:b7Number('jobLeadId'), quote_id:b7Number('jobQuoteId'),
    invoice_id:b7Number('jobInvoiceId'), title:b7Value('jobTitle'),
    status:b7Value('jobStatus'), notes:b7Value('jobNotes')};
  try {
    const job = await b7Post(id ? '/api/jobs/' + id : '/api/jobs', data, id ? 'PUT' : 'POST');
    document.getElementById('jobEditId').value = job.id;
    await loadPipeline();
    showNotice('Job #' + job.id + ' saved.');
  } catch (error) { alert(error.message); }
}

function bookVisitForLead(leadId) {
  showTab('diaryTab');
  document.getElementById('appointmentEditor').open = true;
  document.getElementById('appointmentEditId').value = '';
  document.getElementById('appointmentJobId').value = '';
  document.getElementById('appointmentLeadId').value = leadId;
  document.getElementById('appointmentKind').value = 'site_visit';
  document.getElementById('appointmentStatus').value = 'confirmed';
  document.getElementById('appointmentFollow').classList.add('hidden');
  ['Start','End','FollowDate','Notes'].forEach(key => { document.getElementById('appointment' + key).value = ''; });
  document.getElementById('appointmentLeadId').scrollIntoView({behavior:'smooth', block:'center'});
}
function bookJobForLead(leadId, jobId) {
  showTab('diaryTab');
  document.getElementById('appointmentEditor').open = true;
  document.getElementById('appointmentEditId').value = '';
  document.getElementById('appointmentLeadId').value = leadId;
  document.getElementById('appointmentJobId').value = jobId;
  document.getElementById('appointmentKind').value = 'job';
  document.getElementById('appointmentStatus').value = 'confirmed';
  document.getElementById('appointmentFollow').classList.add('hidden');
  ['Start','End','FollowDate','Notes'].forEach(key => { document.getElementById('appointment' + key).value = ''; });
  document.getElementById('appointmentLeadId').scrollIntoView({behavior:'smooth', block:'center'});
}
async function openPipelineLead(leadId) {
  document.getElementById('leadSearch').value = '';
  document.getElementById('leadStatusFilter').value = 'all';
  showTab('leadsTab');
  await loadLeads();
  document.getElementById('lead_card_' + leadId)?.scrollIntoView({behavior:'smooth', block:'center'});
}
async function quoteFromDiaryLead(leadId) {
  await loadLeads();
  if (!SAVED_LEADS.some(lead => lead.id === leadId)) {
    alert('Lead could not be loaded. Open Leads and try again.');
    return;
  }
  startQuoteFromLead(leadId);
  document.getElementById('quotesTab').scrollIntoView({behavior:'smooth', block:'start'});
}
function shiftDiary(days) { b7WeekOffset += days; renderDiary(); }
function b7LocalDate(day) {
  return day.getFullYear() + '-' + String(day.getMonth() + 1).padStart(2,'0') +
    '-' + String(day.getDate()).padStart(2,'0');
}
function b7CalendarUrl(item) {
  const dates = item.starts_at.replace(/[-:]/g, '') + '00/' + item.ends_at.replace(/[-:]/g, '') + '00';
  const title = (item.kind === 'site_visit' ? 'Site visit / quote survey' : 'Plumbing job') + ' · ' + item.customer_name;
  return 'https://calendar.google.com/calendar/render?action=TEMPLATE&ctz=Europe%2FLondon&dates=' +
    encodeURIComponent(dates) + '&text=' + encodeURIComponent(title) +
    '&details=' + encodeURIComponent('Lead #' + item.lead_id + ' · Check private Nigel Harvey Plumbing app for details.');
}
async function loadDiary() {
  try { b7Appointments = await b7Request('/api/appointments'); renderDiary(); }
  catch (error) { document.getElementById('diaryList').innerText = 'Could not load diary: ' + error.message; }
}
function renderDiary() {
  const now = new Date();
  const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - ((now.getDay() + 6) % 7) + b7WeekOffset);
  const sunday = new Date(monday); sunday.setDate(monday.getDate() + 6);
  document.getElementById('diaryWeek').innerText = monday.toLocaleDateString('en-GB') + ' – ' + sunday.toLocaleDateString('en-GB');
  const followUps = b7Appointments.filter(a => a.status === 'provisional' && a.provisional_follow_up &&
    a.lead_status !== 'lost' && a.provisional_follow_up <= b7LocalDate(new Date()));
  const closedBookings = b7Appointments.filter(a => a.status !== 'cancelled' && a.lead_status === 'lost');
  const days = Array.from({length:7}, (_, index) => {
    const day = new Date(monday); day.setDate(monday.getDate() + index);
    const next = new Date(day); next.setDate(day.getDate() + 1);
    const start = b7LocalDate(day) + 'T00:00';
    const end = b7LocalDate(next) + 'T00:00';
    const items = b7Appointments.filter(a => a.status !== 'cancelled' && a.lead_status !== 'lost' &&
      a.starts_at < end && a.ends_at > start);
    return '<section class="diary-day"><h3>' + escapeHtml(day.toLocaleDateString('en-GB', {weekday:'long',day:'numeric',month:'short'})) +
      (b7LocalDate(day) === b7LocalDate(new Date()) ? ' · Today' : '') + '</h3>' +
      (items.length ? items.map(a => '<div class="history-item"' +
        (b7LocalDate(day) === a.starts_at.slice(0,10) ? ' id="diary_appointment_' + Number(a.id) + '"' : '') +
        '><strong>' + escapeHtml(a.customer_name) +
        '</strong> · ' + (a.kind === 'site_visit' ? 'Site visit / quote survey' : 'Plumbing job') + ' · ' + escapeHtml(a.status) +
        '<div>' + escapeHtml(a.starts_at.replace('T',' ')) + '–' + escapeHtml(a.ends_at.replace('T',' ')) +
        ' · Lead #' + Number(a.lead_id) + '</div><div class="small">' + escapeHtml(a.notes || '') + '</div>' +
        '<button type="button" class="btn-light" onclick="editDiaryAppointment(' + Number(a.id) + ')">Update</button> ' +
        '<button type="button" class="btn-light" onclick="openPipelineLead(' + Number(a.lead_id) + ')">Open lead</button> ' +
        (a.kind === 'site_visit' ? '<button type="button" class="btn-light" onclick="quoteFromDiaryLead(' + Number(a.lead_id) + ')">Start quote</button> ' : '') +
        '<a class="btn-link btn-secondary" target="_blank" rel="noopener" href="' + b7CalendarUrl(a) +
        '">Add to Google Calendar</a></div>').join('') : '<p class="small">No plumbing work booked.</p>') + '</section>';
  });
  document.getElementById('diaryList').innerHTML =
    (followUps.length ? '<p><strong>Provisional bookings to follow up:</strong> ' +
      followUps.map(a => '#' + a.id + ' ' + escapeHtml(a.customer_name)).join(', ') + '</p>' : '') +
    (closedBookings.length ? '<p class="small"><strong>Review bookings linked to closed leads:</strong> ' +
      closedBookings.map(a => '#' + a.id + ' ' + escapeHtml(a.customer_name) +
        ' <button type="button" class="btn-light" onclick="editDiaryAppointment(' + Number(a.id) + ')">Review</button>').join(', ') + '</p>' : '') +
    days.join('');
}
function editDiaryAppointment(id) {
  const a = b7Appointments.find(x => x.id === id);
  if (!a) return;
  document.getElementById('appointmentEditor').open = true;
  ['EditId','LeadId','JobId','Kind','Status','Start','End','FollowDate','Notes'].forEach((key,index) => {
    document.getElementById('appointment' + key).value =
      [a.id,a.lead_id,a.job_id,a.kind,a.status,a.starts_at,a.ends_at,a.provisional_follow_up,a.notes][index] || '';
  });
  document.getElementById('appointmentFollow').classList.toggle('hidden',a.status !== 'provisional');
  document.getElementById('appointmentEditId').scrollIntoView({behavior:'smooth', block:'center'});
}
async function saveDiaryAppointment() {
  const id = b7Number('appointmentEditId');
  const data = {lead_id:b7Number('appointmentLeadId'), job_id:b7Number('appointmentJobId'),
    kind:b7Value('appointmentKind'), status:b7Value('appointmentStatus'),
    starts_at:b7Value('appointmentStart'), ends_at:b7Value('appointmentEnd'),
    provisional_follow_up:b7Value('appointmentStatus') === 'provisional' ? b7Value('appointmentFollowDate') : '',
    notes:b7Value('appointmentNotes')};
  try {
    const a = await b7Post(id ? '/api/appointments/' + id : '/api/appointments', data, id ? 'PUT' : 'POST');
    document.getElementById('appointmentEditId').value = a.id;
    await Promise.all([loadDiary(), loadPipeline()]);
    showNotice('Appointment #' + a.id + ' saved.');
  } catch (error) { alert(error.message); }
}

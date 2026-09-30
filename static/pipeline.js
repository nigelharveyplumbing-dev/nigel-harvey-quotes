/* Batch 7 private workflow: no automatic messages or calendar writes. */
const B7_STAGES = [
  ['new_enquiry', 'New enquiries'],
  ['visit_booked', 'Visits booked'],
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
    b7QuickKey = crypto.randomUUID();
    ['Name','Phone','Email','Description'].forEach(key => {
      document.getElementById('quick' + key).value = data[key.toLowerCase()] || '';
    });
    document.getElementById('quickAddress').value = data.address || data.postcode || '';
    document.getElementById('quickVisitStart').value = data.visit_starts_at || '';
    document.getElementById('quickVisitEnd').value = data.visit_ends_at || '';
    document.getElementById('quickHint').innerText = data.hint;
    document.getElementById('quickPreview').classList.remove('hidden');
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
    work_type:b7Value('quickWork'), visit_starts_at:b7Value('quickVisitStart'),
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
    showNotice((result.already_created ? 'Existing lead returned' : 'Lead saved') +
      ' #' + result.lead.id + (result.appointment_id ? ' with site visit' : '') + '.');
  } catch (error) { alert(error.message); }
  finally { button.disabled = false; }
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
          (card.lead_id ? '<button type="button" class="btn-light" onclick="bookVisitForLead(' + Number(card.lead_id) + ')">Book visit</button>' : '') +
          (card.job_ids.length ? '<button type="button" class="btn-light" onclick="editPipelineJob(' + Number(card.job_ids[0]) + ')">Update job</button>' : '') +
          '</div></div>').join('') || '<p class="small">None</p>') + '</section>';
    }).join('');
  } catch (error) { board.innerText = 'Could not load pipeline: ' + error.message; }
}

function jobFromQuote(id) {
  const quote = (typeof SAVED_QUOTES !== 'undefined' ? SAVED_QUOTES : []).find(x => x.id === id);
  showTab('pipelineTab');
  if (quote) {
    document.getElementById('jobLeadId').value = quote.lead_id || '';
    document.getElementById('jobQuoteId').value = quote.id;
    document.getElementById('jobTitle').value = quote.job || 'Plumbing work';
  }
}
function editPipelineJob(id) {
  const job = b7Jobs.find(x => x.id === id);
  if (!job) return;
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
  document.getElementById('appointmentLeadId').value = leadId;
  document.getElementById('appointmentKind').value = 'site_visit';
  document.getElementById('appointmentLeadId').scrollIntoView({behavior:'smooth', block:'center'});
}
function shiftDiary(days) { b7WeekOffset += days; renderDiary(); }
function b7LocalDate(day) {
  return day.getFullYear() + '-' + String(day.getMonth() + 1).padStart(2,'0') +
    '-' + String(day.getDate()).padStart(2,'0');
}
function b7CalendarUrl(item) {
  const dates = item.starts_at.replace(/[-:]/g, '') + '00/' + item.ends_at.replace(/[-:]/g, '') + '00';
  const title = (item.kind === 'site_visit' ? 'Plumbing site visit' : 'Plumbing job') + ' · ' + item.customer_name;
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
  const first = b7LocalDate(monday);
  const last = b7LocalDate(sunday);
  document.getElementById('diaryWeek').innerText = monday.toLocaleDateString('en-GB') + ' – ' + sunday.toLocaleDateString('en-GB');
  const visible = b7Appointments.filter(a => a.starts_at.slice(0,10) >= first && a.starts_at.slice(0,10) <= last);
  const followUps = b7Appointments.filter(a => a.status === 'provisional' && a.provisional_follow_up &&
    a.provisional_follow_up <= b7LocalDate(new Date()));
  document.getElementById('diaryList').innerHTML =
    (followUps.length ? '<p><strong>Provisional bookings to follow up:</strong> ' +
      followUps.map(a => '#' + a.id + ' ' + escapeHtml(a.customer_name)).join(', ') + '</p>' : '') +
    (visible.map(a => '<div class="history-item"><strong>' + escapeHtml(a.customer_name) +
      '</strong> · ' + escapeHtml(a.kind.replace('_',' ')) + ' · ' + escapeHtml(a.status) +
      '<div>' + escapeHtml(a.starts_at.replace('T',' ')) + '–' + escapeHtml(a.ends_at.slice(11)) +
      ' · Lead #' + Number(a.lead_id) + '</div><div class="small">' + escapeHtml(a.notes || '') + '</div>' +
      '<button type="button" class="btn-light" onclick="editDiaryAppointment(' + Number(a.id) + ')">Update</button> ' +
      '<a class="btn-link btn-secondary" target="_blank" rel="noopener" href="' + b7CalendarUrl(a) +
      '">Add to Google Calendar</a></div>').join('') || '<p class="small">No appointments this week.</p>');
}
function editDiaryAppointment(id) {
  const a = b7Appointments.find(x => x.id === id);
  if (!a) return;
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

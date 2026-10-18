"""Won quotes can be booked without inventing an enquiry record."""
import secrets
import subprocess
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from local_browser_server import disposable_app
from test_business_growth_batch7 import authorization


class PipelineSchedulingTests(unittest.TestCase):
    def test_quote_only_two_day_booking_and_cancellation(self):
        user, password = secrets.token_urlsafe(12), secrets.token_urlsafe(18)
        with disposable_app(user, password) as (module, _), TestClient(module.app) as client:
            auth = authorization(user, password)
            quote = client.post('/api/quote', headers=auth, json={
                'customer_name':'Synthetic customer', 'job_description':'Pipework',
                'customer_phone':'07000000000', 'customer_address':'Test address',
                'labour_cost':250}).json()
            job = client.post('/api/jobs', headers=auth, json={
                'quote_id':quote['id'], 'title':'Pipework'}).json()
            booking = {'job_id':job['id'], 'kind':'job', 'status':'confirmed',
                       'starts_at':'2026-11-02T09:00', 'ends_at':'2026-11-03T17:00'}
            self.assertEqual(client.post('/api/appointments', headers=auth, json=booking).status_code, 422)
            client.put(f"/api/quotes/{quote['id']}/outcome", headers=auth, json={'status':'won'})
            card = client.get('/api/pipeline', headers=auth).json()['stages']['won_unscheduled'][0]
            self.assertEqual(card['won_quote_ids'], [quote['id']])
            saved = client.post('/api/appointments', headers=auth, json=booking)
            self.assertEqual(saved.status_code, 200, saved.text)
            self.assertIsNone(saved.json()['lead_id'])
            self.assertEqual(client.get('/api/appointments').status_code, 401)
            diary = client.get('/api/appointments', headers=auth).json()[0]
            self.assertEqual(diary['customer_name'], 'Synthetic customer')
            self.assertEqual(diary['quote_id'], quote['id'])
            self.assertEqual(diary['customer_address'], 'Test address')
            self.assertEqual(diary['ends_at'], booking['ends_at'])
            self.assertEqual(client.get('/api/pipeline', headers=auth).json()['stages']['scheduled'][0]['quote_ids'], [quote['id']])
            # Extra, nonconsecutive dates reuse the same job.
            extra = dict(booking, starts_at='2026-11-06T09:00', ends_at='2026-11-06T17:00')
            second = client.post('/api/appointments', headers=auth, json=extra).json()
            booking['status'] = 'cancelled'
            client.put(f"/api/appointments/{saved.json()['id']}", headers=auth, json=booking)
            self.assertEqual(client.get('/api/jobs', headers=auth).json()[0]['status'], 'scheduled')
            extra['status'] = 'cancelled'
            client.put(f"/api/appointments/{second['id']}", headers=auth, json=extra)
            self.assertEqual(client.get('/api/jobs', headers=auth).json()[0]['status'], 'awaiting_schedule')
            self.assertEqual(module.database_counts()['leads'], 0)
            self.assertEqual(len(client.get('/api/jobs', headers=auth).json()), 1)
            self.assertEqual(client.post('/api/appointments', headers=auth, json=dict(booking, kind='site_visit')).status_code, 422)
            self.assertEqual(client.post('/api/appointments', headers=auth, json=dict(booking, lead_id=999)).status_code, 422)
            self.assertEqual(client.post('/api/appointments', headers=auth, json=dict(booking, job_id=None)).status_code, 422)

    def test_legacy_diary_migration_preserves_rows_indexes_sequence_and_is_repeatable(self):
        with disposable_app('migration-user', 'migration-password') as (module, _):
            conn = module.get_db()
            conn.execute('DROP TABLE appointments')
            conn.execute('''CREATE TABLE appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id INTEGER NOT NULL,
                job_id INTEGER, kind TEXT NOT NULL, status TEXT NOT NULL,
                starts_at TEXT NOT NULL, ends_at TEXT NOT NULL, provisional_follow_up TEXT,
                notes TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                retained_extra TEXT)''')
            conn.execute('CREATE INDEX legacy_diary_index ON appointments(status)')
            conn.execute('''INSERT INTO appointments VALUES
                (7,42,NULL,'site_visit','confirmed','2026-11-02T09:00','2026-11-02T10:00',
                 NULL,'Keep notes','created','updated','keep extra')''')
            conn.execute("UPDATE sqlite_sequence SET seq=90 WHERE name='appointments'")
            before = tuple(conn.execute('SELECT * FROM appointments').fetchone())
            conn.commit()
            conn.close()
            module.init_db()
            module.init_db()
            conn = module.get_db()
            self.assertEqual(tuple(conn.execute('SELECT * FROM appointments').fetchone()), before)
            self.assertEqual(conn.execute("SELECT seq FROM sqlite_sequence WHERE name='appointments'").fetchone()[0], 90)
            self.assertTrue(conn.execute("SELECT 1 FROM sqlite_master WHERE name='legacy_diary_index'").fetchone())
            self.assertEqual(next(c for c in conn.execute('PRAGMA table_info(appointments)') if c['name']=='lead_id')['notnull'], 0)
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            conn.close()

    def test_pipeline_buttons_open_quote_and_reuse_job_in_booking_form(self):
        script = r'''
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const nodes = new Map(), alerts = [], tabs = [];
function node(id) {
  if (!nodes.has(id)) nodes.set(id, {get value(){return this._value || ''},set value(v){this._value=String(v)}, innerHTML:'', innerText:'',
    classList:{add(){},remove(){},toggle(){}},scrollIntoView(){}});
  return nodes.get(id);
}
const ctx = {document:{getElementById:node}, escapeHtml:String,
  showTab:id=>tabs.push(id),alert:s=>alerts.push(s)};
vm.createContext(ctx); vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
ctx.loadDiary=async()=>{};
let jobs=[], appointments=[], creates=0;
ctx.b7Request=async url=> url==='/api/pipeline' ? {stages:{won_unscheduled:[
  {name:'Synthetic',description:'',lead_id:null,quote_ids:[32],won_quote_ids:[32],job_ids:[]}]}} :
  url==='/api/jobs' ? jobs : url==='/api/appointments' ? appointments : {id:32,status:'won',lead_id:null,customer_name:'Synthetic',job:'Pipework'};
ctx.b7Post=async()=> {creates++; const job={id:9,quote_id:32,lead_id:null,status:'awaiting_schedule',title:'Pipework'};jobs.push(job);return job};
async function run(){
  await ctx.loadPipeline();
  assert.match(node('pipelineBoard').innerHTML,/loadSavedQuote\(32\)/);
  assert.match(node('pipelineBoard').innerHTML,/bookPipelineQuote\(32\)/);
  await Promise.all([ctx.bookPipelineQuote(32),ctx.bookPipelineQuote(32)]);
  await ctx.bookPipelineQuote(32);
  assert.equal(creates,1);assert.equal(alerts.length,0);assert.equal(tabs.at(-1),'diaryTab');
  assert.equal(node('appointmentLeadId').value,'');assert.equal(node('appointmentJobId').value,'9');
  assert.equal(node('appointmentKind').value,'job');assert.match(node('appointmentContext').innerText,/Synthetic.*Quote #32/);
  assert.equal(node('appointmentStart').value,'');assert.equal(node('appointmentEditor').open,true);
  appointments=[{id:12,job_id:9,lead_id:null,quote_id:32,kind:'job',status:'confirmed',customer_name:'Synthetic',starts_at:'2026-11-02T09:00',ends_at:'2026-11-03T17:00'}];
  ctx.renderDiary=()=>{};
  await ctx.bookPipelineQuote(32);
  assert.equal(node('appointmentEditId').value,'12');
  assert.equal(node('appointmentStart').value,'2026-11-02T09:00');
  ctx.addJobBookingDates();
  assert.equal(node('appointmentEditId').value,'');assert.equal(node('appointmentJobId').value,'9');
  assert.equal(creates,1);
  ctx.b7Request=async()=>({status:'pending'});await ctx.bookPipelineQuote(32);
  assert.match(alerts.at(-1),/won/);assert.equal(creates,1);
}
run().catch(e=>{console.error(e);process.exitCode=1});
'''
        result = subprocess.run(['node', '-e', script, str(Path(__file__).resolve().parents[1] / 'static/pipeline.js')],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

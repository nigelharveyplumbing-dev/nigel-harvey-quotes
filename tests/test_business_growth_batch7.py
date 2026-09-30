"""Batch 7 pipeline, appointments and Quick Add using disposable SQLite."""

import base64
import secrets
import shutil
import sqlite3
import subprocess
import unittest
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
from local_browser_server import disposable_app


def authorization(user, password):
    encoded = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": "Basic " + encoded}


class Batch7Tests(unittest.TestCase):
    def test_quick_add_recognises_address_and_signed_name_only_with_clear_evidence(self):
        from business.quick_add import preview

        example = ("Hi Nigel, regarding our conversation our address is "
                   "17 Carroll Avenue, Guildford, Surrey, GU1 2QJ\nBest regards John Ashby")
        address = "17 Carroll Avenue, Guildford, Surrey, GU1 2QJ"
        for message in (example,
                        "My address is " + address + "\nBest regards,\nJohn Ashby",
                        "The address is " + address + "\nRegards John Ashby",
                        "Address is " + address + "\nRegards,\nJohn Ashby",
                        "Address: " + address + "\nThanks John Ashby",
                        address + "\nThanks,\nJohn Ashby"):
            with self.subTest(message=message):
                result = preview(message)
                self.assertEqual(result["name"], "John Ashby")
                self.assertEqual(result["address"], address)
                self.assertEqual(result["postcode"], "GU12QJ")
                self.assertEqual(result["description"], message)
                self.assertTrue(result["needs_review"])
        for message in ("Hi Nigel, my tap is leaking. Thanks for your help",
                        "Hi Nigel\nThe address is near Guildford\nRegards,\nPlease call me",
                        "I discussed 17 taps with Nigel. Best regards to your team"):
            with self.subTest(uncertain=message):
                result = preview(message)
                self.assertEqual(result["name"], "")
                self.assertEqual(result["address"], "")
        result = preview("Hi Nigel\nName: John Ashby\nAddress: 17 Carroll Avenue\n"
                         "Call 07595 725547 or email john@example.com")
        self.assertEqual(result["name"], "John Ashby")
        self.assertEqual(result["address"], "17 Carroll Avenue")
        self.assertEqual(result["phone"], "07595 725547")
        self.assertEqual(result["email"], "john@example.com")

    def test_multi_job_quick_add_suggestions_are_review_only_and_conservative(self):
        from business.quick_add import preview
        message = ("Hi Nigel, can you replace our kitchen tap and also have a look at the toilet "
                   "as the flush isn't working properly. Our address is "
                   "17 Carroll Avenue, Guildford, Surrey, GU1 2QJ.\nBest regards,\nJohn Ashby")
        result = preview(message)
        self.assertEqual(result["name"], "John Ashby")
        self.assertEqual(result["address"], "17 Carroll Avenue, Guildford, Surrey, GU1 2QJ")
        self.assertEqual(result["suggested_work_types"], ["Tap", "Toilet / cistern"])
        self.assertEqual(result["description"], message)
        self.assertTrue(result["needs_review"])
        self.assertEqual(preview("Radiator valve is leaking and the kitchen tap is dripping.")
                         ["suggested_work_types"], ["Tap", "Radiator / TRV"])
        for uncertain in ("Tap to continue. We have toilet paper to deliver.",
                          "Hi Nigel, could we discuss some work soon? Regards, John Ashby"):
            self.assertEqual(preview(uncertain)["suggested_work_types"], [])

    def test_inline_sentence_signoff_requires_a_credible_closing(self):
        from business.quick_add import preview

        exact_iphone_message = ("Hi Nigel, can you replace our kitchen tap and also have a look at the "
            "toilet as the flush isn't working properly. Our address is 17 Carroll Avenue, "
            "Guildford, Surrey, GU1 2QJ. Best regards, John Ashby")
        result = preview(exact_iphone_message)
        self.assertEqual(result["name"], "John Ashby")
        self.assertEqual(result["address"], "17 Carroll Avenue, Guildford, Surrey, GU1 2QJ")
        self.assertEqual(result["suggested_work_types"], ["Tap", "Toilet / cistern"])
        self.assertEqual(result["description"], exact_iphone_message)
        self.assertTrue(result["needs_review"])

        for closing in (". Best regards, John Ashby", ". Best regards John Ashby",
                        ". Regards, John Ashby", ". Thanks, John Ashby",
                        "! Thanks John Ashby", "? Regards John Ashby",
                        "\nBest regards, John Ashby", "\nRegards,\nJohn Ashby"):
            with self.subTest(closing=closing):
                self.assertEqual(preview("Please call me" + closing)["name"], "John Ashby")
        for ordinary in ("Hi Nigel, thanks for your help.",
                         "Hi Nigel, could you replace a tap? Thanks for looking into it.",
                         "I told Nigel: best regards, John Ashby",
                         "Hi Nigel, our address is 17 Carroll Avenue. Thanks for your time"):
            with self.subTest(ordinary=ordinary):
                self.assertEqual(preview(ordinary)["name"], "")

    def test_primary_additional_types_survive_visit_quote_and_reporting_without_double_count(self):
        user, password = secrets.token_urlsafe(12), secrets.token_urlsafe(18)
        with disposable_app(user, password) as (module, _):
            with TestClient(module.app) as client:
                auth = authorization(user, password)
                message = ("Please replace the kitchen tap and repair the toilet flush. "
                           "Our address is 17 Carroll Avenue, Guildford, Surrey, GU1 2QJ\n"
                           "Best regards John Ashby")
                suggested = client.post("/api/quick-add/preview", headers=auth,
                                        json={"message": message}).json()
                self.assertEqual(suggested["suggested_work_types"], ["Tap", "Toilet / cistern"])
                self.assertEqual(module.database_counts()["leads"], 0)
                payload = {"idempotency_key": secrets.token_urlsafe(22),
                           "name": suggested["name"], "email": "john@example.test", "phone": "07123456789",
                           "address": suggested["address"], "description": message,
                           "source_category": "Referral", "work_type": "Tap",
                           "additional_work_types": ["Toilet / cistern"],
                           "visit_starts_at": "2026-10-02T10:00", "visit_ends_at": "2026-10-02T10:30"}
                invalid = dict(payload, idempotency_key=secrets.token_urlsafe(22),
                               additional_work_types=["Tap"])
                self.assertEqual(client.post("/api/quick-add/confirm", headers=auth,
                                             json=invalid).status_code, 422)
                self.assertEqual(module.database_counts()["leads"], 0)
                saved = client.post("/api/quick-add/confirm", headers=auth, json=payload)
                self.assertEqual(saved.status_code, 200, saved.text)
                lead = saved.json()["lead"]
                self.assertEqual(lead["work_type"], "Tap")
                self.assertEqual(lead["additional_work_types"], ["Toilet / cistern"])
                self.assertEqual(client.get("/api/leads", headers=auth).json()[0]["additional_work_types"],
                                 ["Toilet / cistern"])
                self.assertEqual(module.database_counts()["quotes"], 0)
                appointments = client.get("/api/appointments", headers=auth).json()
                self.assertEqual(len(appointments), 1)
                self.assertEqual((appointments[0]["kind"], appointments[0]["job_id"]),
                                 ("site_visit", None))
                stage = client.get("/api/pipeline", headers=auth).json()["stages"]
                self.assertEqual(len(stage["visit_booked"]), 1)
                self.assertEqual(stage["scheduled"], [])
                self.assertEqual(client.post("/api/appointments", headers=auth, json={
                    "lead_id":lead["id"], "kind":"job", "status":"confirmed",
                    "starts_at":"2026-10-05T09:00", "ends_at":"2026-10-05T17:00"}).status_code, 422)
                visit = dict(payload, lead_id=lead["id"], kind="site_visit", status="completed",
                             starts_at=payload["visit_starts_at"], ends_at=payload["visit_ends_at"])
                self.assertEqual(client.put(f"/api/appointments/{appointments[0]['id']}", headers=auth,
                                            json=visit).status_code, 200)
                stage = client.get("/api/pipeline", headers=auth).json()["stages"]
                self.assertTrue(stage["visit_booked"][0]["visit_completed"])
                quote = client.post("/api/quote", headers=auth, json={
                    "lead_id": lead["id"], "customer_name":lead["name"],
                    "customer_phone":lead["phone"], "customer_email":lead["email"],
                    "customer_address":lead["address"], "job_description":lead["description"],
                    "source_category":lead["source_category"], "work_type":lead["work_type"],
                    "additional_work_types":lead["additional_work_types"], "labour_cost":120})
                self.assertEqual(quote.status_code, 200, quote.text)
                self.assertEqual(quote.json()["additional_work_types"], ["Toilet / cistern"])
                self.assertEqual(quote.json()["request"]["customer_email"], "john@example.test")
                self.assertEqual(client.get("/api/pipeline", headers=auth).json()["stages"]
                                 ["quote_pending"][0]["lead_id"], lead["id"])
                self.assertEqual(client.get("/api/business-performance", headers=auth).json()
                                 ["enquiries"], 1)
                report = client.get("/api/business-performance", headers=auth).json()
                self.assertEqual(report["quotes_saved"], 1)
                self.assertEqual(report["by_source"]["Referral"]["quotes"], 1)
                prewon_job = client.post("/api/jobs", headers=auth, json={
                    "lead_id":lead["id"], "quote_id":quote.json()["id"],
                    "title":"Tap and cistern repair", "status":"awaiting_schedule"}).json()
                booking_payload = {"lead_id":lead["id"], "job_id":prewon_job["id"],
                                   "kind":"job", "status":"confirmed",
                                   "starts_at":"2026-10-05T09:00", "ends_at":"2026-10-05T17:00"}
                self.assertEqual(client.post("/api/appointments", headers=auth,
                                             json=booking_payload).status_code, 422)
                won = client.put(f"/api/quotes/{quote.json()['id']}/outcome", headers=auth,
                                 json={"status":"won"})
                self.assertEqual(won.status_code, 200, won.text)
                self.assertEqual(client.get("/api/pipeline", headers=auth).json()["stages"]
                                 ["won_unscheduled"][0]["lead_id"], lead["id"])
                self.assertEqual(client.get("/api/pipeline", headers=auth).json()["stages"]["scheduled"], [])
                self.assertEqual(client.get("/api/business-performance", headers=auth).json()
                                 ["by_source"]["Referral"]["wins"], 1)
                booking = client.post("/api/appointments", headers=auth, json=booking_payload)
                self.assertEqual(booking.status_code, 200, booking.text)
                self.assertEqual(client.get("/api/appointments", headers=auth).json()[-1]["kind"], "job")

    def test_additive_work_type_migration_keeps_legacy_primary_and_quote(self):
        user, password = secrets.token_urlsafe(12), secrets.token_urlsafe(18)
        with disposable_app(user, password) as (module, _):
            with TestClient(module.app) as client:
                auth = authorization(user, password)
                lead = client.post("/api/leads", json={"name":"Existing", "description":"Tap",
                                                       "work_type":"Tap"}).json()
                quote = client.post("/api/quote", headers=auth, json={
                    "customer_name":"Existing", "job_description":"Tap", "labour_cost":100,
                    "work_type":"Tap", "lead_id":lead["id"]}).json()
                module.init_db(); module.init_db()
                self.assertEqual(client.get("/api/leads", headers=auth).json()[0]["work_type"], "Tap")
                self.assertEqual(client.get("/api/leads", headers=auth).json()[0]
                                 ["additional_work_types"], [])
                self.assertEqual(client.get(f"/api/quotes/{quote['id']}", headers=auth).json()
                                 ["additional_work_types"], [])
                self.assertEqual(module.database_counts()["quotes"], 1)
                conn = module.get_db()
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                for table in ("leads", "quotes"):
                    self.assertIn("additional_work_types", {r["name"] for r in conn.execute(
                        f"PRAGMA table_info({table})")})
                conn.close()

    def test_accidental_enquiry_and_visits_delete_without_touching_other_work(self):
        user, password = secrets.token_urlsafe(12), secrets.token_urlsafe(18)
        with disposable_app(user, password) as (module, _):
            with TestClient(module.app) as client:
                auth = authorization(user, password)
                plain = client.post("/api/leads", json={"name":"Plain", "description":"Question"}).json()
                self.assertEqual(client.get(f"/api/leads/{plain['id']}/deletion-check").status_code, 401)
                self.assertEqual(client.get(f"/api/leads/{plain['id']}/deletion-check",
                                            headers=auth).json()["site_visit_count"], 0)
                self.assertEqual(client.delete(f"/api/leads/{plain['id']}", headers=auth).json(), {"ok":True})
                self.assertEqual(client.get(f"/api/leads/{plain['id']}/deletion-check",
                                            headers=auth).status_code, 404)

                other = client.post("/api/leads", json={"name":"Other", "phone":"07111000000",
                                                           "description":"Another job"}).json()
                other_quote = client.post("/api/quote", headers=auth, json={
                    "customer_name":"Other", "customer_phone":"07111000000",
                    "job_description":"Another job", "labour_cost":80, "lead_id":other["id"]}).json()
                other_job = client.post("/api/jobs", headers=auth, json={
                    "lead_id":other["id"], "quote_id":other_quote["id"],
                    "title":"Other plumbing job"}).json()
                payload = {"idempotency_key":secrets.token_urlsafe(22), "name":"Accidental",
                           "phone":"07999000000", "address":"17 Carroll Avenue, Guildford",
                           "description":"Replace tap and repair flush", "work_type":"Tap",
                           "additional_work_types":["Toilet / cistern"],
                           "visit_starts_at":"2026-10-03T10:00", "visit_ends_at":"2026-10-03T10:30"}
                created = client.post("/api/quick-add/confirm", headers=auth, json=payload).json()
                lead_id, contact_id = created["lead"]["id"], created["lead"]["customer_id"]
                second_visit = client.post("/api/appointments", headers=auth, json={
                    "lead_id":lead_id, "kind":"site_visit", "status":"provisional",
                    "starts_at":"2026-10-04T11:00", "ends_at":"2026-10-04T11:30",
                    "provisional_follow_up":"2026-10-02"})
                self.assertEqual(second_visit.status_code, 200, second_visit.text)
                preview = client.get(f"/api/leads/{lead_id}/deletion-check", headers=auth).json()
                self.assertEqual(preview["site_visit_count"], 2)
                self.assertTrue(preview["can_delete"])
                self.assertTrue(preview["customer_contact_will_be_deleted"])
                self.assertEqual(client.delete(f"/api/leads/{lead_id}", headers=auth).status_code, 409)
                self.assertEqual(client.delete(f"/api/leads/{lead_id}?confirm_visits=1",
                                               headers=auth).status_code, 409)
                self.assertEqual(client.delete(f"/api/leads/{lead_id}?confirm_visits=2",
                                               headers=auth).json(), {"ok":True})
                self.assertFalse(any(a["lead_id"] == lead_id for a in
                                     client.get("/api/appointments", headers=auth).json()))
                self.assertFalse(any(l["id"] == lead_id for l in client.get("/api/leads", headers=auth).json()))
                conn = module.get_db()
                self.assertIsNone(conn.execute("SELECT id FROM customers WHERE id=?", (contact_id,)).fetchone())
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                conn.close()
                self.assertEqual(client.get(f"/api/quotes/{other_quote['id']}", headers=auth).status_code, 200)
                self.assertIn(other_job["id"], [j["id"] for j in client.get("/api/jobs", headers=auth).json()])
                self.assertEqual(client.get("/api/pipeline", headers=auth).json()["total"], 1)
                self.assertEqual(client.get("/api/business-performance", headers=auth).json()["enquiries"], 1)

    def test_quote_job_and_invoice_history_block_cascade_and_shared_customer_survives(self):
        user, password = secrets.token_urlsafe(12), secrets.token_urlsafe(18)
        with disposable_app(user, password) as (module, _):
            with TestClient(module.app) as client:
                auth = authorization(user, password)
                base = {"name":"Shared Customer", "phone":"07111000001", "address":"2 Main Road",
                        "description":"Tap repair", "visit_starts_at":"2026-10-05T10:00",
                        "visit_ends_at":"2026-10-05T10:30"}
                first = client.post("/api/quick-add/confirm", headers=auth,
                    json={**base,"idempotency_key":secrets.token_urlsafe(22)}).json()["lead"]
                second = client.post("/api/quick-add/confirm", headers=auth,
                    json={**base,"idempotency_key":secrets.token_urlsafe(22)}).json()["lead"]
                self.assertEqual(first["customer_id"], second["customer_id"])
                quote = client.post("/api/quote", headers=auth, json={
                    "customer_name":second["name"], "customer_phone":second["phone"],
                    "customer_address":second["address"], "job_description":"Tap repair",
                    "labour_cost":100, "lead_id":second["id"]}).json()
                invoice = client.post(f"/api/quotes/{quote['id']}/to-invoice", headers=auth).json()
                client.post(f"/api/invoices/{invoice['id']}/status", headers=auth,
                            json={"status":"paid", "amount_paid":invoice["total_price"]})
                check = client.get(f"/api/leads/{second['id']}/deletion-check", headers=auth).json()
                self.assertFalse(check["can_delete"])
                self.assertIn("saved quote", check["reason"])
                self.assertEqual(client.delete(f"/api/leads/{second['id']}?confirm_visits=1",
                                               headers=auth).status_code, 409)
                self.assertEqual(client.get(f"/api/quotes/{quote['id']}", headers=auth).status_code, 200)
                self.assertEqual(client.get(f"/api/invoices/{invoice['id']}", headers=auth).status_code, 200)
                # The first accidental lead can be removed, but its shared
                # customer and the second lead's paid invoice stay intact.
                first_check = client.get(f"/api/leads/{first['id']}/deletion-check", headers=auth).json()
                self.assertFalse(first_check["customer_contact_will_be_deleted"])
                self.assertEqual(client.delete(f"/api/leads/{first['id']}?confirm_visits=1",
                                               headers=auth).status_code, 200)
                self.assertEqual(client.get(f"/api/customers/{first['customer_id']}/history",
                                            headers=auth).status_code, 200)
                self.assertEqual(client.get(f"/api/invoices/{invoice['id']}", headers=auth).json()["status"], "paid")
                job_only = client.post("/api/leads", json={"name":"Job only", "description":"Work"}).json()
                job = client.post("/api/jobs", headers=auth, json={
                    "lead_id":job_only["id"], "title":"Existing work"}).json()
                blocked = client.get(f"/api/leads/{job_only['id']}/deletion-check", headers=auth).json()
                self.assertFalse(blocked["can_delete"])
                self.assertIn("plumbing job", blocked["reason"])
                self.assertEqual(client.delete(f"/api/leads/{job_only['id']}", headers=auth).status_code, 409)
                self.assertIn(job["id"], [j["id"] for j in client.get("/api/jobs", headers=auth).json()])
                self.assertEqual(module.database_counts()["invoices"], 1)

    def test_lead_and_visits_delete_rollback_together_on_database_error(self):
        user, password = secrets.token_urlsafe(12), secrets.token_urlsafe(18)
        with disposable_app(user, password) as (module, _):
            with TestClient(module.app) as client:
                auth = authorization(user, password)
                lead = client.post("/api/leads", json={"name":"Rollback", "description":"Tap"}).json()
                client.post("/api/appointments", headers=auth, json={
                    "lead_id":lead["id"], "kind":"site_visit", "status":"confirmed",
                    "starts_at":"2026-10-05T10:00", "ends_at":"2026-10-05T10:30"})
                conn = module.get_db()
                conn.execute(f"""CREATE TRIGGER prevent_lead_delete BEFORE DELETE ON leads
                    WHEN OLD.id={int(lead['id'])} BEGIN SELECT RAISE(ABORT, 'test rollback'); END""")
                conn.commit(); conn.close()
                with self.assertRaises(sqlite3.IntegrityError):
                    module.delete_lead_by_id(lead["id"], 1)
                self.assertEqual(len(client.get("/api/appointments", headers=auth).json()), 1)
                self.assertEqual(len(client.get("/api/leads", headers=auth).json()), 1)
                conn = module.get_db()
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                conn.close()

    @unittest.skipUnless(shutil.which("node"), "Node is required for lead delete UI coverage")
    def test_lead_delete_ui_requires_informed_confirmation_and_honours_cancel(self):
        script = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const start = source.indexOf('async function deleteLead(id) {');
const end = source.indexOf('\n\nasync function ', start + 1);
assert(start >= 0 && end > start);
const calls = [], prompts = [], notices = [], alerts = [];
let preview = {can_delete:true, site_visit_count:2,
  customer_contact_will_be_deleted:true}, accepted = false;
const context = {fetch:async(url, options={})=>{
  calls.push([url, options.method || 'GET']);
  return {ok:true, json:async()=>options.method === 'DELETE' ? {ok:true} : preview};
}, confirm:message=>{prompts.push(message); return accepted}, alert:message=>alerts.push(message),
  loadLeads:async()=>{}, loadDashboard:async()=>{}, showNotice:message=>notices.push(message)};
vm.createContext(context);
vm.runInContext(source.slice(start,end), context);
async function run() {
  await context.deleteLead(17);
  assert.equal(calls.length,1);
  assert.match(prompts[0],/2 linked site visits/);
  assert.match(prompts[0],/contact created with it/);
  assert.match(prompts[0],/cannot be undone/);
  accepted=true;
  await context.deleteLead(17);
  assert.deepEqual(calls.at(-1),['/api/leads/17?confirm_visits=2','DELETE']);
  assert.match(notices.at(-1),/site visits deleted/);
  preview = {can_delete:false, reason:'This enquiry has a saved quote.', site_visit_count:1};
  const before=calls.length;
  await context.deleteLead(18);
  assert.equal(calls.length,before+1);
  assert.match(alerts.at(-1),/saved quote/);
}
run().catch(e=>{console.error(e); process.exitCode=1});
'''
        path = Path(__file__).resolve().parents[1] / "static" / "app.js"
        result = subprocess.run(["node", "-e", script, str(path)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node is required for Quick Add browser workflow")
    def test_quick_add_save_exposes_lead_visit_quote_actions_and_diary_location(self):
        source = Path(__file__).resolve().parents[1]
        script = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const nodes = new Map(), tabs = [], notices = [];
function node(id) {
  if (!nodes.has(id)) {
    const classes = new Set(['hidden']);
    nodes.set(id, {value:'', innerHTML:'', classList:{add:c=>classes.add(c),
      remove:c=>classes.delete(c), contains:c=>classes.has(c)},
      scrollIntoView(){this.scrolled=true}});
  }
  return nodes.get(id);
}
const context = {document:{getElementById:node}, crypto:{randomUUID:()=> 'a'.repeat(32)},
  escapeHtml:s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;'),
  loadLeads:async()=>{}, showTab:id=>tabs.push(id), showNotice:s=>notices.push(s),
  alert:s=>{throw Error(s)}};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
async function run() {
  vm.runInContext("b7QuickKey = 'a'.repeat(32)", context);
  context.b7Post = async()=>({lead:{id:42,name:'John Ashby'},appointment_id:7});
  node('quickName').value='John Ashby'; node('quickDescription').value='Original message';
  await vm.runInContext('saveQuickLead()', context);
  const next=node('quickNext');
  assert.equal(next.classList.contains('hidden'),false);
  assert.equal(next.scrolled,true);
  assert.match(next.innerHTML,/Open Lead/);
  assert.match(next.innerHTML,/View Visit in Diary/);
  assert.match(next.innerHTML,/Start Quote/);
  assert.match(next.innerHTML,/Google Calendar.*draft/);
  assert.doesNotMatch(next.innerHTML,/Book Site Visit/);
  assert.equal(node('quickMessage').value,'');
  assert.equal(notices.length,1);
  vm.runInContext("b7Appointments = [{id:7,starts_at:'2026-10-02T10:00'}]",context);
  context.loadDiary=async()=>{}; context.renderDiary=()=>{};
  await vm.runInContext('openQuickVisit(7)',context);
  assert.equal(tabs.at(-1),'diaryTab');
  assert.equal(node('diary_appointment_7').scrolled,true);
  context.SAVED_LEADS=[{id:42}];
  context.startQuoteFromLead=id=>{context.quotedLead=id};
  await vm.runInContext('quoteFromDiaryLead(42)',context);
  assert.equal(context.quotedLead,42);
  assert.equal(node('quotesTab').scrolled,true);
  vm.runInContext("showQuickNextActions({lead:{id:43,name:'Jane Smith'}})",context);
  assert.match(next.innerHTML,/Book Site Visit/);
  assert.match(next.innerHTML,/Start Quote/);
  assert.doesNotMatch(next.innerHTML,/View Visit in Diary/);
}
run().catch(e=>{console.error(e); process.exitCode=1});
'''
        result = subprocess.run(["node", "-e", script, str(source / "static" / "pipeline.js")],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        with disposable_app("quickadd-user", "quickadd-pass") as (module, _):
            with TestClient(module.app) as client:
                page = client.get("/app", headers=authorization("quickadd-user", "quickadd-pass"))
                self.assertIn('id="quickNext"', page.text)

    @unittest.skipUnless(shutil.which("node"), "Node is required for multi-work-type UI workflow")
    def test_mobile_preview_suggestions_and_lead_to_quote_controls(self):
        source = Path(__file__).resolve().parents[1]
        script = r'''
const assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
const nodes=new Map();
function node(id) {
  if (!nodes.has(id)) nodes.set(id,{value:'',innerHTML:'',checkedInputs:[],
    querySelectorAll(){return this.checkedInputs},
    classList:{add(){},remove(){}},scrollIntoView(){}});
  return nodes.get(id);
}
const context={document:{getElementById:node}, crypto:{randomUUID:()=> 'b'.repeat(32)},
  escapeHtml:s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;'),
  startNewQuote(){},toggleBathroomFields(){},updateLabourSuggestion(){},scheduleQuoteLearning(){},
  showTab(){},setEditingStatus(){},alert:s=>{throw Error(s)}};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
const app=fs.readFileSync(process.argv[2],'utf8');
const start=app.indexOf('function startQuoteFromLead(id) {');
const end=app.indexOf('\n\nasync function saveLeadClassification(',start);
assert.ok(start>=0 && end>start);
vm.runInContext(app.slice(start,end),context);
async function run() {
  const message='Hi Nigel, replace our kitchen tap and fix the toilet flush. Best regards John Ashby';
  context.b7Post=async(url,data)=>{
    assert.equal(url,'/api/quick-add/preview'); assert.equal(data.message,message);
    return {name:'John Ashby',description:message,suggested_work_types:['Tap','Toilet / cistern'],hint:'Review'};
  };
  node('quickMessage').value=message;
  await vm.runInContext('previewQuickLead()',context);
  assert.equal(node('quickWork').value,'Tap');
  assert.match(node('quickAdditional').innerHTML,/Toilet \/ cistern/);
  assert.match(node('quickAdditional').innerHTML,/checked/);
  node('quickAdditional').checkedInputs=[{value:'Toilet / cistern'}];
  assert.deepEqual(Array.from(vm.runInContext("b7SelectedAdditional('quickAdditional','Tap')",context)),
    ['Toilet / cistern']);
  context.SAVED_LEADS=[{id:9,name:'John Ashby',phone:'07123456789',
    email:'john@example.test',address:'17 Carroll Avenue, Guildford, Surrey, GU1 2QJ',
    description:message,source_category:'Referral',work_type:'Tap',
    additional_work_types:['Toilet / cistern'],job_type:'small'}];
  vm.runInContext('startQuoteFromLead(9)',context);
  assert.equal(node('quote_source').value,'Referral');
  assert.equal(node('quote_work_type').value,'Tap');
  assert.match(node('quoteAdditional').innerHTML,/checked/);
  assert.equal(node('customer_email').value,'john@example.test');
  assert.equal(node('customer_address').value,'17 Carroll Avenue, Guildford, Surrey, GU1 2QJ');
  assert.equal(node('job').value,message);
}
run().catch(e=>{console.error(e);process.exitCode=1});
'''
        result = subprocess.run(["node", "-e", script, str(source / "static" / "pipeline.js"),
                                 str(source / "static" / "app.js")], capture_output=True, text=True,
                                timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_quick_add_preview_is_conservative_and_confirm_is_atomic_idempotent(self):
        user, password = secrets.token_urlsafe(12), secrets.token_urlsafe(18)
        with disposable_app(user, password) as (module, _):
            with TestClient(module.app) as client:
                auth = authorization(user, password)
                message = "Name: Jane Smith\nAddress: 2 Main Road, Guildford GU1 2AB\nCall 07595 725547\nLeaking tap. Visit 02/10/2026 at 10:30"
                self.assertEqual(client.post("/api/quick-add/preview", json={"message": message}).status_code, 401)
                preview = client.post("/api/quick-add/preview", json={"message": message}, headers=auth).json()
                self.assertEqual(preview["name"], "Jane Smith")
                self.assertEqual(preview["postcode"], "GU12AB")
                self.assertEqual(preview["visit_starts_at"], "2026-10-02T10:30")
                self.assertTrue(preview["needs_review"])
                self.assertEqual(module.database_counts()["leads"], 0)
                payload = {"idempotency_key": secrets.token_urlsafe(22), "name": preview["name"],
                           "phone": preview["phone"], "address": preview["address"],
                           "description": preview["description"], "source_category": "Referral",
                           "work_type": "Tap", "visit_starts_at": preview["visit_starts_at"],
                           "visit_ends_at": preview["visit_ends_at"]}
                unidentified = {**payload, "idempotency_key": secrets.token_urlsafe(22),
                                "name": "", "phone": "", "email": ""}
                self.assertEqual(client.post("/api/quick-add/confirm", json=unidentified,
                                             headers=auth).status_code, 422)
                self.assertEqual(module.database_counts()["leads"], 0)
                self.assertEqual(client.post("/api/quick-add/confirm", json=payload).status_code, 401)
                created = client.post("/api/quick-add/confirm", json=payload, headers=auth)
                self.assertEqual(created.status_code, 200, created.text)
                lead = created.json()["lead"]
                self.assertEqual(lead["source_category"], "Referral")
                self.assertEqual(lead["work_type"], "Tap")
                self.assertEqual(lead["status"], "new")
                self.assertIsNotNone(lead["customer_id"])
                again = client.post("/api/quick-add/confirm", json=payload, headers=auth).json()
                self.assertTrue(again["already_created"])
                self.assertEqual(again["lead"]["id"], lead["id"])
                self.assertEqual(module.database_counts()["leads"], 1)
                self.assertEqual(module.database_counts()["customers"], 1)
                visits = client.get("/api/appointments", headers=auth).json()
                self.assertEqual(len(visits), 1)
                self.assertEqual(visits[0]["lead_id"], lead["id"])
                deletion_check = client.get(f"/api/leads/{lead['id']}/deletion-check", headers=auth)
                self.assertEqual(deletion_check.status_code, 200)
                self.assertEqual(deletion_check.json()["site_visit_count"], 1)
                self.assertEqual(client.delete(f"/api/leads/{lead['id']}", headers=auth).status_code, 409)
                self.assertEqual(module.database_counts()["quotes"], 0)
                bad = dict(payload, idempotency_key=secrets.token_urlsafe(22),
                           visit_ends_at="2026-10-02T09:00")
                self.assertEqual(client.post("/api/quick-add/confirm", json=bad, headers=auth).status_code, 422)
                self.assertEqual(module.database_counts()["leads"], 1)
                self.assertEqual(module.database_counts()["customers"], 1)
                no_guess = client.post("/api/quick-add/preview", headers=auth,
                    json={"message":"Could you come Thursday morning? My tap is leaking."}).json()
                self.assertEqual(no_guess["visit_starts_at"], "")
                pencilled = dict(payload, idempotency_key=secrets.token_urlsafe(22),
                                  visit_status="provisional")
                self.assertEqual(client.post("/api/quick-add/confirm", json=pencilled,
                    headers=auth).status_code, 422)
                self.assertEqual(module.database_counts()["leads"], 1)
                self.assertEqual(module.database_counts()["customers"], 1)
                repeat_customer = dict(payload, idempotency_key=secrets.token_urlsafe(22),
                                       visit_starts_at="", visit_ends_at="")
                second = client.post("/api/quick-add/confirm", json=repeat_customer, headers=auth).json()
                self.assertEqual(second["lead"]["customer_id"], lead["customer_id"])
                self.assertEqual(module.database_counts()["customers"], 1)
                quote = client.post("/api/quote", headers=auth, json={
                    "customer_name":lead["name"], "customer_phone":lead["phone"],
                    "customer_address":lead["address"], "job_description":lead["description"],
                    "labour_cost":100, "lead_id":lead["id"]}).json()
                self.assertEqual(quote["customer_id"], lead["customer_id"])
                self.assertEqual(module.database_counts()["customers"], 1)

    def test_pipeline_prequote_visit_through_payment_and_multi_quote_precedence(self):
        user, password = secrets.token_urlsafe(12), secrets.token_urlsafe(18)
        with disposable_app(user, password) as (module, _):
            with TestClient(module.app) as client:
                auth = authorization(user, password)
                lead = client.post("/api/leads", json={"name":"Jane", "phone":"07000000000",
                    "description":"Tap replacement"}).json()
                lead_id = lead["id"]
                pipeline = client.get("/api/pipeline", headers=auth).json()
                self.assertEqual(pipeline["stages"]["new_enquiry"][0]["lead_id"], lead_id)
                visit = {"lead_id":lead_id,"kind":"site_visit","status":"provisional",
                    "starts_at":"2026-10-02T10:00","ends_at":"2026-10-02T11:00",
                    "provisional_follow_up":"2026-10-01"}
                self.assertEqual(client.post("/api/appointments", json=visit).status_code, 401)
                appointment = client.post("/api/appointments", json=visit, headers=auth).json()
                self.assertEqual(client.get("/api/pipeline", headers=auth).json()["stages"]["visit_booked"][0]["lead_id"], lead_id)
                visit.update(status="confirmed", provisional_follow_up="")
                self.assertEqual(client.put(f"/api/appointments/{appointment['id']}", json=visit,
                    headers=auth).status_code, 200)
                quote = client.post("/api/quote", headers=auth, json={
                    "customer_name":"Jane", "customer_phone":"07000000000",
                    "job_description":"Tap replacement", "labour_cost":100, "lead_id":lead_id}).json()
                self.assertEqual(client.get("/api/pipeline", headers=auth).json()["stages"]["quote_pending"][0]["lead_id"], lead_id)
                other = client.post("/api/quote", headers=auth, json={
                    "customer_name":"Jane", "customer_phone":"07000000000",
                    "job_description":"Other option", "labour_cost":80, "lead_id":lead_id}).json()
                client.put(f"/api/quotes/{quote['id']}/outcome", headers=auth, json={"status":"won"})
                client.put(f"/api/quotes/{other['id']}/outcome", headers=auth, json={"status":"lost"})
                self.assertEqual(client.get("/api/pipeline", headers=auth).json()["stages"]["won_unscheduled"][0]["lead_id"], lead_id)
                job_data = {"lead_id":lead_id, "quote_id":quote["id"], "title":"Replace tap",
                            "status":"awaiting_schedule"}
                job = client.post("/api/jobs", headers=auth, json=job_data).json()
                self.assertEqual(client.post("/api/jobs", headers=auth, json=job_data).status_code, 422)
                job_data["status"] = "scheduled"
                client.put(f"/api/jobs/{job['id']}", headers=auth, json=job_data)
                self.assertEqual(client.get("/api/pipeline", headers=auth).json()["stages"]["won_unscheduled"][0]["lead_id"], lead_id)
                booking = client.post("/api/appointments", headers=auth, json={
                    "lead_id":lead_id,"job_id":job["id"],"kind":"job","status":"confirmed",
                    "starts_at":"2026-10-02T09:00","ends_at":"2026-10-04T17:00"})
                self.assertEqual(booking.status_code, 200, booking.text)
                self.assertEqual(next(a for a in client.get("/api/appointments", headers=auth).json()
                                      if a["kind"] == "job")["ends_at"], "2026-10-04T17:00")
                self.assertEqual(client.get("/api/pipeline", headers=auth).json()["stages"]["scheduled"][0]["lead_id"], lead_id)
                job_data["status"] = "in_progress"
                client.put(f"/api/jobs/{job['id']}", headers=auth, json=job_data)
                self.assertEqual(client.get("/api/pipeline", headers=auth).json()["stages"]["in_progress"][0]["lead_id"], lead_id)
                job_data["status"] = "completed"
                client.put(f"/api/jobs/{job['id']}", headers=auth, json=job_data)
                self.assertEqual(client.get("/api/pipeline", headers=auth).json()["stages"]["completed_uninvoiced"][0]["lead_id"], lead_id)
                invoice = client.post(f"/api/quotes/{quote['id']}/to-invoice", headers=auth).json()
                self.assertEqual(client.get("/api/pipeline", headers=auth).json()["stages"]["invoiced_unpaid"][0]["lead_id"], lead_id)
                paid = client.post(f"/api/invoices/{invoice['id']}/status", headers=auth,
                    json={"status":"paid","amount_paid":invoice["total_price"]})
                self.assertEqual(paid.status_code, 200, paid.text)
                self.assertEqual(client.get("/api/pipeline", headers=auth).json()["stages"]["paid"][0]["lead_id"], lead_id)
                self.assertEqual(module.database_counts()["leads"], 1)
                self.assertEqual(module.database_counts()["quotes"], 2)
                self.assertEqual(module.database_counts()["invoices"], 1)
                self.assertEqual(client.get("/api/jobs").status_code, 401)
                self.assertEqual(client.get("/api/appointments").status_code, 401)

    def test_closed_quote_and_legacy_invoice_are_visible_without_reclassifying_history(self):
        user, password = secrets.token_urlsafe(12), secrets.token_urlsafe(18)
        with disposable_app(user, password) as (module, _):
            with TestClient(module.app) as client:
                auth = authorization(user, password)
                lead = client.post("/api/leads", json={"name":"Closed", "description":"Tap"}).json()
                quote = client.post("/api/quote", headers=auth, json={
                    "customer_name":"Closed", "job_description":"Tap", "labour_cost":100,
                    "lead_id":lead["id"]}).json()
                client.post("/api/appointments", headers=auth, json={
                    "lead_id":lead["id"],"kind":"site_visit","status":"confirmed",
                    "starts_at":"2026-10-02T10:00","ends_at":"2026-10-02T11:00"})
                client.put(f"/api/quotes/{quote['id']}/outcome", headers=auth, json={"status":"expired"})
                report = client.get("/api/pipeline", headers=auth).json()
                self.assertEqual(report["stages"]["closed_lost_expired"][0]["lead_id"], lead["id"])
                self.assertEqual(report["stages"]["visit_booked"], [])
                self.assertEqual(client.get("/api/appointments", headers=auth).json()[0]["lead_status"], "lost")
                orphan = client.post("/api/quote", headers=auth, json={
                    "customer_name":"Historical", "job_description":"Pipework", "labour_cost":80}).json()
                conn = module.get_db()
                conn.execute("UPDATE quotes SET status='unclassified' WHERE id=?", (orphan["id"],))
                conn.commit()
                conn.close()
                invoice = client.post(f"/api/quotes/{orphan['id']}/to-invoice", headers=auth).json()
                report = client.get("/api/pipeline", headers=auth).json()
                self.assertIn(invoice["id"], [i for card in report["stages"]["invoiced_unpaid"]
                                               for i in card["invoice_ids"]])
                self.assertEqual(client.get(f"/api/quotes/{orphan['id']}", headers=auth).json()["status"],
                                 "unclassified")

    def test_batch7_migration_is_idempotent_and_retains_existing_rows(self):
        user, password = secrets.token_urlsafe(12), secrets.token_urlsafe(18)
        with disposable_app(user, password) as (module, _):
            with TestClient(module.app) as client:
                auth = authorization(user, password)
                lead = client.post("/api/leads", json={"name":"Existing", "description":"Leaky pipe"}).json()
                before = module.database_counts()
                module.init_db()
                module.init_db()
                self.assertEqual(module.database_counts(), before)
                self.assertEqual(client.get("/api/leads", headers=auth).json()[0]["id"], lead["id"])
                conn = module.get_db()
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 0)
                conn.close()


if __name__ == "__main__":
    unittest.main()

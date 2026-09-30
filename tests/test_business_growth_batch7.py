"""Batch 7 pipeline, appointments and Quick Add using disposable SQLite."""

import base64
import secrets
import sqlite3
import unittest
from datetime import datetime

from fastapi.testclient import TestClient
from local_browser_server import disposable_app


def authorization(user, password):
    encoded = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": "Basic " + encoded}


class Batch7Tests(unittest.TestCase):
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
                self.assertEqual(client.post("/api/quick-add/confirm", json=payload).status_code, 401)
                created = client.post("/api/quick-add/confirm", json=payload, headers=auth)
                self.assertEqual(created.status_code, 200, created.text)
                lead = created.json()["lead"]
                self.assertEqual(lead["source_category"], "Referral")
                self.assertEqual(lead["work_type"], "Tap")
                self.assertEqual(lead["status"], "new")
                again = client.post("/api/quick-add/confirm", json=payload, headers=auth).json()
                self.assertTrue(again["already_created"])
                self.assertEqual(again["lead"]["id"], lead["id"])
                self.assertEqual(module.database_counts()["leads"], 1)
                visits = client.get("/api/appointments", headers=auth).json()
                self.assertEqual(len(visits), 1)
                self.assertEqual(visits[0]["lead_id"], lead["id"])
                self.assertEqual(client.delete(f"/api/leads/{lead['id']}", headers=auth).status_code, 409)
                self.assertEqual(module.database_counts()["quotes"], 0)
                bad = dict(payload, idempotency_key=secrets.token_urlsafe(22),
                           visit_ends_at="2026-10-02T09:00")
                self.assertEqual(client.post("/api/quick-add/confirm", json=bad, headers=auth).status_code, 422)
                self.assertEqual(module.database_counts()["leads"], 1)
                no_guess = client.post("/api/quick-add/preview", headers=auth,
                    json={"message":"Could you come Thursday morning? My tap is leaking."}).json()
                self.assertEqual(no_guess["visit_starts_at"], "")

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
                client.put(f"/api/quotes/{quote['id']}/outcome", headers=auth, json={"status":"expired"})
                report = client.get("/api/pipeline", headers=auth).json()
                self.assertEqual(report["stages"]["closed_lost_expired"][0]["lead_id"], lead["id"])
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

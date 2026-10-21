"""Temporary owner preview for WhatsApp source tracking. No production/staging disk.

The test harness copies app/config to an isolated temporary directory, disables
outbound HTTP/SMTP, and blocks unauthenticated access in APP_ENVIRONMENT=staging.
All records are synthetic, and the database is discarded on service restart.
"""
import os
import sqlite3
from pathlib import Path

import uvicorn
from fastapi.testclient import TestClient

from local_browser_server import disposable_app


def run():
    port = int(os.environ["PORT"])
    if not 1024 <= port <= 65535:
        raise RuntimeError("Invalid isolated preview port")
    user = os.environ["STAGE6_TEST_USERNAME"]
    password = os.environ["STAGE6_TEST_PASSWORD"]
    if not user or len(password) < 24:
        raise RuntimeError("Private preview login is required")
    base = os.environ["RENDER_EXTERNAL_URL"]
    if not base.startswith("https://") or "onrender.com" not in base:
        raise RuntimeError("Unexpected isolated preview URL")

    with disposable_app(user, password, environment="staging",
                        public_base_url=base,
                        projects_as_drafts=False,
                        advice_as_drafts=False) as (module, directory):
        from business.schema_migrations import migrate

        root = Path(directory).resolve()
        database = (root / "quotes.db").resolve()
        if not database.is_relative_to(root) or database.is_relative_to("/var/data"):
            raise RuntimeError("Preview database is not disposable")
        migrated = migrate(database, apply=True)
        if migrated["version"] != 1:
            raise RuntimeError("Unexpected tracking migration")

        # Seed fictional entries only. No real customer data or imported DB.
        with TestClient(module.app) as client:
            for idx in (1, 2):
                label = f"STAGING DEMO WhatsApp {idx}"
                reference = f"NHP-STAGING-WHATSAPP-{idx}"
                lead_resp = client.post("/api/quick-add/confirm", auth=(user, password),
                    json={"idempotency_key":f"isolated-preview-wa-demo-{idx}-20261021",
                          "name":label, "phone":"07700900000",
                          "description":"Synthetic demo plumbing enquiry only; do not contact anyone.",
                          "source_category":"", "contact_channel":"WhatsApp",
                          "record_kind":"synthetic", "test_reference":reference})
                if lead_resp.status_code != 200:
                    raise RuntimeError(f"Synthetic lead {idx} failed: {lead_resp.status_code}")
                lead = lead_resp.json()["lead"]
                quote_resp = client.post("/api/quote", auth=(user, password),
                    json={"quote_type":"small", "lead_id":lead["id"],
                          "customer_name":label, "customer_phone":"07700900000",
                          "job_description":"Synthetic demo plumbing quote only",
                          "labour_cost":100,
                          "submission_key":f"isolated-preview-wa-quote-{idx}-20261021"})
                if quote_resp.status_code != 200:
                    raise RuntimeError(f"Synthetic quote {idx} failed: {quote_resp.status_code}")
                quote = quote_resp.json()
                if quote["lead_id"] != lead["id"] or quote["origin_id"] != lead["origin_id"]:
                    raise RuntimeError("Lead-to-quote origin linkage broken")
            with sqlite3.connect(database) as conn:
                values = [conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                          for table in ("leads","quotes","enquiry_origins")]
                if values != [2, 2, 2]:
                    raise RuntimeError(f"Unexpected disposable fixture counts: {values}")
        print("ISOLATED PREVIEW READY: synthetic 2 leads, 2 quotes, 2 origins; no persistent disk",
              flush=True)
        uvicorn.run(module.app, host="0.0.0.0", port=port,
                    log_level="warning", access_log=False)


if __name__ == "__main__":
    run()

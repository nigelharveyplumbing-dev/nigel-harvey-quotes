"""PR #34 private staging wrapper: disposable fictional data, no outbound I/O.

Not a production entrypoint. The exact application files are verified before
import, and the existing isolation harness redirects storage before app import.
"""

import base64
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse
from PIL import Image
import uvicorn

from local_browser_server import disposable_app


BASE_CANDIDATE = "b7377ca92338a3e8ede2167b1daaa11a4200fdd9"
CANDIDATE_FILES = {'app.py': 'e015905e0b6b07fc0f212aacfce6cddb4fb8742dbe0432057746da13c5bcd181', 'business/db.py': 'a84e82df3ef6970c450c60e8dca26f1a33ec56b7635bb325fdfc67052db906e0', 'business/document_links.py': 'b680531f6a503e10d4d2dccfafd9d45d56d1821f6ebfb5d4f47d0b43bab741cf', 'business/public_invoice_render.py': '97abde943a35c8d798aa0b28a021407e22e845953ec696de86b7fe26d8e68b7f', 'business/quote_store.py': '7344d52d3b5092f6865901998387cad614e6338d9345c6af7e0502295fcac4aa', 'static/app.js': '1b9e4ddb6ef61670bc5fd8a26226e4ba6a8965a3a901997707b50d847739fa87'}


def verify_candidate():
    root = Path(__file__).resolve().parents[1]
    for name, expected in CANDIDATE_FILES.items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError("Preview candidate verification failed: " + name)


def prepare_preview(module, root, username, password):
    checks = {}

    def check(name, condition):
        checks[name] = bool(condition)
        if not condition:
            raise RuntimeError("Synthetic preview check failed: " + name)

    auth = {"Authorization": "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()}
    with TestClient(module.app) as client:
        fixtures = []
        for name in ("Fictional Preview Customer A", "Fictional Preview Customer B"):
            payload = module.QuoteRequest(customer_name=name, customer_address="1 Fictional Test Lane",
                customer_phone="07000000000", job_description="TEST ONLY — synthetic valve replacement",
                labour_cost=120).model_dump()
            response = client.post("/api/quote", headers=auth, json=payload)
            check("create_legacy_quote_" + name[-1], response.status_code == 200)
            quote = response.json()
            response = client.post(f"/api/quotes/{quote['id']}/to-invoice", headers=auth)
            check("create_legacy_invoice_" + name[-1], response.status_code == 200)
            invoice = response.json()
            image = io.BytesIO()
            Image.new("RGB", (80, 60), "navy").save(image, "PNG")
            response = client.post(f"/api/invoices/{invoice['id']}/photos", headers=auth,
                files={"photos": ("fictional-test-image.png", image.getvalue(), "image/png")})
            check("create_fictional_photo_" + name[-1], response.status_code == 200)
            fixtures.append({"quote_id": quote["id"], "invoice_id": invoice["id"],
                             "photo_id": response.json()["photos"][0]["id"]})

        # Exercise old-schema migration on an actual disposable SQLite backup.
        backup = root / "synthetic-before-links.db"
        conn = module.get_db()
        before_rows = {table: [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]
                       for table in ("quotes", "invoices")}
        with sqlite3.connect(backup) as destination:
            conn.backup(destination)
        conn.close()
        os.environ["CUSTOMER_DOCUMENT_LINK_MODE"] = "prepare"
        module.init_db()
        module.init_db()
        conn = module.get_db()
        for table, rows in before_rows.items():
            current = [{key: row[key] for key in rows[0]} for row in conn.execute(f"SELECT * FROM {table}")]
            check("migration_preserves_" + table, rows == current)
        check("migration_integrity", conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok")
        conn.close()
        restored = root / "synthetic-restore-rehearsal.db"
        with sqlite3.connect(backup) as source, sqlite3.connect(restored) as destination:
            source.backup(destination)
        with sqlite3.connect(restored) as connection:
            check("restore_integrity", connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok")
            check("restore_old_schema", "share_token" not in {r[1] for r in connection.execute("PRAGMA table_info(invoices)")})
            check("restore_records", connection.execute("SELECT count(*) FROM invoices").fetchone()[0] == 2)

        # These anonymous production-policy checks run before any listening
        # server is opened, against fictional records only. Restore staging
        # before serving; all remote routes always require staff authentication.
        os.environ["APP_ENVIRONMENT"] = ""
        first, second = fixtures
        quote = module.get_quote_by_id(first["quote_id"])
        invoice = module.get_invoice_by_id(first["invoice_id"])
        share = invoice["share_path"]
        legacy = [f"/invoice/{invoice['id']}", f"/api/invoices/{invoice['id']}/pdf",
                  f"/api/invoices/{invoice['id']}/payment-qr",
                  f"/api/invoices/{invoice['id']}/photos/{first['photo_id']}",
                  f"/api/quotes/{quote['id']}/pdf"]
        for index, path in enumerate(legacy):
            response = client.get(path)
            check("prepare_old_link_" + str(index), response.status_code == 200 and "location" not in response.headers)
        for index, path in enumerate((share, share + "/pdf", share + "/payment-qr",
                                     share + f"/photos/{first['photo_id']}", quote["share_pdf_path"])):
            response = client.get(path)
            check("token_document_" + str(index), response.status_code == 200)
            check("token_headers_" + str(index), response.headers.get("cache-control") == "no-store"
                  and response.headers.get("referrer-policy") == "no-referrer"
                  and "noindex" in response.headers.get("x-robots-tag", ""))
        page = client.get(share).text
        check("token_children_only", "/api/invoices/" not in page and share + "/pdf" in page)
        check("no_analytics", "analytics" not in page)
        check("photo_scope", client.get(share + f"/photos/{second['photo_id']}").status_code == 404)
        check("quote_invoice_scope", client.get("/share/quote/" + share.rsplit("/", 1)[-1] + "/pdf").status_code == 404)
        check("unknown_token", client.get("/share/invoice/" + "t" * 43).status_code == 404)
        check("malformed_token", client.get("/share/invoice/1").status_code == 404)
        check("private_json", client.get(f"/api/invoices/{invoice['id']}").status_code == 401)
        os.environ["CUSTOMER_DOCUMENT_LINK_MODE"] = "secure"
        before_anonymous = module.DB_PATH.read_bytes()
        for index, path in enumerate(legacy):
            response = client.get(path)
            check("secure_old_link_blocked_" + str(index), response.status_code == 401 and "location" not in response.headers)
            check("staff_old_link_" + str(index), client.get(path, headers=auth).status_code == 200)
        check("secure_token_works", client.get(share).status_code == 200)
        check("anonymous_read_only", module.DB_PATH.read_bytes() == before_anonymous)
        endpoint = f"/api/document-links/invoice/{invoice['id']}"
        check("rotation_requires_staff", client.post(endpoint).status_code == 401)
        check("cross_site_blocked", client.post(endpoint, headers={**auth, "Origin": "https://foreign.invalid"}).status_code == 403)
        response = client.post(endpoint, headers=auth)
        new_path = response.json()["path"]
        check("rotate_old_invalidated", client.get(share).status_code == 404)
        check("rotate_new_works", client.get(new_path).status_code == 200)
        check("revoke", client.delete(endpoint, headers=auth).status_code == 200)
        module.init_db()
        check("revocation_survives_init", client.get(new_path).status_code == 404
              and module.get_invoice_by_id(invoice["id"])["share_path"] == "")
        check("replacement", client.post(endpoint, headers=auth).status_code == 200)
        # Remain private and leave secure mode active for owner review.
        os.environ["APP_ENVIRONMENT"] = "staging"
        for index, path in enumerate(("/app", "/api/health", module.get_invoice_by_id(invoice["id"])["share_path"])):
            check("remote_staging_auth_" + str(index), client.get(path).status_code == 401)
        check("staging_owner_access", client.get("/app", headers=auth).status_code == 200)
        check("staging_robots", "Disallow: /" in client.get("/robots.txt", headers=auth).text)
        check("integrations_disabled", not module.EMAIL_ENABLED and not module.AUTO_OVERDUE_REMINDERS
              and not module.GOOGLE_PLACES_API_KEY and not os.getenv("OPENAI_API_KEY"))
        check("storage_isolated", module.DB_PATH.is_relative_to(root) and not str(module.DB_PATH).startswith("/var/data"))
    return {"base_candidate": BASE_CANDIDATE, "synthetic_only": True, "all_passed": all(checks.values()),
            "check_count": len(checks), "checks": checks, "mode": "secure", "fixtures": fixtures}


def main():
    verify_candidate()
    username = os.environ["APP_USERNAME"]
    password = os.environ["APP_PASSWORD"]
    if not username or len(password) < 24:
        raise RuntimeError("Private preview credentials are required")
    origin = (os.getenv("RENDER_EXTERNAL_URL") or os.getenv("PREVIEW_TEST_ORIGIN") or "").rstrip("/")
    if not origin or (os.getenv("RENDER") and not origin.endswith(".onrender.com")):
        raise RuntimeError("An isolated preview origin is required")
    with disposable_app(username, password, public_base_url=origin, environment="staging",
                        document_link_mode="legacy", projects_as_drafts=True, advice_as_drafts=True) as (module, root):
        report = prepare_preview(module, root, username, password)
        banner = '<div style="padding:14px;background:#fff3cd;color:#432;font-weight:bold">PRIVATE TEST — fictional customers and documents only. Do not enter real customer data.</div>'
        module.HTML = module.HTML.replace("<body>", "<body>" + banner, 1)

        @module.app.get("/__preview/status")
        def preview_status():
            return JSONResponse(report, headers={**module.document_links.HEADERS})

        print("DOCUMENT_LINK_PREVIEW_READY " + json.dumps({"base_candidate": BASE_CANDIDATE,
              "synthetic_only": True, "all_passed": report["all_passed"], "checks": report["check_count"]}), flush=True)
        uvicorn.run(module.app, host="0.0.0.0", port=int(os.getenv("PORT", "10000")), access_log=True)


if __name__ == "__main__":
    main()

"""Fictional records only; harness blocks outbound HTTP, DNS and SMTP."""

import base64
import hashlib
import io
import json
import logging
import importlib.util
import os
import sqlite3
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfReader

from local_browser_server import disposable_app


class DocumentLinkTests(unittest.TestCase):
    def fixture(self, mode="secure", environment=""):
        return disposable_app("synthetic-owner", "test-only-password", environment=environment,
                              public_base_url="https://synthetic.example", document_link_mode=mode)

    def auth(self):
        return {"Authorization": "Basic " + base64.b64encode(b"synthetic-owner:test-only-password").decode()}

    def documents(self, m, c, name="Fictional Customer"):
        payload = m.QuoteRequest(customer_name=name, customer_address="1 Fictional Lane",
                                 customer_phone="07000000000", job_description="Synthetic valve",
                                 labour_cost=120).model_dump()
        response = c.post("/api/quote", json=payload, headers=self.auth())
        self.assertEqual(response.status_code, 200, response.text)
        quote = response.json()
        invoice = c.post(f"/api/quotes/{quote['id']}/to-invoice", headers=self.auth()).json()
        return quote, invoice

    def snapshot(self, root):
        return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in root.rglob("*") if p.is_file() and "__pycache__" not in str(p)}

    def test_secure_routes_content_and_no_anonymous_side_effects(self):
        with self.fixture() as (m, root), TestClient(m.app) as c:
            q, i = self.documents(m, c)
            image = io.BytesIO()
            Image.new("RGB", (10, 10), "blue").save(image, "PNG")
            photo = c.post(f"/api/invoices/{i['id']}/photos", headers=self.auth(),
                           files={"photos": ("synthetic.png", image.getvalue(), "image/png")}).json()["photos"][0]
            share = i["share_path"]
            before = self.snapshot(root)
            legacy = [f"/invoice/{i['id']}", f"/api/invoices/{i['id']}/pdf",
                      f"/api/invoices/{i['id']}/payment-qr", photo["url"], f"/api/quotes/{q['id']}/pdf"]
            for url in legacy:
                blocked = c.get(url)
                self.assertEqual(blocked.status_code, 401, url)
                self.assertNotIn("location", blocked.headers)
                self.assertEqual(c.get(url, headers=self.auth()).status_code, 200, url)
            page = c.get(share)
            self.assertEqual(page.status_code, 200)
            self.assertIn("Fictional Customer", page.text)
            self.assertIn(share + "/pdf", page.text)
            self.assertIn(share + "/payment-qr", page.text)
            self.assertIn(share + f"/photos/{photo['id']}", page.text)
            self.assertNotIn("/api/invoices/", page.text)
            self.assertNotIn("analytics", page.text)
            self.assertNotIn("gross_profit", page.text)
            for url in (share, share + "/pdf", share + "/payment-qr", share + f"/photos/{photo['id']}", q["share_pdf_path"]):
                response = c.get(url)
                self.assertEqual(response.status_code, 200, url)
                self.assertEqual(response.headers["cache-control"], "no-store")
                self.assertEqual(response.headers["referrer-policy"], "no-referrer")
                self.assertIn("noindex", response.headers["x-robots-tag"])
            pdf = c.get(share + "/pdf")
            self.assertEqual(pdf.headers["content-type"], "application/pdf")
            self.assertEqual(pdf.headers["content-disposition"], f'attachment; filename="{i["invoice_number"]}.pdf"')
            self.assertIn("Fictional Customer", "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages))
            self.assertTrue(c.get(share + "/pdf?view=1").headers["content-disposition"].startswith("inline;"))
            self.assertEqual(c.get(share + "/payment-qr").headers["content-type"], "image/png")
            self.assertEqual(c.get(share + f"/photos/{photo['id']}").content, c.get(photo["url"], headers=self.auth()).content)
            self.assertEqual(c.get(f"/api/invoices/{i['id']}").status_code, 401)
            self.assertEqual(c.get(share + "/json").status_code, 401)
            self.assertEqual(self.snapshot(root), before)

    def test_token_scope_missing_revocation_rotation_and_restart(self):
        with self.fixture() as (m, root), TestClient(m.app) as c:
            q, first = self.documents(m, c, "First Fictional Customer")
            other_q, other = self.documents(m, c, "Other Fictional Customer")
            path = m.invoice_photo_folder(other["id"]) / "fictional.jpg"
            Image.new("RGB", (4, 4)).save(path)
            photo_id = m.save_invoice_photo_record(other["id"], "after", "", path.name, "synthetic.jpg")
            old = first["share_path"]
            self.assertNotIn("Other Fictional Customer", c.get(old).text)
            self.assertEqual(c.get(old + f"/photos/{photo_id}").status_code, 404)
            invoice_token = old.rsplit("/", 1)[-1]
            self.assertEqual(c.get(f"/share/quote/{invoice_token}/pdf").status_code, 404)
            for token in ("1", "t" * 42, "t" * 43, "t" * 44, "bad!", "null"):
                response = c.get("/share/invoice/" + token)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json(), {"detail": "Document not found"})
                self.assertEqual(response.headers["cache-control"], "no-store")
            endpoint = f"/api/document-links/invoice/{first['id']}"
            for method in (c.post, c.delete):
                self.assertEqual(method(endpoint).status_code, 401)
                self.assertEqual(method(endpoint, headers={**self.auth(), "Origin": "https://foreign.example"}).status_code, 403)
            new = c.post(endpoint, headers=self.auth()).json()["path"]
            self.assertNotEqual(new, old)
            self.assertEqual(c.get(old).status_code, 404)
            self.assertEqual(c.get(new).status_code, 200)
            self.assertEqual(c.delete(endpoint, headers=self.auth()).status_code, 200)
            m.init_db()
            self.assertEqual(c.get(new).status_code, 404)
            self.assertEqual(m.get_invoice_by_id(first["id"])["share_path"], "")
            with self.assertRaises(RuntimeError):
                m.build_invoice_public_url(first["id"])
            self.assertEqual(c.get(other["share_path"]).status_code, 200)
            quote_path = c.post(f"/api/document-links/quote/{q['id']}", headers=self.auth()).json()["path"]
            self.assertEqual(c.get(q["share_pdf_path"]).status_code, 404)
            self.assertEqual(c.get(quote_path).status_code, 200)
            self.assertEqual(c.post("/api/document-links/invoice/99999", headers=self.auth()).status_code, 404)
            self.assertEqual(c.delete("/api/document-links/invalid/1", headers=self.auth()).status_code, 404)

    def test_prepare_mode_preserves_old_links_and_existing_records(self):
        with self.fixture("legacy") as (m, root), TestClient(m.app) as c:
            q, i = self.documents(m, c)
            conn = m.get_db()
            before = {table: [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]
                      for table in ("quotes", "invoices")}
            backup = root / "synthetic-before.db"
            with sqlite3.connect(backup) as dest:
                conn.backup(dest)
            conn.close()
            self.assertNotIn("share_path", i)
            self.assertEqual(c.get(f"/invoice/{i['id']}").status_code, 200)
            self.assertEqual(c.get("/share/invoice/" + "t" * 43).status_code, 401)
            with patch.dict(os.environ, {"CUSTOMER_DOCUMENT_LINK_MODE": "prepare"}):
                m.init_db()
                m.init_db()
                conn = m.get_db()
                for table, expected in before.items():
                    actual = [{k: row[k] for k in expected[0]} for row in conn.execute(f"SELECT * FROM {table}")]
                    self.assertEqual(actual, expected)
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                conn.close()
                token_path = m.get_invoice_by_id(i["id"])["share_path"]
                self.assertEqual(c.get(token_path).status_code, 200)
                self.assertEqual(c.get(f"/invoice/{i['id']}").status_code, 200)
                self.assertNotIn("location", c.get(f"/invoice/{i['id']}").headers)
                self.assertEqual(m.build_invoice_public_url(i["id"]), "https://synthetic.example" + token_path)
                self.assertEqual(m.get_invoice_by_id(i["id"])["share_path"], token_path)
            # Restore rehearsal: untouched pre-migration snapshot retains old content/schema.
            with sqlite3.connect(backup) as conn:
                self.assertNotIn("share_token", {r[1] for r in conn.execute("PRAGMA table_info(invoices)")})
                self.assertEqual(conn.execute("SELECT count(*) FROM invoices").fetchone()[0], 1)
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_staging_still_requires_staff_login_for_token_routes(self):
        with self.fixture("secure", "staging") as (m, root), TestClient(m.app) as c:
            q, i = self.documents(m, c)
            self.assertEqual(c.get(i["share_path"]).status_code, 401)
            self.assertEqual(c.get(i["share_path"], headers=self.auth()).status_code, 200)

    def test_invalid_mode_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "Invalid CUSTOMER_DOCUMENT_LINK_MODE"):
            with self.fixture("typo"):
                pass

    def test_migration_failure_rolls_back_and_inventory_is_read_only(self):
        with self.fixture("legacy") as (m, root), TestClient(m.app) as c:
            self.documents(m, c)
            database = m.DB_PATH
            before = database.read_bytes()
            with sqlite3.connect(database) as conn:
                before_dump = list(conn.iterdump())
            spec = importlib.util.spec_from_file_location("inventory_under_test", Path(__file__).resolve().parents[1] / "scripts/document_link_inventory.py")
            inventory_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(inventory_module)
            result = inventory_module.inventory(database)
            self.assertFalse(result["cutover_ready"])
            self.assertEqual(len(result["records"]), 2)
            self.assertTrue(all(r["previously_shared"] == "unknown" for r in result["records"]))
            self.assertNotIn("Fictional Customer", json.dumps(result))
            self.assertEqual(database.read_bytes(), before)
            with patch.dict(os.environ, {"CUSTOMER_DOCUMENT_LINK_MODE": "prepare"}), \
                 patch.object(m.document_links, "issue", side_effect=RuntimeError("synthetic migration fault")):
                conn = m.get_db()
                try:
                    with self.assertRaisesRegex(RuntimeError, "synthetic migration fault"):
                        m.document_links.migrate(conn)
                    for table in ("quotes", "invoices"):
                        self.assertNotIn("share_token", {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")})
                finally:
                    conn.close()
            with sqlite3.connect(database) as conn:
                self.assertEqual(list(conn.iterdump()), before_dump)
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            # Restore the pre-migration copy into a different disposable file.
            restored = root / "restored.db"
            with sqlite3.connect(database) as source, sqlite3.connect(restored) as destination:
                source.backup(destination)
            with sqlite3.connect(restored) as conn:
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(conn.execute("SELECT customer_name FROM invoices").fetchone()[0], "Fictional Customer")

    def test_access_logging_redacts_tokens_without_changing_other_paths(self):
        with self.fixture() as (m, root):
            token = "t" * 43
            record = logging.LogRecord("uvicorn.access", logging.INFO, "test", 1,
                                       '%s - "%s %s HTTP/%s" %d',
                                       ("127.0.0.1", "GET", "/share/invoice/" + token + "/pdf?view=1", "1.1", 200), None)
            self.assertTrue(m.document_links.RedactShareTokens().filter(record))
            self.assertNotIn(token, record.getMessage())
            self.assertIn("[redacted]/pdf?view=1", record.getMessage())
            self.assertIn("GET", record.getMessage())

    def test_secure_whatsapp_messages_and_revoked_fallback(self):
        root = Path(__file__).resolve().parents[1]
        js = (root / "static/app.js").read_text()
        quote = js[js.index("function buildQuoteWhatsappMessage(data) {"):js.index("function renderQuoteResult(data) {")]
        invoice = js[js.index('  const invoiceUrl = Object.prototype.hasOwnProperty.call(item, "share_path")'):js.index('  document.getElementById("invoiceOpenBtn").href = invoiceUrl;')]
        script = '''const assert = require('node:assert/strict');
const window={location:{origin:'https://synthetic.example'}};
const CURRENT_QUOTE_ID=42;
const pounds=n=>'£'+Number(n||0).toFixed(2);
const normalisePhone=p=>p;
const document={getElementById:()=>({href:''})};
''' + quote + '''
const path='/share/quote/'+'q'.repeat(43)+'/pdf';
assert(buildQuoteWhatsappMessage({share_pdf_path:path}).includes(path));
assert(!buildQuoteWhatsappMessage({share_pdf_path:''}).includes('/api/quotes/'));
const item={id:99,share_path:'/share/invoice/'+'i'.repeat(43)};
const invoice={};const quoteResult={};
''' + invoice + '''
assert(invoiceUrl.includes('/share/invoice/'));
assert(!invoiceUrl.includes('/invoice/99'));
'''
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

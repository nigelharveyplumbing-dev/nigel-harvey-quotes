"""Stage 6 local HTTP workflows against the same isolated app used by the browser."""

import base64
from email import message_from_string
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import smtplib
import subprocess
import unittest
from types import SimpleNamespace
from urllib.parse import urljoin
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
import requests

from local_browser_server import disposable_app


class LocalIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.username = secrets.token_urlsafe(16)
        cls.password = secrets.token_urlsafe(24)
        cls.sandbox = disposable_app(cls.username, cls.password)
        cls.app_module, cls.root = cls.sandbox.__enter__()
        cls.addClassCleanup(cls.sandbox.__exit__, None, None, None)
        cls.client = TestClient(cls.app_module.app)
        cls.client.__enter__()
        cls.addClassCleanup(cls.client.__exit__, None, None, None)
        token = base64.b64encode(f"{cls.username}:{cls.password}".encode()).decode()
        cls.auth = {"Authorization": "Basic " + token}

    def test_auth_public_pages_and_browser_shell(self):
        c = self.client
        self.assertEqual(c.get("/app").status_code, 401)
        self.assertEqual(c.get("/app").headers["www-authenticate"], "Basic")
        self.assertEqual(c.get("/app", headers={"Authorization": "Basic invalid"}).status_code, 401)
        self.assertEqual(c.get("/api/dashboard").status_code, 401)
        page = c.get("/app", headers=self.auth)
        self.assertEqual(page.status_code, 200)
        self.assertIn('id="dashboardTab"', page.text)
        self.assertIn('id="quotesTab"', page.text)
        self.assertIn("function showTab", page.text)
        self.assertEqual(c.get("/api/dashboard", headers=self.auth).status_code, 200)
        for path in ("/", "/plumber-guildford", "/request-quote", "/robots.txt", "/sitemap.xml"):
            self.assertEqual(c.get(path).status_code, 200, path)
        self.assertEqual(c.get("/emergency-plumber-surrey").status_code, 404)

    def test_invoice_card_payment_defaults_and_client_assets(self):
        """The default display matches server config without shipping payment literals."""
        source = Path(__file__).resolve().parents[1]
        settings = (source / "business" / "config.py").read_text()
        script = (source / "static" / "app.js").read_text()
        template = (source / "templates" / "app.html").read_text()
        defaults = {}
        for field, client_key in (
            ("BANK_NAME", "bank"),
            ("BANK_ACCOUNT_NAME", "accountName"),
            ("BANK_SORT_CODE", "sortCode"),
            ("BANK_ACCOUNT_NUMBER", "accountNumber"),
        ):
            server = re.search(rf'(?m)^{field} = .*? or "([^"]+)"', settings)
            self.assertIsNotNone(server, f"Missing default for {field}")
            defaults[client_key] = server.group(1)
            self.assertNotIn(server.group(1), script, f"Payment literal in JS: {field}")
            self.assertNotIn(server.group(1), template, f"Payment literal in HTML: {field}")
            self.assertIn(f"{client_key}: APP_PAYMENT_CONFIG.{client_key}", script)
        self.assertIn("window.CURRENT_INVOICE_PAYMENT_DETAILS = bankDetails", script)
        with disposable_app(self.username, self.password, bank_settings={}) as (m, _):
            with TestClient(m.app) as client:
                page = client.get("/app", headers=self.auth)
                self.assertEqual(page.status_code, 200)
                config = re.search(r'const APP_PAYMENT_CONFIG = (\{.*?\});', page.text)
                self.assertIsNotNone(config)
                self.assertTrue(json.loads(config.group(1)) == defaults,
                                "Default invoice display differs from server configuration")
                self.assertTrue(all(getattr(m, field) == defaults[key] for field, key in (
                    ("BANK_NAME", "bank"), ("BANK_ACCOUNT_NAME", "accountName"),
                    ("BANK_SORT_CODE", "sortCode"),
                    ("BANK_ACCOUNT_NUMBER", "accountNumber"))),
                    "Default configuration differs from invoice display")

    def test_synthetic_staging_payment_config_and_safe_embedding(self):
        page = self.client.get("/app", headers=self.auth)
        self.assertEqual(page.status_code, 200)
        config = re.search(r'const APP_PAYMENT_CONFIG = (\{.*?\});', page.text)
        self.assertIsNotNone(config)
        self.assertTrue(json.loads(config.group(1)) == {
            "bank": self.app_module.BANK_NAME,
            "accountName": self.app_module.BANK_ACCOUNT_NAME,
            "sortCode": self.app_module.BANK_SORT_CODE,
            "accountNumber": self.app_module.BANK_ACCOUNT_NUMBER,
        }, "Staging invoice display differs from configured payment data")
        self.assertEqual(self.client.get("/app").status_code, 401)
        injection = {'BANK_NAME': '</script><script>window.bad=1</script>'}
        with disposable_app(self.username, self.password, bank_settings=injection) as (m, _):
            with TestClient(m.app) as client:
                html = client.get("/app", headers=self.auth).text
                self.assertNotIn(injection["BANK_NAME"], html)
                config = re.search(r'const APP_PAYMENT_CONFIG = (\{.*?\});', html)
                self.assertIsNotNone(config)
                self.assertTrue(json.loads(config.group(1))["bank"] == injection["BANK_NAME"],
                                "Escaped payment configuration was altered")

    @unittest.skipUnless(shutil.which("node"), "Node is required to execute browser JavaScript")
    def test_copy_bank_details_uses_configured_staging_values(self):
        page = self.client.get("/app", headers=self.auth).text
        match = re.search(r'const APP_PAYMENT_CONFIG = (\{.*?\});', page)
        self.assertIsNotNone(match)
        script = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const data = JSON.parse(fs.readFileSync(0, 'utf8'));
const source = fs.readFileSync(process.argv[1], 'utf8');
const start = source.indexOf('async function copyInvoiceBankDetails() {');
const end = source.indexOf('\nasync function sendCurrentOverdueReminder()', start);
if (start < 0 || end < 0) process.exit(2);
let copied = null;
const context = {
  window: { CURRENT_INVOICE_PAYMENT_DETAILS: {
    ...data, reference: 'INV-STAGING', amount: 12.5,
  } },
  navigator: { clipboard: { writeText: async value => { copied = value; } } },
  pounds: value => `£${Number(value).toFixed(2)}`,
  showNotice: () => {},
  prompt: () => { throw new Error('Unexpected clipboard fallback'); },
};
vm.runInNewContext(source.slice(start, end) + '\ncopyInvoiceBankDetails()', context)
  .then(() => {
    const expected = [
      `Bank: ${data.bank}`, `Account name: ${data.accountName}`,
      `Sort code: ${data.sortCode}`, `Account number: ${data.accountNumber}`,
      'Amount due: £12.50', 'Reference: INV-STAGING',
    ].join('\n');
    if (copied !== expected) process.exitCode = 1;
  }).catch(() => { process.exitCode = 1; });
"""
        result = subprocess.run(
            ["node", "-e", script, str(self.root / "static" / "app.js")],
            input=match.group(1), text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, "Copy action ignored staging payment configuration")

    def test_quote_invoice_customer_documents_and_deletion(self):
        c = self.client
        payload = self.app_module.QuoteRequest(
            customer_name="Synthetic Browser Customer", customer_address="1 Test Lane",
            customer_phone="07000000000", job_description="Replace test valve",
            labour_cost=100.10,
            materials=[self.app_module.MaterialItem(name="Test valve", quantity=2, manual_price=10)],
        ).model_dump()
        created = c.post("/api/quote", headers=self.auth, json=payload)
        self.assertEqual(created.status_code, 200)
        quote = created.json()
        self.assertEqual(quote["result"]["total_price"], 125.10)
        quote_id = quote["id"]
        self.assertEqual(c.get(f"/api/quotes/{quote_id}").status_code, 401)
        self.assertEqual(c.get(f"/api/quotes/{quote_id}/pdf").status_code, 200)
        self.assertEqual(c.get(f"/api/quotes/{quote_id}/pdf").content[:4], b"%PDF")
        payload["labour_cost"] = 120.20
        edited = c.put(f"/api/quotes/{quote_id}", headers=self.auth, json=payload)
        self.assertEqual(edited.json()["result"]["total_price"], 145.20)
        invoice = c.post(f"/api/quotes/{quote_id}/to-invoice", headers=self.auth).json()
        invoice_id = invoice["id"]
        customer_id = quote["customer_id"]
        self.assertEqual(invoice["quote_id"], quote_id)
        self.assertEqual(invoice["invoice"]["customer_name"], payload["customer_name"])
        self.assertEqual(c.get(f"/api/invoices/{invoice_id}").status_code, 401)
        self.assertEqual(c.get(f"/invoice/{invoice_id}").status_code, 200)
        self.assertEqual(c.get(f"/api/invoices/{invoice_id}/pdf").content[:4], b"%PDF")
        self.assertEqual(c.get(f"/api/invoices/{invoice_id}/payment-qr").status_code, 200)
        history = c.get(f"/api/customers/{customer_id}/history", headers=self.auth).json()
        self.assertTrue(history["quotes"])
        self.assertTrue(history["invoices"])
        self.assertIn("Synthetic Browser Customer", str(c.get("/api/customers", headers=self.auth).json()))
        edit = self.app_module.InvoiceEditRequest(
            customer_name=payload["customer_name"], customer_address=payload["customer_address"],
            customer_phone=payload["customer_phone"], job=payload["job_description"],
            job_reference="LOCAL-1", labour=120.20, materials=25,
            due_date=invoice["due_date"], payment_link="https://example.test/pay",
        ).model_dump()
        self.assertEqual(c.put(f"/api/invoices/{invoice_id}", headers=self.auth,
                               json=edit).json()["job_reference"], "LOCAL-1")
        status = c.post(f"/api/invoices/{invoice_id}/status", headers=self.auth,
                        json={"status": "part paid", "amount_paid": 20}).json()
        self.assertEqual(status["balance_due"], 125.20)
        self.assertEqual(c.delete(f"/api/invoices/{invoice_id}", headers=self.auth).status_code, 200)
        self.assertEqual(c.delete(f"/api/quotes/{quote_id}", headers=self.auth).status_code, 200)
        self.assertEqual(c.delete(f"/api/customers/{customer_id}", headers=self.auth).status_code, 200)

    def test_lead_material_and_synthetic_photo_workflow(self):
        c = self.client
        lead = c.post("/api/leads", json={"name": "Synthetic Lead", "phone": "07000000000",
                                           "description": "Test tap"})
        self.assertEqual(lead.status_code, 200)
        lead_id = lead.json()["id"]
        self.assertEqual(c.get("/api/leads").status_code, 401)
        self.assertEqual(c.put(f"/api/leads/{lead_id}/status", headers=self.auth,
                               json={"status": "contacted"}).status_code, 200)
        self.assertEqual(c.delete(f"/api/leads/{lead_id}", headers=self.auth).status_code, 200)

        self.app_module.upsert_material_price_cache("https://example.test/local-valve",
                                                   "Local valve", "Synthetic Supplier", price=5)
        prices = c.get("/api/material-prices", headers=self.auth).json()
        material_id = next(row["id"] for row in prices if row["name"] == "Local valve")
        self.assertEqual(c.get("/api/material-search?q=valve", headers=self.auth).status_code, 200)
        self.assertEqual(c.put(f"/api/material-prices/{material_id}", headers=self.auth,
                               json={"name": "Local valve", "supplier": "Synthetic Supplier",
                                     "url": "https://example.test/local-valve", "manual_price": 7.25}).status_code, 200)
        self.assertEqual(c.delete(f"/api/material-prices/{material_id}", headers=self.auth).status_code, 200)

        payload = self.app_module.QuoteRequest(customer_name="Synthetic Photo Customer",
                                               job_description="Photo test", labour_cost=10).model_dump()
        quote = c.post("/api/quote", headers=self.auth, json=payload).json()
        invoice = c.post(f"/api/quotes/{quote['id']}/to-invoice", headers=self.auth).json()
        invoice_id = invoice["id"]
        picture = Image.new("RGB", (16, 16), "blue")
        image_bytes = io.BytesIO()
        picture.save(image_bytes, format="PNG")
        uploaded = c.post(f"/api/invoices/{invoice_id}/photos", headers=self.auth,
                          data={"category": "after", "caption": "Synthetic installation"},
                          files={"photos": ("sample.png", image_bytes.getvalue(), "image/png")})
        self.assertEqual(uploaded.status_code, 200)
        photo = uploaded.json()["photos"][0]
        self.assertEqual(c.get(photo["url"]).headers["content-type"], "image/jpeg")
        self.assertTrue((self.root / "photos" / str(invoice_id) / photo["filename"]).exists())
        self.assertEqual(c.delete(photo["url"], headers=self.auth).status_code, 200)
        self.assertFalse((self.root / "photos" / str(invoice_id) / photo["filename"]).exists())

    def test_network_and_smtp_are_blocked(self):
        self.assertTrue(self.app_module.DB_PATH.is_relative_to(self.root))
        self.assertNotEqual(str(self.app_module.DB_PATH), "/var/data/quotes.db")
        self.assertIn("accountName: APP_PAYMENT_CONFIG.accountName",
                      (self.root / "static" / "app.js").read_text())
        with self.assertRaisesRegex(RuntimeError, "External HTTP blocked"):
            requests.get("https://example.test")
        with self.assertRaisesRegex(RuntimeError, "External DNS blocked"):
            socket.getaddrinfo("example.test", 443)
        with self.assertRaisesRegex(RuntimeError, "SMTP blocked"):
            smtplib.SMTP_SSL("example.test")

    def test_default_invoice_link_still_uses_live_domain(self):
        with patch.dict(os.environ, {"PUBLIC_BASE_URL": "", "APP_ENVIRONMENT": ""}):
            self.assertEqual(self.app_module.build_invoice_public_url(1),
                             "https://www.nigelharveyplumbing.co.uk/invoice/1")

    def test_default_absolute_document_and_website_urls(self):
        m = self.app_module
        base = "https://www.nigelharveyplumbing.co.uk"
        with patch.dict(os.environ, {"PUBLIC_BASE_URL": "", "APP_ENVIRONMENT": ""}):
            self.assertEqual(m.get_public_base_url(), base)
            for path in ("/invoice/47", "/api/invoices/47/pdf",
                         "/api/quotes/12/pdf", "/api/invoices/47/payment-qr"):
                self.assertEqual(m.absolute_url(path), base + path)
            self.assertEqual(m.build_invoice_public_url(47), base + "/invoice/47")
            home = self.client.get("/").text
            self.assertIn(f'<link rel="canonical" href="{base}/">', home)
            self.assertIn(f'<meta property="og:url" content="{base}/">', home)
            # This page currently has no canonical placeholder; preserve it.
            self.assertNotIn('rel="canonical"', self.client.get("/request-quote").text)
            self.assertIn(base + "/plumber-guildford", self.client.get("/plumber-guildford").text)
            self.assertIn(base + "/sitemap.xml", self.client.get("/robots.txt").text)
            self.assertIn(base + "/plumber-guildford", self.client.get("/sitemap.xml").text)

    def test_default_invoice_and_lead_email_url(self):
        m = self.app_module
        item = {
            "id": 47, "invoice_number": "INV-TEST-47", "job_reference": "JOB-47",
            "invoice": {"customer_name": "Synthetic Customer"}, "status": "unpaid",
            "balance_due": 12.5,
        }
        context = SimpleNamespace(
            build_invoice_public_url=m.build_invoice_public_url,
            company_name="Test company", company_phone="000", company_email="test@example.test",
            pounds_text=m.pounds_text, get_company_logo_value=lambda: "",
            generate_invoice_pdf_bytes=lambda _: b"%PDF-synthetic",
            from_header="Test sender <sender@example.test>",
        )
        with patch.dict(os.environ, {"PUBLIC_BASE_URL": "", "APP_ENVIRONMENT": ""}):
            invoice_msg = m.document_sharing.prepare_invoice_email(
                item, "recipient@example.test", "", context)
            plain = next(p for p in invoice_msg.walk() if p.get_content_type() == "text/plain")
            self.assertIn("Invoice link: https://www.nigelharveyplumbing.co.uk/invoice/47",
                          plain.get_payload(decode=True).decode())
            with patch.object(m, "EMAIL_ENABLED", True), \
                 patch.object(m, "EMAIL_USER", "sender@example.test"), \
                 patch.object(m, "EMAIL_PASS", "test-only"), \
                 patch.object(m.smtplib, "SMTP_SSL") as smtp:
                m.send_lead_notification_email({"name": "Synthetic Lead"})
                raw = smtp.return_value.__enter__.return_value.sendmail.call_args.args[2]
            lead_msg = message_from_string(raw)
            lead_plain = next(p for p in lead_msg.walk() if p.get_content_type() == "text/plain")
            self.assertIn("Open app: \n", lead_plain.get_payload(decode=True).decode())

    def test_staging_document_and_website_urls_stay_on_staging_origin(self):
        m = self.app_module
        stage = "https://quotes-stage.example.test"
        production = "https://www.nigelharveyplumbing.co.uk"
        with patch.dict(os.environ, {"PUBLIC_BASE_URL": f"  {stage}///  ",
                                     "APP_ENVIRONMENT": "staging"}):
            self.assertEqual(m.get_public_base_url(), stage)
            paths = ("/invoice/47", "/api/invoices/47/pdf", "/api/quotes/12/pdf",
                     "/api/invoices/47/payment-qr", "/api/invoices/47/photos/3")
            for path in paths:
                with self.subTest(path=path):
                    self.assertEqual(m.absolute_url(path), stage + path)
                    self.assertNotIn(production, m.absolute_url(path))
            self.assertEqual(m.absolute_url("invoice/47"), stage + "/invoice/47")
            self.assertEqual(m.build_invoice_public_url(47), stage + "/invoice/47")

            for page in ("/", "/new-home", "/plumber-guildford", "/emergency-plumber-guildford",
                         "/request-quote", "/robots.txt", "/sitemap.xml"):
                response = self.client.get(page)
                self.assertEqual(response.status_code, 200, page)
                self.assertNotIn(production, response.text, page)
            home = self.client.get("/").text
            self.assertIn(f'<link rel="canonical" href="{stage}/">', home)
            self.assertIn(f'<meta property="og:url" content="{stage}/">', home)
            self.assertIn(stage + "/sitemap.xml", self.client.get("/robots.txt").text)
            self.assertIn(stage + "/plumber-guildford", self.client.get("/sitemap.xml").text)
            self.assertIn(stage + "/emergency-plumber-surrey",
                          m.render_service_page(m.SERVICE_PAGES[0], ""))

            payload = m.QuoteRequest(customer_name="Stage Link Customer", labour_cost=10).model_dump()
            quote = self.client.post("/api/quote", headers=self.auth, json=payload).json()
            invoice = self.client.post(f"/api/quotes/{quote['id']}/to-invoice",
                                       headers=self.auth).json()
            invoice_page = self.client.get(f"/invoice/{invoice['id']}").text
            for relative in (f"/api/invoices/{invoice['id']}/pdf",
                             f"/api/invoices/{invoice['id']}/payment-qr"):
                self.assertIn(relative, invoice_page)
                self.assertEqual(urljoin(stage + "/", relative), stage + relative)
            self.assertNotIn(production, invoice_page)

    def test_staging_invoice_email_and_lead_notification_urls(self):
        m = self.app_module
        stage = "https://quotes-stage.example.test"
        item = {"id": 47, "invoice_number": "INV-STAGE-47", "job_reference": "JOB-47",
                "invoice": {"customer_name": "Synthetic Customer"}, "status": "unpaid",
                "balance_due": 12.5}
        context = SimpleNamespace(
            build_invoice_public_url=m.build_invoice_public_url,
            company_name="Test company", company_phone="000", company_email="test@example.test",
            pounds_text=m.pounds_text, get_company_logo_value=lambda: "",
            generate_invoice_pdf_bytes=lambda _: b"%PDF-synthetic",
            from_header="Test sender <sender@example.test>",
        )
        with patch.dict(os.environ, {"PUBLIC_BASE_URL": stage + "/",
                                     "APP_ENVIRONMENT": "staging"}):
            invoice_msg = m.document_sharing.prepare_invoice_email(
                item, "recipient@example.test", "", context)
            plain = next(p for p in invoice_msg.walk() if p.get_content_type() == "text/plain")
            html = next(p for p in invoice_msg.walk() if p.get_content_type() == "text/html")
            self.assertIn("Invoice link: " + stage + "/invoice/47",
                          plain.get_payload(decode=True).decode())
            self.assertIn('href="' + stage + '/invoice/47"', html.get_payload(decode=True).decode())
            with patch.object(m, "EMAIL_ENABLED", True), \
                 patch.object(m, "EMAIL_USER", "sender@example.test"), \
                 patch.object(m, "EMAIL_PASS", "test-only"), \
                 patch.object(m.smtplib, "SMTP_SSL") as smtp:
                m.send_lead_notification_email({"name": "Synthetic Lead"})
                raw = smtp.return_value.__enter__.return_value.sendmail.call_args.args[2]
            lead_msg = message_from_string(raw)
            lead_plain = next(p for p in lead_msg.walk() if p.get_content_type() == "text/plain")
            self.assertIn("Open app: " + stage + "\n", lead_plain.get_payload(decode=True).decode())

    def test_staging_origin_configuration_fails_closed(self):
        m = self.app_module
        for configured in ("", "https://www.nigelharveyplumbing.co.uk/",
                           "https://nigelharveyplumbing.co.uk", "not-a-url",
                           "https://quotes-stage.example.test/path",
                           "https://quotes-stage.example.test?redirect=live",
                           "https://quotes-stage.example.test:badport"):
            with self.subTest(origin=configured), \
                 patch.dict(os.environ, {"APP_ENVIRONMENT": "staging",
                                          "PUBLIC_BASE_URL": configured}):
                with self.assertRaises(ValueError):
                    m.get_public_base_url()

    def test_staging_startup_rejects_missing_origin(self):
        with self.assertRaisesRegex(ValueError, "required in staging"):
            with disposable_app(self.username, self.password, environment="staging"):
                self.fail("Staging app started without PUBLIC_BASE_URL")

    def test_explicit_production_origin_matches_default(self):
        production = "https://www.nigelharveyplumbing.co.uk"
        with patch.dict(os.environ, {"PUBLIC_BASE_URL": production + "/",
                                     "APP_ENVIRONMENT": "production"}):
            self.assertEqual(self.app_module.get_public_base_url(), production)
            self.assertEqual(self.app_module.build_invoice_public_url(47),
                             production + "/invoice/47")
            self.assertIn(f'href="{production}/"', self.client.get("/").text)


if __name__ == "__main__":
    unittest.main()

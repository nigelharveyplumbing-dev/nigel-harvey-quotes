"""Behaviour checks against a disposable copy of the app.

Importing app.py initializes SQLite, so the test copy redirects every persistent
path before import. No test opens production /var/data.
"""

import importlib.util
import base64
import hashlib
from contextlib import contextmanager
from datetime import datetime
from email import message_from_string
import json
import io
import os
import re
import secrets
import subprocess
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from bs4 import BeautifulSoup
from PIL import Image
from pypdf import PdfReader
from encoding_audit import hits as encoding_hits, scan_database, text_leaves


ROOT = Path(__file__).resolve().parents[1]

# Explicit policy for the 67 application method/path routes. All others are private.
PUBLIC_WEBSITE_ROUTES = {
    ("GET", path) for path in (
        "/", "/new-home", "/request-quote", "/robots.txt", "/sitemap.xml",
        "/site-images/{filename}",
        "/plumber-{area_slug}", "/{service_slug}-{area_slug}", "/{service_slug}",
    )
} | {("POST", "/api/leads")}
PUBLIC_CUSTOMER_ROUTES = {
    ("GET", path) for path in (
        "/invoice/{invoice_id}", "/api/invoices/{invoice_id}/pdf",
        "/api/invoices/{invoice_id}/payment-qr",
        "/api/invoices/{invoice_id}/photos/{photo_id}",
        "/api/quotes/{quote_id}/pdf",
    )
}


@contextmanager
def dashboard_database(quote_rows=(), invoice_rows=(), customer_count=0):
    """Only the columns read by the reporting queries, in a disposable SQLite file."""
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "dashboard.db"
        conn = sqlite3.connect(path)
        try:
            conn.executescript("""
                CREATE TABLE quotes (total_price REAL, gross_profit REAL, created_at_sort TEXT);
                CREATE TABLE invoices (
                    total_price REAL, amount_paid REAL, balance_due REAL, created_at_sort TEXT
                );
                CREATE TABLE customers (id INTEGER);
            """)
            conn.executemany("INSERT INTO quotes VALUES (?, ?, ?)", quote_rows)
            conn.executemany("INSERT INTO invoices VALUES (?, ?, ?, ?)", invoice_rows)
            conn.executemany("INSERT INTO customers VALUES (?)",
                             [(i,) for i in range(customer_count)])
            conn.commit()
        finally:
            conn.close()

        def get_connection():
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            return conn

        yield get_connection


class BaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        root = Path(cls.temp.name)
        for asset_dir in ("templates", "static"):
            if (ROOT / asset_dir).exists():
                shutil.copytree(ROOT / asset_dir, root / asset_dir)
        if (ROOT / "business").exists():
            shutil.copytree(ROOT / "business", root / "business")
            config = root / "business" / "config.py"
            settings = config.read_text()
            settings = settings.replace('Path("/var/data/quotes.db")', f'Path({str(root / "quotes.db")!r})')
            settings = settings.replace('Path("/var/data/backups")', f'Path({str(root / "backups")!r})')
            settings = settings.replace('Path("/var/data/invoice_photos")', f'Path({str(root / "photos")!r})')
            assert 'Path("/var/data/' not in settings
            config.write_text(settings)
            sys.path.insert(0, str(root))
            cls.addClassCleanup(lambda: sys.path.remove(str(root)))
        source = (ROOT / "app.py").read_text()
        source = source.replace('Path("/var/data/quotes.db")', f'Path({str(root / "quotes.db")!r})')
        source = source.replace('Path("/var/data/backups")', f'Path({str(root / "backups")!r})')
        source = source.replace('Path("/var/data/invoice_photos")', f'Path({str(root / "photos")!r})')
        assert '/var/data/' not in source or 'Path("/var/data/' not in source
        path = root / "app_under_test.py"
        path.write_text(source)
        spec = importlib.util.spec_from_file_location("app_under_test", path)
        cls.module = importlib.util.module_from_spec(spec)
        cls.test_username = secrets.token_urlsafe(18)
        cls.test_password = secrets.token_urlsafe(36)
        with patch.dict(os.environ, {
            "GOOGLE_PLACES_API_KEY": "", "EMAIL_ENABLED": "0", "OPENAI_API_KEY": "",
            "PUBLIC_BASE_URL": "", "APP_ENVIRONMENT": "",
            "APP_USERNAME": cls.test_username, "APP_PASSWORD": cls.test_password,
        }):
            spec.loader.exec_module(cls.module)
        cls.module.init_db()
        cls.auth_headers = {"Authorization": "Basic " + base64.b64encode(
            f"{cls.test_username}:{cls.test_password}".encode()).decode()}

    def test_route_inventory(self):
        routes_list = [(method, route.path) for route in self.module.app.routes
                       if route.path not in {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
                       for method in getattr(route, "methods", [])]
        routes = set(routes_list)
        expected = {tuple(item) for item in json.loads((ROOT / "tests/route_inventory.json").read_text())}
        self.assertEqual(routes, expected)
        self.assertEqual(len(routes_list), len(routes), "Duplicate method/path route")
        self.assertEqual(len(routes), 67)
        self.assertEqual(len(PUBLIC_WEBSITE_ROUTES), 10)
        self.assertEqual(len(PUBLIC_CUSTOMER_ROUTES), 5)
        self.assertEqual(len(routes - PUBLIC_WEBSITE_ROUTES - PUBLIC_CUSTOMER_ROUTES), 52)
        self.assertTrue(PUBLIC_WEBSITE_ROUTES | PUBLIC_CUSTOMER_ROUTES <= routes)
        self.assertEqual(self.module.PUBLIC_ROUTE_KEYS,
                         PUBLIC_WEBSITE_ROUTES | PUBLIC_CUSTOMER_ROUTES)
        for route in [("GET", "/app"), ("GET", "/"), ("POST", "/api/quote"),
                      ("GET", "/api/quotes/{quote_id}/pdf"),
                      ("GET", "/invoice/{invoice_id}"),
                      ("POST", "/api/invoices/{invoice_id}/send-email")]:
            self.assertIn(route, routes)

    def test_dashboard_empty_database_and_uk_month_boundaries(self):
        m = self.module
        january = datetime(2026, 1, 1, 0, 30, tzinfo=ZoneInfo("Europe/London"))
        empty = {
            "month_label": "January 2026", "quote_count": 0, "quoted_total": 0,
            "gross_profit_total": 0, "invoice_count": 0, "invoiced_total": 0,
            "paid_total": 0, "balance_total": 0, "avg_quote": 0,
            "customer_count": 0,
        }
        labels = ["2025-08", "2025-09", "2025-10", "2025-11", "2025-12", "2026-01"]
        expected_series = [{
            "month_key": month, "label": label, "revenue": 0, "profit": 0,
        } for month, label in zip(labels, (
            "Aug 2025", "Sep 2025", "Oct 2025", "Nov 2025", "Dec 2025", "Jan 2026",
        ))]
        with dashboard_database() as get_connection, \
                patch.object(m, "get_db", get_connection), patch.object(m, "now_uk", return_value=january):
            self.assertEqual(m.get_dashboard(), empty)
            self.assertEqual(m.get_monthly_profit_series(), expected_series)
            self.assertEqual(m.get_monthly_profit_series(0), [])
            with TestClient(m.app) as client:
                for path, expected in (("/api/dashboard", empty),
                                       ("/api/dashboard/monthly-profit", expected_series)):
                    with self.subTest(path=path):
                        unauthenticated = client.get(path)
                        self.assertEqual(unauthenticated.status_code, 401)
                        self.assertEqual(unauthenticated.headers.get("www-authenticate"), "Basic")
                        response = client.get(path, headers=self.auth_headers)
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.json(), expected)

            april_uk = datetime(2026, 4, 1, 0, 30, tzinfo=ZoneInfo("Europe/London"))
            with patch.object(m, "now_uk", return_value=april_uk):
                self.assertEqual(m.get_dashboard()["month_label"], "April 2026")
                self.assertEqual([item["month_key"] for item in m.get_monthly_profit_series(2)],
                                 ["2026-03", "2026-04"])

    def test_dashboard_totals_rounding_nulls_and_quote_based_monthly_series(self):
        m = self.module
        january = datetime(2026, 1, 31, 23, 59, tzinfo=ZoneInfo("Europe/London"))
        quotes = [
            (100.125, 30.125, "2026-01-02T09:00:00"),
            (50.125, None, "2026-01-31T23:59:00"),
            (None, None, "2026-01-15T12:00:00"),
            (900.5, 90.5, "2025-12-20T12:00:00"),
            (999, 999, "2026-02-01T00:00:00"),
        ]
        invoices = [
            (60.125, 10.125, 50.0, "2026-01-04T09:00:00"),
            (None, None, None, "2026-01-10T09:00:00"),
            (700, 700, 0, "2025-12-12T09:00:00"),
        ]
        expected = {
            "month_label": "January 2026", "quote_count": 3, "quoted_total": 150.25,
            "gross_profit_total": 30.12, "invoice_count": 2, "invoiced_total": 60.12,
            "paid_total": 10.12, "balance_total": 50.0, "avg_quote": 75.12,
            "customer_count": 3,
        }
        with dashboard_database(quotes, invoices, 3) as get_connection, \
                patch.object(m, "get_db", get_connection), patch.object(m, "now_uk", return_value=january):
            self.assertEqual(m.get_dashboard(), expected)
            series = m.get_monthly_profit_series()
            self.assertEqual(series[-2:], [
                {"month_key": "2025-12", "label": "Dec 2025", "revenue": 900.5, "profit": 90.5},
                {"month_key": "2026-01", "label": "Jan 2026", "revenue": 150.25, "profit": 30.12},
            ])
            self.assertEqual(series[:-2], [
                {"month_key": month, "label": label, "revenue": 0, "profit": 0}
                for month, label in zip(("2025-08", "2025-09", "2025-10", "2025-11"),
                                        ("Aug 2025", "Sep 2025", "Oct 2025", "Nov 2025"))
            ])
            with TestClient(m.app) as client:
                self.assertEqual(client.get("/api/dashboard", headers=self.auth_headers).json(), expected)
                self.assertEqual(client.get("/api/dashboard/monthly-profit",
                                            headers=self.auth_headers).json(), series)

    def test_internal_app_markup_and_injected_data_baseline(self):
        """Freeze the inline UI, payment settings and five route-time substitutions."""
        m = self.module
        config = re.search(r'const APP_PAYMENT_CONFIG = (\{.*?\});', m.HTML)
        self.assertIsNotNone(config)
        masked = m.HTML.replace(config.group(1), "__PAYMENT_CONFIG__", 1)
        self.assertEqual(hashlib.sha256(masked.encode()).hexdigest(),
                         "274a31ea90339fe743dc8ad43bdf3d081afdf54dd1bc55fab825ba2b53b59168")
        self.assertEqual(m.HTML.count("<style>"), 1)
        self.assertEqual(m.HTML.count("<script>"), 1)
        self.assertEqual(set(re.findall(r"__[A-Z][A-Z_]+__", m.HTML)), {
            "__MATERIAL_LIBRARY__", "__FAVOURITE_MATERIALS__", "__JOB_TEMPLATES__",
            "__MATERIAL_ALIAS_RULES__", "__COMPANY_LOGO_HTML__",
        })
        self.assertEqual(set(re.findall(r"/api/[A-Za-z0-9_/-]+", m.HTML)), {
            "/api/ai-quote-draft", "/api/ai-quote-status", "/api/backups", "/api/backups/",
            "/api/customers", "/api/customers/", "/api/dashboard",
            "/api/dashboard/monthly-profit", "/api/intelligence", "/api/invoices",
            "/api/invoices/", "/api/labour-intelligence", "/api/leads", "/api/leads/",
            "/api/live-product-refresh", "/api/live-product-search", "/api/material-prices",
            "/api/material-prices/", "/api/material-prices/refresh", "/api/material-search",
            "/api/quote", "/api/quote-learning", "/api/quotes", "/api/quotes/",
            "/api/site-survey", "/api/supplier-preference", "/api/supplier-preferences",
        })
        with patch.object(m, "get_material_search_library", return_value=[{"name": "Test valve"}]), \
                patch.object(m, "get_all_job_templates", return_value=[{"name": "Test job"}]), \
                patch.object(m, "get_company_logo_value", return_value="data:image/png;base64,test"), \
                patch.object(m, "FAVOURITE_MATERIALS", [{"name": "Test fitting"}]), \
                patch.object(m, "MATERIAL_ALIAS_RULES", [{"alias": "test"}]):
            with TestClient(m.app) as client:
                self.assertEqual(client.get("/app").status_code, 401)
                self.assertEqual(client.get("/api/quotes").status_code, 401)
                page = client.get("/app", headers=self.auth_headers)
            self.assertEqual(page.status_code, 200)
            self.assertIn("text/html", page.headers["content-type"])
            expected = m.HTML.replace("__MATERIAL_LIBRARY__", json.dumps([{"name": "Test valve"}]))
            expected = expected.replace("__FAVOURITE_MATERIALS__", json.dumps([{"name": "Test fitting"}]))
            expected = expected.replace("__JOB_TEMPLATES__", json.dumps([{"name": "Test job"}]))
            expected = expected.replace("__MATERIAL_ALIAS_RULES__", json.dumps([{"alias": "test"}]))
            expected = expected.replace("__COMPANY_LOGO_HTML__",
                                        '<img src="data:image/png;base64,test" alt="Logo">')
            self.assertEqual(page.text, expected)

    def test_all_private_routes_reject_before_handler(self):
        """A patched endpoint would fail if any private request reached its handler."""
        m = self.module
        private = {tuple(row) for row in json.loads((ROOT / "tests/route_inventory.json").read_text())}
        private -= PUBLIC_WEBSITE_ROUTES | PUBLIC_CUSTOMER_ROUTES
        self.assertEqual(len(private), 52)
        parameters = {"invoice_id": "1", "quote_id": "1", "customer_id": "1",
                      "lead_id": "1", "material_id": "1", "photo_id": "1", "filename": "sample.db"}
        def file_state():
            return {
                str(path.relative_to(self.temp.name)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in Path(self.temp.name).rglob("*") if path.is_file()
            }

        with TestClient(m.app) as client, \
             patch.object(m, "get_db", side_effect=AssertionError("database accessed")), \
             patch.object(m.smtplib, "SMTP_SSL", side_effect=AssertionError("email sent")), \
             patch.object(m.requests, "get", side_effect=AssertionError("external GET")), \
             patch.object(m.requests, "post", side_effect=AssertionError("external POST")):
            before = file_state()
            for method, template in sorted(private):
                route = next(r for r in m.app.routes if r.path == template and method in r.methods)
                path = template.format(**parameters)
                with self.subTest(method=method, path=template), patch.object(
                    route.dependant, "call", side_effect=AssertionError("private handler invoked")):
                    response = client.request(method, path)
                    self.assertEqual(response.status_code, 401)
                    self.assertEqual(response.headers.get("www-authenticate"), "Basic")
            for path in ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"):
                with self.subTest(framework_path=path):
                    self.assertEqual(client.get(path).status_code, 401)
            self.assertEqual(client.get("/api/future-internal-route").status_code, 401)
            self.assertEqual(file_state(), before)

    def test_public_routes_and_health_policy(self):
        m = self.module
        paths = {
            "/plumber-{area_slug}": f"/plumber-{m.LOCATION_PAGES[0]['slug']}",
            "/{service_slug}-{area_slug}":
                f"/{m.LOCAL_SERVICE_PAGES[0]['slug']}-{m.LOCATION_PAGES[0]['slug']}",
            "/{service_slug}": f"/{m.SERVICE_PAGES[0]['slug']}",
            "/site-images/{filename}": "/site-images/bathroom-illustrative.webp",
        }
        with TestClient(m.app) as client, patch.object(m, "send_lead_notification_email") as notify:
            for method, template in sorted(PUBLIC_WEBSITE_ROUTES):
                if method == "GET":
                    with self.subTest(path=template):
                        expected = 200
                        self.assertEqual(client.get(paths.get(template, template)).status_code, expected)
            lead = client.post("/api/leads", json={
                "name": "Public Test", "phone": "07000000000", "description": "Enquiry",
            })
            self.assertEqual(lead.status_code, 200)
            notify.assert_called_once()
            self.assertEqual(client.get("/api/health").status_code, 401)
            detailed = client.get("/api/health", headers=self.auth_headers)
            self.assertEqual(detailed.status_code, 200)
            self.assertTrue({"ok", "db_path", "db_size_bytes", "counts", "backup_count"} <= detailed.json().keys())
            self.assertEqual(client.get("/emergency-plumber-surrey").status_code, 200)
            self.assertEqual(client.get("/general-plumbing-surrey").status_code, 200)

    def test_public_page_literals_and_rendered_html_are_byte_identical(self):
        m = self.module
        literals = {
            "LANDING_PAGE_HTML": "0557ccac52285b3f8400972513c71c58c822defd224200f3bace562811472bb5",
            "SEO_CSS": "a22e53ee58ed48079fc147e3b604c75a2dfca3478da0ca9591cd9632f47cba0f",
            "LEAD_FORM_HTML": "0e54841b8a4353a8b874131f110ac25fed9cbb355b835bdcd1a63dbf6e56cb7d",
            "NEW_HOMEPAGE_PREVIEW_HTML":
                "0547f41f471a464389de6d5bf8e7cc3a06b9ddc32281fec7aeb814274f67c8c9",
        }
        for name, digest in literals.items():
            with self.subTest(literal=name):
                self.assertEqual(hashlib.sha256(getattr(m, name).encode()).hexdigest(), digest)

        page_hashes = {
            "/": "e05e23707848917bd5bcbd8963e3f61ce7bf6d635d6dadd1a91ddaa47b44065a",
            "/new-home": "e05e23707848917bd5bcbd8963e3f61ce7bf6d635d6dadd1a91ddaa47b44065a",
            "/request-quote": "060507aab53d82c01df105c487258e52cbf438453a04253eed545c209b55205b",
        }
        with patch.dict(os.environ, {"APP_ENVIRONMENT": "production",
                                     "PUBLIC_BASE_URL": "https://stage6.invalid",
                                     "GOOGLE_PLACES_API_KEY": ""}), \
                patch.object(m, "_google_reviews_html", return_value="<div>Synthetic reviews</div>"), \
                patch.object(m, "get_company_logo_value",
                             return_value="data:image/png;base64,dGVzdA=="):
            with TestClient(m.app) as client:
                for path, digest in page_hashes.items():
                    with self.subTest(path=path):
                        response = client.get(path)
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(hashlib.sha256(response.content).hexdigest(), digest)

    def test_active_homepage_open_app_navigation(self):
        m = self.module
        with patch.dict(os.environ, {"APP_ENVIRONMENT": "production",
                                     "PUBLIC_BASE_URL": "https://stage6.invalid",
                                     "GOOGLE_PLACES_API_KEY": ""}), \
                patch.object(m, "_google_reviews_html", return_value="<div>Synthetic reviews</div>"):
            with TestClient(m.app) as client:
                for path in ("/", "/new-home"):
                    with self.subTest(path=path):
                        response = client.get(path)
                        self.assertEqual(response.status_code, 200)
                        page = BeautifulSoup(response.text, "html.parser")
                        nav = page.select_one("header .navlinks")
                        self.assertIsNotNone(nav)
                        self.assertEqual([(a.get_text(strip=True), a.get("href"))
                                          for a in nav.select("a.btn")],
                                         [("Get a Quote", "/request-quote"),
                                          ("Open App", "/app")])
                        self.assertIn('class="mobile-contact"', response.text)
                        self.assertIn('href="/app"', response.text)
                self.assertEqual(client.get("/app").status_code, 401)
                self.assertEqual(client.get("/app", headers=self.auth_headers).status_code, 200)

    def test_customer_document_routes_remain_public(self):
        m = self.module
        request = m.QuoteRequest(customer_name="Document Test", labour_cost=10)
        result = m.calculate_quote(request)
        quote_id = m.save_quote(request.model_dump(), result)
        invoice = m.create_invoice_from_quote(quote_id)
        photo = m.invoice_photo_folder(invoice["id"]) / "public-test.jpg"
        Image.new("RGB", (12, 12), "blue").save(photo)
        photo_id = m.save_invoice_photo_record(invoice["id"], "after", "Test", photo.name, photo.name)
        urls = {
            "/invoice/{invoice_id}": f"/invoice/{invoice['id']}",
            "/api/quotes/{quote_id}/pdf": f"/api/quotes/{quote_id}/pdf",
            "/api/invoices/{invoice_id}/pdf": f"/api/invoices/{invoice['id']}/pdf",
            "/api/invoices/{invoice_id}/payment-qr": f"/api/invoices/{invoice['id']}/payment-qr",
            "/api/invoices/{invoice_id}/photos/{photo_id}":
                f"/api/invoices/{invoice['id']}/photos/{photo_id}",
        }
        self.assertEqual({("GET", key) for key in urls}, PUBLIC_CUSTOMER_ROUTES)
        with TestClient(m.app) as client:
            for template, url in urls.items():
                with self.subTest(path=template):
                    self.assertEqual(client.get(url).status_code, 200)
            self.assertEqual(client.get(f"/api/invoices/{invoice['id']}").status_code, 401)
            self.assertEqual(client.get(f"/api/quotes/{quote_id}").status_code, 401)

    def test_basic_auth_is_environment_backed_and_fails_closed(self):
        m = self.module
        with TestClient(m.app) as client:
            self.assertEqual(client.get("/app", headers=self.auth_headers).status_code, 200)
            self.assertEqual(client.get("/api/quotes", headers=self.auth_headers).status_code, 200)
            wrong = "Basic " + base64.b64encode(
                f"{self.test_username}:{secrets.token_urlsafe(24)}".encode()).decode()
            self.assertEqual(client.get("/api/quotes", headers={"Authorization": wrong}).status_code, 401)
            self.assertEqual(client.get("/api/quotes", headers={"Authorization": "Basic invalid"}).status_code, 401)
            malformed_unicode = "Basic " + base64.b64encode(
                f"{chr(233)}:{secrets.token_urlsafe(8)}".encode()).decode()
            self.assertEqual(client.get("/api/quotes", headers={"Authorization": malformed_unicode}).status_code, 401)
            with patch.object(m, "APP_USERNAME", ""), patch.object(m, "APP_PASSWORD", ""):
                self.assertEqual(client.get("/app", headers=self.auth_headers).status_code, 401)
                self.assertEqual(client.get("/api/quotes", headers=self.auth_headers).status_code, 401)

    def test_authenticated_cross_site_writes_rejected_before_handler(self):
        m = self.module
        attempts = (
            ("POST", "/api/quote", "/api/quote"),
            ("PUT", "/api/invoices/{invoice_id}", "/api/invoices/1"),
            ("DELETE", "/api/customers/{customer_id}", "/api/customers/1"),
            ("POST", "/api/invoices/{invoice_id}/send-email", "/api/invoices/1/send-email"),
            ("POST", "/api/invoices/{invoice_id}/photos", "/api/invoices/1/photos"),
            ("GET", "/api/live-product-refresh", "/api/live-product-refresh"),
        )
        with TestClient(m.app) as client:
            for method, template, path in attempts:
                route = next(r for r in m.app.routes if r.path == template and method in r.methods)
                for origin_headers in ({"Origin": "https://elsewhere.example"},
                                       {"Sec-Fetch-Site": "cross-site"}):
                    with self.subTest(path=template, headers=origin_headers), patch.object(
                        route.dependant, "call", side_effect=AssertionError("handler invoked")):
                        response = client.request(method, path,
                            headers={**self.auth_headers, **origin_headers})
                        self.assertEqual(response.status_code, 403)
            self.assertEqual(client.get("/api/quotes", headers={
                **self.auth_headers, "Origin": "http://testserver",
                "Sec-Fetch-Site": "same-origin",
            }).status_code, 200)
            valid = m.QuoteRequest(customer_name="Same Origin Test", job_description="Tap")
            self.assertEqual(client.post("/api/forgotten-items", json=valid.model_dump(), headers={
                **self.auth_headers, "Origin": "http://testserver",
                "Sec-Fetch-Site": "same-origin",
            }).status_code, 200)

    def test_invoice_email_sharing_baseline(self):
        m = self.module
        invoice = {
            "id": 47, "invoice_number": "INV-TEST-47", "job_reference": "JOB-47",
            "invoice": {"customer_name": "Pat & Co"}, "status": "part paid",
            "balance_due": 125.5, "payment_link": "https://example.test/pay/47",
        }
        logo = "data:image/png;base64," + base64.b64encode(b"test-logo").decode()
        with patch.object(m, "EMAIL_ENABLED", True), patch.object(m, "EMAIL_USER", "sender@example.test"), \
             patch.object(m, "EMAIL_PASS", "test-only"), patch.object(m, "EMAIL_FROM_NAME", "Test Sender"), \
             patch.object(m, "EMAIL_HOST", "smtp.example.test"), patch.object(m, "EMAIL_PORT", 465), \
             patch.object(m, "build_invoice_public_url", return_value="https://example.test/invoice/47") as url, \
             patch.object(m, "generate_invoice_pdf_bytes", return_value=b"%PDF-test-attachment") as pdf, \
             patch.object(m, "get_company_logo_value", return_value=logo), \
             patch.object(m.smtplib, "SMTP_SSL") as smtp:
            m.send_invoice_email_now(invoice, "  pat@example.test  ", " Please review <today>. ")
            smtp.assert_called_once()
            self.assertEqual(smtp.call_args.args, ("smtp.example.test", 465))
            server = smtp.return_value.__enter__.return_value
            server.login.assert_called_once_with("sender@example.test", "test-only")
            sender, recipients, raw = server.sendmail.call_args.args
            self.assertEqual((sender, recipients), ("sender@example.test", ["pat@example.test"]))
            url.assert_called_once_with(47)
            pdf.assert_called_once_with(invoice)
        msg = message_from_string(raw)
        self.assertEqual(msg["Subject"], "Invoice INV-TEST-47 - Job Ref JOB-47 - Nigel Harvey Ltd")
        self.assertEqual(msg["From"], "Test Sender <sender@example.test>")
        self.assertEqual(msg["To"], "pat@example.test")
        parts = list(msg.walk())
        plain = next(p for p in parts if p.get_content_type() == "text/plain").get_payload(decode=True).decode()
        html = next(p for p in parts if p.get_content_type() == "text/html").get_payload(decode=True).decode()
        self.assertIn("Hello Pat & Co,\n\nPlease review <today>.\n\nInvoice number: INV-TEST-47", plain)
        self.assertIn("Job Ref: JOB-47\nBalance due: £125.50\nInvoice link: https://example.test/invoice/47", plain)
        self.assertIn("Please review &lt;today&gt;.", html)
        self.assertIn('href="https://example.test/invoice/47"', html)
        self.assertIn("Hello Pat & Co,", html)
        attachment = next(p for p in parts if p.get_content_type() == "application/pdf")
        self.assertEqual(attachment.get_filename(), "INV-TEST-47.pdf")
        self.assertEqual(attachment.get_content_disposition(), "attachment")
        self.assertEqual(attachment.get_payload(decode=True), b"%PDF-test-attachment")
        image = next(p for p in parts if p.get_content_type() == "image/png")
        self.assertEqual((image.get("Content-ID"), image.get_filename()), ("<companylogo>", "logo.png"))

        with patch.object(m, "EMAIL_ENABLED", True), patch.object(m, "EMAIL_USER", "sender@example.test"), \
             patch.object(m, "EMAIL_PASS", "test-only"), patch.object(m, "get_company_logo_value", return_value=""), \
             patch.object(m, "generate_invoice_pdf_bytes", return_value=b"%PDF-default"), \
             patch.object(m.smtplib, "SMTP_SSL") as smtp:
            m.send_invoice_email_now({**invoice, "job_reference": ""}, "pat@example.test")
            raw_default = smtp.return_value.__enter__.return_value.sendmail.call_args.args[2]
        default_msg = message_from_string(raw_default)
        self.assertEqual(default_msg["Subject"], "Invoice INV-TEST-47 - Nigel Harvey Ltd")
        default_plain = next(p for p in default_msg.walk() if p.get_content_type() == "text/plain")
        self.assertIn("Please find your invoice attached as a PDF.\n\nInvoice number:",
                      default_plain.get_payload(decode=True).decode())
        self.assertIn("Job Ref: -", default_plain.get_payload(decode=True).decode())

    def test_invoice_email_route_responses_without_sending(self):
        m = self.module
        invoice = {"id": 47, "invoice_number": "INV-TEST-47", "invoice": {"customer_name": "Pat"},
                   "status": "unpaid", "balance_due": 50}
        with TestClient(m.app) as client, patch.object(m.smtplib, "SMTP_SSL") as smtp:
            client.headers.update(self.auth_headers)
            payload = {"to_email": "pat@example.test", "message": "Please review"}
            missing = client.post("/api/invoices/-1/send-email", json=payload)
            self.assertEqual((missing.status_code, missing.json()), (404, {"detail": "Invoice not found"}))
            with patch.object(m, "get_invoice_by_id", return_value=invoice):
                unconfigured = client.post("/api/invoices/47/send-email", json=payload)
                self.assertEqual((unconfigured.status_code, unconfigured.json()),
                                 (400, {"detail": "Email sending is not configured yet. Set EMAIL_ENABLED=1, EMAIL_USER and EMAIL_PASS."}))
                with patch.object(m, "EMAIL_ENABLED", True), patch.object(m, "EMAIL_USER", "sender@example.test"), \
                     patch.object(m, "EMAIL_PASS", "test-only"), patch.object(m, "get_company_logo_value", return_value=""), \
                     patch.object(m, "generate_invoice_pdf_bytes", return_value=b"%PDF-route"):
                    sent = client.post("/api/invoices/47/send-email", json=payload)
                    self.assertEqual((sent.status_code, sent.json()), (200, {"ok": True}))
                    smtp.side_effect = OSError("mock SMTP failure")
                    failed = client.post("/api/invoices/47/send-email", json=payload)
                    self.assertEqual((failed.status_code, failed.json()),
                                     (500, {"detail": "Email send failed: mock SMTP failure"}))
            self.assertEqual(smtp.call_count, 2)

    def test_browser_sharing_messages_and_phone_baseline(self):
        """Execute only pure browser snippets; never open a WhatsApp URL."""
        node = shutil.which("node")
        if not node:
            self.skipTest("Node is required to execute the existing browser sharing snippets")
        html = self.module.HTML
        normalise = html[html.index("function normalisePhone(phone) {"):html.index("function setEditingStatus(")]
        quote = html[html.index("function buildQuoteWhatsappMessage(data) {"):html.index("function renderQuoteResult(data) {")]
        invoice = html[html.index("  const invoiceUrl = window.location.origin + \"/invoice/\" + item.id;"):
                       html.index("  document.getElementById(\"invoiceOpenBtn\").href = invoiceUrl;")]
        script = f"""
const assert = require('node:assert/strict');
const window = {{location: {{origin: 'https://example.test'}}}};
const CURRENT_QUOTE_ID = 12;
const pounds = n => String.fromCharCode(163) + Number(n || 0).toFixed(2);
const document = {{nodes: {{}}, getElementById(id) {{return this.nodes[id] ||= {{href: ''}};}}}};
{normalise}
{quote}
assert.equal(normalisePhone('07595 725547'), '447595725547');
assert.equal(normalisePhone('+44 (7595) 725547'), '447595725547');
assert.equal(normalisePhone('not supplied'), '');
assert.equal(buildQuoteWhatsappMessage({{customer_name:'Pat', total_price:125.5}}),
  'Hi Pat,\\n\\nPlease find your quote below.\\n\\nQuote total: £125.50\\n\\nView/download your quote PDF:\\nhttps://example.test/api/quotes/12/pdf\\n\\nIf you have any questions, just let me know.\\n\\nNigel Harvey Ltd\\n07595 725547');
const item = {{id:47, invoice_number:'INV-TEST-47', balance_due:125.5}};
const invoice = {{customer_name:'Pat', customer_phone:'07595 725547'}};
const quoteResult = {{customer_phone:''}};
{invoice}
assert.equal(document.getElementById('invoiceWhatsappBtn').href,
 'https://wa.me/447595725547?text=' + encodeURIComponent('Nigel Harvey Ltd Invoice\\n\\nInvoice: INV-TEST-47\\nCustomer: Pat\\nBalance due: £125.50\\n\\nView your invoice:\\nhttps://example.test/invoice/47'));
"""
        result = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_http_app_access_and_public_site(self):
        m = self.module
        credentials = base64.b64encode(f"{m.APP_USERNAME}:{m.APP_PASSWORD}".encode()).decode()
        with TestClient(m.app) as client:
            blocked = client.get("/app")
            self.assertEqual(blocked.status_code, 401)
            self.assertEqual(blocked.headers["www-authenticate"], "Basic")
            self.assertEqual(client.get("/app", headers={"Authorization": "Basic invalid"}).status_code, 401)
            app_page = client.get("/app", headers={"Authorization": f"Basic {credentials}"})
            self.assertEqual(app_page.status_code, 200)
            self.assertIn("text/html", app_page.headers["content-type"])
            self.assertEqual(client.get("/api/quotes").status_code, 401)
            for path in ("/", "/new-home", "/request-quote", "/plumber-guildford", "/plumber-woking"):
                response = client.get(path)
                self.assertEqual(response.status_code, 200, path)
                self.assertIn("text/html", response.headers["content-type"])
            home = client.get("/").text
            self.assertIn("Plumber in Guildford", home)
            self.assertIn('rel="canonical"', home)
            # Established Surrey service URLs resolve despite route precedence.
            self.assertEqual(client.get("/emergency-plumber-surrey").status_code, 200)
            self.assertEqual(client.get("/general-plumbing-surrey").status_code, 200)
            self.assertEqual(client.get("/plumber-not-a-real-place").status_code, 404)
            sitemap = client.get("/sitemap.xml")
            self.assertEqual(sitemap.status_code, 200)
            self.assertIn("<urlset", sitemap.text)
            self.assertIn("plumber-guildford", sitemap.text)
            robots = client.get("/robots.txt")
            self.assertEqual(robots.status_code, 200)
            self.assertIn("Sitemap:", robots.text)

    def test_http_quote_invoice_pdf_customer_routes(self):
        m = self.module
        with TestClient(m.app) as client:
            client.headers.update(self.auth_headers)
            payload = m.QuoteRequest(customer_name="Route Customer", customer_address="4 Test Lane",
                                     customer_phone="07333333333", job_description="Install valve",
                                     labour_cost=100.10,
                                     materials=[m.MaterialItem(name="valve", quantity=2, manual_price=10)]).model_dump()
            created = client.post("/api/quote", json=payload)
            self.assertEqual(created.status_code, 200)
            quote = created.json()
            self.assertTrue({"id", "customer_id", "request", "result", "total_price"} <= quote.keys())
            self.assertEqual(quote["result"]["materials"], 25)
            self.assertEqual(quote["result"]["total_price"], 125.10)
            quote_id = quote["id"]
            self.assertEqual(client.get(f"/api/quotes/{quote_id}").json()["result"], quote["result"])
            self.assertTrue(any(q["id"] == quote_id for q in client.get("/api/quotes").json()))
            payload["labour_cost"] = 120.20
            updated = client.put(f"/api/quotes/{quote_id}", json=payload)
            self.assertEqual(updated.status_code, 200)
            self.assertEqual(updated.json()["result"]["total_price"], 145.20)
            pdf = client.get(f"/api/quotes/{quote_id}/pdf")
            self.assertEqual(pdf.status_code, 200)
            self.assertEqual(pdf.headers["content-type"], "application/pdf")
            self.assertTrue(pdf.content.startswith(b"%PDF"))

            converted = client.post(f"/api/quotes/{quote_id}/to-invoice")
            self.assertEqual(converted.status_code, 200)
            invoice = converted.json()
            self.assertTrue({"id", "invoice_number", "quote_id", "invoice", "quote_result",
                             "balance_due", "status", "photos"} <= invoice.keys())
            self.assertEqual(invoice["quote_id"], quote_id)
            self.assertEqual(invoice["invoice"]["job"], "Install valve")
            self.assertEqual(invoice["total_price"], 145.20)
            invoice_id = invoice["id"]
            self.assertEqual(client.get(f"/api/invoices/{invoice_id}").json(), invoice)
            self.assertTrue(any(i["id"] == invoice_id for i in client.get("/api/invoices").json()))
            public = client.get(f"/invoice/{invoice_id}")
            self.assertEqual(public.status_code, 200)
            self.assertIn(invoice["invoice_number"], public.text)
            self.assertIn("Route Customer", public.text)
            self.assertIn(f"/api/invoices/{invoice_id}/pdf", public.text)
            invoice_pdf = client.get(f"/api/invoices/{invoice_id}/pdf")
            self.assertEqual(invoice_pdf.status_code, 200)
            self.assertTrue(invoice_pdf.content.startswith(b"%PDF"))
            self.assertEqual(client.get(f"/api/invoices/{invoice_id}/payment-qr").status_code, 200)
            edit = m.InvoiceEditRequest(customer_name="Route Customer", customer_address="4 Test Lane",
                                        customer_phone="07333333333", job="Install valve",
                                        job_reference="ROUTE-1", labour=120.20, materials=25,
                                        due_date=invoice["due_date"],
                                        payment_link="https://example.test/pay", amount_paid=0).model_dump()
            edited = client.put(f"/api/invoices/{invoice_id}", json=edit)
            self.assertEqual(edited.status_code, 200)
            self.assertEqual(edited.json()["job_reference"], "ROUTE-1")
            self.assertEqual(edited.json()["payment_link"], "https://example.test/pay")
            status = client.post(f"/api/invoices/{invoice_id}/status",
                                 json={"status": "part paid", "amount_paid": 20})
            self.assertEqual(status.status_code, 200)
            self.assertEqual(status.json()["amount_paid"], 20)
            self.assertEqual(status.json()["balance_due"], 125.20)
            self.assertEqual(client.put("/api/invoices/-1", json=edit).status_code, 404)

            customers = client.get("/api/customers")
            self.assertEqual(customers.status_code, 200)
            customer_id = quote["customer_id"]
            self.assertTrue(any(c["id"] == customer_id for c in customers.json()))
            history = client.get(f"/api/customers/{customer_id}/history")
            self.assertEqual(history.status_code, 200)
            self.assertIn("quotes", history.json())
            self.assertIn("invoices", history.json())
            self.assertEqual(client.get("/api/customers/-1/history").status_code, 404)
            self.assertEqual(client.get("/invoice/-1").status_code, 404)
            self.assertEqual(client.get("/api/quotes/-1/pdf").status_code, 404)
            self.assertEqual(client.get("/api/invoices/-1/pdf").status_code, 404)
            self.assertEqual(client.delete(f"/api/invoices/{invoice_id}").status_code, 200)
            self.assertEqual(client.delete(f"/api/quotes/{quote_id}").status_code, 200)
            self.assertEqual(client.delete(f"/api/customers/{customer_id}").status_code, 200)

    def test_http_material_routes_without_network(self):
        m = self.module
        credentials = base64.b64encode(f"{m.APP_USERNAME}:{m.APP_PASSWORD}".encode()).decode()
        headers = {"Authorization": f"Basic {credentials}"}
        with TestClient(m.app) as client:
            self.assertEqual(client.get("/api/material-prices").status_code, 401)
            self.assertEqual(client.get("/api/material-search?q=ptfe").status_code, 401)
            lookup = client.get("/api/material-search?q=ptfe", headers=headers)
            self.assertEqual(lookup.status_code, 200)
            self.assertIsInstance(lookup.json(), list)
            resolved = client.get("/api/material-resolve?name=ptfe%20tape", headers=headers)
            self.assertEqual(resolved.status_code, 200)
            self.assertEqual(set(resolved.json()), {"requested_name", "matched", "best", "alternatives"})
            self.assertEqual(client.get("/api/material-resolve", headers=headers).status_code, 400)
            self.assertEqual(client.get("/api/material-alias?q=ptfe", headers=headers).status_code, 200)
            self.assertEqual(client.get("/api/material-charging?q=ptfe", headers=headers).status_code, 200)
            url = "https://example.test/route-material"
            m.upsert_material_price_cache(url, "Route valve", "Test", price=5, status="live")
            rows = client.get("/api/material-prices", headers=headers).json()
            item = next(row for row in rows if row["url"] == url)
            changed = client.put(f"/api/material-prices/{item['id']}", headers=headers,
                                 json={"name": "Changed", "supplier": "Test", "url": url, "manual_price": 7.25})
            self.assertEqual((changed.status_code, changed.json()), (200, {"ok": True}))
            deleted = client.delete(f"/api/material-prices/{item['id']}", headers=headers)
            self.assertEqual((deleted.status_code, deleted.json()), (200, {"ok": True}))
            self.assertEqual(client.delete("/api/material-prices/-1", headers=headers).status_code, 404)

    def test_customer_lookup_history_and_delete_order_baseline(self):
        m = self.module
        suffix = secrets.token_hex(5)
        phone = "07" + suffix
        customer_id = m.upsert_customer("  First " + suffix + "  ", " 1 Test Road ", phone)
        self.assertEqual(m.upsert_customer(" Updated " + suffix, " 2 Test Road ", phone), customer_id)
        conn = m.get_db()
        row = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        self.assertEqual((row["name"], row["address"], row["phone"]),
                         ("Updated " + suffix, "2 Test Road", phone))
        conn.close()
        self.assertEqual(m.upsert_customer("Updated " + suffix, "2 Test Road", ""), customer_id)
        self.assertEqual(set(next(c for c in m.get_customers() if c["id"] == customer_id)),
                         {"id", "name", "address", "phone", "updated_at"})
        self.assertIsNone(m.get_customer_history(-1))

        request = m.QuoteRequest(customer_name="Updated " + suffix,
                                 customer_address="2 Test Road", customer_phone=phone,
                                 job_description="Test customer history", labour_cost=12)
        quote_id = m.save_quote(request.model_dump(), m.calculate_quote(request))
        invoice = m.create_invoice_from_quote(quote_id)
        self.assertEqual(m.get_quote_by_id(quote_id)["customer_id"], customer_id)
        self.assertEqual(invoice["customer_id"], customer_id)
        history = m.get_customer_history(customer_id)
        self.assertEqual(set(history), {"customer", "quotes", "invoices"})
        self.assertEqual(history["customer"], {
            "id": customer_id, "name": "Updated " + suffix,
            "address": "2 Test Road", "phone": phone,
        })
        self.assertIn(quote_id, [q["id"] for q in history["quotes"]])
        self.assertIn(invoice["id"], [i["id"] for i in history["invoices"]])
        photo_file = m.invoice_photo_folder(invoice["id"]) / "cascade-existing.jpg"
        photo_file.write_bytes(b"fixture")
        photo_id = m.save_invoice_photo_record(invoice["id"], "after", "Cascade fixture",
                                                photo_file.name, photo_file.name)

        # Temporary-database triggers record the existing child-before-customer delete order.
        conn = m.get_db()
        conn.execute("CREATE TABLE customer_delete_order (seq INTEGER PRIMARY KEY, item TEXT)")
        for table in ("invoices", "quotes", "customers"):
            conn.execute(f"CREATE TRIGGER watch_{table}_delete AFTER DELETE ON {table} "
                         f"BEGIN INSERT INTO customer_delete_order(item) VALUES ('{table}'); END")
        conn.commit()
        conn.close()
        with TestClient(m.app) as client:
            self.assertEqual(client.delete("/api/customers/-1", headers=self.auth_headers).status_code, 404)
            deleted = client.delete(f"/api/customers/{customer_id}", headers=self.auth_headers)
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json(), {"ok": True, "deleted_customers": 1,
                                          "deleted_quotes": 1, "deleted_invoices": 1})
        conn = m.get_db()
        order = [r["item"] for r in conn.execute("SELECT item FROM customer_delete_order ORDER BY seq")]
        self.assertEqual(order, ["invoices", "quotes", "customers"])
        for table in ("customers", "quotes", "invoices"):
            conn.execute(f"DROP TRIGGER watch_{table}_delete")
        conn.execute("DROP TABLE customer_delete_order")
        conn.commit()
        conn.close()
        self.assertIsNone(m.get_customer_history(customer_id))
        self.assertIsNone(m.get_invoice_by_id(invoice["id"]))
        # The existing customer cascade leaves photo metadata/files orphaned.
        self.assertEqual(m.load_invoice_photos(invoice["id"])[0]["id"], photo_id)
        self.assertTrue(photo_file.exists())
        self.assertTrue(m.delete_invoice_photo_record(invoice["id"], photo_id))

    def test_lead_fields_status_notification_and_missing_ids_baseline(self):
        m = self.module
        seen = []
        def committed_before_notification(lead):
            seen.append(m.get_lead_by_id(lead["id"]))

        with TestClient(m.app) as client, patch.object(
            m, "send_lead_notification_email", side_effect=committed_before_notification
        ):
            created = client.post("/api/leads", json={
                "name": "  Test Lead  ", "phone": " 07123456789 ",
                "email": " lead@example.test ", "address": " 5 Example Road ",
                "job_type": " bathroom ", "description": "  Replace tap  ", "source": " referral ",
            })
            self.assertEqual(created.status_code, 200)
            lead = created.json()
            self.assertEqual(set(lead), {"id", "name", "phone", "email", "address",
                                         "job_type", "description", "status", "source",
                                         "created_at", "updated_at"})
            self.assertEqual((lead["name"], lead["phone"], lead["email"], lead["address"],
                              lead["job_type"], lead["description"], lead["status"], lead["source"]),
                             ("Test Lead", "07123456789", "lead@example.test", "5 Example Road",
                              "bathroom", "Replace tap", "new", "referral"))
            self.assertEqual(seen, [lead])
            self.assertEqual(m.get_lead_by_id(lead["id"]), lead)
            self.assertIn(lead, client.get("/api/leads", headers=self.auth_headers).json())
            changed = client.put(f"/api/leads/{lead['id']}/status", headers=self.auth_headers,
                                 json={"status": " WON "})
            self.assertEqual(changed.status_code, 200)
            self.assertEqual(changed.json()["status"], "won")
            self.assertEqual(changed.json()["name"], lead["name"])
            self.assertEqual(m.update_lead_status(lead["id"], "invalid")["status"], "new")
            self.assertIsNone(m.get_lead_by_id(-1))
            self.assertIsNone(m.update_lead_status(-1, "won"))
            self.assertFalse(m.delete_lead_by_id(-1))
            self.assertEqual(client.put("/api/leads/-1/status", headers=self.auth_headers,
                                        json={"status": "won"}).status_code, 404)
            self.assertEqual(client.delete("/api/leads/-1", headers=self.auth_headers).status_code, 404)
            self.assertEqual(client.delete(f"/api/leads/{lead['id']}", headers=self.auth_headers).json(),
                             {"ok": True})
            self.assertIsNone(m.get_lead_by_id(lead["id"]))

    def test_invoice_photo_metadata_file_and_commit_order_baseline(self):
        m = self.module
        request = m.QuoteRequest(customer_name="Photo Baseline " + secrets.token_hex(4),
                                 job_description="Photo fixture", labour_cost=10)
        invoice = m.create_invoice_from_quote(
            m.save_quote(request.model_dump(), m.calculate_quote(request)))
        invoice_id = invoice["id"]
        self.assertEqual(m.load_invoice_photos(invoice_id), [])
        self.assertIsNone(m.invoice_photo_path(invoice_id, -1))
        self.assertFalse(m.delete_invoice_photo_record(invoice_id, -1))
        self.assertEqual(m.normalise_photo_category(" Hidden pipework "), "hidden_pipework")
        self.assertEqual(m.normalise_photo_category("unknown"), "other")
        image = io.BytesIO()
        Image.new("RGBA", (20, 15), (200, 100, 40, 128)).save(image, format="PNG")
        image_bytes = image.getvalue()
        persisted_before_record = []
        save_record = m.save_invoice_photo_record
        def inspect_save(*args):
            persisted_before_record.append((m.invoice_photo_folder(invoice_id) / args[3]).is_file())
            return save_record(*args)

        with TestClient(m.app) as client, patch.object(m, "save_invoice_photo_record", side_effect=inspect_save):
            uploaded = client.post(f"/api/invoices/{invoice_id}/photos", headers=self.auth_headers,
                                   data={"category": "before", "caption": "  First visit  "},
                                   files=[("photos", ("visit.png", image_bytes, "image/png"))])
            self.assertEqual(client.post("/api/invoices/-1/photos", headers=self.auth_headers,
                                         files=[("photos", ("visit.png", image_bytes, "image/png"))]).status_code, 404)
        self.assertEqual(uploaded.status_code, 200)
        self.assertEqual(persisted_before_record, [True])
        result = uploaded.json()
        self.assertEqual((result["ok"], result["added"], result["errors"]), (True, 1, []))
        photo = result["photos"][0]
        self.assertEqual(set(photo), {"id", "invoice_id", "category", "category_label",
                                      "caption", "filename", "original_filename", "sort_order",
                                      "created_at", "url"})
        self.assertEqual((photo["category"], photo["category_label"], photo["caption"],
                          photo["original_filename"], photo["sort_order"]),
                         ("before", "Before", "First visit", "visit.png", 1))
        self.assertEqual(photo["url"], f"/api/invoices/{invoice_id}/photos/{photo['id']}")
        path = m.invoice_photo_path(invoice_id, photo["id"])
        self.assertEqual(path.parent, m.invoice_photo_folder(invoice_id))
        self.assertTrue(path.exists())
        with Image.open(path) as stored:
            self.assertEqual((stored.format, stored.mode), ("JPEG", "RGB"))
        self.assertEqual(m.get_invoice_by_id(invoice_id)["photos"], [photo])

        original_unlink = Path.unlink
        rows_at_unlink = []
        def inspect_unlink(path, *args, **kwargs):
            rows_at_unlink.append(m.load_invoice_photos(invoice_id))
            return original_unlink(path, *args, **kwargs)
        with patch.object(Path, "unlink", inspect_unlink), TestClient(m.app) as client:
            self.assertEqual(client.get(photo["url"]).content, path.read_bytes())
            deleted = client.delete(photo["url"], headers=self.auth_headers)
            self.assertEqual(deleted.json(), {"ok": True, "photos": []})
            self.assertEqual(client.get(photo["url"]).status_code, 404)
            self.assertEqual(client.delete(photo["url"], headers=self.auth_headers).status_code, 404)
        self.assertEqual(rows_at_unlink, [[]])
        self.assertFalse(path.exists())
        self.assertIsNone(m.invoice_photo_path(invoice_id, photo["id"]))

    def test_model_defaults_and_quote_calculation(self):
        request = self.module.QuoteRequest(customer_name="Test Customer", labour_cost=200,
            materials=[self.module.MaterialItem(name="Tap", quantity=2, manual_price=10)])
        self.assertEqual(request.materials_handling_percent, 25)
        result = self.module.calculate_quote(request)
        self.assertEqual(result["materials"], 25)
        self.assertEqual(result["total_price"], 225)
        self.assertEqual(result["deposit_amount"], 0)
        self.assertEqual(result["material_lines"][0]["line_total"], 20)

    def test_database_and_pdfs(self):
        m = self.module
        self.assertTrue(m.DB_PATH.exists())
        request = m.QuoteRequest(customer_name="Test Customer", labour_cost=200)
        quote_id = m.save_quote(request.model_dump(), m.calculate_quote(request))
        quote = m.get_quote_by_id(quote_id)
        self.assertEqual(quote["result"]["total_price"], 200)
        self.assertTrue(m.generate_quote_pdf_bytes(quote).startswith(b"%PDF"))
        invoice = m.create_invoice_from_quote(quote_id)
        self.assertTrue(m.generate_invoice_pdf_bytes(invoice).startswith(b"%PDF"))
        self.assertIn("/invoice/", m.build_invoice_public_url(invoice["id"]))

    def test_pdf_visible_content_and_photo(self):
        m = self.module
        request = m.QuoteRequest(
            customer_name="PDF Customer", customer_address="5 Sample Street",
            customer_phone="07444444444", job_description="Replace bathroom tap and valve",
            labour_cost=120, include_callout_charge=True, callout_charge=30,
            include_travel_charge=True, travel_charge=15,
            materials=[m.MaterialItem(name="valve", quantity=2, manual_price=10)],
            deposit_percent=50,
        )
        result = m.calculate_quote(request)
        quote_id = m.save_quote(request.model_dump(), result)
        quote = m.get_quote_by_id(quote_id)
        quote_pdf = m.generate_quote_pdf_bytes(quote)
        quote_reader = PdfReader(io.BytesIO(quote_pdf))
        quote_text = "\n".join(page.extract_text() or "" for page in quote_reader.pages)
        for visible in ("PDF Customer", "5 Sample Street", "07444444444",
                        "Replace bathroom tap and valve", "Materials Used", "valve (manual)",
                        "Labour", "Call-out charge", "Travel charge", "Materials supplied",
                        "Materials procurement & handling (25%)", "Deposit", "Total Price",
                        "£120.00", "£30.00", "£15.00", "£25.00", "£190.00"):
            self.assertIn(visible, quote_text)
        self.assertIn(f"Quote #{quote_id}", quote_text)

        invoice = m.create_invoice_from_quote(quote_id)
        edit = m.InvoiceEditRequest(
            customer_name="PDF Customer", customer_address="5 Sample Street",
            customer_phone="07444444444", job="Replace bathroom tap and valve",
            job_reference="PDF-JOB-7", labour=120, materials=25,
            callout_charge=30, travel_charge=15, due_date=invoice["due_date"],
            payment_link="https://example.test/pay/pdf-7", amount_paid=20,
        )
        invoice = m.update_invoice_by_id(invoice["id"], edit)
        photo_path = m.invoice_photo_folder(invoice["id"]) / "sample.jpg"
        Image.new("RGB", (90, 60), "blue").save(photo_path)
        m.save_invoice_photo_record(invoice["id"], "after", "Completed sample work",
                                    photo_path.name, "sample.jpg")
        invoice = m.get_invoice_by_id(invoice["id"])
        invoice_pdf = m.generate_invoice_pdf_bytes(invoice)
        invoice_reader = PdfReader(io.BytesIO(invoice_pdf))
        invoice_text = "\n".join(page.extract_text() or "" for page in invoice_reader.pages)
        for visible in (invoice["invoice_number"], "PDF Customer", "5 Sample Street",
                        "PDF-JOB-7", "Replace bathroom tap and valve", "Materials Used",
                        "Labour", "Call-out charge", "Travel charge", "Invoice totals",
                        "£190.00", "£20.00", "£170.00", "Payment details", "Bank transfer",
                        m.BANK_NAME, m.BANK_ACCOUNT_NAME, m.BANK_SORT_CODE,
                        m.BANK_ACCOUNT_NUMBER, "Reference", "Amount due",
                        "https://example.test/pay/pdf-7", "Job Photos", "Completed sample work"):
            self.assertIn(visible, invoice_text)
        self.assertGreaterEqual(len(invoice_reader.pages), 2)
        self.assertEqual(m.bank_payment_reference(invoice), invoice["invoice_number"])
        self.assertTrue(m.bank_payment_qr_png(invoice).startswith(b"\x89PNG"))
        with TestClient(m.app) as client:
            quote_route = client.get(f"/api/quotes/{quote_id}/pdf")
            invoice_route = client.get(f"/api/invoices/{invoice['id']}/pdf")
            self.assertEqual(quote_route.headers["content-disposition"],
                             f'attachment; filename="quote-{quote_id}.pdf"')
            self.assertEqual(invoice_route.headers["content-disposition"],
                             f'attachment; filename="{invoice["invoice_number"]}.pdf"')
            self.assertEqual(client.get(f"/api/quotes/{quote_id}/pdf?view=1").headers["content-disposition"],
                             f'inline; filename="quote-{quote_id}.pdf"')
            self.assertEqual(client.get(f"/api/invoices/{invoice["id"]}/pdf?view=1").headers["content-disposition"],
                             f'inline; filename="{invoice["invoice_number"]}.pdf"')

    def test_database_schema_connection_and_counts(self):
        m = self.module
        conn = m.get_db()
        self.assertIsInstance(conn.row_factory, type(sqlite3.Row))
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"customers", "quotes", "invoices", "invoice_photos", "leads",
                         "material_price_cache", "material_price_history",
                         "quote_intelligence", "app_backups"} <= tables)
        invoice_columns = {row["name"]: row for row in conn.execute("PRAGMA table_info(invoices)")}
        self.assertEqual(invoice_columns["reminders_enabled"]["dflt_value"], "0")
        self.assertEqual(invoice_columns["status"]["notnull"], 1)
        cache_columns = {row["name"]: row for row in conn.execute("PRAGMA table_info(material_price_cache)")}
        self.assertEqual(cache_columns["times_used"]["dflt_value"], "0")
        conn.close()
        before = m.database_counts()
        self.assertEqual(set(before), {"customers", "quotes", "invoices", "leads", "material_price_cache"})
        m.init_db()
        self.assertEqual(m.database_counts(), before)

    def test_invoice_number_and_database_backup(self):
        m = self.module
        first = m.next_invoice_number()
        self.assertTrue(first)
        backup = m.create_db_backup("baseline test")
        self.assertEqual(backup["reason"], "baseline test")
        self.assertTrue(Path(backup["path"]).exists())
        self.assertTrue(any(item["filename"] == backup["filename"] for item in m.list_db_backups()))
        conn = sqlite3.connect(backup["path"])
        self.assertTrue(conn.execute("SELECT name FROM sqlite_master WHERE name='quotes'").fetchone())
        conn.close()

    def test_invoice_lifecycle_and_missing_ids(self):
        m = self.module
        request = m.QuoteRequest(
            customer_name="Invoice Customer", customer_address="2 Test Road",
            customer_phone="07111111111", job_description="Heating and tap work",
            labour_cost=100.10, include_callout_charge=True, callout_charge=20.20,
            include_travel_charge=True, travel_charge=10.30,
            materials=[m.MaterialItem(name="Valve", quantity=2, manual_price=5.55)],
            deposit_percent=25,
        )
        result = m.calculate_quote(request)
        quote_id = m.save_quote(request.model_dump(), result)
        number = m.next_invoice_number()
        invoice = m.create_invoice_from_quote(quote_id)
        self.assertEqual(invoice["invoice_number"], number)
        self.assertEqual(invoice["customer_name"], "Invoice Customer")
        self.assertEqual(invoice["customer_id"], m.get_quote_by_id(quote_id)["customer_id"])
        self.assertEqual(invoice["quote_result"], result)
        self.assertEqual(invoice["invoice"]["job"], "Heating and tap work")
        for field in ("labour", "materials", "callout_charge", "travel_charge",
                      "total_price", "deposit_amount", "deposit_percent"):
            self.assertEqual(invoice["invoice"][field], result[field])
        self.assertEqual(invoice["payment_link"], "")
        self.assertEqual(invoice["job_reference"], "")
        self.assertEqual(invoice["amount_paid"], 0)
        self.assertEqual(invoice["balance_due"], result["total_price"])
        self.assertEqual(invoice["status"], "unpaid")
        self.assertEqual(invoice["invoice"]["due_date"], invoice["due_date"])
        self.assertEqual(m.build_invoice_public_url(invoice["id"]),
                         f"https://www.nigelharveyplumbing.co.uk/invoice/{invoice['id']}")
        self.assertEqual(m.get_invoice_by_id(invoice["id"]), invoice)
        self.assertIn(invoice, m.load_invoices())

        edited = m.InvoiceEditRequest(
            customer_name="Edited Customer", customer_address="3 Test Road",
            customer_phone="07222222222", job="Updated work", job_reference="JOB-42",
            labour=111.125, materials=22.235, callout_charge=33.345,
            travel_charge=44.455, due_date="20/10/2026",
            payment_link="https://example.test/pay/42", amount_paid=50.01,
            reminder_email="customer@example.test", reminders_enabled=True,
        )
        updated = m.update_invoice_by_id(invoice["id"], edited)
        self.assertEqual(updated["id"], invoice["id"])
        self.assertEqual(updated["invoice_number"], number)
        self.assertEqual(updated["customer_name"], "Edited Customer")
        self.assertEqual(updated["invoice"]["customer_address"], "3 Test Road")
        self.assertEqual(updated["invoice"]["job"], "Updated work")
        self.assertEqual(updated["job_reference"], "JOB-42")
        self.assertEqual(updated["payment_link"], "https://example.test/pay/42")
        self.assertEqual(updated["due_date"], "20/10/2026")
        self.assertEqual(updated["reminder_email"], "customer@example.test")
        self.assertTrue(updated["reminders_enabled"])
        self.assertEqual(updated["invoice"]["labour"], 111.12)
        self.assertEqual(updated["invoice"]["materials"], 22.23)
        self.assertEqual(updated["invoice"]["callout_charge"], 33.34)
        self.assertEqual(updated["invoice"]["travel_charge"], 44.45)
        self.assertEqual(updated["total_price"], 211.16)
        self.assertEqual(updated["amount_paid"], 50.01)
        self.assertEqual(updated["balance_due"], 161.15)
        self.assertEqual(updated["status"], "part paid")
        paid = m.update_invoice_status(invoice["id"], "unpaid", 9999)
        self.assertEqual(paid["status"], "paid")
        self.assertEqual(paid["amount_paid"], paid["total_price"])
        self.assertEqual(paid["balance_due"], 0)

        self.assertIsNone(m.get_invoice_by_id(-1))
        self.assertIsNone(m.update_invoice_by_id(-1, edited))
        self.assertIsNone(m.update_invoice_status(-1, "paid", 1))
        self.assertFalse(m.delete_invoice_by_id(-1))
        self.assertTrue(m.delete_invoice_by_id(invoice["id"]))
        self.assertIsNone(m.get_invoice_by_id(invoice["id"]))
        self.assertFalse(m.delete_invoice_by_id(invoice["id"]))
        self.assertEqual(m.next_invoice_number(), number)  # COUNT-based numbering after deletion

    def test_material_cache_routes_lookup_and_fallback(self):
        m = self.module
        credential = base64.b64encode(f"{m.APP_USERNAME}:{m.APP_PASSWORD}".encode()).decode()
        request = m.Request({"type": "http", "method": "GET", "path": "/api/material-prices",
                             "headers": [(b"authorization", f"Basic {credential}".encode())]})
        url = "https://example.test/material/valve"
        m.upsert_material_price_cache(url, "Valve", "Test Supplier", price=12.345,
                                      manual_price=10.25, status="live")
        cached = m.get_cached_material_price(url)
        self.assertEqual(cached["name"], "Valve")
        self.assertEqual(cached["supplier"], "Test Supplier")
        self.assertEqual(cached["last_price"], 12.345)
        self.assertEqual(cached["last_live_price"], 12.345)
        self.assertEqual(cached["last_manual_price"], 10.25)
        self.assertEqual(cached["times_used"], 1)
        self.assertEqual(cached["last_status"], "live")
        m.upsert_material_price_cache(url, "", "", price=11.5, status="cached")
        cached = m.get_cached_material_price(url)
        self.assertEqual(cached["name"], "Valve")
        self.assertEqual(cached["last_price"], 11.5)
        self.assertEqual(cached["last_live_price"], 12.345)
        self.assertEqual(cached["last_manual_price"], 10.25)
        self.assertEqual(cached["times_used"], 2)
        self.assertEqual(cached["last_status"], "cached")
        self.assertIsNone(m.get_cached_material_price(""))
        self.assertEqual(m.normalize_material_url(f" {url} "), url)

        listed = json.loads(m.api_material_prices(request).body)
        self.assertEqual(next(row for row in listed if row["id"] == cached["id"])["last_price"], 11.5)
        library = m.get_material_search_library()
        self.assertTrue(any(item.get("url") == url for item in library))
        searched = json.loads(m.api_material_search("Valve", request).body)
        self.assertTrue(any(item.get("url") == url for item in searched))
        resolved = json.loads(m.api_material_resolve("Valve", request).body)
        self.assertTrue(resolved["matched"])
        self.assertEqual(resolved["requested_name"], "Valve")

        old_scraper = m.scrape_live_price
        try:
            m.scrape_live_price = lambda _url: None
            self.assertEqual(m.fetch_tracked_price(url, "Valve", "Test Supplier", 10.25), (12.345, "cached"))
        finally:
            m.scrape_live_price = old_scraper
        self.assertEqual(m.get_cached_material_price(url)["last_status"], "cached")
        payload = m.MaterialCacheUpdateRequest(name="Changed Valve", supplier="Other",
                                                url=url, manual_price=9.75)
        self.assertEqual(m.api_update_material_price(cached["id"], payload, request), {"ok": True})
        changed = m.get_cached_material_price(url)
        self.assertEqual((changed["name"], changed["supplier"], changed["last_manual_price"]),
                         ("Changed Valve", "Other", 9.75))
        self.assertEqual(m.api_delete_material_price(cached["id"], request), {"ok": True})
        self.assertIsNone(m.get_cached_material_price(url))

    def test_material_charging_and_quote_totals(self):
        m = self.module
        self.assertEqual(m.MaterialItem().model_dump()["charge_method"], "full")
        self.assertEqual(m.MaterialItem().model_dump()["manual_price"], 0)
        self.assertEqual(m.get_material_charging_rule("ptfe tape")["default_charge"], 0.5)
        self.assertEqual(m.material_quote_unit_price("ptfe tape", 8), 0.5)
        self.assertEqual(m.material_quote_unit_price("ptfe tape", 8, 1.25), 1.25)
        self.assertEqual(m.material_quote_unit_price("valve", 8), 8)
        data = m.QuoteRequest(labour_cost=100, materials=[
            m.MaterialItem(name="ptfe tape", quantity=2, manual_price=8),
            m.MaterialItem(name="valve", quantity=1, manual_price=20)])
        result = m.calculate_quote(data)
        self.assertEqual(result["internal_raw_materials"], 21)
        self.assertEqual(result["materials_base"], 21)
        self.assertEqual(result["materials_procurement_amount"], 5.25)
        self.assertEqual(result["materials"], 26.25)
        self.assertEqual(result["total_price"], 126.25)
        self.assertEqual(result["material_lines"][0]["full_unit_price"], 8)
        self.assertEqual(result["material_lines"][0]["unit_price_used"], 0.5)
        no_handling = m.calculate_quote(data.model_copy(update={"include_materials_handling": False}))
        self.assertEqual(no_handling["materials"], 21)
        self.assertEqual(no_handling["total_price"], 121)

    def test_quote_calculation_golden_cases_without_live_pricing(self):
        """Full output snapshots from the pre-extraction calculation, including raw rounding."""
        m = self.module
        golden = json.loads((ROOT / "tests/quote_calculation_golden.json").read_text())
        fixed = datetime.fromisoformat(golden["fixed_time"])
        self.assertEqual(fixed.utcoffset(), ZoneInfo("Europe/London").utcoffset(fixed))
        prices = {url: tuple(result) for url, result in golden["mock_prices"].items()}
        requested_urls = []
        def mocked_price(url, *args):
            requested_urls.append(url)
            if url not in prices:
                raise AssertionError("A live merchant lookup was attempted")
            return prices[url]

        with patch.object(m, "now_uk", return_value=fixed), \
                patch.object(m, "fetch_tracked_price", side_effect=mocked_price):
            for case in golden["cases"]:
                with self.subTest(case=case["name"]):
                    result = m.calculate_quote(m.QuoteRequest.model_validate(case["request"]))
                    self.assertEqual(result, case["expected"])
                    self.assertEqual(set(result), set(case["expected"]))
                    self.assertNotIn("vat", result)
                    self.assertNotIn("discount", result)
            self.assertEqual(requested_urls, list(prices))

        unusual = next(c["expected"] for c in golden["cases"]
                       if c["name"] == "consumables_quantities")
        # Current raw-float arithmetic can differ from a sum of displayed rounded parts.
        self.assertEqual(unusual["materials"], 30.02)
        self.assertEqual(unusual["materials_base"] + unusual["materials_procurement_amount"], 30.01)

    def test_local_quote_rule_snapshots_and_matching(self):
        m = self.module
        golden = json.loads((ROOT / "tests/quote_calculation_golden.json").read_text())
        for name, expected in golden["rule_hashes"].items():
            value = m.get_all_job_templates() if name == "assembled_templates" else getattr(m, name)
            digest = hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            self.assertEqual(digest, expected, name)
        self.assertEqual(len(m.get_all_job_templates()), 36)
        self.assertEqual(m.canonical_material_name("Plumbright PTFE tape"), "ptfe tape")
        self.assertEqual(m.get_material_charging_rule("ptfe tape")["default_charge"], 0.50)
        self.assertEqual(m.material_quote_unit_price("ptfe tape", 8), 0.50)
        self.assertEqual(m.material_quote_unit_price("ptfe tape", 8, 0), 0)
        self.assertEqual(m.canonical_material_name("15mm copper olive"), "15mm copper pipe")
        self.assertEqual(m.material_quote_unit_price("15mm copper olive", 5), 5)
        self.assertEqual(m.suggest_material_quantity("15mm pipe clips", "outside tap"), 6)
        self.assertEqual(m.find_labour_suggestion("small", "replace tap")["suggestion"], 120)

    def test_quote_save_load_update_and_conversion(self):
        m = self.module
        request = m.QuoteRequest(
            quote_type="small", customer_name="Before Customer",
            customer_address="1 Test Street", customer_phone="07000000000",
            job_description="Replace basin tap", labour_cost=101.235,
            materials=[m.MaterialItem(name="Basin tap", quantity=2, manual_price=12.345)],
            deposit_percent=50,
        )
        result = m.calculate_quote(request)
        self.assertEqual(result["labour"], 101.23)
        self.assertEqual(result["materials"], 30.86)
        self.assertEqual(result["total_price"], 132.1)
        self.assertEqual(result["deposit_amount"], 66.05)
        quote_id = m.save_quote(request.model_dump(), result)
        saved = m.get_quote_by_id(quote_id)
        self.assertEqual(saved["request"], request.model_dump())
        self.assertEqual(saved["result"], result)
        self.assertIn(saved, m.load_quotes())
        self.assertEqual(saved["id"], quote_id)
        self.assertEqual(saved["customer_name"], "Before Customer")

        edited = request.model_copy(update={
            "customer_name": "After Customer", "labour_cost": 202.25,
            "job_description": "Replace kitchen tap"})
        edited_result = m.calculate_quote(edited)
        updated = m.update_quote_by_id(quote_id, edited.model_dump(), edited_result)
        self.assertEqual(updated["id"], quote_id)
        self.assertEqual(updated["result"], edited_result)
        self.assertEqual(updated["request"], edited.model_dump())
        self.assertEqual(updated["customer_name"], "After Customer")
        self.assertIsNone(m.update_quote_by_id(-1, edited.model_dump(), edited_result))

        expected_number = m.next_invoice_number()
        invoice = m.create_invoice_from_quote(quote_id)
        self.assertEqual(invoice["invoice_number"], expected_number)
        self.assertEqual(invoice["quote_id"], quote_id)
        self.assertEqual(invoice["customer_id"], updated["customer_id"])
        self.assertEqual(invoice["quote_result"], edited_result)
        self.assertEqual(invoice["invoice"]["customer_name"], "After Customer")
        self.assertEqual(invoice["invoice"]["customer_address"], "1 Test Street")
        self.assertEqual(invoice["invoice"]["job"], "Replace kitchen tap")
        for key in ("labour", "materials", "total_price", "deposit_amount"):
            self.assertEqual(invoice["invoice"][key], edited_result[key])
        self.assertEqual(invoice["status"], "unpaid")
        self.assertEqual(invoice["balance_due"], edited_result["total_price"])
        self.assertEqual(m.get_invoice_by_id(invoice["id"]), invoice)
        self.assertIsNone(m.create_invoice_from_quote(-1))
        self.assertEqual(m.next_invoice_number(),
                         f"INV-{m.now_uk().year}-{int(expected_number[-4:]) + 1:04d}")


    def test_stage7_public_seo_rendering_golden(self):
        """Freeze the three existing SEO page families before moving renderers."""
        m = self.module
        cases = (
            ("location", "109b57c9af0e81fe33d45b095c6ab6cd67ebede2949692bbda9081071c66b099"),
            ("service", "11a6083f4d60a05bf8c6cc0b784ca65988f7fdb5b0bcd82460644eae66bfab26"),
            ("local", "b266c843193f4c1c57dae5cd0dafda1836f26558d4068b582582afa695a1da0a"),
        )
        with patch.dict(os.environ, {"APP_ENVIRONMENT": "production",
                                     "PUBLIC_BASE_URL": "https://stage7.invalid",
                                     "GOOGLE_PLACES_API_KEY": ""}), \
                patch.object(m, "_google_reviews_html", return_value="<div>Synthetic reviews</div>"):
            rendered = {
                "location": m.render_location_page("Guildford", "<span>Test logo</span>"),
                "service": m.render_service_page(m.SERVICE_PAGES[1], "<span>Test logo</span>"),
                "local": m.render_local_service_location_page(
                    m.LOCAL_SERVICE_PAGES[0], m.LOCATION_PAGES[0], "<span>Test logo</span>"),
            }
        for name, digest in cases:
            with self.subTest(page=name):
                self.assertEqual(hashlib.sha256(rendered[name].encode()).hexdigest(), digest)

    def test_stage7_merchant_parsing_and_matching_offline(self):
        """No merchant request escapes the process; preserve exact parsed shapes."""
        m = self.module
        search_html = ('<html><body><div class="product-card"><a href="/p/12345">'
                       '<h3>600 x 1200 Type 22 radiator</h3></a><span>£123.45</span>'
                       '</div></body></html>')
        self.assertEqual(m._extract_search_page_products(
            search_html, "https://www.toolstation.com/search?q=radiator", "Toolstation",
            ["toolstation.com"]), [{
                "name": "600 x 1200 Type 22 radiator",
                "url": "https://www.toolstation.com/p/12345", "price": 123.45,
                "sku": "", "image_url": "",
            }])
        self.assertEqual(m._strict_product_match(
            "600 x 1200 Type 22 radiator", "600 x 1200 type 22 radiator"),
            (99, True, ""))
        self.assertEqual(m._strict_product_match(
            "22mm copper endfeed elbow", "22mm copper elbow"), (41, False, ""))

        class Response:
            status_code = 200
            text = '<meta property="product:price:amount" content="23.45"><p>£90</p>'

        with patch.object(m.requests, "get", return_value=Response()) as mocked:
            self.assertEqual(m.scrape_live_price("https://www.screwfix.com/p/example"), 23.45)
            mocked.assert_called_once()

    def test_stage7_google_review_rendering_offline(self):
        m = self.module

        class Response:
            ok = True

            def json(self):
                return {
                    "rating": 4.8, "userRatingCount": 12,
                    "googleMapsLinks": {"reviewsUri": "https://example.invalid/reviews"},
                    "reviews": [{
                        "rating": 5,
                        "authorAttribution": {"displayName": "A & B",
                                              "uri": "https://example.invalid/a"},
                        "text": {"text": "Great <work>"},
                        "relativePublishTimeDescription": "recent",
                    }],
                }

        with patch.object(m, "GOOGLE_PLACES_API_KEY", "test-only"), \
                patch.object(m, "_google_place_id", return_value="test-place"), \
                patch.object(m.requests, "get", return_value=Response()) as mocked:
            html = m._google_reviews_html()
        self.assertEqual(hashlib.sha256(html.encode()).hexdigest(),
                         "ea542a3a14068e0a2d2296ec01b563becd7ca77538d84b42182725e9544736ce")
        self.assertIn("A &amp; B", html)
        self.assertIn("&lt;work&gt;", html)
        mocked.assert_called_once()

    def test_google_reviews_config_to_authenticated_staging_homepage(self):
        """The configured key and Place ID reach Google and its cards reach / in staging."""
        m = self.module

        class Response:
            ok = True

            def json(self):
                return {
                    "rating": 4.9, "userRatingCount": 7,
                    "reviews": [{"rating": 5, "authorAttribution": {"displayName": "Test customer"},
                                 "text": {"text": "Synthetic review"}}],
                }

        with patch.dict(os.environ, {"APP_ENVIRONMENT": "staging",
                                     "PUBLIC_BASE_URL": "https://staging.example.invalid"}), \
                patch.object(m, "GOOGLE_PLACES_API_KEY", "synthetic-key"), \
                patch.object(m, "GOOGLE_PLACE_ID", "synthetic-place"), \
                patch.object(m.google_reviews.requests, "get", return_value=Response()) as fetch:
            with TestClient(m.app) as client:
                self.assertEqual(client.get("/").status_code, 401)
                response = client.get("/", headers=self.auth_headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Synthetic review", response.text)
        self.assertIn('class="google-review-card"', response.text)
        self.assertIn("4.9", response.text)
        self.assertNotIn("See feedback from customers on Google", response.text)
        fetch.assert_called_once()
        self.assertTrue(fetch.call_args.args[0].endswith("/synthetic-place"))
        self.assertEqual(fetch.call_args.kwargs["headers"]["X-Goog-Api-Key"], "synthetic-key")

        with patch.dict(os.environ, {"APP_ENVIRONMENT": "staging",
                                     "PUBLIC_BASE_URL": "https://staging.example.invalid"}), \
                patch.object(m, "GOOGLE_PLACES_API_KEY", ""), \
                patch.object(m.google_reviews.requests, "get") as fetch:
            with TestClient(m.app) as client:
                fallback = client.get("/", headers=self.auth_headers)
        self.assertEqual(fallback.status_code, 200)
        self.assertIn("See feedback from customers on Google", fallback.text)
        fetch.assert_not_called()

    def test_stage7_merchant_search_orchestration_offline(self):
        m = self.module

        class Response:
            status_code = 200
            ok = True

            def __init__(self, url):
                self.url = url
                if "/p/12345" in url:
                    self.text = ('<html><head><meta property="product:price:amount" '
                                 'content="123.45"></head><body><h1>600 x 1200 '
                                 'Type 22 radiator</h1></body></html>')
                else:
                    self.text = ('<html><body><div class="product-card">'
                                 '<a href="/p/12345"><h3>600 x 1200 Type 22 '
                                 'radiator</h3></a><span>£123.45</span></div></body></html>')

        with patch.object(m.requests, "get", side_effect=lambda url, **kwargs: Response(url)) as fetch, \
                patch.object(m, "upsert_material_price_cache") as save:
            result = m.search_live_merchant_products(
                "600 x 1200 Type 22 radiator", suppliers=["Toolstation"])
        self.assertEqual(len(result), 1)
        self.assertEqual({key: value for key, value in result[0].items()
                          if key != "checked_at"}, {
            "name": "600 x 1200 Type 22 radiator", "supplier": "Toolstation",
            "url": "https://www.toolstation.com/p/12345",
            "default_price": 123.45, "live_price": 123.45,
            "price_source": "live", "availability": "", "image_url": "", "sku": "",
            "match_score": 99, "search_only": False, "strict_match": True,
        })
        self.assertEqual(fetch.call_count, 2)
        save.assert_called_once()

    def test_stage7_material_search_matching_rules(self):
        m = self.module
        self.assertEqual(m._material_match_normalise("22 mm End-Feed 90 degree Elbow"),
                         "22mm endfeed elbow")
        self.assertEqual(m._material_match_sizes("22mm to 15 mm"), [15, 22])
        self.assertEqual(m._material_match_score("22mm copper elbow", {
            "name": "22 mm endfeed elbow", "source": "built-in", "default_price": 3,
        }), 80)
        self.assertEqual(m._material_match_score("radiator valve", {
            "name": "15mm TRV radiator valve", "source": "built-in", "default_price": 8,
        }), 0)
        self.assertEqual(m._material_match_score("PTFE tape", {
            "name": "PTFE tape", "source": "built-in", "default_price": 1,
        }), 94)

    def test_unicode_material_roundtrip_and_read_only_encoding_audit(self):
        """Catch mojibake in cached/JSON fields while preserving valid Unicode in output."""
        m = self.module
        good = "22mm chrome–plated elbow £3.50 – builder’s pack"
        bad = "22mm chromeâ€“plated elbow Â£3.50"
        self.assertFalse(encoding_hits(good))
        self.assertTrue(encoding_hits(bad))
        self.assertTrue(encoding_hits("Damaged replacement character �"))
        self.assertFalse(any(encoding_hits(value) for item in m.MATERIAL_LIBRARY
                             for _, value in text_leaves(item, "material")))

        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "encoding.db"
            conn = sqlite3.connect(db_path)
            conn.executescript("CREATE TABLE material_price_cache (id INTEGER PRIMARY KEY, name TEXT, supplier TEXT);"
                               "CREATE TABLE quotes (id INTEGER PRIMARY KEY, result_json TEXT);")
            conn.execute("INSERT INTO material_price_cache VALUES (1, ?, ?)", (good, "Supplier"))
            conn.execute("INSERT INTO material_price_cache VALUES (2, ?, ?)", (bad, "Supplier"))
            conn.execute("INSERT INTO quotes VALUES (1, ?)",
                         (json.dumps({"materials": [{"name": "Seal â€™ trim"}]}),))
            conn.commit()
            conn.close()
            report = scan_database(db_path)
        self.assertEqual(report["affected_records"], {"material_price_cache": 1, "quotes": 1})
        self.assertEqual(report["affected_fields"], {
            "material_price_cache.name": 1, "quotes.result_json.materials[0].name": 1,
        })

        merchant_html = ('<a href="/p/12345">' + good + '</a>')
        parsed = m._extract_search_page_products(
            merchant_html, "https://www.toolstation.com/search?q=elbow",
            "Toolstation", ["toolstation.com"])
        self.assertEqual(parsed[0]["name"], good)
        self.assertFalse(encoding_hits(parsed[0]["name"]))

        with patch.object(m, "get_material_search_library", return_value=[{
            "name": good, "supplier": "Supplier", "url": "", "default_price": 3.5,
        }]):
            with TestClient(m.app) as client:
                response = client.get("/api/material-search", headers=self.auth_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["name"], good)
        self.assertEqual(response.content.decode("utf-8"), response.text)
        self.assertFalse(encoding_hits(response.text))

        script = (ROOT / "static/app.js").read_text(encoding="utf-8")
        start = script.index("function escapeHtml(text) {")
        end = script.index("\n}", start) + 2
        rendered = subprocess.run(
            ["node", "-e", script[start:end] + f"\nconsole.log(escapeHtml({json.dumps(good)}));"],
            check=True, capture_output=True, text=True,
        )
        self.assertEqual(rendered.stdout.strip(), good)

    def test_quote_history_reporting_and_supplier_rules_contract(self):
        m = self.module
        quote = {
            "id": 42, "created_at": "27/09/2026", "job": "Install outside tap",
            "request": {"quote_type": "small"},
            "result": {"quote_type": "small", "labour": 180, "materials": 6,
                       "total_price": 186, "material_lines": [{
                           "name": "PTFE tape", "quantity": 2,
                           "unit_price_used": 3, "full_unit_price": 3,
                           "supplier": "Toolstation", "price_source": "manual",
                       }]},
        }
        with patch.object(m, "load_quotes", return_value=[quote]):
            result = m.analyse_similar_quotes("outside tap", "small")
            self.assertEqual(result["similar_count"], 1)
            self.assertEqual(result["averages"], {
                "labour": 180.0, "materials": 6.0, "total_price": 186.0,
            })
            self.assertEqual(result["similar_quotes"], [{
                "id": 42, "created_at": "27/09/2026", "job": "Install outside tap",
                "labour": 180.0, "materials": 6.0, "total_price": 186.0,
            }])
            self.assertEqual(result["common_materials"][0]["supplier"], "Toolstation")
            self.assertEqual(result["common_materials"][0]["average_quantity"], 2)
            self.assertEqual(result["common_materials"][0]["bundle_status"], "essential")
            self.assertEqual(m.supplier_preference_for_material("PTFE tape")
                             ["preferred_supplier"], "Toolstation")
            self.assertEqual(m.supplier_preferences_summary()[0]["total_uses"], 1)
            labour = m.labour_intelligence_for_job("outside tap", "small", 100)
            self.assertEqual((labour["status"], labour["average_labour"]),
                             ("too_low", 180.0))
            with TestClient(m.app) as client:
                response = client.get("/api/quote-learning?q=outside+tap&quote_type=small",
                                      headers=self.auth_headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), result)

        missing = m.detect_forgotten_items("Install outside tap", [{"name": "PTFE tape"}])
        self.assertEqual(missing[0]["missing"], [
            "15mm isolating valve", "double check valve 15mm", "pipe clips 15mm",
            "drain off cock 15mm",
        ])
        with patch.object(m, "load_quotes", return_value=[]):
            self.assertEqual(m.analyse_similar_quotes("outside tap")["similar_count"], 0)
            self.assertEqual(m.supplier_preferences_summary(), [])

    def test_public_invoice_html_exact_render_contract(self):
        m = self.module
        item = {
            "id": 9, "invoice_number": "INV-SYNTHETIC", "created_at": "27/09/2026",
            "job_reference": "STAGING-JOB", "due_date": "01/10/2026",
            "status": "unpaid", "total_price": 186, "amount_paid": 0,
            "balance_due": 186, "payment_link": "", "photos": [],
            "quote_result": {"quote_type": "small"},
            "invoice": {"customer_name": "Synthetic Customer",
                        "customer_address": "Test Road", "customer_phone": "000000",
                        "job": "Replace tap", "labour": 180, "materials": 6},
        }
        values = {"BANK_NAME": "TEST BANK", "BANK_ACCOUNT_NAME": "TEST ACCOUNT",
                  "BANK_SORT_CODE": "00-00-00", "BANK_ACCOUNT_NUMBER": "00000000",
                  "COMPANY_NAME": "TEST COMPANY", "COMPANY_ADDRESS": "TEST ADDRESS",
                  "COMPANY_PHONE": "000", "COMPANY_EMAIL": "test@example.invalid",
                  "COMPANY_LOGO_URL": "", "QRCODE_AVAILABLE": False}
        with patch.object(m, "get_invoice_by_id", return_value=item), \
                patch.multiple(m, **values):
            response = m.public_invoice(9)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.media_type, "text/html; charset=utf-8")
        self.assertIn(b"Synthetic Customer", response.body)
        self.assertIn(b"TEST BANK", response.body)
        self.assertEqual(hashlib.sha256(response.body).hexdigest(),
                         "d548f7956fd5e1c8d42fe3c62b4b7b9903713dc6a7cff73d9835dccbd4227bc3")

    def test_lead_notification_and_overdue_reminder_ordering_offline(self):
        m = self.module
        lead = {"name": "Synthetic <Lead>", "phone": "000", "email": "fake@example.invalid",
                "address": "Test Road", "job_type": "Bathroom", "description": "Tap <leak>"}
        with patch.multiple(m, EMAIL_ENABLED=True, EMAIL_USER="sender@example.invalid",
                            EMAIL_PASS="synthetic", EMAIL_FROM_NAME="Test",
                            EMAIL_HOST="smtp.example.invalid", EMAIL_PORT=465), \
                patch.object(m, "get_public_base_url", return_value="https://test.example.invalid"), \
                patch.dict(os.environ, {"PUBLIC_BASE_URL": "https://test.example.invalid"}), \
                patch.object(m.smtplib, "SMTP_SSL") as smtp:
            m.send_lead_notification_email(lead)
        smtp.assert_called_once()
        payload = message_from_string(smtp.return_value.__enter__.return_value.sendmail.call_args.args[2])
        self.assertIn("Synthetic <Lead>", str(payload["Subject"]))
        self.assertIn("https://test.example.invalid", payload.get_payload()[0].get_payload(decode=True).decode())
        self.assertIn("Synthetic &lt;Lead&gt;", payload.get_payload()[1].get_payload(decode=True).decode())

        invoice = {"id": 7, "invoice_number": "INV-TEST", "job_reference": "REF",
                   "balance_due": 20, "reminder_email": "synthetic@example.invalid",
                   "reminders_enabled": True, "last_reminder_at": ""}
        order = []
        with patch.object(m, "invoice_is_overdue", return_value=True), \
                patch.object(m, "send_invoice_email_now",
                             side_effect=lambda *args: order.append("send")), \
                patch.object(m, "update_invoice_reminder_timestamp",
                             side_effect=lambda *args: order.append("timestamp")), \
                patch.object(m, "get_invoice_by_id", return_value={"id": 7}) as reload, \
                patch.object(m, "load_invoices", return_value=[invoice]):
            self.assertEqual(m.process_overdue_invoice_reminders(), {"sent": [7], "skipped": []})
        self.assertEqual(order, ["send", "timestamp"])
        reload.assert_called_once_with(7)

    def test_deterministic_ai_presentation_and_context_contract(self):
        m = self.module
        job = ("Replace kitchen tap. Customer supplying the tap. "
               "Install outside tap. Access is limited.")
        parsed = m.parse_context_aware_jobs(job)
        self.assertEqual(len(parsed["jobs"]), 2)
        self.assertEqual(parsed["jobs"][0]["supply_responsibility"], "customer")
        self.assertEqual(m.split_multi_job_description(job),
                         [row["job_text"] for row in parsed["jobs"]])
        self.assertEqual(hashlib.sha256(json.dumps(parsed, sort_keys=True).encode()).hexdigest(),
                         "9f400872951287e71681926adb6e6f4bb5cdb464e675e18ba5d5f973671b08ba")

        materials = m.merge_multi_job_materials([
            {"job_number": 1, "display_name": "Tap", "materials": [
                {"name": "PTFE tape", "quantity": 0.5, "required": True}]},
            {"job_number": 2, "display_name": "Outside tap", "materials": [
                {"name": "PTFE tape", "quantity": 0.5, "required": False}]},
        ])
        self.assertEqual(len(materials), 1)
        self.assertEqual(materials[0]["quantity"], 1.0)
        self.assertEqual(materials[0]["used_for_jobs"], [1, 2])

        draft = {"materials": [{"name": "PTFE tape", "manual_price": 3,
                                 "data_source": "saved_material", "learned_used_count": 2}],
                 "questions_to_confirm": ["Check access", "Check access"],
                 "risk_notes": ["Concealed pipework"], "warnings": []}
        context = {"multi_job_estimate": {"is_multi_job": True,
                                           "classified_jobs": parsed["jobs"],
                                           "unclassified_segments": []}}
        presented = m.build_professional_quote_mode(draft, context)
        self.assertIs(presented, draft)
        self.assertEqual(hashlib.sha256(json.dumps(presented, sort_keys=True).encode()).hexdigest(),
                         "fa50c7546849d0c7ee7fa7297856c3e2b29199e258981cb760c7247d6fa1fa63")


if __name__ == "__main__":
    unittest.main()

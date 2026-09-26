"""Behaviour checks against a disposable copy of the app.

Importing app.py initializes SQLite, so the test copy redirects every persistent
path before import. No test opens production /var/data.
"""

import importlib.util
import base64
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]


class BaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        root = Path(cls.temp.name)
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
        with patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": "", "EMAIL_ENABLED": "0", "OPENAI_API_KEY": ""}):
            spec.loader.exec_module(cls.module)
        cls.module.init_db()

    def test_route_inventory(self):
        routes_list = [(method, route.path) for route in self.module.app.routes
                       if route.path not in {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
                       for method in getattr(route, "methods", [])]
        routes = set(routes_list)
        expected = {tuple(item) for item in json.loads((ROOT / "tests/route_inventory.json").read_text())}
        self.assertEqual(routes, expected)
        self.assertEqual(len(routes_list), len(routes), "Duplicate method/path route")
        for route in [("GET", "/app"), ("GET", "/"), ("POST", "/api/quote"),
                      ("GET", "/api/quotes/{quote_id}/pdf"),
                      ("GET", "/invoice/{invoice_id}"),
                      ("POST", "/api/invoices/{invoice_id}/send-email")]:
            self.assertIn(route, routes)

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
            # Existing access behaviour, including the known unprotected admin API.
            self.assertEqual(client.get("/api/quotes").status_code, 200)
            for path in ("/", "/new-home", "/request-quote", "/plumber-guildford", "/plumber-woking"):
                response = client.get(path)
                self.assertEqual(response.status_code, 200, path)
                self.assertIn("text/html", response.headers["content-type"])
            home = client.get("/").text
            self.assertIn("Plumber in Guildford", home)
            self.assertIn('rel="canonical"', home)
            # Existing route precedence sends this service slug to the location handler.
            self.assertEqual(client.get("/emergency-plumber-surrey").status_code, 404)
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
            self.assertEqual(client.get("/api/material-alias?q=ptfe").status_code, 200)
            self.assertEqual(client.get("/api/material-charging?q=ptfe").status_code, 200)
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


if __name__ == "__main__":
    unittest.main()

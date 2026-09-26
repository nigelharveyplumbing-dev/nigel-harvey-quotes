"""Behaviour checks against a disposable copy of the app.

Importing app.py initializes SQLite, so the test copy redirects every persistent
path before import. No test opens production /var/data.
"""

import importlib.util
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


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
        spec.loader.exec_module(cls.module)
        cls.module.init_db()

    def test_route_inventory(self):
        routes = {(method, route.path) for route in self.module.app.routes
                  for method in getattr(route, "methods", [])}
        for route in [("GET", "/app"), ("GET", "/"), ("POST", "/api/quote"),
                      ("GET", "/api/quotes/{quote_id}/pdf"),
                      ("GET", "/invoice/{invoice_id}"),
                      ("POST", "/api/invoices/{invoice_id}/send-email")]:
            self.assertIn(route, routes)

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

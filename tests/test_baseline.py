"""Behaviour checks against a disposable copy of the app.

Importing app.py initializes SQLite, so the test copy redirects every persistent
path before import. No test opens production /var/data.
"""

import importlib.util
import shutil
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


if __name__ == "__main__":
    unittest.main()

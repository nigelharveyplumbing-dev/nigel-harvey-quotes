"""Stage 6 local HTTP workflows against the same isolated app used by the browser."""

import base64
import io
import secrets
import socket
import smtplib
import unittest

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
        self.assertIn('accountName: "Synthetic Test Account"',
                      (self.root / "static" / "app.js").read_text())
        with self.assertRaisesRegex(RuntimeError, "External HTTP blocked"):
            requests.get("https://example.test")
        with self.assertRaisesRegex(RuntimeError, "External DNS blocked"):
            socket.getaddrinfo("example.test", 443)
        with self.assertRaisesRegex(RuntimeError, "SMTP blocked"):
            smtplib.SMTP_SSL("example.test")

    def test_known_server_generated_link_still_uses_live_domain(self):
        # Read-only characterization for Stage 6 Step 3; never open this URL.
        self.assertEqual(self.app_module.build_invoice_public_url(1),
                         "https://www.nigelharveyplumbing.co.uk/invoice/1")


if __name__ == "__main__":
    unittest.main()

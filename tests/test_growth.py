"""Growth Batch 1 checks against isolated SQLite/files and blocked external I/O."""

import base64
import json
import re
import secrets
import unittest
from urllib.parse import urlsplit
from unittest.mock import patch
from xml.etree import ElementTree

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from local_browser_server import disposable_app


class GrowthBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sandbox = disposable_app(secrets.token_urlsafe(12), secrets.token_urlsafe(16))
        cls.module, cls.root = cls.sandbox.__enter__()
        cls.addClassCleanup(cls.sandbox.__exit__, None, None, None)
        cls.client = TestClient(cls.module.app)
        cls.client.__enter__()
        cls.addClassCleanup(cls.client.__exit__, None, None, None)
        auth = f"{cls.module.APP_USERNAME}:{cls.module.APP_PASSWORD}".encode()
        cls.auth = {"Authorization": "Basic " + base64.b64encode(auth).decode()}

    def test_homepage_conversion_links_and_review_proof(self):
        m = self.module
        review = ('<div class="google-rating"><strong>4.9</strong>'
                  '<span>7 Google reviews</span></div><div class="google-review-grid">'
                  '<article class="google-review-card">Synthetic</article></div>')
        with patch.object(m, "_google_reviews_html", return_value=review):
            page = self.client.get("/").text
        for text in ("Local Plumber Across Surrey", "Meet Nigel",
                     "WhatsApp Nigel", "Call Nigel", 'href="/app"',
                     "plumber-guildford", "plumber-epsom", "plumber-leatherhead",
                     "plumber-farnborough", "4.9", "7 Google reviews",
                     "google-review-card"):
            self.assertIn(text, page)
        self.assertEqual(page.count("4.9"), 2)  # fetched once, concise and full sections
        self.assertIn('rel="canonical" href="https://www.nigelharveyplumbing.co.uk/"', page)
        self.assertNotIn("images.unsplash.com", page)
        self.assertNotIn("Illustrative stock photography; this is not a completed", page)
        self.assertIn("landing_page", page)
        self.assertIn("utm_campaign", page)
        self.assertIn("https://wa.me/447595725547?text=Hi%20Nigel", page)
        self.assertIn('<a href="#reviews"', page)
        with patch.object(m, "_google_reviews_html", return_value='<h2>Customer reviews</h2>'):
            fallback = self.client.get("/").text
        self.assertIn("Read customer reviews on Google", fallback)
        self.assertNotIn("4.9", fallback)

    def test_website_contact_links(self):
        from business import website_contact
        self.assertEqual(website_contact.whatsapp_url("07595 725547", "Hi Nigel, plumbing job"),
                         "https://wa.me/447595725547?text=Hi%20Nigel%2C%20plumbing%20job")
        self.assertEqual(website_contact.whatsapp_url("+44 7595 725547", "Photo?"),
                         "https://wa.me/447595725547?text=Photo%3F")
        self.assertEqual(website_contact.whatsapp_url("0044 7595 725547", "Hello"),
                         "https://wa.me/447595725547?text=Hello")

    def test_service_and_location_hierarchy(self):
        c = self.client
        for slug in ("emergency-plumber-surrey", "general-plumbing-surrey",
                     "bathroom-plumbing-surrey", "heating-repairs-surrey"):
            response = c.get("/" + slug)
            self.assertEqual(response.status_code, 200, slug)
            self.assertIn("/" + slug + '"', response.text)
            self.assertNotIn("This page supports", response.text)
        for slug, phrase in (("guildford", "Guildford"), ("epsom", "leaking tap"),
                             ("leatherhead", "radiator valve"),
                             ("farnborough", "Farnborough is in Hampshire")):
            response = c.get("/plumber-" + slug)
            self.assertEqual(response.status_code, 200, slug)
            self.assertIn(phrase, response.text)
            self.assertIn('href="https://www.nigelharveyplumbing.co.uk/plumber-' + slug + '"', response.text)
        self.assertEqual(c.get("/plumber-not-real").status_code, 404)
        self.assertEqual(c.get("/leak-repair-farnborough").status_code, 404)
        sitemap = c.get("/sitemap.xml").text
        self.assertIn("/plumber-farnborough", sitemap)
        self.assertNotIn("/leak-repair-farnborough", sitemap)
        self.assertIn("/emergency-plumber-surrey", sitemap)

    def test_public_page_enquiry_context_and_no_broken_farnborough_links(self):
        for path in ("/plumber-epsom", "/plumber-leatherhead", "/plumber-farnborough",
                     "/emergency-plumber-surrey", "/general-plumbing-surrey",
                     "/leak-repair-guildford"):
            page = self.client.get(path).text
            self.assertIn("next.searchParams.set('landing_page', location.pathname)", page, path)
            self.assertIn("next.searchParams.set('referrer', referring)", page, path)
            self.assertIn("utm_campaign", page, path)
            self.assertIn('href="/request-quote"', page, path)
        self.assertNotIn('href="/leak-repair-farnborough"',
                         self.client.get("/leak-repair-guildford").text)
        form = self.client.get("/request-quote").text
        self.assertIn("params.get('landing_page')", form)
        self.assertIn("params.get('referrer')", form)

    def test_every_sitemap_page_uses_shared_layout_and_keeps_seo(self):
        m, c = self.module, self.client
        with patch.object(m, "_google_reviews_html", return_value='<h2>Customer reviews</h2>'):
            sitemap = ElementTree.fromstring(c.get("/sitemap.xml").text)
            paths = [urlsplit(loc.text).path for loc in sitemap.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
            self.assertEqual(len(paths), 72)
            for path in paths:
                with self.subTest(path=path):
                    response = c.get(path)
                    self.assertEqual(response.status_code, 200)
                    page = BeautifulSoup(response.text, "html.parser")
                    self.assertEqual(len(page.select("header .navlinks")), 1)
                    self.assertEqual(len(page.select("footer .foot")), 1)
                    self.assertEqual(len(page.select(".mobile-contact")), 1)
                    self.assertEqual(len(page.select("main#main")), 1)
                    self.assertEqual(len(page.select("h1")), 1)
                    self.assertFalse(page.select(".sticky-call,.mobile-call,.site-header,.topbar,.footer"))
                    self.assertIn("--blue:#176092", page.style.text)
                    self.assertEqual(urlsplit(page.select_one('link[rel="canonical"]')["href"]).path, path)
                    self.assertTrue(page.select_one('meta[name="description"]')["content"])
                    for schema in page.select('script[type="application/ld+json"]'):
                        self.assertEqual(json.loads(schema.text)["@context"], "https://schema.org")

    def test_google_review_cards_survive_shared_layout(self):
        m = self.module

        class Response:
            ok = True

            def json(self):
                return {"rating": 4.9, "userRatingCount": 7,
                        "reviews": [{"rating": 5, "authorAttribution": {"displayName": "Synthetic customer"},
                                     "text": {"text": "Synthetic review"}}]}

        with patch.object(m, "GOOGLE_PLACES_API_KEY", "synthetic-key"), \
                patch.object(m, "GOOGLE_PLACE_ID", "synthetic-place"), \
                patch.object(m.google_reviews.requests, "get", return_value=Response()) as fetch:
            for path in ("/", "/plumber-guildford", "/plumber-epsom", "/plumber-farnborough"):
                page = BeautifulSoup(self.client.get(path).text, "html.parser")
                self.assertIn("Synthetic review", page.text)
                self.assertTrue(page.select(".google-review-card"), path)
            self.assertEqual(fetch.call_count, 4)
        with patch.object(m, "GOOGLE_PLACES_API_KEY", ""), \
                patch.object(m.google_reviews.requests, "get") as fetch:
            for path in ("/", "/plumber-leatherhead"):
                self.assertIn("Read Google Reviews", self.client.get(path).text)
            fetch.assert_not_called()

    def test_local_stock_image_allowlist_and_staging_guard(self):
        c = self.client
        for filename in ("bathroom-illustrative.webp", "shower-illustrative.webp",
                         "radiator-illustrative.webp"):
            response = c.get("/site-images/" + filename)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["content-type"], "image/webp")
            self.assertLess(len(response.content), 200_000)
        self.assertEqual(c.get("/site-images/unknown.webp").status_code, 404)
        with patch.dict(__import__("os").environ, {"APP_ENVIRONMENT": "staging"}):
            self.assertEqual(c.get("/site-images/bathroom-illustrative.webp").status_code, 401)
            self.assertEqual(c.get("/site-images/bathroom-illustrative.webp", headers=self.auth).status_code, 200)

    def test_enhanced_lead_keeps_legacy_fields_and_context_in_same_row(self):
        m = self.module
        payload = {"name":"Synthetic Growth", "phone":"07000000000",
                   "email":"test@example.invalid", "address":"Example Road",
                   "description":"Shower fitting", "job_type":"bathroom", "source":"website",
                   "postcode":"GU1 2AA", "urgency":"planned", "preferred_contact":"email",
                   "landing_page":"/plumber-epsom", "referrer":"https://search.invalid/results",
                   "utm_source":"search", "utm_medium":"organic", "utm_campaign":"bathroom",
                   "utm_content":"hero", "utm_term":"shower"}
        with patch.object(m, "send_lead_notification_email") as notify:
            response = self.client.post("/api/leads", json=payload)
        self.assertEqual(response.status_code, 200)
        lead = response.json()
        notify.assert_called_once_with(lead)
        self.assertEqual({key: lead[key] for key in payload}, payload)
        self.assertEqual(lead["status"], "new")
        self.assertIn(lead, self.client.get("/api/leads", headers=self.auth).json())
        conn = m.get_db()
        stored = conn.execute("SELECT source, address, job_type FROM leads WHERE id=?", (lead["id"],)).fetchone()
        conn.close()
        self.assertTrue(stored["source"].startswith("website-context-v1:"))
        self.assertEqual(json.loads(stored["source"].split(":",1)[1])["landing_page"], "/plumber-epsom")
        self.assertEqual((stored["address"], stored["job_type"]), ("Example Road", "bathroom"))
        self.assertEqual(m.get_lead_by_id(lead["id"]), lead)
        self.assertEqual(self.client.delete(f"/api/leads/{lead['id']}", headers=self.auth).status_code, 200)

    def test_quote_form_safe_contact_and_no_public_upload(self):
        page = self.client.get("/request-quote").text
        for field in ("lead_name", "lead_phone", "lead_email", "lead_postcode",
                      "lead_address", "lead_job_type", "lead_urgency", "lead_preferred_contact",
                      "lead_description"):
            self.assertIn(f'id="{field}"', page)
        self.assertIn('href="https://www.nigelharveyplumbing.co.uk/request-quote"', page)
        self.assertIn("WhatsApp Nigel", page)
        self.assertNotIn('type="file"', page)
        self.assertIn("does not upload files", page)
        self.assertEqual(self.client.post("/api/leads", files={"photo": ("test.jpg", b"fake", "image/jpeg")}).status_code, 422)

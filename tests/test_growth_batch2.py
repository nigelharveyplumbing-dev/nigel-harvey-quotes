"""Search and conversion checks against disposable storage and blocked outbound I/O."""

import base64
import json
import secrets
import subprocess
import unittest
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from local_browser_server import disposable_app


ROOT = Path(__file__).resolve().parents[1]


class GrowthBatch2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sandbox = disposable_app(secrets.token_urlsafe(12), secrets.token_urlsafe(16))
        cls.module, cls.root = cls.sandbox.__enter__()
        cls.addClassCleanup(cls.sandbox.__exit__, None, None, None)
        cls.client = TestClient(cls.module.app)
        cls.client.__enter__()
        cls.addClassCleanup(cls.client.__exit__, None, None, None)

    def test_sitemap_routes_contact_links_metadata_and_analytics(self):
        response = self.client.get("/sitemap.xml")
        self.assertEqual(response.status_code, 200)
        root = ElementTree.fromstring(response.text)
        paths = [urlsplit(loc.text).path for loc in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
        self.assertEqual(len(paths), 85)
        self.assertEqual(len(set(paths)), len(paths))
        titles = {}
        for path in paths:
            with self.subTest(path=path):
                page = self.client.get(path)
                self.assertEqual(page.status_code, 200)
                soup = BeautifulSoup(page.text, "html.parser")
                title = soup.title.text.strip()
                self.assertTrue(title)
                self.assertNotIn(title, titles, f"{title} also on {titles.get(title)}")
                titles[title] = path
                self.assertTrue(soup.select_one('meta[name="description"]')["content"])
                self.assertEqual(soup.select_one('link[rel="canonical"]')["href"],
                                 "https://www.nigelharveyplumbing.co.uk" + path)
                self.assertEqual(len(soup.select("h1")), 1)
                self.assertEqual(len(soup.select("#public-analytics")), 1)
                self.assertEqual(len(soup.select("#analytics-settings")), 1)
                self.assertNotIn("Illustrative stock photography; this is not a completed", page.text)
                self.assertFalse(soup.select('script[src*="googletagmanager"]'))
                for link in soup.select('a[href^="tel:"]'):
                    self.assertEqual(link["href"], "tel:07595725547")
                for link in soup.select("a[href]"):
                    href = link["href"]
                    if href.startswith("/") and not href.startswith("//"):
                        target = urlsplit(href).path
                        self.assertEqual(self.client.get(target).status_code,
                                         401 if target == "/app" else 200,
                                         f"{path} → {href}")
        self.assertNotIn("/app", paths)
        self.assertIn("Disallow: /app", self.client.get("/robots.txt").text)
        self.assertEqual(self.client.get("/app").status_code, 401)

    def test_priority_intent_and_internal_routes(self):
        for path, phrases in {
            "/": ("Local Plumber Across Surrey", "Guildford based", "/plumber-guildford"),
            "/plumber-guildford": ("Plumber in Guildford", "Common Guildford plumbing enquiries",
                                   "/leak-repair-guildford", "/general-plumbing-surrey"),
            "/plumber-aldershot": ("Guildford-based Nigel", "/leak-repair-aldershot"),
            "/plumber-camberley": ("Guildford-based Nigel", "/leak-repair-camberley"),
            "/general-plumbing-surrey": ("Everyday repairs and small plumbing jobs", "outside tap"),
            "/leak-repair-camberley": ("what to check before calling", "stopcock"),
            "/leak-repair-farnham": ("Describing a leak in Farnham", "postcode"),
            "/toilet-repair-leatherhead": ("What is wrong with the toilet?", "running cistern"),
        }.items():
            with self.subTest(path=path):
                html = self.client.get(path).text
                for phrase in phrases:
                    self.assertIn(phrase, html)

    def test_staging_never_sends_to_live_analytics(self):
        with disposable_app("batch2user", "batch2password",
                            public_base_url="https://stage.invalid", environment="staging") as (module, _):
            auth = {"Authorization": "Basic " + base64.b64encode(b"batch2user:batch2password").decode()}
            with TestClient(module.app) as client:
                for path in ("/", "/request-quote", "/plumber-guildford"):
                    page = client.get(path, headers=auth)
                    self.assertEqual(page.status_code, 200)
                    tag = BeautifulSoup(page.text, "html.parser").select_one("#public-analytics")
                    self.assertEqual(tag["data-send-to-google"], "false")
                    self.assertEqual(tag["data-measurement-id"], "G-Q9Z2WWNF6F")
                self.assertEqual(client.get("/").status_code, 401)
                self.assertEqual(client.get("/app").status_code, 401)
                self.assertEqual(client.get("/robots.txt", headers=auth).text,
                                 "User-agent: *\nDisallow: /\n")

    def test_offline_event_workflow(self):
        result = subprocess.run(["node", str(ROOT / "tests/growth_batch2_events.mjs")],
                                cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

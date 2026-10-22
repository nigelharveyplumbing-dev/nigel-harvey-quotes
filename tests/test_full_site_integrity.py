"""Full public sitemap crawl: broken links, images, canonical, privacy and redirects.

Runs ONLY against an isolated TestClient backed by disposable synthetic storage.
No live site, business database, Google or third-party network requests.
"""
import unittest
from collections import Counter
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from local_browser_server import disposable_app


ORIGIN = "https://www.nigelharveyplumbing.co.uk"
XMLNS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


class FullSiteIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sandbox = disposable_app(
            "full-site-review", "synthetic-offline-only",
            projects_as_drafts=False, advice_as_drafts=False)
        cls.app, _ = cls.sandbox.__enter__()
        cls.addClassCleanup(cls.sandbox.__exit__, None, None, None)
        cls.client = TestClient(cls.app.app)
        cls.client.__enter__()
        cls.addClassCleanup(cls.client.__exit__, None, None, None)

    def sitemap(self):
        r = self.client.get("/sitemap.xml")
        self.assertEqual(r.status_code, 200)
        self.assertIn("xml", r.headers.get("content-type", ""))
        urls = [e.text for e in ET.fromstring(r.text).iter(XMLNS + "loc")]
        self.assertEqual(len(urls), 82)
        self.assertEqual(len(urls), len(set(urls)), "Sitemap contains duplicates")
        self.assertTrue(all(u and u.startswith(ORIGIN + "/") for u in urls))
        return urls

    def test_all_82_live_public_routes_are_indexable_and_self_canonical(self):
        titles, descriptions, h1s = [], [], []
        for url in self.sitemap():
            path = url[len(ORIGIN):]
            with self.subTest(page=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, path)
                self.assertIn("text/html", response.headers.get("content-type", ""))
                self.assertNotIn("noindex", response.headers.get("x-robots-tag", "").lower())
                page = BeautifulSoup(response.text, "html.parser")
                title = page.title.get_text(" ", strip=True) if page.title else ""
                description = page.select_one('meta[name="description"]')
                canonical = page.select('link[rel="canonical"]')
                h1 = page.select("h1")
                self.assertTrue(title, path)
                self.assertEqual(len(canonical), 1, path)
                self.assertEqual(canonical[0].get("href"), url, path)
                self.assertIsNotNone(description, path)
                self.assertTrue(description.get("content", ""), path)
                self.assertEqual(len(h1), 1, path)
                self.assertNotIn("noindex", response.text.lower().split("</head>", 1)[0], path)
                titles.append(title)
                descriptions.append(description["content"])
                h1s.append(h1[0].get_text(" ", strip=True))
        self.assertEqual(len(titles), len(set(titles)), "Duplicated page title")
        self.assertEqual(len(descriptions), len(set(descriptions)), "Duplicated meta description")
        self.assertEqual(len(h1s), len(set(h1s)), "Duplicated page H1")

    def test_every_internal_link_and_public_media_target_resolves(self):
        sitemap = self.sitemap()
        seen = {}
        link_sources = {}
        for url in sitemap:
            path = url[len(ORIGIN):]
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            page = BeautifulSoup(response.text, "html.parser")
            for a in page.select("a[href]"):
                raw = (a.get("href") or "").strip()
                if not raw or raw.startswith("#"):
                    continue
                candidate = urlsplit(urljoin(url, raw))
                if candidate.scheme not in ("http", "https"):
                    continue  # tel, mailto, WhatsApp and other external actions
                if candidate.netloc != urlsplit(ORIGIN).netloc:
                    continue
                target = candidate.path or "/"
                if target in ("/app",) or target.startswith("/api/"):
                    continue  # Explicitly private; checked separately below
                seen.setdefault(target, "link")
                link_sources.setdefault(target, []).append(path)
            for img in page.select("img[src], source[srcset]"):
                raw = img.get("src") or (img.get("srcset") or "").split(",")[0].split(" ")[0]
                if not raw or raw.startswith(("data:", "blob:")):
                    continue
                candidate = urlsplit(urljoin(url, raw))
                if candidate.scheme not in ("http", "https"):
                    continue
                if candidate.netloc != urlsplit(ORIGIN).netloc:
                    continue
                target = candidate.path or "/"
                seen.setdefault(target, "media")
                link_sources.setdefault(target, []).append(path)
        self.assertTrue(len(seen) >= 20, "Not enough public internal links discovered")
        for target, kind in sorted(seen.items()):
            with self.subTest(destination=target, kind=kind):
                r = self.client.get(target, follow_redirects=False)
                self.assertIn(r.status_code, (200, 301, 302, 307, 308),
                              f"Broken {kind} at {target}; linked from {link_sources.get(target, [])[:3]}")
                if r.status_code != 200:
                    loc = r.headers.get("location", "")
                    self.assertTrue(loc, target)
                    rerouted = urlsplit(urljoin(ORIGIN + target, loc))
                    self.assertEqual(rerouted.netloc, urlsplit(ORIGIN).netloc)
                    self.assertEqual(self.client.get(rerouted.path).status_code, 200, target)

    def test_legacy_redirects_and_private_app_indexing_controls(self):
        robots = self.client.get("/robots.txt")
        self.assertEqual(robots.status_code, 200)
        self.assertIn("Allow: /", robots.text)
        self.assertIn("Disallow: /app", robots.text)
        self.assertIn("Disallow: /api/", robots.text)
        self.assertIn("Sitemap: " + ORIGIN + "/sitemap.xml", robots.text)
        for town in self.app.LOCATION_PAGES:
            if town["slug"] == "farnborough":
                continue
            with self.subTest(redirect=town["slug"]):
                response = self.client.get("/blocked-drains-" + town["slug"],
                                           follow_redirects=False)
                self.assertEqual(response.status_code, 301)
                self.assertEqual(response.headers.get("location"),
                                 "/plumber-" + town["slug"])
        for path in ("/app", "/api/quotes", "/api/invoices", "/api/jobs"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 401, path)
            self.assertIn("noindex", response.headers.get("x-robots-tag", ""))

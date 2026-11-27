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

    def test_homepage_meet_nigel_portrait_asset(self):
        """Approved owner portrait is rendered only in the Meet Nigel section."""
        page = BeautifulSoup(self.client.get("/").text, "html.parser")
        photo = page.select_one("section#about .photo-panel img")
        self.assertIsNotNone(photo)
        self.assertEqual(photo.get("src"), "/site-images/nigel-harvey-portrait.webp")
        self.assertEqual(photo.get("alt"), "Portrait of Nigel Harvey")
        self.assertEqual(photo.get("width"), "900")
        self.assertEqual(photo.get("height"), "985")
        self.assertEqual(photo.get("loading"), "lazy")
        image = self.client.get(photo["src"])
        self.assertEqual(image.status_code, 200)
        self.assertIn("image/webp", image.headers.get("content-type", ""))
        self.assertGreater(len(image.content), 20000)
        self.assertLess(len(image.content), 100000)
        self.assertEqual(self.client.get("/site-images/not-approved.webp").status_code, 404)

    def test_five_page_broad_plumbing_enquiry_routes(self):
        """Check balanced service links, quote paths and existing canonical URLs."""
        checks = {
            "/": ["/general-plumbing-surrey", "/bathroom-plumbing-surrey",
                  "/heating-repairs-surrey", "/leak-repair-guildford", "/request-quote"],
            "/plumber-guildford": ["/general-plumbing-surrey", "/toilet-repair-guildford",
                                    "/bathroom-plumbing-guildford", "/request-quote"],
            "/plumber-merrow": ["/general-plumbing-surrey", "/leak-repair-merrow",
                                "/bathroom-plumbing-merrow", "/heating-repairs-surrey",
                                "/projects/ensuite-renovation-merrow-guildford", "/request-quote"],
            "/plumber-woking": ["/general-plumbing-surrey", "/leak-repair-woking",
                                "/bathroom-plumbing-woking", "/request-quote"],
            "/general-plumbing-surrey": ["/plumber-guildford", "/plumber-woking",
                                          "/bathroom-plumbing-surrey", "/heating-repairs-surrey",
                                          "/request-quote"],
        }
        for path, destinations in checks.items():
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                page = BeautifulSoup(response.text, "html.parser")
                hrefs = {link.get("href") for link in page.select("a[href]")}
                for destination in destinations:
                    self.assertIn(destination, hrefs, (path, destination))
                canonical = page.select_one('link[rel="canonical"]')
                self.assertIsNotNone(canonical)
                self.assertEqual(canonical.get("href"), ORIGIN + path)
        self.assertIn("General plumbing repairs and fitting work",
                      self.client.get("/general-plumbing-surrey").text)
        self.assertIn("Repairs and planned plumbing work in Merrow",
                      self.client.get("/plumber-merrow").text)

    def test_keyword_led_plumbing_and_bathroom_pages(self):
        """Keyword focus stays within existing public URLs and truthful service scope."""
        home = BeautifulSoup(self.client.get("/").text, "html.parser")
        self.assertIn("general plumbing", home.get_text(" ", strip=True).lower())
        self.assertIn("bathroom fitting", home.get_text(" ", strip=True).lower())
        self.assertIn("/bathroom-plumbing-surrey",
                      {a.get("href") for a in home.select("a[href]")})
        for path, title_part, related_area in (
            ("/bathroom-plumbing-woking", "Bathroom Fitting", "/plumber-woking"),
            ("/bathroom-plumbing-leatherhead", "Bathroom Installation", "/plumber-leatherhead"),
            ("/bathroom-plumbing-godalming", "Bathroom Fitter", "/plumber-godalming"),
        ):
            with self.subTest(page=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                page = BeautifulSoup(response.text, "html.parser")
                self.assertIn(title_part, page.title.get_text(" ", strip=True))
                self.assertIn("Bathroom Fitting & Installation",
                              page.select_one("h1").get_text(" ", strip=True))
                self.assertEqual(page.select_one('link[rel="canonical"]')["href"],
                                 ORIGIN + path)
                links = {link.get("href") for link in page.select("a[href]")}
                self.assertTrue({related_area, "/bathroom-plumbing-surrey",
                                 "/request-quote"} <= links)
                self.assertNotIn("Gas Safe registered", response.text)
        for path in ("/plumber-guildford", "/plumber-woking", "/general-plumbing-surrey",
                     "/bathroom-plumbing-surrey"):
            with self.subTest(page=path):
                page = BeautifulSoup(self.client.get(path).text, "html.parser")
                self.assertIn("plumb", page.get_text(" ", strip=True).lower())
                self.assertIn("/request-quote",
                              {a.get("href") for a in page.select("a[href]")})

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
                brand = page.select_one('header a.brand[href="/"]')
                self.assertIsNotNone(brand, path)
                self.assertEqual(brand.get('aria-label'), 'Nigel Harvey Plumbing home', path)
                logos = brand.select('img.brand-logo')
                self.assertEqual(len(logos), 1, path)
                self.assertEqual(logos[0].get('src'), '/site-images/nigel-harvey-logo.png', path)
                self.assertEqual(logos[0].get('alt'), 'Nigel Harvey Ltd', path)
                footer = page.select_one("footer")
                self.assertIsNotNone(footer, path)
                self.assertEqual(footer.select_one("strong").get_text(strip=True),
                                 "Nigel Harvey Plumbing", path)
                self.assertIn("Nigel Harvey Ltd · Guildford, Surrey",
                              footer.get_text(" ", strip=True), path)
                disclosure = footer.select(".company-disclosure")
                self.assertEqual(len(disclosure), 1, path)
                self.assertEqual(disclosure[0].get_text(" ", strip=True),
                                 "Registered in England and Wales · Company no. 09507904 "
                                 "Registered office: 125 Bushy Hill Drive, Guildford, "
                                 "Surrey, England, GU1 2UG", path)
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

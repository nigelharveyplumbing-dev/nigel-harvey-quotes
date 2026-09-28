"""Search-evidence-led SEO and conversion coverage for Growth Batch 4."""

import json
import secrets
import unittest
from urllib.parse import urlsplit
from xml.etree import ElementTree

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from local_browser_server import disposable_app


PRODUCTION = "https://www.nigelharveyplumbing.co.uk"


def owned_urls(value):
    result = []
    if isinstance(value, dict):
        for nested in value.values():
            result.extend(owned_urls(nested))
    elif isinstance(value, list):
        for nested in value:
            result.extend(owned_urls(nested))
    elif isinstance(value, str) and value.startswith(("http://", "https://")):
        if urlsplit(value).hostname in {
                "www.nigelharveyplumbing.co.uk", "nigelharveyplumbing.co.uk"}:
            result.append(value)
    return result


class GrowthBatch4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sandbox = disposable_app(secrets.token_urlsafe(12), secrets.token_urlsafe(16))
        cls.module, cls.root = cls.sandbox.__enter__()
        cls.addClassCleanup(cls.sandbox.__exit__, None, None, None)
        cls.client = TestClient(cls.module.app)
        cls.client.__enter__()
        cls.addClassCleanup(cls.client.__exit__, None, None, None)

    def soup(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, path)
        return BeautifulSoup(response.text, "html.parser")

    def test_homepage_matches_search_demand_and_visible_faq_schema(self):
        page = self.soup("/")
        self.assertEqual(page.title.get_text(strip=True),
                         "Plumber in Guildford & Surrey | Nigel Harvey Plumbing")
        self.assertEqual(page.h1.get_text(" ", strip=True),
                         "Plumber in Guildford & Across Surrey")
        description = page.select_one('meta[name="description"]')["content"]
        self.assertIn("24 hours a day, including overnight", description)
        self.assertLessEqual(len(description), 160)
        text = page.get_text(" ", strip=True)
        for phrase in ("West Horsley", "Aldershot", "Camberley",
                       "deal directly with me, Nigel", "Timing depends on the problem and location"):
            self.assertIn(phrase, text)
        for path in ("/plumber-guildford", "/plumber-aldershot", "/plumber-camberley",
                     "/emergency-plumber-surrey", "/leak-repair-guildford"):
            self.assertTrue(page.select_one(f'a[href="{path}"]'), path)

        schemas = [json.loads(tag.get_text())
                   for tag in page.select('script[type="application/ld+json"]')]
        business = next(item for item in schemas if item.get("@type") == "Plumber")
        faq = next(item for item in schemas if item.get("@type") == "FAQPage")
        self.assertEqual(business["name"], "Nigel Harvey Plumbing")
        self.assertEqual(business["legalName"], "Nigel Harvey Ltd")
        self.assertIn("operated by Nigel Harvey", business["description"])
        self.assertIn("West Horsley", business["areaServed"])
        visible_questions = [item.get_text(" ", strip=True)
                             for item in page.select("section.faq details summary")]
        schema_questions = [item["name"] for item in faq["mainEntity"]]
        self.assertEqual(schema_questions, visible_questions)

    def test_priority_snippets_and_urgent_wording(self):
        expectations = {
            "/plumber-guildford": (
                "Plumber in Guildford | Local Repairs | Nigel Harvey Plumbing",
                "24 hours", "/emergency-plumber-surrey"),
            "/emergency-plumber-surrey": (
                "24-Hour Plumber in Surrey | Nigel Harvey Plumbing",
                "including overnight", "/emergency-plumber-guildford"),
            "/general-plumbing-surrey": (
                "General Plumbing & Small Repairs in Surrey | Nigel Harvey Plumbing",
                "minor pipework repairs", "/plumber-guildford"),
            "/leak-repair-camberley": (
                "Leak Repair Camberley | Leaking Pipes | Nigel Harvey Plumbing",
                "whether it can be isolated", "/general-plumbing-surrey"),
            "/leak-repair-aldershot": (
                "Leak Repair Aldershot | Leaking Pipes | Nigel Harvey Plumbing",
                "Leaking pipe", "/request-quote"),
            "/toilet-repair-leatherhead": (
                "Toilet Repair Leatherhead | Cisterns & Leaks | Nigel Harvey Plumbing",
                "running or leaking", "/general-plumbing-surrey"),
        }
        for path, (title, meta_phrase, linked_path) in expectations.items():
            with self.subTest(path=path):
                page = self.soup(path)
                self.assertEqual(page.title.get_text(strip=True), title)
                self.assertIn(meta_phrase,
                              page.select_one('meta[name="description"]')["content"])
                self.assertEqual(page.select_one('link[rel="canonical"]')["href"],
                                 PRODUCTION + path)
                self.assertEqual(page.select_one('meta[property="og:url"]')["content"],
                                 PRODUCTION + path)
                self.assertTrue(page.select_one(f'a[href="{linked_path}"]'))
        urgent_text = self.soup("/emergency-plumber-surrey").get_text(" ", strip=True).lower()
        self.assertNotIn("guaranteed arrival", urgent_text)
        self.assertNotIn("immediate attendance", urgent_text)

    def test_complete_sitemap_metadata_targets_and_internal_links(self):
        sitemap = ElementTree.fromstring(self.client.get("/sitemap.xml").text)
        urls = [item.text for item in sitemap.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
        self.assertEqual(len(urls), 72)
        self.assertEqual(len(set(urls)), 72)
        self.assertTrue(all(url.startswith(PRODUCTION + "/") for url in urls))

        titles = {}
        descriptions = {}
        internal_targets = set()
        for url in urls:
            path = urlsplit(url).path
            with self.subTest(path=path):
                page = self.soup(path)
                title = page.title.get_text(" ", strip=True)
                description = page.select_one('meta[name="description"]')["content"].strip()
                self.assertTrue(title)
                self.assertTrue(description)
                self.assertEqual(len(page.select("h1")), 1)
                self.assertEqual(page.select_one('link[rel="canonical"]')["href"], url)
                self.assertEqual(page.select_one('meta[property="og:url"]')["content"], url)
                self.assertNotIn(title, titles, f"duplicate title: {title}")
                self.assertNotIn(description, descriptions,
                                 f"duplicate description: {description}")
                titles[title] = path
                descriptions[description] = path
                for tag in page.select('script[type="application/ld+json"]'):
                    for owned in owned_urls(json.loads(tag.get_text())):
                        self.assertEqual(urlsplit(owned).hostname,
                                         "www.nigelharveyplumbing.co.uk")
                for link in page.select("a[href]"):
                    href = link["href"]
                    if href.startswith("/") and not href.startswith("//"):
                        internal_targets.add(urlsplit(href).path)
        for path in internal_targets:
            expected = 401 if path == "/app" else 200
            self.assertEqual(self.client.get(path).status_code, expected, path)


if __name__ == "__main__":
    unittest.main()

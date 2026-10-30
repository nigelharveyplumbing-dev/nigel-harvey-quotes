"""Read-only SEO regressions for two GSC-confirmed crawled/not-indexed pages.

Synthetic local app only. No external requests or indexing submissions.
"""
import unittest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from local_browser_server import disposable_app


class FocusedIndexingReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sandbox = disposable_app("seo-fixture", "local-synthetic-review")
        cls.module, _root = cls.sandbox.__enter__()
        cls.addClassCleanup(cls.sandbox.__exit__, None, None, None)
        cls.client = TestClient(cls.module.app)
        cls.client.__enter__()
        cls.addClassCleanup(cls.client.__exit__, None, None, None)

    def page(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, path)
        self.assertNotIn("noindex", response.headers.get("x-robots-tag", "").lower())
        return BeautifulSoup(response.text, "html.parser")

    def test_confirmed_pages_have_self_canonical_and_distinct_helpful_copy(self):
        checks = {
            "/leak-repair-leatherhead": ("waste is draining", "leaking supply joint", "/plumber-leatherhead"),
            "/toilet-repair-godalming": ("flush mechanisms and seals", "concealed cistern", "/plumber-godalming"),
            "/toilet-repair-fairlands": ("repeatedly refills", "supply pipe", "/plumber-fairlands"),
        }
        contents = []
        for path, (first, second, link) in checks.items():
            with self.subTest(path=path):
                page = self.page(path)
                canonical = page.select('link[rel="canonical"]')
                self.assertEqual(len(canonical), 1)
                self.assertEqual(canonical[0]["href"], "https://www.nigelharveyplumbing.co.uk"+path)
                self.assertEqual(page.select_one('meta[property="og:url"]')['content'],canonical[0]['href'])
                body = page.get_text(" ", strip=True)
                self.assertIn(first, body)
                self.assertIn(second, body)
                self.assertIn("postcode", body.lower())
                self.assertTrue(page.select_one(f'a[href="{link}"]'))
                self.assertTrue(page.select_one('a[href="/request-quote"]'))
                self.assertIsNotNone(page.select_one('a[href^="https://wa.me/"]'))
                contents.append(body)
        self.assertNotEqual(contents[0], contents[1])

    def test_priority_two_pages_explain_different_customer_decisions(self):
        checks = {
            "/toilet-repair-godalming": (
                "Repairing a cistern or replacing a toilet?",
                "removable access panel", "/plumber-godalming"),
            "/toilet-repair-fairlands": (
                "What if the toilet is leaking outside the pan?",
                "only after flushing", "/plumber-fairlands"),
            "/leak-repair-leatherhead": (
                "Is the leak on the supply or waste side?",
                "around the trap or waste outlet", "/plumber-leatherhead"),
        }
        for path, (heading, phrase, parent) in checks.items():
            with self.subTest(path=path):
                page = self.page(path)
                h3 = next((h for h in page.select("h3") if h.get_text(strip=True) == heading), None)
                self.assertIsNotNone(h3)
                para = h3.find_next_sibling("p")
                self.assertIsNotNone(para)
                self.assertIn(phrase, para.get_text())
                self.assertIsNotNone(para.select_one(f'a[href="{parent}"]'))
                self.assertNotIn("completed job in", para.get_text().lower())
                self.assertEqual(page.select_one('meta[name="robots"]')['content']
                                 if page.select_one('meta[name="robots"]') else "index,follow",
                                 "index,follow")

    def test_priority_guildford_and_surrey_pages_have_distinct_helpful_content(self):
        cases = {
            "/toilet-repair-guildford": ("What to check before a toilet repair in Guildford", "flush mechanism", "Guildford postcode"),
            "/bathroom-plumbing-guildford": ("Planning a bathroom or shower plumbing job in Guildford", "waste fall", "Guildford postcode"),
            "/toilet-repair-woking": ("What details help with a toilet repair in Woking?", "flush plate", "Woking postcode"),
            "/bathroom-plumbing-farnham": ("Replacing bathroom fittings or changing pipework in Farnham", "tray junction", "Farnham postcode"),
        }
        headings = []
        for path, (heading, phrase, postcode) in cases.items():
            with self.subTest(path=path):
                page = self.page(path)
                h2 = next((h for h in page.select("h2") if h.get_text(strip=True) == heading), None)
                self.assertIsNotNone(h2)
                para = h2.find_next_sibling("p")
                self.assertIsNotNone(para)
                self.assertIn(phrase, para.get_text())
                self.assertIn(postcode, para.get_text())
                self.assertEqual(page.select_one('link[rel="canonical"]')['href'],
                                 "https://www.nigelharveyplumbing.co.uk" + path)
                self.assertIsNotNone(page.select_one('a[href="/request-quote"]'))
                headings.append(heading)
        self.assertEqual(len(set(headings)), len(headings))

    def test_project_evidence_only_when_published_and_correctly_located(self):
        with disposable_app("seo-project-proof", "synthetic-test", projects_as_drafts=False, advice_as_drafts=False) as (module, _):
            with TestClient(module.app) as client:
                for path in ("/bathroom-plumbing-guildford", "/bathroom-plumbing-farnham"):
                    with self.subTest(path=path):
                        response = client.get(path)
                        self.assertEqual(response.status_code, 200)
                        page = BeautifulSoup(response.text, "html.parser")
                        self.assertIsNotNone(page.select_one('a[href="/projects/ensuite-renovation-merrow-guildford"]'))
                        self.assertIsNotNone(page.select_one('a[href="/advice/shower-replacement-waterproofing-rebuild"]'))
                        self.assertIn("Merrow", page.get_text())
                        self.assertEqual(len(page.select('h1')), 1)
        for path in ("/bathroom-plumbing-guildford", "/bathroom-plumbing-farnham"):
            page = self.page(path)
            self.assertIsNone(page.select_one('a[href="/projects/ensuite-renovation-merrow-guildford"]'))

    def test_local_overviews_offer_direct_links_into_relevant_repairs(self):
        for overview, repair in [
            ("/plumber-leatherhead", "/leak-repair-leatherhead"),
            ("/plumber-godalming", "/toilet-repair-godalming"),
            ("/plumber-fairlands", "/toilet-repair-fairlands"),
        ]:
            with self.subTest(path=overview):
                page = self.page(overview)
                self.assertTrue(page.select_one(f'a[href="{repair}"]'))
                self.assertEqual(page.select_one('link[rel="canonical"]')['href'],
                                 "https://www.nigelharveyplumbing.co.uk"+overview)

    def test_historical_surrey_wide_404s_are_currently_valid_routes(self):
        # GSC's older 404 crawl times were in May, before the current code.
        for path in ("/emergency-plumber-surrey",
                     "/general-plumbing-surrey",
                     "/bathroom-plumbing-surrey"):
            with self.subTest(path=path):
                page=self.page(path)
                self.assertEqual(page.select_one('link[rel="canonical"]')['href'],
                                 "https://www.nigelharveyplumbing.co.uk"+path)

    def test_sitemap_does_not_gain_or_lose_urls_or_expose_private_app(self):
        xml = self.client.get("/sitemap.xml").text
        # Disposable browser fixtures intentionally make 4 published advice/project
        # records into private drafts; this leaves 78 instead of the live 82.
        self.assertEqual(xml.count("<loc>"), 78)
        for slug in ("/leak-repair-leatherhead","/toilet-repair-godalming","/toilet-repair-fairlands"):
            self.assertIn("https://www.nigelharveyplumbing.co.uk"+slug+"</loc>",xml)
        self.assertNotIn("/app</loc>",xml)
        self.assertNotIn("/api/",xml)
        self.assertIn("Disallow: /app",self.client.get("/robots.txt").text)


if __name__ == "__main__":
    unittest.main()

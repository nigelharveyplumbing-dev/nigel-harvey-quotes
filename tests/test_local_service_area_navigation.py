"""Public-only navigation audit using isolated synthetic test storage.

Use the same disposable public-site harness as the existing 82-page audit.
Avoid importing business.config at unittest discovery time: doing so bypasses
the existing baseline suite's storage isolation.
"""
import unittest

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from local_browser_server import disposable_app


SERVICE_SLUGS = ("emergency-plumber", "toilet-repair", "leak-repair", "bathroom-plumbing")
TOWN_SLUGS = (
    "guildford", "woking", "farnham", "godalming", "camberley",
    "aldershot", "leatherhead", "epsom", "fairlands",
    "worplesdon", "merrow", "burpham", "shalford",
)


class LocalServiceAreaNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = disposable_app(
            "local-navigation-synthetic", "synthetic-only-no-production-data",
            projects_as_drafts=False, advice_as_drafts=False,
        )
        cls.app_module, _ = cls.context.__enter__()
        cls.addClassCleanup(cls.context.__exit__, None, None, None)
        cls.client = TestClient(cls.app_module.app)
        cls.client.__enter__()
        cls.addClassCleanup(cls.client.__exit__, None, None, None)

    def test_all_52_public_local_pages_have_focused_service_area_links(self):
        checked = 0
        known_paths = {
            f"/{service}-{town}" for service in SERVICE_SLUGS for town in TOWN_SLUGS
        }
        self.assertEqual(len(known_paths), 52)
        for service in SERVICE_SLUGS:
            for town in TOWN_SLUGS:
                path = f"/{service}-{town}"
                with self.subTest(path=path):
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 200)
                    soup = BeautifulSoup(response.text, "html.parser")
                    heading = soup.find("h2", string="Other Local Service Areas")
                    self.assertIsNotNone(heading)
                    links_region = heading.find_next("div", class_="pill-links")
                    self.assertIsNotNone(links_region)
                    links = [a.get("href") for a in links_region.find_all("a")]
                    self.assertGreaterEqual(len(links), 3)
                    self.assertLessEqual(len(links), 4)
                    self.assertEqual(len(links), len(set(links)))
                    self.assertTrue(set(links) <= known_paths)
                    self.assertNotIn(path, links)
                    self.assertTrue(all(x.startswith("/" + service + "-") for x in links))
                    self.assertIsNotNone(soup.select_one('link[rel="canonical"]'))
                    self.assertIsNotNone(soup.select_one('a[href="/request-quote"]'))
                    checked += 1
        self.assertEqual(checked, 52)

    def test_fairlands_and_guildford_emergency_navigation_is_local(self):
        expected = {
            "/emergency-plumber-fairlands": (
                "/emergency-plumber-worplesdon", "/emergency-plumber-burpham",
                "/emergency-plumber-guildford", "/emergency-plumber-woking",
            ),
            "/emergency-plumber-guildford": (
                "/emergency-plumber-merrow", "/emergency-plumber-burpham",
                "/emergency-plumber-shalford", "/emergency-plumber-worplesdon",
            ),
        }
        for path, target_links in expected.items():
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                soup = BeautifulSoup(response.text, "html.parser")
                heading = soup.find("h2", string="Other Local Service Areas")
                links = [
                    a.get("href")
                    for a in heading.find_next("div", class_="pill-links").find_all("a")
                ]
                self.assertEqual(tuple(links), target_links)


if __name__ == "__main__":
    unittest.main()

"""Public service-area links stay useful without breaking discoverability.

This module uses unittest so the standard CI test discovery actually runs it.
No app/database import, external requests or customer data access.
"""
import sys
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

# unittest discovery executes from tests/, not always from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from business.public_pages import (
    LOCAL_SERVICE_AREA_NAMES,
    LOCAL_SERVICE_NEARBY_AREAS,
    LOCAL_SERVICE_PAGES,
    LOCATION_PAGES,
    render_local_service_location_page,
)


def _url(path, request=None):
    return "https://www.nigelharveyplumbing.co.uk" + path


class LocalServiceAreaNavigationTests(unittest.TestCase):
    def test_nearby_map_matches_published_towns(self):
        service_towns = {p["slug"] for p in LOCATION_PAGES if p["slug"] != "farnborough"}
        self.assertEqual(set(LOCAL_SERVICE_NEARBY_AREAS), service_towns)
        self.assertTrue(service_towns.issubset(LOCAL_SERVICE_AREA_NAMES))
        for town, neighbours in LOCAL_SERVICE_NEARBY_AREAS.items():
            with self.subTest(town=town):
                self.assertGreaterEqual(len(neighbours), 3)
                self.assertLessEqual(len(neighbours), 4)
                self.assertEqual(len(neighbours), len(set(neighbours)))
                self.assertNotIn(town, neighbours)
                self.assertTrue(set(neighbours) <= service_towns)

    def test_all_52_local_service_pages_link_only_relevant_areas(self):
        audited = 0
        for service in LOCAL_SERVICE_PAGES:
            for location in LOCATION_PAGES:
                if location["slug"] == "farnborough":
                    continue
                with self.subTest(service=service["slug"], town=location["slug"]):
                    html = render_local_service_location_page(
                        service, location, "", absolute_url=_url
                    )
                    soup = BeautifulSoup(html, "html.parser")
                    heading = soup.find("h2", string="Other Local Service Areas")
                    self.assertIsNotNone(heading)
                    container = heading.find_next("div", class_="pill-links")
                    self.assertIsNotNone(container)
                    links = [a["href"] for a in container.find_all("a")]
                    expected = [
                        f'/{service["slug"]}-{neighbour}'
                        for neighbour in LOCAL_SERVICE_NEARBY_AREAS[location["slug"]]
                    ]
                    self.assertEqual(links, expected)
                    self.assertTrue(all(x.startswith("/") and not x.startswith("//") for x in links))
                    self.assertIsNotNone(soup.select_one('link[rel="canonical"]'))
                    self.assertIsNotNone(soup.select_one('a[href="/request-quote"]'))
                    audited += 1
        self.assertEqual(audited, 52)


if __name__ == "__main__":
    unittest.main()

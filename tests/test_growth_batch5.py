"""Google Business Profile and website identity stay explicitly aligned."""

import json
import secrets
import unittest

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from local_browser_server import disposable_app


GOOGLE_PROFILE = "https://maps.google.com/maps?cid=10784369675639695050"


class GrowthBatch5LocalSeoTests(unittest.TestCase):
    def test_business_schema_links_the_verified_google_profile(self):
        with disposable_app(secrets.token_urlsafe(12), secrets.token_urlsafe(16)) as (module, _):
            with TestClient(module.app) as client:
                response = client.get("/")
                self.assertEqual(response.status_code, 200)
                schemas = [
                    json.loads(tag.get_text())
                    for tag in BeautifulSoup(response.text, "html.parser").select(
                        'script[type="application/ld+json"]'
                    )
                ]
                business = next(item for item in schemas if item.get("@type") == "Plumber")
                self.assertEqual(business["hasMap"], GOOGLE_PROFILE)
                self.assertEqual(business["sameAs"], [GOOGLE_PROFILE])

    def test_google_review_fallback_uses_the_verified_profile(self):
        with disposable_app(secrets.token_urlsafe(12), secrets.token_urlsafe(16)) as (module, _):
            self.assertEqual(module.GOOGLE_REVIEWS_URL, GOOGLE_PROFILE)
            html = module._google_reviews_html()
            link = BeautifulSoup(html, "html.parser").select_one("a[href]")
            self.assertEqual(link["href"], GOOGLE_PROFILE)


if __name__ == "__main__":
    unittest.main()

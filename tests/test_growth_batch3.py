"""Public entity markup stays consistent while review cards remain visible."""

import json
import secrets
import unittest

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from local_browser_server import disposable_app


class GrowthBatch3EntityTests(unittest.TestCase):
    def test_shared_business_identity_and_service_provider(self):
        with disposable_app(secrets.token_urlsafe(12), secrets.token_urlsafe(16)) as (module, _):
            with TestClient(module.app) as client:
                base = "https://www.nigelharveyplumbing.co.uk/"
                for path in ("/", "/plumber-guildford", "/plumber-aldershot", "/plumber-camberley"):
                    with self.subTest(path=path):
                        response = client.get(path)
                        self.assertEqual(response.status_code, 200)
                        soup = BeautifulSoup(response.text, "html.parser")
                        schema = [json.loads(tag.text) for tag in soup.select('script[type="application/ld+json"]')]
                        business = next(item for item in schema if item.get("@type") == "Plumber")
                        self.assertEqual(business["@id"], base + "#business")
                        self.assertEqual(business["url"], base)
                        self.assertEqual(business["name"], "Nigel Harvey Plumbing")
                        self.assertEqual(business["legalName"], "Nigel Harvey Ltd")
                        self.assertEqual(business["telephone"], "+447595725547")
                        self.assertIn("Guildford", business["areaServed"])
                        self.assertNotIn("address", business)
                        self.assertNotIn("aggregateRating", business)
                        self.assertNotIn("review", business)
                        self.assertEqual(soup.select_one('link[rel="canonical"]')["href"], base.rstrip("/") + path)
                for path in ("/general-plumbing-surrey", "/leak-repair-camberley"):
                    with self.subTest(path=path):
                        schema = [json.loads(tag.text) for tag in BeautifulSoup(
                            client.get(path).text, "html.parser").select('script[type="application/ld+json"]')]
                        service = next(item for item in schema if item.get("@type") == "Service")
                        self.assertEqual(service["provider"], {"@id": base + "#business"})


if __name__ == "__main__":
    unittest.main()

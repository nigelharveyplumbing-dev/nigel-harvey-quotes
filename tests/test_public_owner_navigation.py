"""Public navigation never advertises the owner-only app.

All rendering is isolated and synthetic. Owner /app remains available through
an authenticated direct bookmark, not a customer-facing website link.
"""
import unittest
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from local_browser_server import disposable_app


class PublicOwnerNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context=disposable_app('owner-navigation-synthetic','test-only-private-app',
                                   projects_as_drafts=False,advice_as_drafts=False)
        cls.app, _root=cls.context.__enter__()
        cls.addClassCleanup(cls.context.__exit__,None,None,None)
        cls.client=TestClient(cls.app.app)
        cls.client.__enter__()
        cls.addClassCleanup(cls.client.__exit__,None,None,None)
        cls.auth=('owner-navigation-synthetic','test-only-private-app')

    def test_all_82_public_pages_omit_staff_app_link(self):
        response=self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code,200)
        urls=[x.text for x in ET.fromstring(response.text).iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
        self.assertEqual(len(urls),82)
        for url in urls:
            path=url.split('.co.uk',1)[1]
            with self.subTest(page=path):
                response=self.client.get(path)
                self.assertEqual(response.status_code,200)
                page=BeautifulSoup(response.text,'html.parser')
                self.assertEqual(page.select('a[href="/app"]'),[],path)
                self.assertNotIn('Open App',page.get_text(' ',strip=True),path)
                self.assertTrue(page.select('a[href="/request-quote"]'),path)
        self.assertIn('Disallow: /app',self.client.get('/robots.txt').text)

    def test_private_staff_app_still_requires_auth(self):
        response=self.client.get('/app')
        self.assertEqual(response.status_code,401)
        self.assertIn('noindex',response.headers.get('x-robots-tag',''))
        self.assertEqual(self.client.get('/app',auth=self.auth).status_code,200)
        self.assertEqual(self.client.get('/api/quotes').status_code,401)


if __name__=='__main__':
    unittest.main()

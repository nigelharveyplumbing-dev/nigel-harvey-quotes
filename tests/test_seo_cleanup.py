import base64
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from local_browser_server import disposable_app

ROOT = Path(__file__).resolve().parents[1]


class SeoCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sandbox = disposable_app('seo-test-only', 'isolated-password', projects_as_drafts=False, advice_as_drafts=False)
        cls.m, cls.root = cls.sandbox.__enter__()
        cls.addClassCleanup(cls.sandbox.__exit__, None, None, None)
        cls.client = TestClient(cls.m.app)
        cls.client.__enter__()
        cls.addClassCleanup(cls.client.__exit__, None, None, None)

    def test_all_public_metadata_remains_unique_concise_and_canonical(self):
        sitemap = ET.fromstring(self.client.get('/sitemap.xml').text)
        urls = sitemap.findall('{http://www.sitemaps.org/schemas/sitemap/0.9}url/{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
        titles, descriptions = [], []
        self.assertEqual(len(urls), 82)
        for loc in urls:
            path = loc.text.split('.co.uk', 1)[1]
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                soup = BeautifulSoup(response.text, 'html.parser')
                title = soup.title.get_text(); description = soup.select_one('meta[name=description]')['content']
                self.assertLessEqual(len(title), 60)
                self.assertLessEqual(len(description), 160)
                self.assertEqual(soup.select_one('link[rel=canonical]')['href'], loc.text)
                self.assertEqual(len(soup.select('h1')), 1)
                titles.append(title); descriptions.append(description)
        self.assertEqual(len(set(titles)), len(titles))
        self.assertEqual(len(set(descriptions)), len(descriptions))

    def test_logo_reuses_existing_public_brand_asset(self):
        from business.config import DEFAULT_COMPANY_LOGO_URL
        self.assertEqual((ROOT / 'static/site-images/nigel-harvey-logo.png').read_bytes(), base64.b64decode(DEFAULT_COMPANY_LOGO_URL.split(',', 1)[1]))
        soup = BeautifulSoup(self.client.get('/').text, 'html.parser')
        business = json.loads(soup.select_one('script[type="application/ld+json"]').string)
        logo = business['logo']
        self.assertEqual((logo['width'], logo['height']), (430, 130))
        response = self.client.get(logo['url'].split('.co.uk', 1)[1])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['content-type'], 'image/png')
        self.assertNotIn('address', business)

    def test_article_image_matches_visible_approved_project_photo(self):
        article = self.m.plumbing_advice.ARTICLES[0]
        soup = BeautifulSoup(self.client.get(article.path).text, 'html.parser')
        schema = json.loads(soup.select_one('script[type="application/ld+json"]').string)
        graph_article = next(n for n in schema['@graph'] if n['@type'] == 'Article')
        image = soup.select_one('.advice-project-image img')
        self.assertTrue(image['alt'])
        self.assertEqual(graph_article['image'], ['https://www.nigelharveyplumbing.co.uk' + image['src']])
        self.assertEqual(soup.select_one('meta[property="og:image"]')['content'], graph_article['image'][0])
        self.assertEqual(self.client.get(image['src']).status_code, 200)
        self.assertIn('marmox-board-and-pipework', image['src'])
        for paragraph in [p for s in article.sections for p in s.paragraphs] + article.safety:
            self.assertIn(paragraph, soup.get_text())

    def test_unpublished_article_or_project_cannot_supply_public_image(self):
        advice = self.m.plumbing_advice
        article = advice.ARTICLES[0]
        draft_article = article.model_copy(update={'status': 'draft', 'approved_at': None, 'published_at': None})
        self.assertIsNone(advice.article_project_image(draft_article))
        with patch.object(self.m.real_projects, 'PROJECTS', tuple(p.model_copy(update={'status': 'draft', 'approved_at': None, 'published_at': None}) for p in self.m.real_projects.PROJECTS)):
            self.assertIsNone(advice.article_project_image(article))
            schema = advice.schema_graph(article, self.m.absolute_url)
            self.assertNotIn('image', next(n for n in schema['@graph'] if n['@type'] == 'Article'))

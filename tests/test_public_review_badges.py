"""Public-only rating presentation, using synthetic Google data and isolated storage."""
import json
import secrets
import unittest
from unittest.mock import patch
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from local_browser_server import disposable_app

REVIEW_HTML = ('<div class="google-rating"><strong>4.6</strong><span class="stars">★★★★★</span>'
               '<span>23 Google reviews</span></div><div class="google-review-grid">' +
               ''.join('<article class="google-review-card">Synthetic customer feedback</article>' for _ in range(5)) + '</div>')

class PublicReviewBadgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sandbox = disposable_app(secrets.token_urlsafe(12), secrets.token_urlsafe(16), projects_as_drafts=False, advice_as_drafts=False)
        cls.m, cls.root = cls.sandbox.__enter__()
        cls.addClassCleanup(cls.sandbox.__exit__, None, None, None)
        cls.client = TestClient(cls.m.app)
        cls.client.__enter__()
        cls.addClassCleanup(cls.client.__exit__, None, None, None)

    def assert_badge(self, html):
        page = BeautifulSoup(html, 'html.parser')
        badges = page.select('.hero-review-badge')
        self.assertEqual(len(badges), 1)
        badge = badges[0]
        self.assertIn('4.6', badge.text)
        self.assertIn('23 Google reviews', badge.text)
        self.assertEqual(badge.a['href'], '/#reviews')
        self.assertIn('review-summary', badge.a['class'])
        self.assertFalse(page.select('.google-review-card'))
        self.assertEqual(len(page.select('header .brand-logo')), 1)
        self.assertFalse(page.select('.hero img.logo'))
        return page

    def test_all_surrey_service_and_london_pages(self):
        m = self.m
        paths = ['/' + p['slug'] for p in m.SERVICE_PAGES]
        paths += ['/plumber-' + p['slug'] for p in m.LOCATION_PAGES + m.public_pages.SOUTH_WEST_LONDON_PAGES]
        local_paths = ['/' + s['slug'] + '-' + l['slug'] for s in m.LOCAL_SERVICE_PAGES
                       for l in m.LOCATION_PAGES if l['slug'] != 'farnborough']
        self.assertEqual(len(local_paths), 52)
        paths += local_paths
        with patch.object(m, '_google_reviews_html', return_value=REVIEW_HTML):
            for path in paths:
                with self.subTest(path=path):
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 200)
                    page = self.assert_badge(response.text)
                    hero = page.select_one('.hero-copy, .hero-card')
                    self.assertIsNotNone(hero)
                    children = list(hero.children)
                    badge = hero.select_one('.hero-review-badge')
                    actions = hero.select_one('.actions, .nav-actions')
                    self.assertLess(children.index(badge), children.index(actions))
                    self.assertIsNotNone(page.select_one('link[rel=canonical]'))

    def test_homepage_keeps_full_cards_and_strip(self):
        with patch.object(self.m, '_google_reviews_html', return_value=REVIEW_HTML):
            page = BeautifulSoup(self.client.get('/').text, 'html.parser')
        self.assertEqual(len(page.select('#reviews .google-review-card')), 5)
        self.assertEqual(len(page.select('.review-strip a.review-summary')), 1)
        self.assertEqual(page.select_one('.review-strip a.review-summary')['href'], '#reviews')
        self.assertFalse(page.select('.hero-review-badge'))
        self.assertNotIn('aggregateRating', str(page))

    def test_advice_projects_and_enquiry_exclusions(self):
        m = self.m
        with patch.object(m, '_google_reviews_html', return_value=REVIEW_HTML):
            paths = ['/advice', '/projects']
            paths += [a.path for a in m.plumbing_advice.visible_articles()]
            paths += [p.path for p in m.real_projects.visible_projects()]
            for path in paths:
                with self.subTest(path=path):
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 200)
                    self.assert_badge(response.text)
            self.assertNotIn('hero-review-badge', BeautifulSoup(self.client.get('/request-quote').text, 'html.parser').main.decode())
        self.assertEqual(self.client.get('/app').status_code, 401)

    def test_fallback_is_clickable_without_an_invented_score(self):
        with patch.object(self.m, '_google_reviews_html', return_value='<h2>Customer reviews</h2>'):
            for path in ['/leak-repair-guildford', '/plumber-wimbledon', '/plumber-guildford', '/advice']:
                page = BeautifulSoup(self.client.get(path).text, 'html.parser')
                badge = page.select_one('.hero-review-badge')
                self.assertEqual(badge.text, 'Read customer reviews on Google')
                self.assertTrue(badge.a['href'].startswith('https://'))
                self.assertFalse(badge.select('.google-rating, .stars'))

    def test_decoration_preserves_seo_content_and_is_idempotent(self):
        m = self.m
        original = m.public_pages.render_location_page('Guildford', '', absolute_url=m.absolute_url,
                                                      _google_reviews_html=lambda: REVIEW_HTML)
        updated = m.website_contact.add_public_review_badge(original, REVIEW_HTML, m.GOOGLE_REVIEWS_URL)
        again = m.website_contact.add_public_review_badge(updated, REVIEW_HTML, m.GOOGLE_REVIEWS_URL)
        self.assertEqual(updated, again)
        before, after = [BeautifulSoup(h, 'html.parser') for h in (original, updated)]
        self.assertEqual(str(before.head), str(after.head))
        for page in (before, after):
            for node in page.select('.hero-review-badge, .reviewbox'):
                node.decompose()
        self.assertEqual(before.main.get_text(' ', strip=True), after.main.get_text(' ', strip=True))
        self.assertEqual([a['href'] for a in before.main.select('a[href]')],
                         [a['href'] for a in after.main.select('a[href]')])

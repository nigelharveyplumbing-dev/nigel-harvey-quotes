"""Owner-confirmed London area pages: coverage, SEO and no extra service matrix."""
import json
import secrets
import unittest
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from local_browser_server import disposable_app

AREAS = {'richmond':'Richmond','kingston':'Kingston upon Thames','wimbledon':'Wimbledon','putney':'Putney','merton':'Merton','morden':'Morden'}

class SouthWestLondonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sandbox=disposable_app(secrets.token_urlsafe(12),secrets.token_urlsafe(16))
        cls.module,cls.root=cls.sandbox.__enter__()
        cls.addClassCleanup(cls.sandbox.__exit__,None,None,None)
        cls.client=TestClient(cls.module.app)
        cls.client.__enter__();cls.addClassCleanup(cls.client.__exit__,None,None,None)

    def page(self,slug):
        response=self.client.get('/plumber-'+slug)
        self.assertEqual(response.status_code,200)
        return BeautifulSoup(response.text,'html.parser')

    def test_six_area_pages_have_distinct_useful_planning_content(self):
        plans=[]
        for slug,name in AREAS.items():
            with self.subTest(slug=slug):
                page=self.page(slug)
                self.assertEqual(page.h1.get_text(),f'Plumber in {name}')
                plans.append(page.find('h2',string=f'Planning plumbing work in {name}').find_next('p').get_text())
        self.assertEqual(len(set(plans)),6)
        self.assertTrue(any('floor, access arrangements' in p for p in plans))
        self.assertTrue(any('hot water, cold water or both' in p for p in plans))

    def test_coverage_and_emergency_availability_are_qualified(self):
        for slug in AREAS:
            text=self.page(slug).get_text(' ',strip=True)
            for phrase in ['based in Guildford','depending on the location and work involved','subject to availability','may not answer immediately','not guaranteed','no London office']:
                self.assertIn(phrase,text)
            self.assertNotIn('surrounding Surrey areas',text)
            self.assertNotIn('Gas Safe',text)

    def test_unique_canonical_metadata_and_visible_faq_match_schema(self):
        metas=[]
        for slug in AREAS:
            page=self.page(slug)
            self.assertEqual(urlsplit(page.select_one('link[rel="canonical"]')['href']).path,'/plumber-'+slug)
            meta=page.select_one('meta[name="description"]')['content']
            self.assertLessEqual(len(meta),160);metas.append(meta)
            schemas=[json.loads(s.string) for s in page.select('script[type="application/ld+json"]')]
            faq=next(x for x in schemas if x.get('@type')=='FAQPage')
            for answer in faq['mainEntity']:
                self.assertEqual(page.find('h3',string=answer['name']).find_next('p').get_text(),answer['acceptedAnswer']['text'])
        self.assertEqual(len(set(metas)),6)

    def test_structured_service_uses_single_guildford_business_identity(self):
        for slug,name in AREAS.items():
            schemas=[json.loads(s.string) for s in self.page(slug).select('script[type="application/ld+json"]')]
            service=next(x for x in schemas if x.get('@type')=='Service')
            self.assertEqual(service['areaServed'],[name,'South West London'])
            self.assertTrue(service['provider']['@id'].endswith('/#business'))
            self.assertNotIn('address',service);self.assertNotIn('openingHours',service)

    def test_homepage_links_to_all_six_confirmed_areas(self):
        home=BeautifulSoup(self.client.get('/').text,'html.parser')
        areas=home.select_one('#areas')
        self.assertIn('South West London plumbing enquiries',areas.get_text())
        for slug in AREAS:self.assertEqual(len(areas.select(f'a[href="/plumber-{slug}"]')),1)

    def test_only_six_overviews_added_to_sitemap_without_service_matrix(self):
        xml=self.client.get('/sitemap.xml').text
        for slug in AREAS:
            self.assertEqual(xml.count('/plumber-'+slug+'</loc>'),1)
            for service in ['toilet-repair','leak-repair','bathroom-plumbing','emergency-plumber']:
                self.assertNotIn('/'+service+'-'+slug+'</loc>',xml)
                self.assertEqual(self.client.get('/'+service+'-'+slug).status_code,404)
        self.assertEqual(self.client.get('/plumber-unconfirmed-town').status_code,404)

    def test_quote_links_keep_area_attribution_and_no_submission(self):
        for slug in AREAS:
            links=self.page(slug).select('a[href^="/request-quote"]')
            self.assertTrue(links)
            self.assertTrue(all(link['href']=='/request-quote' for link in links))
            self.assertIn('next.searchParams.set',str(self.page(slug)))

    def test_london_list_does_not_change_surrey_matrix(self):
        self.assertEqual(len(self.module.LOCATION_PAGES),14)
        self.assertEqual(len(self.module.public_pages.SOUTH_WEST_LONDON_PAGES),6)
        self.assertEqual(self.client.get('/leak-repair-guildford').status_code,200)

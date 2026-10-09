import base64
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from pydantic import ValidationError
from local_browser_server import disposable_app

ROOT = Path(__file__).resolve().parents[1]

class AdviceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sandbox = disposable_app('advice-test-only', 'isolated-password', projects_as_drafts=False)
        cls.m, cls.root = cls.sandbox.__enter__()
        cls.addClassCleanup(cls.sandbox.__exit__, None, None, None)
        cls.client = TestClient(cls.m.app)
        cls.client.__enter__(); cls.addClassCleanup(cls.client.__exit__, None, None, None)
        cls.advice=cls.m.plumbing_advice; cls.a=cls.advice.ARTICLES[0]
        cls.auth={'Authorization':'Basic '+base64.b64encode(b'advice-test-only:isolated-password').decode()}

    def published(self):
        data=self.a.model_dump(mode='json')
        data.update(status='published', approved_at='2026-10-09T10:00:00+01:00', published_at='2026-10-09T10:05:00+01:00')
        return self.advice.Advice.model_validate(data)

    def test_anonymous_draft_privacy_and_no_public_discovery(self):
        for path in ['/advice',self.a.path,self.a.path+'?preview=1', '/advice/unknown']:
            response=self.client.get(path)
            self.assertEqual(response.status_code,404)
            self.assertNotIn(self.a.summary,response.text)
            self.assertIn('noindex',response.headers['x-robots-tag'])
            self.assertEqual(response.headers['cache-control'],'private, no-store')
        self.assertEqual(self.client.get(self.a.path,headers={'Authorization':'Basic ZmFrZTpmYWtl'}).status_code,404)
        for path in ['/', '/projects','/sitemap.xml','/bathroom-plumbing-surrey','/bathroom-plumbing-guildford','/projects/ensuite-renovation-merrow-guildford']:
            self.assertNotIn(self.a.path,self.client.get(path).text)
        self.assertEqual(self.client.post(self.a.path,headers=self.auth).status_code,405)
        self.assertEqual(self.client.get('/api/customers').status_code,401)

    def test_owner_preview_metadata_schema_and_links(self):
        response=self.client.get(self.a.path+'?utm_source=test',headers={**self.auth,'Host':'untrusted.example'})
        self.assertEqual(response.status_code,200)
        self.assertIn('noindex',response.headers['x-robots-tag'])
        self.assertEqual(response.headers['cache-control'],'private, no-store')
        soup=BeautifulSoup(response.text,'html.parser')
        self.assertEqual(soup.select_one('link[rel=canonical]')['href'],'https://www.nigelharveyplumbing.co.uk'+self.a.path)
        self.assertEqual(len(soup.select('h1')),1)
        self.assertEqual(soup.select_one('#public-analytics')['data-send-to-google'],'false')
        graph=json.loads(soup.select_one('script[type="application/ld+json"]').string)['@graph']
        article=next(x for x in graph if x['@type']=='Article')
        self.assertNotIn('datePublished',article);self.assertNotIn('dateModified',article)
        self.assertEqual(article['author']['name'],'Nigel Harvey')
        self.assertEqual(article['publisher']['@id'],graph[0]['@id'])
        self.assertNotIn('Review',[x['@type'] for x in graph])
        for link in soup.select('main a[href^="/"]'):
            self.assertEqual(self.client.get(link['href'].split('#')[0],headers=self.auth).status_code,200,link['href'])
        self.assertIn(self.a.title,self.client.get('/advice',headers=self.auth).text)

    def test_publication_requires_explicit_approval_and_dates(self):
        data=self.a.model_dump(mode='json'); data.update(status='published', approved_at=None, published_at=None)
        with self.assertRaises(ValidationError):self.advice.Advice.model_validate(data)
        for changes in [dict(approved_at='2026-10-09T11:00:00+01:00',published_at='2026-10-09T10:00:00+01:00'),dict(approved_at='2026-10-09T10:00:00',published_at='2026-10-09T11:00:00'),dict(approved_at='2026-10-09T10:00:00+01:00',published_at='2026-10-10T11:00:00+01:00')]:
            with self.assertRaises(ValidationError):self.advice.Advice.model_validate({**data,**changes})

    def test_future_publication_sitemap_and_backlinks_in_memory_only(self):
        a=self.published()
        with patch.object(self.advice,'ARTICLES',(a,)):
            self.assertEqual(self.client.get(a.path).status_code,200)
            self.assertEqual(self.client.get('/advice').status_code,200)
            response=self.client.get(a.path)
            self.assertNotIn('noindex',response.headers.get('x-robots-tag',''))
            self.assertEqual(self.client.get('/sitemap.xml').text.count('<loc>'),76)
            self.assertIn(a.path,self.client.get('/sitemap.xml').text)
            for path in [l.path for l in a.services]+['/projects/'+s for s in a.project_slugs]:
                self.assertIn('href="'+a.path+'"',self.client.get(path).text)
            graph=json.loads(BeautifulSoup(response.text,'html.parser').select_one('script[type="application/ld+json"]').string)['@graph']
            self.assertIn('datePublished',next(x for x in graph if x['@type']=='Article'))
        self.assertEqual(self.advice.ARTICLES[0].status,'draft')
        self.assertEqual(self.client.get('/sitemap.xml').text.count('<loc>'),74)

    def test_duplicate_and_near_duplicate_records_rejected(self):
        data=self.a.model_dump(mode='json')
        for change in [{},dict(slug='another-title',topic_key='another-topic',title='A slightly different title')]:
            with self.assertRaises(ValueError):self.advice.validate_catalogue([data,{**data,**change}])
        with self.assertRaises(ValidationError):self.advice.Advice.model_validate({**data,'customer_phone':'not allowed'})

    def test_catalogue_rejects_private_or_unknown_related_links(self):
        data = self.a.model_dump(mode='json')
        for changes in [
            {'services': [{'path': '/app', 'label': 'Private app'}]},
            {'services': [{'path': '/api/customers', 'label': 'Customers'}]},
            {'locations': [{'path': '/request-quote', 'label': 'Not a location'}]},
            {'project_slugs': ['missing-project']},
        ]:
            with self.assertRaises(ValueError):
                self.advice.validate_catalogue([{**data, **changes}])

    def test_staging_entire_site_remains_protected(self):
        with patch.dict('os.environ',{'APP_ENVIRONMENT':'staging','PUBLIC_BASE_URL':'https://isolated.example'}):
            for path in ['/advice',self.a.path,'/sitemap.xml','/app']:
                self.assertEqual(self.client.get(path).status_code,401)
            page=self.client.get(self.a.path,headers=self.auth)
            self.assertIn('noindex',page.headers['x-robots-tag'])
            self.assertIn('https://isolated.example'+self.a.path,page.text)
            self.assertIn('Disallow: /',self.client.get('/robots.txt',headers=self.auth).text)

    def test_existing_public_content_files_and_core_assets_unchanged(self):
        # Batch 8 explicitly authorises targeted public_pages.py changes. The
        # mixed published/draft and unchanged-page checks live in test_growth_batch8.
        paths=['business/project_content.json','business/real_projects.py','business/quote_calculation.py','business/account_pricing.py','business/city_account_prices.py','business/db.py','business/lead_email_store.py','business/lead_store.py','business/notifications.py','business/invoice_store.py','business/pdf_render.py','business/quote_store.py','static/app.js','static/city_account_prices.js','static/public_analytics.js','templates/public_footer.html','templates/public_header.html']
        for path in paths:
            baseline=subprocess.check_output(['git','show','bdcacc9ff02d041e4ab4c63269b5c7ebba4942a2:'+path],cwd=ROOT)
            self.assertEqual((ROOT/path).read_bytes(),baseline,path)

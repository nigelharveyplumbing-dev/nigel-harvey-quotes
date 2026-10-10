"""Batch 8 proposals preserve the live article, projects and protected app code."""
import ast
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from local_browser_server import disposable_app

ROOT=Path(__file__).resolve().parents[1]
BASE='63d2505c8d566f63d10b84414d10ed7aec713cab'
DRAFT='/advice/radiators-cold-heating-unevenly'

class GrowthBatch8Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private_env=patch.dict(os.environ,{'PLUMBING_ADVICE_PRIVATE_DRAFTS':str(ROOT/'tests/fixtures/private_advice_synthetic.json')})
        cls.private_env.__enter__();cls.addClassCleanup(cls.private_env.__exit__,None,None,None)
        cls.sandbox=disposable_app('batch8-review','isolated-password',projects_as_drafts=False,advice_as_drafts=False)
        cls.module,cls.root=cls.sandbox.__enter__();cls.addClassCleanup(cls.sandbox.__exit__,None,None,None)
        cls.client=TestClient(cls.module.app);cls.client.__enter__();cls.addClassCleanup(cls.client.__exit__,None,None,None)
        cls.auth={'Authorization':'Basic '+base64.b64encode(b'batch8-review:isolated-password').decode()}

    def test_mixed_catalogue_keeps_radiator_draft_private(self):
        for suffix in ['', '?preview=1', '?utm_source=google']:
            r=self.client.get(DRAFT+suffix)
            self.assertEqual(r.status_code,404)
            self.assertEqual(r.headers['cache-control'],'private, no-store')
            self.assertIn('noindex',r.headers['x-robots-tag'])
            self.assertNotIn('trapped air',r.text)
        self.assertEqual(self.client.get(DRAFT,headers={'Authorization':'Basic ZmFrZTpmYWtl'}).status_code,404)
        for path in ['/', '/advice','/projects','/sitemap.xml','/plumber-guildford','/plumber-woking','/heating-repairs-surrey','/projects/ensuite-renovation-merrow-guildford']:
            r=self.client.get(path);self.assertEqual(r.status_code,200)
            self.assertNotIn(DRAFT,r.text)
        self.assertEqual(self.client.get('/sitemap.xml').text.count('<loc>'),76)
        self.assertEqual(self.client.get('/advice/shower-replacement-waterproofing-rebuild').status_code,200)

    def test_private_owner_preview_has_safe_metadata_and_links(self):
        r=self.client.get(DRAFT,headers=self.auth);self.assertEqual(r.status_code,200)
        self.assertEqual(r.headers['cache-control'],'private, no-store');self.assertIn('noindex',r.headers['x-robots-tag'])
        s=BeautifulSoup(r.text,'html.parser')
        self.assertEqual(len(s.select('h1')),1)
        self.assertEqual(s.select_one('h1').get_text(),'Why are some radiators cold or heating unevenly?')
        self.assertEqual(s.select_one('link[rel=canonical]')['href'],'https://www.nigelharveyplumbing.co.uk'+DRAFT)
        self.assertEqual(s.select_one('#public-analytics')['data-send-to-google'],'false')
        graph=json.loads(s.select_one('script[type="application/ld+json"]').get_text())['@graph']
        a=next(x for x in graph if x['@type']=='Article')
        self.assertNotIn('datePublished',a);self.assertNotIn('dateModified',a)
        self.assertEqual(a['author']['name'],'Nigel Harvey')
        self.assertEqual(len(s.select('main img')),0)
        self.assertIn('Help with radiators and heating pipework',r.text)
        for link in s.select('main a[href^="/"]'):
            self.assertEqual(self.client.get(link['href'].split('#')[0],headers=self.auth).status_code,200)
        self.assertIn(DRAFT,self.client.get('/advice',headers=self.auth).text)

    def test_public_context_links_have_real_destinations(self):
        for path,heading in [('/', 'Planning a shower or bathroom job?'),('/plumber-guildford','Choosing the next step for your Guildford plumbing job'),('/plumber-woking','Planning a repair or bathroom visit in Woking'),('/leak-repair-farnham','An active leak or an occasional drip?')]:
            r=self.client.get(path);s=BeautifulSoup(r.text,'html.parser')
            self.assertIn(heading,r.text);self.assertEqual(len(s.select('h1')),1)
            self.assertEqual(s.select_one('link[rel=canonical]')['href'],'https://www.nigelharveyplumbing.co.uk'+path)
            for link in s.select('main a[href^="/"]'):
                href=link['href'].split('#')[0]
                self.assertEqual(self.client.get(href).status_code,200,href)
            for tag in s.select('script[type="application/ld+json"]'):json.loads(tag.get_text())
        self.assertIn('project took place in Merrow, Guildford',self.client.get('/plumber-woking').text)
        self.assertEqual(self.client.get('/app').status_code,401)
        self.assertEqual(self.client.get('/api/customers').status_code,401)

    def test_farnham_uses_shared_branding_without_legacy_hero_logo(self):
        for path in ['/', '/plumber-guildford', '/plumber-woking', '/leak-repair-farnham']:
            with self.subTest(path=path):
                response=self.client.get(path)
                self.assertEqual(response.status_code,200)
                page=BeautifulSoup(response.text,'html.parser')
                self.assertIn('Nigel Harvey',page.select_one('header .brand').get_text())
                self.assertIn('PLUMBING',page.select_one('header .brand').get_text())
                self.assertEqual(len(page.select('main img.logo')),0)
        # The approved correction must not remove logos from other service pages.
        for path in ['/leak-repair-camberley', '/bathroom-plumbing-farnham']:
            page=BeautifulSoup(self.client.get(path).text,'html.parser')
            self.assertEqual(len(page.select('.hero-card img.logo')),1)

    def test_original_published_article_record_and_project_assets_preserved(self):
        original=json.loads(subprocess.check_output(['git','show',BASE+':business/advice_content.json'],cwd=ROOT))
        current=json.loads((ROOT/'business/advice_content.json').read_text())
        self.assertEqual(current,original);self.assertEqual(len(current),1)
        draft=self.module.plumbing_advice.ARTICLES[1]
        self.assertEqual(draft.status,'draft')
        self.assertIsNone(draft.approved_at);self.assertIsNone(draft.published_at)
        self.assertEqual(draft.project_slugs,[])
        for path in ['business/project_content.json','business/real_projects.py','docs/growth-batch-7/final-approved-shower-article.md','docs/growth-batch-7/publication-approval.json']:
            self.assertEqual((ROOT/path).read_bytes(),subprocess.check_output(['git','show',BASE+':'+path],cwd=ROOT))
        tracked=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE,'static/project-images'],cwd=ROOT,text=True).splitlines()
        for path in tracked:self.assertEqual((ROOT/path).read_bytes(),subprocess.check_output(['git','show',BASE+':'+path],cwd=ROOT),path)

    def test_app_changes_limited_to_public_html_insertion(self):
        old=ast.parse(subprocess.check_output(['git','show',BASE+':app.py'],cwd=ROOT))
        new=ast.parse((ROOT/'app.py').read_text())
        allowed={'render_public_homepage','add_project_evidence'}
        before=[ast.dump(n) for n in old.body if getattr(n,'name',None) not in allowed]
        after=[ast.dump(n) for n in new.body if getattr(n,'name',None) not in allowed]
        self.assertEqual(before,after)
        for tree in [old,new]:self.assertEqual(sum(getattr(n,'name',None) in allowed for n in tree.body),2)
        for path in ['business/db.py','business/lead_email_store.py','business/lead_store.py','business/notifications.py','business/quote_calculation.py','business/quote_store.py','business/invoice_store.py','business/pdf_render.py','business/account_pricing.py','business/city_account_prices.py','static/app.js','static/city_account_prices.js','static/public_analytics.js','templates/request_quote.html']:
            self.assertEqual((ROOT/path).read_bytes(),subprocess.check_output(['git','show',BASE+':'+path],cwd=ROOT),path)

    def test_private_file_cannot_publish_or_bypass_approval(self):
        private_file=self.root/'invalid-private-advice.json'
        private_file.write_text(json.dumps([{'status':'published'}]))
        with patch.dict(os.environ,{'PLUMBING_ADVICE_PRIVATE_DRAFTS':str(private_file)}):
            with self.assertRaisesRegex(ValueError,'drafts only'):
                self.module.plumbing_advice.load_catalogue()
        private_file.write_text(json.dumps([{'status':'draft','approved_at':'2026-10-09T12:00:00Z'}]))
        with patch.dict(os.environ,{'PLUMBING_ADVICE_PRIVATE_DRAFTS':str(private_file)}):
            with self.assertRaises(ValueError):self.module.plumbing_advice.load_catalogue()

    def test_public_ci_rejects_private_owner_files_before_launch(self):
        outcome=subprocess.run(['node',str(ROOT/'tests/run_batch8_browser.mjs')],cwd=ROOT,
            env={**os.environ,'CI':'true','STAGE6_CHROMIUM_EXECUTABLE':sys.executable},
            capture_output=True,text=True,timeout=10)
        self.assertNotEqual(outcome.returncode,0)
        self.assertIn('Private owner content must not be loaded in public CI',outcome.stderr)
        self.assertNotIn('Synthetic test content',outcome.stderr)

if __name__=='__main__':unittest.main()

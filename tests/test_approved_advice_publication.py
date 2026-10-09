"""Check the owner attachment against the public release, using disposable records."""
import hashlib
import json
from pathlib import Path
import re
import unittest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from local_browser_server import disposable_app

ROOT = Path(__file__).resolve().parents[1]

class ApprovedPublicationTests(unittest.TestCase):
    def test_exact_approved_text_metadata_links_and_discovery(self):
        source=ROOT/'docs/growth-batch-7/final-approved-shower-article.md'
        manifest=json.loads((source.parent/'publication-approval.json').read_text())
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),manifest['sha256'])
        body=source.read_text().split('\n---\n',1)[0]
        approved=re.split(r'^## ',body,flags=re.M)[1:]
        with disposable_app('publication-test','isolated-password',projects_as_drafts=False,advice_as_drafts=False) as (m,_):
            with TestClient(m.app) as client:
                a=m.plumbing_advice.ARTICLES[0]
                response=client.get(a.path)
                self.assertEqual(response.status_code,200)
                soup=BeautifulSoup(response.text,'html.parser')
                self.assertEqual(soup.select_one('h1').get_text(),a.title)
                article=soup.select_one('article.advice-story')
                expected=[]
                for section in approved:
                    heading,content=section.split('\n',1)
                    if heading==a.title:
                        expected.extend(content.strip().split('\n\n'))
                    elif heading=='Homeowner questions':
                        for faq in re.split(r'^### ',content,flags=re.M)[1:]:
                            question,answer=faq.split('\n',1)
                            self.assertIn(question,[h.get_text() for h in article.select('h3')])
                            expected.append(answer.strip())
                    else:
                        self.assertIn(heading,[h.get_text() for h in article.select('h2')])
                        expected.extend(content.strip().split('\n\n'))
                paragraphs=[p.get_text() for p in article.select('p')]
                self.assertEqual([p for p in paragraphs if p in expected],expected)
                self.assertEqual(len(expected),25)
                self.assertNotIn('Publication metadata and link instructions',response.text)
                self.assertEqual(len(article.select('img')),0)
                self.assertNotIn('noindex',response.headers.get('x-robots-tag',''))
                self.assertEqual(soup.title.get_text(),a.seo_title)
                self.assertEqual(soup.select_one('meta[name=description]')['content'],a.meta_description)
                canonical='https://www.nigelharveyplumbing.co.uk'+a.path
                self.assertEqual(soup.select_one('link[rel=canonical]')['href'],canonical)
                graph=json.loads(soup.select_one('script[type="application/ld+json"]').string)['@graph']
                schema=next(n for n in graph if n['@type']=='Article')
                self.assertEqual(schema['datePublished'][:10],'2026-10-09')
                self.assertEqual(schema['mainEntityOfPage'],canonical)
                self.assertEqual(schema['author']['name'],'Nigel Harvey')
                for path in ['/','/advice','/bathroom-plumbing-surrey','/bathroom-plumbing-guildford','/projects/ensuite-renovation-merrow-guildford']:
                    page=client.get(path); self.assertEqual(page.status_code,200)
                    self.assertIn('href="/advice"',page.text)
                for link in article.select('a[href^="/"]'):
                    self.assertEqual(client.get(link['href'].split('#')[0]).status_code,200)
                sitemap=client.get('/sitemap.xml').text
                self.assertEqual(sitemap.count('<loc>'),76)
                self.assertIn(canonical,sitemap)
                self.assertEqual(client.get('/app').status_code,401)
                self.assertEqual(client.get('/api/customers').status_code,401)
                self.assertEqual(client.get('/advice/unknown').status_code,404)

"""Business outcomes and legacy migration using disposable local SQLite only."""

import json
import base64
import secrets
import sqlite3
import unittest
from urllib.parse import urlsplit
from xml.etree import ElementTree

from fastapi.testclient import TestClient
from local_browser_server import disposable_app


class BusinessGrowthTests(unittest.TestCase):
    def test_linked_lead_quote_outcomes_and_source_report(self):
        username, password = secrets.token_urlsafe(12), secrets.token_urlsafe(16)
        auth = {'Authorization': 'Basic ' + base64.b64encode(f'{username}:{password}'.encode()).decode()}
        with disposable_app(username, password) as (module, _):
            with TestClient(module.app) as client:
                public_lead = client.post('/api/leads', json={
                    'name': 'Local test', 'phone': '07000000000', 'description': 'Leaky tap',
                    'source': 'website', 'landing_page': '/plumber-guildford',
                    'utm_source': 'google', 'utm_medium': 'organic'},
                ).json()
                self.assertEqual(public_lead['source_category'], 'Google organic search')
                self.assertEqual(public_lead['landing_page'], '/plumber-guildford')
                self.assertEqual(client.get('/api/business-performance').status_code, 401)
                self.assertEqual(client.put('/api/quotes/1/outcome', json={'status': 'won'}).status_code, 401)
                request = {'customer_name': 'Local test', 'customer_phone': '07000000000',
                           'job_description': 'Leaky tap', 'labour_cost': 100,
                           'lead_id': public_lead['id'], 'work_type': 'Tap'}
                quote_response = client.post('/api/quote', headers=auth, json=request)
                self.assertEqual(quote_response.status_code, 200, quote_response.text)
                quote = quote_response.json()
                self.assertEqual(quote['status'], 'pending')
                self.assertEqual(quote['lead_id'], public_lead['id'])
                self.assertEqual(client.get('/api/leads', headers=auth).json()[0]['status'], 'quoted')
                outcome_url = f"/api/quotes/{quote['id']}/outcome"
                for status in ('pending', 'won', 'lost', 'expired'):
                    payload = {'status': status, 'next_follow_up': '2020-01-02',
                               'loss_reason': 'Price', 'loss_note': 'Customer chose a lower price'}
                    response = client.put(outcome_url, headers=auth, json=payload)
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()['status'], status)
                    self.assertEqual(response.json()['next_follow_up'], '2020-01-02' if status == 'pending' else '')
                    self.assertEqual(response.json()['loss_reason'], 'Price' if status == 'lost' else '')
                    if status == 'pending':
                        due = client.get('/api/business-performance', headers=auth).json()['follow_ups']
                        self.assertEqual(due[0]['id'], quote['id'])
                        self.assertTrue(due[0]['overdue'])
                    if status == 'lost':
                        recent = client.get('/api/business-performance', headers=auth).json()['recent_lost']
                        self.assertEqual(recent, [{'id': quote['id'], 'customer_name': 'Local test',
                                                   'total_price': quote['total_price']}])
                self.assertEqual(client.put(outcome_url, headers=auth,
                                            json={'status': 'nonsense'}).status_code, 422)
                self.assertEqual(client.put(outcome_url, headers=auth,
                                            json={'status': 'pending', 'next_follow_up': '2020-15-45'}).status_code, 422)
                client.put(outcome_url, headers=auth, json={'status': 'won'})
                report = client.get('/api/business-performance', headers=auth).json()
                self.assertEqual(report['status_counts']['won'], 1)
                self.assertEqual(report['status_counts']['pending'], 0)
                self.assertEqual(report['by_source']['Google organic search']['wins'], 1)
                self.assertEqual(report['win_rate_percent'], 100)
                self.assertEqual(report['recent_won'], [{'id': quote['id'], 'customer_name': 'Local test',
                                                         'total_price': quote['total_price']}])
                invoice = client.post(f"/api/quotes/{quote['id']}/to-invoice", headers=auth).json()
                self.assertEqual(invoice['quote_id'], quote['id'])
                report = client.get('/api/business-performance', headers=auth).json()
                self.assertEqual(report['by_source']['Google organic search']['invoiced_value'], quote['total_price'])
                self.assertEqual(report['by_source']['Google organic search']['paid_value'], 0)
                classification = client.put(f"/api/leads/{public_lead['id']}/classification", headers=auth,
                                            json={'source_category': 'Referral', 'work_type': 'Tap'})
                self.assertEqual(classification.status_code, 200)
                self.assertEqual(classification.json()['utm_source'], 'google')
                self.assertEqual(classification.json()['work_type'], 'Tap')
                updated_report = client.get('/api/business-performance', headers=auth).json()
                self.assertEqual(updated_report['by_source']['Referral']['wins'], 1)
                self.assertEqual(updated_report['by_source']['Referral']['invoiced_value'], quote['total_price'])
                self.assertEqual(client.get(f"/api/quotes/{quote['id']}/pdf", headers=auth).status_code, 200)
                self.assertEqual(client.get(f"/api/invoices/{invoice['id']}/pdf", headers=auth).status_code, 200)

    def test_legacy_quotes_remain_unclassified_and_counts_survive_migration(self):
        from business import db
        from unittest.mock import patch
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory() as directory, patch.object(db, 'DB_PATH', Path(directory) / 'legacy.db'):
            legacy = sqlite3.connect(db.DB_PATH)
            legacy.execute("""CREATE TABLE quotes (id INTEGER PRIMARY KEY, customer_id INTEGER,
                customer_name TEXT, job TEXT, total_price REAL, gross_profit REAL, margin_percent REAL,
                created_at TEXT NOT NULL, created_at_sort TEXT NOT NULL,
                request_json TEXT NOT NULL, result_json TEXT NOT NULL)""")
            legacy.execute("""CREATE TABLE leads (id INTEGER PRIMARY KEY, name TEXT, phone TEXT,
                email TEXT, address TEXT, job_type TEXT, description TEXT, status TEXT NOT NULL,
                source TEXT, created_at TEXT NOT NULL, created_at_sort TEXT NOT NULL,
                updated_at TEXT NOT NULL)""")
            legacy.execute("INSERT INTO quotes (customer_name, created_at, created_at_sort, request_json, result_json) VALUES ('Legacy', 'old', 'old', '{}', '{}')")
            legacy.execute("INSERT INTO leads (name, status, created_at, created_at_sort, updated_at) VALUES ('Legacy lead', 'new', 'old', 'old', 'old')")
            legacy.commit()
            legacy.close()
            db.init_db()
            before = db.database_counts()
            self.assertEqual((before['quotes'], before['leads']), (1, 1))
            db.init_db()
            db.init_db()
            self.assertEqual(before, db.database_counts())
            conn = db.get_db()
            row = conn.execute('SELECT status, lead_id, next_follow_up FROM quotes').fetchone()
            self.assertEqual(row['status'], 'unclassified')
            self.assertIsNone(row['lead_id'])
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            conn.close()

    def test_public_drain_urls_redirect_to_relevant_existing_pages(self):
        with disposable_app(secrets.token_urlsafe(12), secrets.token_urlsafe(16)) as (module, auth):
            with TestClient(module.app) as client:
                xml = ElementTree.fromstring(client.get('/sitemap.xml').text)
                paths = [urlsplit(el.text).path for el in xml.iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
                self.assertEqual(len(paths), 72)
                self.assertFalse(any('blocked-drains' in path for path in paths))
                for town in ('guildford', 'camberley', 'epsom'):
                    response = client.get('/blocked-drains-' + town, follow_redirects=False)
                    self.assertEqual((response.status_code, response.headers['location']),
                                     (301, '/plumber-' + town))
                    self.assertEqual(client.get(response.headers['location']).status_code, 200)
                self.assertNotIn('blocked drains', client.get('/toilet-repair-guildford').text.lower())
                self.assertNotIn('blocked toilets', client.get('/toilet-repair-guildford').text.lower())


if __name__ == '__main__':
    unittest.main()

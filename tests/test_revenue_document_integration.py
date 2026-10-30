"""Current secure customer links and revenue writes on disposable SQLite only."""
import os
import unittest
import uuid
from unittest.mock import patch
from fastapi.testclient import TestClient
import test_document_links as document_tests


class RevenueDocumentIntegration(unittest.TestCase):
    def test_both_migration_orders_preserve_links_and_new_tracked_documents(self):
        helper = document_tests.DocumentLinkTests()
        for mode in ('prepare', 'secure'):
            for order in ('links_first', 'revenue_first'):
                with self.subTest(mode=mode, order=order):
                    initial_mode = mode if order == 'links_first' else 'legacy'
                    with helper.fixture(initial_mode) as (m, root), TestClient(m.app) as client:
                        from business.schema_migrations import migrate, connect, inventory, hashes
                        quote, invoice = helper.documents(m, client)
                        with patch.dict(os.environ, {'CUSTOMER_DOCUMENT_LINK_MODE': mode}):
                            if order == 'links_first':
                                # A revoked link must stay revoked, including after restart.
                                self.assertEqual(client.delete(f"/api/document-links/quote/{quote['id']}", headers=helper.auth()).status_code, 200)
                            with connect(root/'quotes.db') as conn:
                                before=inventory(conn); old=hashes(conn,before)
                            self.assertTrue(migrate(root/'quotes.db')['dry_run'])
                            migrate(root/'quotes.db', apply=True)
                            with connect(root/'quotes.db') as conn:
                                self.assertEqual(hashes(conn,before),old)
                            m.init_db()  # revenue-first then links, or restart of links-first
                            self.assertTrue(migrate(root/'quotes.db',apply=True)['already_applied'])
                            if order == 'links_first':
                                self.assertEqual(m.get_quote_by_id(quote['id'])['share_pdf_path'],'')
                                self.assertEqual(m.get_invoice_by_id(invoice['id'])['share_path'],invoice['share_path'])
                            # Both normal and staged invoices must issue a usable token in
                            # the transaction; retrying creation must retain that same token.
                            new_quote, normal = helper.documents(m,client,'New Fictional Customer')
                            self.assertTrue(new_quote['share_pdf_path'].startswith('/share/quote/'))
                            self.assertTrue(normal['share_path'].startswith('/share/invoice/'))
                            retry=client.post(f"/api/quotes/{new_quote['id']}/to-invoice",headers=helper.auth()).json()
                            self.assertEqual(retry['share_path'],normal['share_path'])
                            data={'operation_key':str(uuid.uuid4())}
                            staged=client.post(f"/api/revenue/quotes/{new_quote['id']}/stage-invoice",json=data,headers=helper.auth())
                            self.assertEqual(staged.status_code,200,staged.text)
                            staged=staged.json()
                            self.assertNotEqual(staged['share_path'],normal['share_path'])
                            self.assertEqual(client.post(f"/api/revenue/quotes/{new_quote['id']}/stage-invoice",json=data,headers=helper.auth()).json()['share_path'],staged['share_path'])
                            for item in (normal,staged):
                                response=client.get(item['share_path'])
                                self.assertEqual(response.status_code,200)
                                self.assertEqual(response.headers['cache-control'],'no-store')
                                self.assertEqual(response.headers['referrer-policy'],'no-referrer')
                                self.assertEqual(client.get(item['share_path']+'/pdf').status_code,200)
                                self.assertEqual(client.get(f"/invoice/{item['id']}").status_code,401 if mode=='secure' else 200)
                            self.assertEqual(client.get(new_quote['share_pdf_path']).status_code,200)
                            # Rotation/revocation still works for tracking-created documents.
                            endpoint=f"/api/document-links/invoice/{staged['id']}"
                            rotated=client.post(endpoint,headers=helper.auth()).json()['path']
                            self.assertEqual(client.get(staged['share_path']).status_code,404)
                            self.assertEqual(client.get(rotated).status_code,200)
                            client.delete(endpoint,headers=helper.auth())
                            m.init_db()
                            self.assertEqual(client.get(rotated).status_code,404)
                            with connect(root/'quotes.db') as conn:
                                self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                                self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(),[])

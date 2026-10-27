"""Completion gates: aggregate privacy, distinct enquiries and explicit revisions."""
import csv
import io
import sqlite3
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import test_revenue_tracking as helpers


class RevenueCompletionTests(unittest.TestCase):
    setUp=helpers.RevenueTests.setUp
    activate=helpers.RevenueTests.activate
    post=helpers.RevenueTests.post
    get=helpers.RevenueTests.get
    lead=helpers.RevenueTests.lead
    quote=helpers.RevenueTests.quote
    invoice=helpers.RevenueTests.invoice
    payment=helpers.RevenueTests.payment
    report=helpers.RevenueTests.report
    correction=helpers.RevenueTests.correction

    def outcome(self, quote, status):
        return self.post(f"/api/revenue/workflow/quote/{quote['id']}",
                         {'status':status,'reason':'Local decision fixture','operation_key':self.key()})

    def revision(self, current, previous, code=200, **extra):
        return self.post(f"/api/revenue/quotes/{current['id']}/revision",
            {'supersedes_quote_id':previous['id'],'confirmed_same_scope':True,
             'reason':'Owner checked same work; replacement version','operation_key':self.key(),**extra},code)

    def test_export_is_private_aggregate_only_and_reconciles(self):
        self.activate();l=self.lead();q=self.quote(l,customer_name='PRIVATE-NAME-SENTINEL',
            customer_address='PRIVATE-ADDRESS-SENTINEL',job_description='PRIVATE-JOB-SENTINEL')
        i=self.invoice(q);self.payment(i,reference='PRIVATE-PAYMENT-SENTINEL')
        url='/api/revenue/export?start=2020-01-01&end='+self.today
        self.assertEqual(self.client.get(url).status_code,401)
        r=self.client.get(url,auth=self.auth)
        self.assertEqual(r.status_code,200);self.assertEqual(r.headers['cache-control'],'private, no-store')
        self.assertIn('noindex',r.headers['x-robots-tag']);self.assertIn('attachment',r.headers['content-disposition'])
        self.assertIn('text/csv',r.headers['content-type'])
        rows=list(csv.DictReader(io.StringIO(r.text)));self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['source'],'Unknown');self.assertEqual(int(rows[0]['cash_pence']),3000)
        from business.revenue_reporting import EXPORT_COLUMNS
        self.assertEqual(set(rows[0]),{'source','period_start','period_end','as_of','currency',*EXPORT_COLUMNS})
        for marker in ['PRIVATE-','07700900000','Synthetic development','customer','reference','description','quote_id','origin_id']:
            self.assertNotIn(marker,r.text)
        self.assertEqual(sum(int(row['outstanding_pence']) for row in rows),self.report()['totals']['outstanding_pence'])

    def test_export_requires_activation_valid_dates_and_controlled_source(self):
        url='/api/revenue/export?start=2020-01-01&end='+self.today
        self.assertEqual(self.client.get(url,auth=self.auth).status_code,409)
        self.activate()
        self.assertEqual(self.client.get('/api/revenue/export?start=bad&end='+self.today,auth=self.auth).status_code,409)
        from business.revenue_reporting import export_csv
        with self.assertRaises(ValueError):export_csv({'by_source':{'=HYPERLINK(private)':{}},'start':self.today,'end':self.today,'as_of':self.today})
        rows=list(csv.DictReader(io.StringIO(self.client.get(url,auth=self.auth).text)))
        self.assertEqual(rows,[])

    def test_enquiry_rate_distinct_from_quote_rate_and_mixed_decisions(self):
        self.activate();a=self.lead();b=self.lead();pending=self.lead()
        for status in ['won','won','lost']:self.outcome(self.quote(a),status)
        for status in ['lost','pending']:self.outcome(self.quote(b),status)
        self.quote(pending)
        row=self.report()['by_source']['Unknown']
        self.assertEqual((row['won_quotes'],row['lost_quotes'],row['quote_win_percent']),(2,2,50.0))
        self.assertEqual((row['won_enquiries'],row['lost_enquiries'],row['decided_enquiries'],row['enquiry_win_percent']),(1,1,2,50.0))
        self.outcome(self.quote(a),'won')
        row=self.report()['by_source']['Unknown']
        self.assertEqual(row['quote_win_percent'],60.0);self.assertEqual(row['enquiry_win_percent'],50.0)
        self.assertEqual(row['enquiries'],3)

    def test_enquiry_rate_excludes_synthetic_standalone_and_undecided(self):
        self.activate();l=self.lead();self.outcome(self.quote(l),'expired')
        self.outcome(self.quote(),'won')
        synthetic=self.lead(kind='synthetic',test_reference='LOCAL-COMPLETION')
        self.outcome(self.quote(synthetic),'won')
        data=self.report();row=data['by_source']['Unknown']
        self.assertEqual(row['enquiries'],1);self.assertEqual(row['decided_enquiries'],0)
        self.assertIsNone(row['enquiry_win_percent']);self.assertEqual(row['quote_win_percent'],100)
        self.assertEqual(data['synthetic_origins_excluded'],1)
        self.correction(l,source='Referral');self.assertIn('Referral',self.report()['by_source'])

    def test_revision_requires_explicit_confirmation_reason_auth_and_same_origin(self):
        self.activate();l=self.lead();a=self.quote(l);b=self.quote(l)
        self.revision(b,a,409,confirmed_same_scope=False)
        self.revision(b,a,422,confirmed_same_scope='true')
        self.revision(b,a,409,reason='   ')
        url=f"/api/revenue/quotes/{b['id']}/revision"
        payload={'supersedes_quote_id':a['id'],'confirmed_same_scope':True,'reason':'Same work','operation_key':self.key()}
        self.assertEqual(self.client.post(url,json=payload).status_code,401)
        self.assertEqual(self.client.post(url,json=payload,auth=self.auth,headers={'Origin':'https://evil.invalid'}).status_code,403)
        self.assertEqual(self.get(f"/api/revenue/workflow/quote/{b['id']}")['history'],[])

    def test_revision_history_is_append_only_and_retry_safe(self):
        self.activate();l=self.lead();a=self.quote(l);b=self.quote(l);key=self.key()
        first=self.revision(b,a,operation_key=key);retry=self.revision(b,a,operation_key=key)
        self.assertFalse(first['already_recorded']);self.assertTrue(retry['already_recorded'])
        self.revision(b,a,409,operation_key=key,reason='Changed request')
        history=self.get(f"/api/revenue/workflow/quote/{b['id']}")['history']
        self.assertEqual(len(history),1);event=history[0]
        self.assertEqual(event['event_kind'],'quote_revision');self.assertEqual(event['to_status'],str(a['id']))
        self.assertEqual(event['actor'],'revenue-owner');self.assertTrue(event['recorded_at']);self.assertTrue(event['reason'])
        with self.migration.connect(self.root/'quotes.db') as conn:
            with self.assertRaises(sqlite3.IntegrityError):conn.execute('DELETE FROM workflow_events')

    def test_revision_rejects_loops_branches_cross_enquiries_and_reassignment(self):
        self.activate();l=self.lead();a=self.quote(l);b=self.quote(l);c=self.quote(l);other=self.quote(self.lead())
        self.revision(a,a,409);self.revision(a,b,409);self.revision(other,a,409)
        self.revision(b,a);self.revision(c,a,409);self.revision(c,b)
        self.revision(b,c,409);self.revision(c,a,409)
        row=self.report()['by_source']['Unknown'];self.assertEqual(row['quotes'],2)

    def test_revision_rejects_separate_jobs_without_inference(self):
        self.activate();l=self.lead();a=self.quote(l);b=self.quote(l)
        for q in [a,b]:self.post('/api/jobs',{'quote_id':q['id'],'title':'Independent synthetic scope','operation_key':self.key()})
        self.revision(b,a,409)
        self.assertEqual(self.report()['by_source']['Unknown']['quotes'],2)

    def test_revision_rejects_retroactive_links_and_corrupt_ancestry(self):
        self.activate();l=self.lead();a=self.quote(l);b=self.quote(l);c=self.quote(l)
        self.revision(c,b)
        # No automatic merging of independent scope, and no retroactive mutation
        # of an already replaced quote's chain.
        self.revision(b,a,409)
        other=self.quote(self.lead());newest=self.quote(l)
        with self.migration.connect(self.root/'quotes.db') as conn:
            conn.execute('UPDATE quotes SET supersedes_quote_id=? WHERE id=?',(other['id'],c['id']));conn.commit()
        self.revision(newest,c,409)
        with self.migration.connect(self.root/'quotes.db') as conn:
            conn.execute('UPDATE quotes SET supersedes_quote_id=? WHERE id=?',(c['id'],c['id']));conn.commit()
        self.revision(newest,c,409)

    def test_revision_concurrency_and_transaction_rollback(self):
        self.activate();l=self.lead();a=self.quote(l);b=self.quote(l);key=self.key()
        with patch('business.quote_revisions.events',side_effect=ValueError('Injected after writes')):
            self.revision(b,a,409,operation_key=key)
        with self.migration.connect(self.root/'quotes.db') as conn:
            self.assertIsNone(conn.execute('SELECT supersedes_quote_id FROM quotes WHERE id=?',(b['id'],)).fetchone()[0])
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM workflow_events').fetchone()[0],0)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:self.revision(b,a,operation_key=key),range(4)))
        self.assertEqual(sum(not x['already_recorded'] for x in results),1)

    def test_revision_restates_decisions_without_changing_money_and_migration_reruns(self):
        self.activate();l=self.lead();a=self.quote(l);b=self.quote(l)
        self.outcome(a,'won');self.outcome(b,'lost');i=self.invoice(a);self.payment(i)
        before=self.get(f"/api/revenue/invoices/{i['id']}/payments")
        self.assertEqual(self.report()['by_source']['Unknown']['enquiry_win_percent'],100)
        self.revision(b,a)
        self.assertEqual(self.report()['by_source']['Unknown']['enquiry_win_percent'],0)
        self.assertEqual(self.get(f"/api/revenue/invoices/{i['id']}/payments"),before)
        self.assertTrue(self.activate()['already_applied'])
        self.assertEqual(len(self.get(f"/api/revenue/workflow/quote/{b['id']}")['history']),2)


if __name__=='__main__':unittest.main()

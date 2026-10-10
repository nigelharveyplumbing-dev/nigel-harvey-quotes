"""Synthetic, isolated attribution/ledger/migration regressions. Outbound I/O denied."""
import json
import sqlite3
import unittest
import uuid
from datetime import datetime
from pathlib import Path
from fastapi.testclient import TestClient
from local_browser_server import disposable_app

class RevenueTests(unittest.TestCase):
    def setUp(self):
        self.context=disposable_app('revenue-owner','local-test-only')
        self.m,self.root=self.context.__enter__()
        self.addCleanup(self.context.__exit__,None,None,None)
        self.client=TestClient(self.m.app)
        self.auth=('revenue-owner','local-test-only')
        from business import schema_migrations, enquiry_attribution, payment_store
        self.migration,self.attribution,self.payments=schema_migrations,enquiry_attribution,payment_store
        self.key=lambda:str(uuid.uuid4())
        self.today=datetime.now(self.m.ZoneInfo('Europe/London')).date().isoformat() if hasattr(self.m,'ZoneInfo') else datetime.now().date().isoformat()
    def activate(self):
        return self.migration.migrate(self.root/'quotes.db',apply=True)
    def post(self,path,data,code=200):
        r=self.client.post(path,json=data,auth=self.auth);self.assertEqual(r.status_code,code,r.text[:400]);return r.json()
    def get(self,path):
        r=self.client.get(path,auth=self.auth);self.assertEqual(r.status_code,200,r.text[:300]);return r.json()
    def lead(self,source='',channel='Phone',kind='genuine',test_reference='',key=None,customer_id=None):
        return self.post('/api/quick-add/confirm',{'idempotency_key':key or self.key(),'name':'Synthetic development','phone':'07700900000','description':'Synthetic local radiator repair','source_category':source,'contact_channel':channel,'record_kind':kind,'test_reference':test_reference,'customer_id':customer_id})['lead']
    def quote(self,lead=None,key=None,**extra):
        return self.post('/api/quote',{'quote_type':'small','customer_name':'Synthetic development','customer_phone':'07700900000','job_description':'Local synthetic radiator repair','labour_cost':100,'lead_id':lead['id'] if lead else None,'submission_key':key or self.key(),**extra})
    def invoice(self,quote):
        return self.post('/api/quotes/'+str(quote['id'])+'/to-invoice',{})
    def payment(self,i,amount='30.00',action='receipt',key=None,**extra):
        return self.post(f"/api/revenue/invoices/{i['id']}/payments",{'action':action,'amount':amount,'received_on':self.today,'method':'Bank transfer','operation_key':key or self.key(),**extra})
    def correction(self,lead,source='Referral',kind='genuine',revision=0,**extra):
        return self.post(f"/api/revenue/origins/{lead['origin_id']}/corrections",{'source':source,'kind':kind,'reason':'Owner confirmed original enquiry evidence','expected_revision':revision,**extra})
    def report(self):
        return self.get('/api/revenue/report?start=2020-01-01&end='+self.today)
    def test_activation_is_explicit_and_private(self):
        self.assertFalse(self.get('/api/revenue/options')['active'])
        self.m.init_db();self.assertFalse(self.get('/api/revenue/options')['active'])
        self.assertEqual(self.client.get('/api/revenue/options').status_code,401)
        self.assertEqual(self.client.get('/api/revenue/report?start=2026-01-01&end=2026-01-02',auth=self.auth).status_code,409)
        self.activate()
        r=self.client.get('/app',auth=self.auth)
        self.assertIn('noindex',r.headers['x-robots-tag']);self.assertEqual(r.headers['cache-control'],'private, no-store')
        for path in ['/api/revenue/review','/api/revenue/origins/1','/api/revenue/invoices/1/payments','/api/revenue/workflow/quote/1']:
            self.assertEqual(self.client.get(path).status_code,401)
        self.assertNotIn('/api/revenue',self.client.get('/sitemap.xml').text)
        self.assertNotIn('revenueTab',self.client.get('/').text)
    def test_migration_preserves_legacy_records_and_reruns(self):
        q=self.quote();i=self.invoice(q)
        self.m.update_invoice_status(i['id'],'part paid',35)
        with self.migration.connect(self.root/'quotes.db') as c:
            before=self.migration.inventory(c); hashes=self.migration.hashes(c,before)
        dry=self.migration.migrate(self.root/'quotes.db');self.assertTrue(dry['dry_run'])
        result=self.activate();self.assertTrue(result['legacy_fields_unchanged'])
        self.assertTrue(self.activate()['already_applied'])
        with self.migration.connect(self.root/'quotes.db') as c:
            self.assertEqual(hashes,self.migration.hashes(c,before))
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
        ledger=self.get(f"/api/revenue/invoices/{i['id']}/payments")
        self.assertEqual(ledger['undated_balance_pence'],3500);self.assertIsNone(ledger['entries'][0]['received_on'])
        report=self.report();self.assertEqual(report['totals']['cash_pence'],0);self.assertEqual(report['totals']['legacy_undated_pence'],3500)
    def test_migration_atomic_rollback(self):
        self.quote()
        with self.migration.connect(self.root/'quotes.db') as c:
            before=self.migration.inventory(c); hashes=self.migration.hashes(c,before)
        with self.assertRaises(RuntimeError):self.migration.migrate(self.root/'quotes.db',apply=True,fail_after=1)
        with self.migration.connect(self.root/'quotes.db') as c:
            self.assertEqual(before,self.migration.inventory(c));self.assertEqual(hashes,self.migration.hashes(c,before))
        self.activate()
    def test_unknown_and_source_inheritance_reopen_edit(self):
        self.activate();l=self.lead();q=self.quote(l);i=self.invoice(q)
        o=self.get(f"/api/revenue/origins/{l['origin_id']}");self.assertEqual(o['source'],'Unknown');self.assertEqual(o['contact_channel'],'Phone')
        self.assertEqual(q['origin_id'],l['origin_id']);self.assertEqual(i['origin_id'],l['origin_id'])
        self.correction(l)
        self.post(f"/api/revenue/workflow/quote/{q['id']}",{'status':'won','operation_key':self.key()})
        self.post(f"/api/revenue/workflow/quote/{q['id']}",{'status':'pending','reason':'Customer asked for revision','operation_key':self.key()})
        payload={**q['request'],'labour_cost':120,'source_category':'Website/direct'}
        edited=self.client.put(f"/api/quotes/{q['id']}",json=payload,auth=self.auth)
        self.assertEqual(edited.status_code,200,edited.text)
        self.assertEqual(edited.json()['source_category'],'Referral');self.assertEqual(edited.json()['origin_id'],q['origin_id']);self.assertEqual(edited.json()['created_at'],q['created_at'])
        self.assertEqual(self.get(f"/api/revenue/origins/{l['origin_id']}")['source'],'Referral')
    def test_corrections_append_and_conflict(self):
        self.activate();l=self.lead();o=self.correction(l)
        self.assertEqual(o['captured_source'],'Unknown');self.assertEqual(o['revision'],1)
        self.assertEqual(len(o['history']),1)
        self.post(f"/api/revenue/origins/{l['origin_id']}/corrections",{'source':'Bing','kind':'genuine','reason':'Stale edit','expected_revision':0},409)
        with self.migration.connect(self.root/'quotes.db') as c:
            with self.assertRaises(sqlite3.IntegrityError):c.execute('UPDATE enquiry_origins SET captured_source=?',('Bing',))
        self.post(f"/api/revenue/origins/{l['origin_id']}/interactions",{'channel':'WhatsApp','note':'Later conversation'})
        o=self.get(f"/api/revenue/origins/{l['origin_id']}");self.assertEqual(o['source'],'Referral');self.assertEqual(o['interactions'][0]['channel'],'WhatsApp')
    def test_synthetic_excluded_and_reference_required(self):
        self.activate();l=self.lead('Google organic search',kind='synthetic',test_reference='LOCAL-SYNTHETIC-1');q=self.quote(l);i=self.invoice(q);self.payment(i)
        report=self.report();self.assertEqual(report['synthetic_origins_excluded'],1);self.assertEqual(report['totals'],{})
        l2=self.lead();self.post(f"/api/revenue/origins/{l2['origin_id']}/corrections",{'source':'Unknown','kind':'synthetic','reason':'Local test','expected_revision':0},409)
        self.correction(l2,source='Unknown',kind='synthetic',test_reference='LOCAL-SYNTHETIC-2')
    def test_no_automatic_customer_matching_and_returning_enquiries(self):
        self.activate();l1=self.lead('Referral');q1=self.quote(l1);l2=self.lead('Google organic search');q2=self.quote(l2)
        self.assertNotEqual(q1['customer_id'],q2['customer_id']);self.assertNotEqual(q1['origin_id'],q2['origin_id'])
        l3=self.lead('Repeat customer',customer_id=q1['customer_id']);q3=self.quote(l3)
        self.assertEqual(q3['customer_id'],q1['customer_id']);self.assertNotEqual(q3['origin_id'],q1['origin_id'])
    def test_duplicate_manual_website_quote_invoice_and_payments(self):
        self.activate();key=self.key();l=self.lead(key=key);self.assertEqual(l['id'],self.lead(key=key)['id'])
        self.post('/api/quick-add/confirm',{'idempotency_key':key,'name':'Different synthetic','description':'Changed'},422)
        key=self.key();q=self.quote(l,key=key);self.assertEqual(self.quote(l,key=key)['id'],q['id'])
        i=self.invoice(q);self.assertEqual(self.invoice(q)['id'],i['id'])
        key=self.key();self.payment(i,key=key);self.assertTrue(self.payment(i,key=key)['already_recorded'])
        with self.migration.connect(self.root/'quotes.db') as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM invoice_payments').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM quote_intelligence WHERE quote_id=?',(q['id'],)).fetchone()[0],1)
        self.post(f"/api/revenue/invoices/{i['id']}/payments",{'amount':'40','received_on':self.today,'operation_key':key},409)
        payload={'name':'Synthetic web','phone':'07700900000','description':'No response required','submission_key':self.key(),'analytics_consent':True,'utm_source':'google','utm_medium':'organic','landing_page':'/plumber-guildford'}
        a=self.client.post('/api/leads',json=payload);b=self.client.post('/api/leads',json=payload)
        self.assertEqual(a.status_code,200,a.text);self.assertEqual(a.json()['id'],b.json()['id'])
        with self.migration.connect(self.root/'quotes.db') as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM lead_email_notifications WHERE lead_id=?',(a.json()['id'],)).fetchone()[0],1)
    def test_consent_minimises_data_and_context_sanitises(self):
        self.activate()
        payload={'name':'Synthetic','phone':'07700900000','description':'Local test','utm_source':'google','utm_medium':'organic','landing_page':'/plumber-woking?email=private@example.invalid','referrer':'https://google.com/search?q=private','analytics_consent':False,'source_category':'Referral'}
        l=self.client.post('/api/leads',json=payload).json();o=self.get(f"/api/revenue/origins/{l['origin_id']}")
        self.assertEqual(o['source'],'Website/direct');self.assertEqual(o['evidence'],{'landing_page':'/plumber-woking'})
        payload.update(analytics_consent=True,utm_source='person@example.invalid',utm_campaign='07700900000')
        l=self.client.post('/api/leads',json=payload).json();o=self.get(f"/api/revenue/origins/{l['origin_id']}")
        self.assertNotIn('utm_source',o['evidence']);self.assertNotIn('utm_campaign',o['evidence']);self.assertEqual(o['evidence']['referrer'],'https://google.com')
    def test_partial_full_refund_reversal_correction(self):
        self.activate();i=self.invoice(self.quote(self.lead('Referral')))
        first=self.payment(i);self.assertEqual(first['invoice']['status'],'part paid');self.assertEqual(first['invoice']['balance_due'],70)
        full=self.payment(i,'70');self.assertEqual(full['invoice']['status'],'paid')
        refund=self.payment(i,'15',action='refund',reason='Owner refunded test amount');self.assertEqual(refund['invoice']['amount_paid'],85)
        reversed=self.payment(i,action='reversal',related_entry_id=refund['entries'][-1]['id'],reason='Refund entry was erroneous');self.assertEqual(reversed['invoice']['amount_paid'],100)
        corrected=self.payment(i,'20',action='correction',related_entry_id=first['entries'][0]['id'],reason='Correct receipt amount');self.assertEqual(corrected['invoice']['amount_paid'],90)
        self.assertEqual(self.report()['totals']['cash_pence'],9000)
        self.post(f"/api/revenue/invoices/{i['id']}/payments",{'action':'reversal','related_entry_id':first['entries'][0]['id'],'reason':'Already corrected','operation_key':self.key()},409)
    def test_overpayment_retained_and_invalid_payments_atomic(self):
        self.activate();i=self.invoice(self.quote(self.lead()))
        for payload in [{'amount':'NaN'},{'amount':'1.234'},{'amount':'0'},{'amount':'1','received_on':'2999-01-01'},{'action':'refund','amount':'101','reason':'Exceeds received'}]:
            self.post(f"/api/revenue/invoices/{i['id']}/payments",{'received_on':self.today,'operation_key':self.key(),**payload},409)
        self.assertEqual(self.get(f"/api/revenue/invoices/{i['id']}/payments")['entries'],[])
        paid=self.payment(i,'120');self.assertEqual(paid['invoice']['amount_paid'],120);self.assertEqual(paid['overpayment_credit_pence'],2000)
        r=self.client.post(f"/api/invoices/{i['id']}/status",json={'status':'paid','amount_paid':100},auth=self.auth);self.assertEqual(r.status_code,409,r.text)
    def test_legacy_date_requires_owner_correction(self):
        q=self.quote();i=self.invoice(q);self.m.update_invoice_status(i['id'],'part paid',40);self.activate()
        old=self.get(f"/api/revenue/invoices/{i['id']}/payments")['entries'][0]
        fixed=self.payment(i,'40',action='correction',related_entry_id=old['id'],reason='Genuine dated bank receipt reviewed')
        self.assertEqual(fixed['invoice']['amount_paid'],40);self.assertEqual(fixed['undated_balance_pence'],0);self.assertEqual(self.report()['totals']['cash_pence'],4000)
    def test_multiple_quotes_invoices_jobs_and_milestones(self):
        self.activate();l=self.lead('Referral');q=self.quote(l);q2=self.quote(l)
        self.post(f"/api/revenue/quotes/{q2['id']}/revision",{'supersedes_quote_id':q['id']})
        key=self.key();self.post(f"/api/revenue/workflow/quote/{q2['id']}",{'status':'won','operation_key':key});self.post(f"/api/revenue/workflow/quote/{q2['id']}",{'status':'won','operation_key':key})
        job=self.post('/api/jobs',{'quote_id':q2['id'],'lead_id':l['id'],'title':'Synthetic local job'})
        self.post(f"/api/revenue/workflow/job/{job['id']}",{'status':'accepted','operation_key':self.key()})
        self.post(f"/api/revenue/workflow/job/{job['id']}",{'status':'completed','operation_key':self.key()})
        first=self.invoice(q2);second=self.post(f"/api/revenue/quotes/{q2['id']}/stage-invoice",{'job_id':job['id'],'operation_key':self.key()})
        self.assertNotEqual(first['invoice_number'],second['invoice_number']);self.assertEqual(second['origin_id'],l['origin_id']);self.assertEqual(second['job_id'],job['id'])
        self.payment(first,'30');self.payment(second,'20')
        totals=self.report()['totals'];self.assertEqual(totals['enquiries'],1);self.assertEqual(totals['quoted_enquiries'],1);self.assertEqual(totals['accepted_enquiries'],1);self.assertEqual(totals['completed_enquiries'],1);self.assertEqual(totals['won_quotes'],1);self.assertEqual(totals['cash_pence'],5000);self.assertEqual(totals['outstanding_pence'],15000)
    def test_conflicting_origin_links_rejected(self):
        self.activate();l1=self.lead();l2=self.lead();q=self.quote(l1)
        self.post('/api/jobs',{'quote_id':q['id'],'lead_id':l2['id'],'title':'Invalid origin link'},422)
        job=self.post('/api/jobs',{'quote_id':q['id'],'title':'Synthetic job'})
        r=self.client.put(f"/api/jobs/{job['id']}",json={'lead_id':l2['id'],'title':'Different enquiry'},auth=self.auth);self.assertEqual(r.status_code,422,r.text)
    def test_paid_ledger_protected_from_previous_version_writes(self):
        self.activate();i=self.invoice(self.quote(self.lead()));self.payment(i)
        with self.migration.connect(self.root/'quotes.db') as c:
            with self.assertRaises(sqlite3.IntegrityError):c.execute('UPDATE invoices SET amount_paid=99 WHERE id=?',(i['id'],))
            with self.assertRaises(sqlite3.IntegrityError):c.execute('DELETE FROM invoice_payments')
            # Existing readers retain the exact compatibility projection.
            self.assertEqual(c.execute('SELECT amount_paid,balance_due FROM invoices WHERE id=?',(i['id'],)).fetchone()[0],30)
        self.assertEqual(self.client.delete(f"/api/invoices/{i['id']}",auth=self.auth).status_code,409)
        self.assertEqual(self.client.get(f"/api/invoices/{i['id']}/pdf",auth=self.auth).status_code,200)
        self.assertEqual(self.client.get(f"/api/quotes/{i['quote_id']}/pdf",auth=self.auth).status_code,200)
        self.assertEqual(self.client.get('/api/lead-email-status',auth=self.auth).status_code,200)

if __name__=='__main__':unittest.main()

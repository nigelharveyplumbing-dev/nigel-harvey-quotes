"""Migration preflight, frozen-write rollback and previous-release compatibility."""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import unittest
import test_revenue_tracking as helpers

# Reuse helpers without duplicating the inherited 15 regression test methods.
class RevenueSafetyTests(unittest.TestCase):
    setUp=helpers.RevenueTests.setUp
    activate=helpers.RevenueTests.activate
    post=helpers.RevenueTests.post
    get=helpers.RevenueTests.get
    lead=helpers.RevenueTests.lead
    quote=helpers.RevenueTests.quote
    invoice=helpers.RevenueTests.invoice
    payment=helpers.RevenueTests.payment
    def test_dangling_references_stop_before_ddl(self):
        q=self.quote()
        with self.migration.connect(self.root/'quotes.db') as c:
            c.execute('UPDATE quotes SET lead_id=999 WHERE id=?',(q['id'],));c.commit();before=self.migration.inventory(c)
        with self.assertRaisesRegex(ValueError,'dangling historical'):self.activate()
        with self.migration.connect(self.root/'quotes.db') as c:self.assertEqual(before,self.migration.inventory(c))
    def test_paid_flag_is_not_a_receipt(self):
        i=self.invoice(self.quote())
        with self.migration.connect(self.root/'quotes.db') as c:c.execute("UPDATE invoices SET status='paid' WHERE id=?",(i['id'],));c.commit()
        self.activate();data=self.get(f"/api/revenue/invoices/{i['id']}/payments")
        self.assertEqual(data['entries'],[]);self.assertEqual(data['invoice']['amount_paid'],0)
    def test_concurrent_payment_retries_record_exactly_once(self):
        self.activate();i=self.invoice(self.quote(self.lead()));key=self.key()
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:self.payment(i,'10',key=key),range(8)))
        self.assertEqual(sum(not x['already_recorded'] for x in results),1)
        self.assertEqual(self.get(f"/api/revenue/invoices/{i['id']}/payments")['invoice']['amount_paid'],10)
    def test_job_retries_and_contact_channel_correction(self):
        self.activate();l=self.lead();q=self.quote(l);key=self.key()
        payload={'quote_id':q['id'],'title':'Synthetic job','operation_key':key}
        a=self.post('/api/jobs',payload);b=self.post('/api/jobs',payload);self.assertEqual(a['id'],b['id'])
        c=self.post(f"/api/revenue/origins/{l['origin_id']}/corrections",{'source':'Referral','channel':'WhatsApp','kind':'genuine','reason':'Owner confirmed first contact channel','expected_revision':0})
        self.assertEqual(c['captured_channel'],'Phone');self.assertEqual(c['contact_channel'],'WhatsApp');self.assertEqual(c['history'][0]['old_channel'],'Phone')
    def test_post_migration_restore_with_frozen_writes_and_sidecar(self):
        self.quote();primary=self.root/'quotes.db';checkpoint=self.root/'primary-checkpoint.db'
        with sqlite3.connect(primary) as src,sqlite3.connect(checkpoint) as dst:src.backup(dst)
        side=self.root/'local-city.db';backup=self.root/'city-checkpoint.db'
        with sqlite3.connect(side) as c:c.execute('CREATE TABLE synthetic_price(sku TEXT,price_pence INTEGER)');c.execute("INSERT INTO synthetic_price VALUES ('123456',1200)");c.commit()
        with sqlite3.connect(side) as src,sqlite3.connect(backup) as dst:src.backup(dst)
        with self.migration.connect(primary) as c:before=self.migration.inventory(c);hashes=self.migration.hashes(c,before)
        self.activate();self.m.init_db() # Existing startup must not remigrate or change originals.
        with self.migration.connect(primary) as c:self.assertEqual(hashes,self.migration.hashes(c,before))
        # There have been no business writes since the checkpoint: paired rollback rehearsal.
        with sqlite3.connect(checkpoint) as src,sqlite3.connect(primary) as dst:src.backup(dst)
        with sqlite3.connect(backup) as src,sqlite3.connect(side) as dst:src.backup(dst)
        with self.migration.connect(primary) as c:self.assertEqual(before,self.migration.inventory(c));self.assertEqual(hashes,self.migration.hashes(c,before))
        with sqlite3.connect(side) as c:self.assertEqual(c.execute('SELECT * FROM synthetic_price').fetchall(),[('123456',1200)])
    def test_duplicate_reference_and_loss_reopen_history(self):
        self.activate();l=self.lead();q=self.quote(l);i=self.invoice(q)
        self.payment(i,reference='LOCAL-RECEIPT-REFERENCE')
        self.post(f"/api/revenue/invoices/{i['id']}/payments",{'amount':'30','received_on':self.today,'method':'Bank transfer','reference':'local-receipt-reference','operation_key':self.key()},409)
        self.post(f"/api/revenue/workflow/quote/{q['id']}",{'status':'lost','reason':'Customer postponed the work','operation_key':self.key()})
        self.post(f"/api/revenue/workflow/quote/{q['id']}",{'status':'pending','operation_key':self.key()},409)
        self.post(f"/api/revenue/workflow/quote/{q['id']}",{'status':'pending','reason':'Customer asked to reconsider','operation_key':self.key()})
        reloaded=self.get('/api/quotes/'+str(q['id']));self.assertEqual(reloaded['loss_reason'],'');self.assertEqual(reloaded['origin_id'],l['origin_id'])
        self.assertEqual(len(self.get(f"/api/revenue/workflow/quote/{q['id']}")['history']),2)

    def test_concurrent_quote_save_and_uncertain_search_source(self):
        self.activate();l=self.lead();key=self.key()
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(lambda _:self.quote(l,key=key),range(4)))
        self.assertEqual(len({x['id'] for x in results}),1)
        with self.migration.connect(self.root/'quotes.db') as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM quote_intelligence').fetchone()[0],1)
        for context,expected in [({'referrer':'https://google.com'},'Other'),({'referrer':'https://google.com','utm_medium':'organic'},'Unknown'),({'utm_source':'google','utm_medium':'cpc'},'Other')]:
            response=self.client.post('/api/leads',json={'name':'Synthetic source','phone':'07700900000','description':'Local only','analytics_consent':True,**context})
            self.assertEqual(response.status_code,200)
            source=self.get('/api/revenue/origins/'+str(response.json()['origin_id']))
            self.assertEqual(source['source'],expected)

    def test_previous_release_reads_and_paid_write_guard(self):
        q=self.quote();i=self.invoice(q);self.m.update_invoice_status(i['id'],'part paid',30);self.activate()
        repo=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='revenue-previous-release-') as folder:
            root=Path(folder);archive=root/'baseline.tar';old=root/'app';old.mkdir()
            subprocess.run(['git','archive','c4f57d379e3463fc414814b43ca0e81f8e5a68c7','-o',str(archive)],cwd=repo,check=True,timeout=15)
            with tarfile.open(archive) as tar:tar.extractall(old,filter='data')
            shutil.copy2(self.root/'quotes.db',old/'quotes.db')
            p=old/'business/config.py';s=p.read_text()
            for name,target in [('quotes.db','quotes.db'),('backups','backups'),('invoice_photos','photos')]:s=s.replace('Path("/var/data/'+name+'")',repr_path:=f'Path({str(old/target)!r})')
            self.assertNotIn('Path("/var/data/',s);p.write_text(s)
            probe=old/'compat_probe.py';probe.write_text('''import os,sqlite3
import sys
sys.path.insert(0,'tests')
from local_browser_server import block_external_connections
block_external_connections()
os.environ.update(APP_USERNAME='old-local',APP_PASSWORD='local-only',EMAIL_ENABLED='0',EMAIL_USER='',EMAIL_PASS='',OPENAI_API_KEY='',GOOGLE_PLACES_API_KEY='',PUBLIC_BASE_URL='',APP_ENVIRONMENT='')
import app
from fastapi.testclient import TestClient
with TestClient(app.app,raise_server_exceptions=False) as c:
 assert c.get('/app',auth=('old-local','local-only')).status_code==200
 assert c.get('/api/quotes',auth=('old-local','local-only')).status_code==200
 assert c.get('/api/invoices',auth=('old-local','local-only')).json()[0]['amount_paid']==30
 assert c.get('/api/invoices/1/pdf').status_code==200
 r=c.post('/api/invoices/1/status',auth=('old-local','local-only'),json={'status':'paid','amount_paid':100})
 assert r.status_code==500 # Old cumulative writer is deliberately incompatible and rejected.
with sqlite3.connect(app.DB_PATH) as db: assert db.execute('SELECT amount_paid FROM invoices WHERE id=1').fetchone()[0]==30
print('Previous release reads/PDF PASS; obsolete paid writer blocked without balance loss')
''')
            # The old release's test helper imports safely from its own checkout.
            result=subprocess.run([sys.executable,'-B',str(probe)],cwd=old,env={**os.environ,'PYTHONPATH':str(old)+os.pathsep+os.environ.get('PYTHONPATH','')},capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr[-1500:]);self.assertIn('without balance loss',result.stdout)

if __name__=='__main__':unittest.main()

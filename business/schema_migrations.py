"""Explicit additive migration. Never invoked by application startup."""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

from business.enquiry_attribution import create_origin, enabled, utc_now

VERSION = 1
DDL = (
'''CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)''',
'''CREATE TABLE enquiry_origins(id INTEGER PRIMARY KEY, lead_id INTEGER UNIQUE REFERENCES leads(id),
 captured_source TEXT NOT NULL, contact_channel TEXT NOT NULL, record_kind TEXT NOT NULL,
 evidence_json TEXT NOT NULL, method TEXT NOT NULL, confidence TEXT NOT NULL, captured_at TEXT NOT NULL,
 test_reference TEXT NOT NULL DEFAULT '')''',
'''CREATE TABLE origin_corrections(id INTEGER PRIMARY KEY, origin_id INTEGER NOT NULL REFERENCES enquiry_origins(id),
 revision INTEGER NOT NULL, old_source TEXT NOT NULL,new_source TEXT NOT NULL,old_kind TEXT NOT NULL,new_kind TEXT NOT NULL,
 reason TEXT NOT NULL,actor TEXT NOT NULL,recorded_at TEXT NOT NULL,new_test_reference TEXT NOT NULL DEFAULT '',old_channel TEXT NOT NULL,new_channel TEXT NOT NULL,UNIQUE(origin_id,revision))''',
'''CREATE TABLE invoice_payments(id INTEGER PRIMARY KEY,invoice_id INTEGER NOT NULL REFERENCES invoices(id),
 amount_pence INTEGER NOT NULL CHECK(amount_pence != 0),received_on TEXT,recorded_at TEXT NOT NULL,
 entry_type TEXT NOT NULL,method TEXT NOT NULL,reference TEXT NOT NULL DEFAULT '',reason TEXT NOT NULL DEFAULT '',
 related_entry_id INTEGER REFERENCES invoice_payments(id),actor TEXT NOT NULL,operation_key TEXT NOT NULL UNIQUE,
 request_hash TEXT NOT NULL)''',
'''CREATE TABLE workflow_events(id INTEGER PRIMARY KEY,entity_type TEXT NOT NULL,entity_id INTEGER NOT NULL,
 event_kind TEXT NOT NULL,from_status TEXT NOT NULL,to_status TEXT NOT NULL,occurred_at TEXT NOT NULL,
 recorded_at TEXT NOT NULL,actor TEXT NOT NULL,reason TEXT NOT NULL DEFAULT '',operation_key TEXT UNIQUE)''',
'''CREATE TABLE enquiry_interactions(id INTEGER PRIMARY KEY,origin_id INTEGER NOT NULL REFERENCES enquiry_origins(id),
 channel TEXT NOT NULL,occurred_at TEXT NOT NULL,recorded_at TEXT NOT NULL,actor TEXT NOT NULL,note TEXT NOT NULL)''',
'''CREATE TABLE revenue_operations(operation_key TEXT PRIMARY KEY,operation_type TEXT NOT NULL,entity_id INTEGER NOT NULL,request_hash TEXT NOT NULL)''',
'''CREATE UNIQUE INDEX idx_revenue_lead_request ON leads(submission_key) WHERE submission_key IS NOT NULL''',
'''CREATE INDEX idx_payments_date ON invoice_payments(received_on,invoice_id)''',
'''CREATE INDEX idx_workflow_entity ON workflow_events(entity_type,entity_id,id)''',
)
NEW_TABLES = ('schema_migrations','enquiry_origins','origin_corrections','invoice_payments','workflow_events','enquiry_interactions','revenue_operations')

def connect(path, readonly=False):
    conn = sqlite3.connect('file:'+str(Path(path).resolve())+('?mode=ro' if readonly else '?mode=rw'), uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    return conn

def inventory(conn):
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    return {t:{'count':conn.execute('SELECT COUNT(*) FROM "'+t+'"').fetchone()[0],
               'columns':[r[1] for r in conn.execute('PRAGMA table_info("'+t+'")')]} for t in tables}

def hashes(conn, before):
    return {t:hashlib.sha256('\n'.join(sorted(repr(tuple(r)) for r in conn.execute('SELECT '+','.join('"'+c+'"' for c in v['columns'])+' FROM "'+t+'"'))).encode()).hexdigest() for t,v in before.items()}

def preflight(conn):
    """Fail before DDL when existing relationships or paid projections are unsafe."""
    missing = {}
    links = {'leads':{'customer_id':'customers'},'quotes':{'lead_id':'leads','customer_id':'customers'},
             'invoices':{'quote_id':'quotes','customer_id':'customers'},
             'jobs':{'lead_id':'leads','quote_id':'quotes','invoice_id':'invoices','customer_id':'customers'},
             'appointments':{'lead_id':'leads','job_id':'jobs'}}
    for table,fields in links.items():
        for field,target in fields.items():
            count = conn.execute('SELECT COUNT(*) FROM '+table+' x LEFT JOIN '+target+' y ON y.id=x.'+field+' WHERE x.'+field+' IS NOT NULL AND y.id IS NULL').fetchone()[0]
            if count: missing[table+'.'+field]=count
    if missing:
        raise ValueError('Preflight: dangling historical references require owner review: '+json.dumps(missing,sort_keys=True))
    if conn.execute('SELECT 1 FROM invoices GROUP BY invoice_number HAVING COUNT(*)>1 LIMIT 1').fetchone():
        raise ValueError('Preflight: duplicate historical invoice numbers require owner review')
    from business.payment_store import pence
    for row in conn.execute('SELECT total_price,amount_paid,balance_due FROM invoices'):
        total,paid,balance=(pence(row[k] or 0) for k in ('total_price','amount_paid','balance_due'))
        if min(total,paid,balance)<0 or balance!=max(total-paid,0):
            raise ValueError('Preflight: historical invoice projection requires owner review; no automatic repair')
    return {'historical_relationships':'valid','invoice_projections':'reconciled'}


def migrate(path, *, apply=False, fail_after=None):
    with connect(path, readonly=not apply) as conn:
        before = inventory(conn)
        if enabled(conn):
            return {'version':VERSION,'already_applied':True,'inventory':before}
        safety = preflight(conn)
        original = hashes(conn,before)
        plan = {'version':VERSION,'already_applied':False,'dry_run':not apply,'inventory':before,'preflight':safety,
                'legacy_positive_paid':conn.execute('SELECT COUNT(*) FROM invoices WHERE amount_paid>0').fetchone()[0]}
        if not apply:
            return plan
        conn.execute('BEGIN IMMEDIATE')
        try:
            for t in ('leads','quotes','jobs','invoices'):
                conn.execute('ALTER TABLE '+t+' ADD COLUMN origin_id INTEGER REFERENCES enquiry_origins(id)')
            conn.execute('ALTER TABLE leads ADD COLUMN submission_key TEXT')
            conn.execute('ALTER TABLE leads ADD COLUMN submission_hash TEXT')
            conn.execute('ALTER TABLE invoices ADD COLUMN job_id INTEGER REFERENCES jobs(id)')
            conn.execute('ALTER TABLE quotes ADD COLUMN supersedes_quote_id INTEGER REFERENCES quotes(id)')
            for sql in DDL:
                conn.execute(sql)
            from business.lead_store import parse_lead_source
            from business.growth_tracking import SOURCES
            for row in conn.execute('SELECT id,source,source_category FROM leads').fetchall():
                raw,ctx = parse_lead_source(row['source'] or '')
                source = row['source_category'] if row['source_category'] in SOURCES else 'Unknown'
                oid = create_origin(conn,lead_id=row['id'],source=source,channel='Website form' if raw=='website' else 'Unknown',context=ctx,kind='legacy',method='legacy_record',confidence='limited')
                conn.execute('UPDATE leads SET origin_id=? WHERE id=?',(oid,row['id']))
            for row in conn.execute('SELECT id,lead_id,source_category FROM quotes').fetchall():
                lead = conn.execute('SELECT origin_id FROM leads WHERE id=?',(row['lead_id'],)).fetchone()
                oid = lead[0] if lead else create_origin(conn,source=row['source_category'] if row['source_category'] in SOURCES else 'Unknown',kind='legacy',method='legacy_quote',confidence='limited')
                conn.execute('UPDATE quotes SET origin_id=? WHERE id=?',(oid,row['id']))
            for row in conn.execute('SELECT id,lead_id,quote_id FROM jobs').fetchall():
                q = conn.execute('SELECT origin_id FROM quotes WHERE id=?',(row['quote_id'],)).fetchone()
                l = conn.execute('SELECT origin_id FROM leads WHERE id=?',(row['lead_id'],)).fetchone()
                if q and l and q[0] != l[0]:
                    raise ValueError('Historical job has conflicting origins; owner review required')
                conn.execute('UPDATE jobs SET origin_id=? WHERE id=?',((q or l or [None])[0],row['id']))
            for row in conn.execute('SELECT id,quote_id,amount_paid FROM invoices').fetchall():
                q = conn.execute('SELECT origin_id FROM quotes WHERE id=?',(row['quote_id'],)).fetchone()
                oid = q[0] if q else create_origin(conn,kind='legacy',method='legacy_invoice',confidence='limited')
                job = conn.execute('SELECT id FROM jobs WHERE invoice_id=?',(row['id'],)).fetchone()
                conn.execute('UPDATE invoices SET origin_id=?,job_id=? WHERE id=?',(oid,job[0] if job else None,row['id']))
                if row['amount_paid']:
                    from business.payment_store import pence
                    conn.execute('''INSERT INTO invoice_payments(invoice_id,amount_pence,received_on,recorded_at,entry_type,method,actor,operation_key,request_hash)
                        VALUES (?,?,NULL,?,'legacy_opening_balance','Unknown','migration',?,?)''',
                        (row['id'],pence(row['amount_paid']),utc_now(),'legacy-opening-'+str(row['id']),'legacy'))
            if fail_after:
                raise RuntimeError('Injected migration rollback rehearsal')
            if hashes(conn,before) != original:
                raise RuntimeError('Legacy records changed during additive migration')
            conn.execute('INSERT INTO schema_migrations VALUES (?,?)',(VERSION,utc_now()))
            for table in ('enquiry_origins','origin_corrections','invoice_payments','workflow_events'):
                for operation in ('UPDATE','DELETE'):
                    conn.execute('CREATE TRIGGER immutable_'+table+'_'+operation.lower()+' BEFORE '+operation+' ON '+table+" BEGIN SELECT RAISE(ABORT,'History is append-only'); END")
            conn.execute("CREATE TRIGGER protect_invoice_paid BEFORE UPDATE OF amount_paid ON invoices WHEN ROUND(NEW.amount_paid*100) != (SELECT COALESCE(SUM(amount_pence),0) FROM invoice_payments WHERE invoice_id=OLD.id) BEGIN SELECT RAISE(ABORT,'Use the dated payment ledger'); END")
            for t in ('leads','quotes','jobs','invoices'):
                conn.execute('CREATE TRIGGER protect_'+t+'_delete BEFORE DELETE ON '+t+" WHEN OLD.origin_id IS NOT NULL BEGIN SELECT RAISE(ABORT,'Retain tracked history'); END")
                conn.execute('CREATE TRIGGER protect_'+t+'_origin BEFORE UPDATE OF origin_id ON '+t+" WHEN OLD.origin_id IS NOT NULL AND NEW.origin_id IS NOT OLD.origin_id BEGIN SELECT RAISE(ABORT,'Original enquiry is immutable'); END")
            conn.execute("CREATE TRIGGER protect_quote_created BEFORE UPDATE OF created_at,created_at_sort ON quotes WHEN OLD.created_at != NEW.created_at OR OLD.created_at_sort != NEW.created_at_sort BEGIN SELECT RAISE(ABORT,'Quote creation is immutable'); END")
            if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or conn.execute('PRAGMA foreign_key_check').fetchone():
                raise RuntimeError('Migration integrity check failed')
            conn.commit()
            return {**plan,'dry_run':False,'legacy_fields_unchanged':True,'after':inventory(conn)}
        except Exception:
            conn.rollback()
            raise

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--database',required=True)
    parser.add_argument('--apply',action='store_true')
    args = parser.parse_args()
    if Path(args.database).resolve().is_relative_to('/var/data'):
        parser.error('Production/shared disk migration is outside this development command; use a separately approved release procedure')
    print(json.dumps(migrate(args.database,apply=args.apply),indent=2))

"""Aggregate reports only. Cash and enquiry cohorts use different clocks."""
from datetime import date, datetime
from zoneinfo import ZoneInfo
from business.enquiry_attribution import origin
from business.payment_store import pence

def report(conn, start, end):
    try:
        a,b = date.fromisoformat(start),date.fromisoformat(end)
        if a > b or (b-a).days > 3660:
            raise ValueError
    except (TypeError,ValueError):
        raise ValueError('Choose a valid reporting period of at most ten years') from None
    origins = {r[0]:origin(conn,r[0]) for r in conn.execute('SELECT id FROM enquiry_origins')}
    leads = [dict(r) for r in conn.execute('SELECT id,origin_id,created_at_sort FROM leads')]
    quotes = [dict(r) for r in conn.execute('SELECT id,lead_id,origin_id,status,total_price,created_at_sort,supersedes_quote_id FROM quotes')]
    invoices = [dict(r) for r in conn.execute('SELECT id,origin_id,total_price,amount_paid,balance_due,job_id FROM invoices')]
    jobs = [dict(r) for r in conn.execute('SELECT id,origin_id,status FROM jobs')]
    payments = [dict(r) for r in conn.execute('SELECT invoice_id,amount_pence,received_on FROM invoice_payments')]
    rows = {}
    excluded_tests = {oid for oid,o in origins.items() if o['kind']=='synthetic'}
    def bucket(oid):
        source = origins.get(oid,{}).get('source','Unknown')
        return rows.setdefault(source,{'enquiries':0,'quoted_enquiries':0,'accepted_enquiries':0,'completed_enquiries':0,
            'quotes':0,'won_quotes':0,'lost_quotes':0,'cash_pence':0,'cohort_paid_pence':0,
            'legacy_undated_pence':0,'outstanding_pence':0,'invoiced_pence':0})
    cohort = {l['id'] for l in leads if start <= (l['created_at_sort'] or '')[:10] <= end and l['origin_id'] not in excluded_tests}
    cohort_origins = {l['origin_id'] for l in leads if l['id'] in cohort}
    superseded = {q['supersedes_quote_id'] for q in quotes if q['supersedes_quote_id']}
    accepted_origins = {r[0] for r in conn.execute("SELECT DISTINCT j.origin_id FROM jobs j JOIN workflow_events w ON w.entity_id=j.id AND w.entity_type='job' WHERE w.to_status IN ('accepted','scheduled','in_progress','completed') AND j.status!='cancelled'")}
    completed_origins = {j['origin_id'] for j in jobs if j['status']=='completed'}
    for lead in leads:
        if lead['id'] not in cohort:
            continue
        target = bucket(lead['origin_id']);target['enquiries']+=1
        target['quoted_enquiries']+=any(q['lead_id']==lead['id'] for q in quotes)
        target['accepted_enquiries']+=lead['origin_id'] in accepted_origins
        target['completed_enquiries']+=lead['origin_id'] in completed_origins
    for q in quotes:
        if q['origin_id'] in excluded_tests or q['id'] in superseded:
            continue
        if q['origin_id'] in cohort_origins or (q['lead_id'] is None and start <= (q['created_at_sort'] or '')[:10] <= end):
            target=bucket(q['origin_id']);target['quotes']+=1
            target['won_quotes']+=q['status']=='won';target['lost_quotes']+=q['status']=='lost'
    invoice_origins={i['id']:i['origin_id'] for i in invoices}
    for invoice in invoices:
        if invoice['origin_id'] in excluded_tests:
            continue
        target=bucket(invoice['origin_id'])
        target['outstanding_pence']+=pence(invoice['balance_due'] or 0)
        target['invoiced_pence']+=pence(invoice['total_price'] or 0)
    for payment in payments:
        oid=invoice_origins.get(payment['invoice_id'])
        if oid in excluded_tests:
            continue
        target=bucket(oid)
        if payment['received_on'] is None:
            target['legacy_undated_pence']+=payment['amount_pence']
        elif start <= payment['received_on'] <= end:
            target['cash_pence']+=payment['amount_pence']
        if oid in cohort_origins:
            target['cohort_paid_pence']+=payment['amount_pence']
    for target in rows.values():
        n=target['enquiries'];decisions=target['won_quotes']+target['lost_quotes']
        target['quoted_percent']=round(100*target['quoted_enquiries']/n,1) if n else None
        target['accepted_percent']=round(100*target['accepted_enquiries']/n,1) if n else None
        target['quote_win_percent']=round(100*target['won_quotes']/decisions,1) if decisions else None
    return {'start':start,'end':end,'currency':'GBP','as_of':datetime.now(ZoneInfo('Europe/London')).date().isoformat(),
            'by_source':rows,'totals':{k:sum(v[k] for v in rows.values()) for k in next(iter(rows.values()),{}) if not k.endswith('percent')},
            'synthetic_origins_excluded':len(excluded_tests),
            'definitions':{'cash':'Dated confirmed receipts minus refunds/reversal effects within selected UK receipt dates',
                'cohort':'Distinct enquiries created in selected dates; later linked recorded payments shown separately',
                'legacy':'Undated historical opening balances; excluded from period cash',
                'outstanding':'Current all-time invoice balance, not filtered by receipt dates',
                'paid':'Owner-recorded amounts, not automatic bank verification or net profit'}}

def review(conn):
    checks = {
        'historical_paid_flag_mismatch':"SELECT id AS invoice_id,status FROM invoices WHERE status='paid' AND balance_due>0",
        'legacy_test_marker_review':"SELECT l.id AS lead_id,l.origin_id FROM leads l JOIN enquiry_origins o ON o.id=l.origin_id WHERE o.record_kind='legacy' AND (l.description LIKE '%NHP-GA4-20261010-ONE%' OR l.description LIKE '%GA4 Conversion Verification — TEST — 10 October 2026%') AND NOT EXISTS(SELECT 1 FROM origin_corrections c WHERE c.origin_id=o.id)",
        'source_conflicts':"SELECT q.id AS quote_id,q.lead_id FROM quotes q JOIN leads l ON l.id=q.lead_id JOIN enquiry_origins o ON o.id=l.origin_id WHERE q.source_category IS NOT NULL AND q.source_category!='' AND q.source_category!=o.captured_source",
        'legacy_without_enquiry':"SELECT id AS quote_id FROM quotes WHERE lead_id IS NULL",
        'undated_paid_balances':"SELECT invoice_id,SUM(amount_pence) AS amount_pence FROM invoice_payments WHERE received_on IS NULL GROUP BY invoice_id HAVING SUM(amount_pence)!=0",
        'unknown_origins':"SELECT id AS origin_id,lead_id FROM enquiry_origins WHERE COALESCE((SELECT new_source FROM origin_corrections c WHERE c.origin_id=enquiry_origins.id ORDER BY revision DESC LIMIT 1),captured_source)='Unknown'",
    }
    return {name:{'count':conn.execute('SELECT COUNT(*) FROM ('+sql+')').fetchone()[0],
                  'records':[dict(r) for r in conn.execute(sql+' LIMIT 50')]} for name,sql in checks.items()}

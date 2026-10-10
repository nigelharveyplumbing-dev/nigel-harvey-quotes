"""Transactional tracking-aware quote/invoice creation; legacy calculations untouched."""
import json
from datetime import timedelta
from business.db import get_db
from business import enquiry_attribution as attribution
from business.payment_store import request_hash

def save_quote(request,result,now):
    key=request.get('submission_key','')
    if key and not 16 <= len(key) <= 128:
        raise ValueError('Invalid quote save key')
    digest=request_hash(request)
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if key:
            old=conn.execute('SELECT * FROM revenue_operations WHERE operation_key=?',(key,)).fetchone()
            if old:
                if old['operation_type']!='quote' or old['request_hash']!=digest:
                    raise ValueError('Save key reused for different quote details')
                return old['entity_id'],False
        lead_id=request.get('lead_id')
        oid=attribution.inherited(conn,lead_id=lead_id) if lead_id else None
        customer_id=request.get('customer_id')
        if lead_id:
            linked=conn.execute('SELECT customer_id FROM leads WHERE id=?',(lead_id,)).fetchone()[0]
            if linked and customer_id and linked!=customer_id:
                raise ValueError('Selected customer conflicts with the original enquiry')
            customer_id=customer_id or linked
        if customer_id:
            if not conn.execute('SELECT 1 FROM customers WHERE id=?',(customer_id,)).fetchone():
                raise ValueError('Selected customer does not exist')
        else:
            timestamp=now().isoformat()
            customer_id=conn.execute('INSERT INTO customers(name,address,phone,created_at,updated_at) VALUES (?,?,?,?,?)',
                (request.get('customer_name',''),request.get('customer_address',''),request.get('customer_phone',''),timestamp,timestamp)).lastrowid
        oid=oid or attribution.create_origin(conn,source=request.get('source_category') or 'Unknown')
        source=attribution.origin(conn,oid)['source']
        normalized={**request,'source_category':source,'customer_id':customer_id}
        qid=conn.execute('''INSERT INTO quotes(customer_id,customer_name,job,total_price,gross_profit,margin_percent,
            created_at,created_at_sort,request_json,result_json,status,lead_id,source_category,work_type,additional_work_types,origin_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (customer_id,result.get('customer_name',''),result.get('job',''),result.get('total_price',0),result.get('gross_profit',0),result.get('margin_percent',0),
             result['created_at'],result['created_at_sort'],json.dumps(normalized),json.dumps(result),'pending',lead_id,source,
             request.get('work_type') or None,json.dumps(request.get('additional_work_types',[])),oid)).lastrowid
        if lead_id:
            conn.execute('UPDATE leads SET customer_id=COALESCE(customer_id,?) WHERE id=?',(customer_id,lead_id))
            from business.quote_store import sync_lead_status_from_quotes
            sync_lead_status_from_quotes(conn,lead_id,now().isoformat())
        if key:
            conn.execute('INSERT INTO revenue_operations VALUES (?,?,?,?)',(key,'quote',qid,digest))
        return qid,True

def create_invoice(quote_id,now,format_dt,*,operation_key='',job_id=None,separate=False):
    from business.quote_store import build_payment_link
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        q=conn.execute('SELECT * FROM quotes WHERE id=?',(quote_id,)).fetchone()
        if not q:
            return None
        digest=request_hash({'quote_id':quote_id,'job_id':job_id,'separate':separate})
        if operation_key:
            if not 16 <= len(operation_key) <= 128:
                raise ValueError('Valid invoice operation key required')
            old=conn.execute('SELECT * FROM revenue_operations WHERE operation_key=?',(operation_key,)).fetchone()
            if old:
                if old['operation_type']!='invoice' or old['request_hash']!=digest:
                    raise ValueError('Operation key reused for different invoice details')
                return old['entity_id']
        if separate and not operation_key:
            raise ValueError('Separate stage/final invoice requires an operation key')
        if not separate:
            existing=conn.execute('SELECT id FROM invoices WHERE quote_id=? ORDER BY id LIMIT 1',(quote_id,)).fetchone()
            if existing:
                return existing[0]
        if job_id:
            job=conn.execute('SELECT origin_id,quote_id FROM jobs WHERE id=?',(job_id,)).fetchone()
            if not job or job['origin_id']!=q['origin_id'] or job['quote_id']!=quote_id:
                raise ValueError('Job must belong to this quote and original enquiry')
        year=now().strftime('%Y')
        numbers=[r[0] for r in conn.execute('SELECT invoice_number FROM invoices WHERE invoice_number LIKE ?',(f'INV-{year}-%',))]
        sequence=max([int(x.rsplit('-',1)[1]) for x in numbers if x.rsplit('-',1)[1].isdigit()]+[0])+1
        number=f'INV-{year}-{sequence:04d}'
        result=json.loads(q['result_json'])
        payload={k:result.get(k,'') for k in ('customer_name','customer_address','customer_phone','job','labour','callout_charge','travel_charge','materials','total_price','deposit_percent','deposit_amount')}
        payload.update(invoice_number=number,quote_id=quote_id,due_date=(now()+timedelta(days=14)).strftime('%d/%m/%Y'),
            payment_link=build_payment_link(number),job_reference='',status='unpaid',amount_paid=0,balance_due=result.get('total_price',0))
        iid=conn.execute('''INSERT INTO invoices(quote_id,customer_id,invoice_number,customer_name,total_price,amount_paid,balance_due,status,
            due_date,payment_link,job_reference,reminder_email,reminders_enabled,last_reminder_at,created_at,created_at_sort,quote_result_json,invoice_json,origin_id,job_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (quote_id,q['customer_id'],number,q['customer_name'],q['total_price'],0,q['total_price'],'unpaid',payload['due_date'],payload['payment_link'],
             '','',0,'',format_dt(now()),now().isoformat(),json.dumps(result),json.dumps(payload),q['origin_id'],job_id)).lastrowid
        if operation_key:
            conn.execute('INSERT INTO revenue_operations VALUES (?,?,?,?)',(operation_key,'invoice',iid,digest))
        return iid

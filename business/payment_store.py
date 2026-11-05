"""Append-only, owner-confirmed GBP receipts; never inferred from invoice status."""
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from business.enquiry_attribution import utc_now

METHODS = ('Bank transfer','Cash','Card','Other','Unknown')

def pence(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount.quantize(Decimal('0.01')) != amount or abs(amount) > Decimal('100000000'):
            raise ValueError
        return int(amount * 100)
    except (InvalidOperation,ValueError,TypeError):
        raise ValueError('Use a finite GBP amount with no more than two decimal places') from None

def receipt_date(value):
    try:
        day = date.fromisoformat(value)
        if day.isoformat() != value or day.year < 1900 or day > datetime.now(ZoneInfo('Europe/London')).date():
            raise ValueError
        return value
    except (ValueError,TypeError):
        raise ValueError('Enter the genuine UK receipt date as YYYY-MM-DD, not a future date') from None

def request_hash(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def project(conn, invoice_id):
    invoice = conn.execute('SELECT total_price,invoice_json FROM invoices WHERE id=?',(invoice_id,)).fetchone()
    if not invoice:
        raise ValueError('Invoice not found')
    paid = conn.execute('SELECT COALESCE(SUM(amount_pence),0) FROM invoice_payments WHERE invoice_id=?',(invoice_id,)).fetchone()[0]
    if paid < 0:
        raise ValueError('Recorded refunds/reversals exceed the invoice receipts')
    total = pence(invoice['total_price'] or 0)
    status = 'unpaid' if paid == 0 else 'paid' if paid >= total else 'part paid'
    payload = json.loads(invoice['invoice_json'])
    payload.update(amount_paid=paid/100,balance_due=max(total-paid,0)/100,status=status)
    conn.execute('UPDATE invoices SET amount_paid=?,balance_due=?,status=?,invoice_json=? WHERE id=?',
                 (paid/100,max(total-paid,0)/100,status,json.dumps(payload),invoice_id))

def history(conn, invoice_id):
    row = conn.execute('SELECT id,invoice_number,total_price,amount_paid,balance_due,status,origin_id,job_id FROM invoices WHERE id=?',(invoice_id,)).fetchone()
    if not row:
        raise ValueError('Invoice not found')
    entries = [dict(x) for x in conn.execute('SELECT * FROM invoice_payments WHERE invoice_id=? ORDER BY id',(invoice_id,))]
    return {'invoice':dict(row),'entries':entries,'currency':'GBP',
            'undated_balance_pence':sum(x['amount_pence'] for x in entries if x['received_on'] is None),
            'overpayment_credit_pence':max(sum(x['amount_pence'] for x in entries)-pence(row['total_price']),0)}

def record(conn, invoice_id, data, actor):
    """Caller owns BEGIN IMMEDIATE; correction is reversal + replacement atomically."""
    action = data.get('action','receipt')
    key = data.get('operation_key','')
    if not isinstance(key,str) or not 16 <= len(key) <= 128:
        raise ValueError('A stable operation key is required')
    digest = request_hash({'invoice_id':invoice_id,**data})
    previous = conn.execute('SELECT * FROM revenue_operations WHERE operation_key=?',(key,)).fetchone()
    if previous:
        if previous['request_hash'] != digest or previous['operation_type'] != 'payment':
            raise ValueError('Operation key reused for different details')
        return {**history(conn,invoice_id),'already_recorded':True}
    if not conn.execute('SELECT 1 FROM invoices WHERE id=?',(invoice_id,)).fetchone():
        raise ValueError('Invoice not found')
    method = data.get('method','Unknown')
    if method not in METHODS:
        raise ValueError('Choose a valid payment method')
    reason = str(data.get('reason') or '').strip()[:500]
    reference = str(data.get('reference') or '').strip()[:180]
    target = None
    if action in ('reversal','correction'):
        target = conn.execute('SELECT * FROM invoice_payments WHERE id=? AND invoice_id=?',(data.get('related_entry_id'),invoice_id)).fetchone()
        if not target or target['entry_type']=='reversal' or not reason:
            raise ValueError('Select an original entry and provide a correction/reversal reason')
        if conn.execute("SELECT 1 FROM invoice_payments WHERE related_entry_id=? AND entry_type='reversal'",(target['id'],)).fetchone():
            raise ValueError('This entry has already been reversed')
    def add(amount,day,kind,suffix='',related=None,payment_method=method):
        conn.execute('''INSERT INTO invoice_payments(invoice_id,amount_pence,received_on,recorded_at,entry_type,
            method,reference,reason,related_entry_id,actor,operation_key,request_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
            (invoice_id,amount,day,utc_now(),kind,payment_method,reference,reason,related,actor,key+suffix,digest))
    if target:
        add(-target['amount_pence'],target['received_on'],'reversal','-reverse',target['id'],target['method'])
    if action in ('receipt','refund','correction'):
        amount = pence(data.get('amount'))
        if amount <= 0:
            raise ValueError('Enter a positive amount; use Refund or Reversal to reduce receipts')
        day = receipt_date(data.get('received_on'))
        duplicate_amount = -amount if action == 'refund' else amount
        if reference and action in ('receipt','refund') and conn.execute('''SELECT 1 FROM invoice_payments p
            WHERE p.invoice_id=? AND p.amount_pence=? AND p.received_on=? AND p.method=?
            AND lower(trim(p.reference))=lower(?) AND NOT EXISTS
            (SELECT 1 FROM invoice_payments r WHERE r.entry_type='reversal' AND r.related_entry_id=p.id)''',
            (invoice_id,duplicate_amount,day,method,reference)).fetchone():
            raise ValueError('Matching payment reference, amount and UK date already recorded; review history')
        if action == 'refund' and not reason:
            raise ValueError('Provide the refund reason')
        if action == 'correction' and target['amount_pence'] < 0:
            amount = -amount
        elif action == 'refund':
            amount = -amount
        add(amount,day,'refund' if amount < 0 else 'receipt','-replacement' if action=='correction' else '',target['id'] if target else None)
    elif action != 'reversal':
        raise ValueError('Choose Receipt, Refund, Reversal or Correction')
    project(conn,invoice_id)
    conn.execute('INSERT INTO revenue_operations VALUES (?,?,?,?)',(key,'payment',invoice_id,digest))
    return {**history(conn,invoice_id),'already_recorded':False}

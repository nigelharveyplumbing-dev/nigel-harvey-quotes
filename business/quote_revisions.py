"""Explicit owner-confirmed revision links using existing append-only history."""
from business.enquiry_attribution import utc_now
from business.payment_store import request_hash
from business.workflow_history import events


def link(conn, quote_id, data, actor):
    previous_id = data['supersedes_quote_id']
    reason = data['reason'].strip()
    key = data['operation_key']
    if data['confirmed_same_scope'] is not True or not reason:
        raise ValueError('Confirm this is a genuine revision of the same work and give a reason')
    digest = request_hash({'quote_id':quote_id, **data})
    prior = conn.execute('SELECT * FROM revenue_operations WHERE operation_key=?',(key,)).fetchone()
    if prior:
        if prior['operation_type']!='quote_revision' or prior['request_hash']!=digest:
            raise ValueError('Operation key reused for different details')
        return {'saved':True,'already_recorded':True,'history':events(conn,'quote',quote_id)}
    current = conn.execute('SELECT origin_id,lead_id,supersedes_quote_id FROM quotes WHERE id=?',(quote_id,)).fetchone()
    previous = conn.execute('SELECT origin_id,lead_id,supersedes_quote_id FROM quotes WHERE id=?',(previous_id,)).fetchone()
    if not current or not previous or not current['origin_id'] or current['origin_id']!=previous['origin_id'] or current['lead_id']!=previous['lead_id']:
        raise ValueError('Choose quotes from the same original enquiry')
    # Older numeric IDs enforce a DAG; traversal also refuses corrupt pre-existing chains.
    if previous_id >= quote_id:
        raise ValueError('A revision must replace an earlier quote; loops are not allowed')
    seen = {quote_id}
    ancestor = previous_id
    while ancestor is not None:
        if ancestor in seen:
            raise ValueError('Revision loop detected')
        seen.add(ancestor)
        row = conn.execute('SELECT origin_id,lead_id,supersedes_quote_id FROM quotes WHERE id=?',(ancestor,)).fetchone()
        if not row or row['origin_id'] != current['origin_id'] or row['lead_id'] != current['lead_id']:
            raise ValueError('Broken revision chain; review before linking')
        ancestor = row['supersedes_quote_id']
    if current['supersedes_quote_id'] is not None:
        raise ValueError('This quote already has a revision link; existing history is retained')
    if conn.execute('SELECT 1 FROM quotes WHERE supersedes_quote_id=?',(previous_id,)).fetchone():
        raise ValueError('That quote already has a later revision; choose the current revision')
    if conn.execute('SELECT 1 FROM quotes WHERE supersedes_quote_id=?',(quote_id,)).fetchone():
        raise ValueError('This quote has already been replaced; choose the current revision')
    jobs = conn.execute('SELECT DISTINCT id FROM jobs WHERE quote_id IN ('+','.join('?' for _ in seen)+')',tuple(seen)).fetchall()
    if len(jobs)>1:
        raise ValueError('Quotes linked to separate jobs cannot be treated as revisions')
    conn.execute('UPDATE quotes SET supersedes_quote_id=? WHERE id=?',(previous_id,quote_id))
    now = utc_now()
    conn.execute('''INSERT INTO workflow_events(entity_type,entity_id,event_kind,from_status,to_status,
        occurred_at,recorded_at,actor,reason,operation_key) VALUES (?,?,?,?,?,?,?,?,?,?)''',
        ('quote',quote_id,'quote_revision','',str(previous_id),now,now,actor,reason,key))
    conn.execute('INSERT INTO revenue_operations VALUES (?,?,?,?)',(key,'quote_revision',quote_id,digest))
    return {'saved':True,'already_recorded':False,'history':events(conn,'quote',quote_id)}

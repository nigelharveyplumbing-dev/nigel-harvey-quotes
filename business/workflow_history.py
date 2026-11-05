"""Private status history with idempotent, auditable milestone corrections."""
from business.enquiry_attribution import utc_now
from business.payment_store import request_hash

def append(conn, entity_type, entity_id, before, after, actor='application', reason='', operation_key=None):
    conn.execute('''INSERT INTO workflow_events(entity_type,entity_id,event_kind,from_status,to_status,
        occurred_at,recorded_at,actor,reason,operation_key) VALUES (?,?,?,?,?,?,?,?,?,?)''',
        (entity_type,entity_id,'status',before or '',after,utc_now(),utc_now(),actor,reason[:500],operation_key))

def events(conn, entity_type, entity_id):
    return [dict(r) for r in conn.execute('SELECT * FROM workflow_events WHERE entity_type=? AND entity_id=? ORDER BY id',(entity_type,entity_id))]

def milestone(conn, entity_type, entity_id, data, actor):
    if entity_type not in ('quote','job'):
        raise ValueError('Choose a quote or job')
    table = {'quote':'quotes','job':'jobs'}[entity_type]
    allowed = {'quote':('pending','won','lost','expired','unclassified'),
               'job':('awaiting_schedule','accepted','scheduled','in_progress','completed','cancelled')}[entity_type]
    status = data.get('status')
    key = data.get('operation_key','')
    if status not in allowed or not 16 <= len(key) <= 128:
        raise ValueError('Valid status and stable operation key required')
    digest = request_hash({'type':entity_type,'id':entity_id,**data})
    prior = conn.execute('SELECT * FROM revenue_operations WHERE operation_key=?',(key,)).fetchone()
    if prior:
        if prior['request_hash'] != digest or prior['operation_type'] != 'milestone':
            raise ValueError('Operation key reused for different details')
        return {'history':events(conn,entity_type,entity_id),'already_recorded':True}
    row = conn.execute('SELECT * FROM '+table+' WHERE id=?',(entity_id,)).fetchone()
    if not row:
        raise ValueError('Linked record not found')
    reason = str(data.get('reason') or '').strip()[:500]
    if (status in ('lost','cancelled') or (row['status'] in ('completed','won','lost','expired') and row['status'] != status)) and not reason:
        raise ValueError('Provide a loss, cancellation or milestone-correction reason')
    if entity_type == 'job' and status in ('accepted','scheduled','in_progress','completed'):
        q = conn.execute('SELECT status FROM quotes WHERE id=?',(row['quote_id'],)).fetchone()
        if not q or q[0] != 'won':
            raise ValueError('Accept the linked quote before confirming job milestones')
    append(conn,entity_type,entity_id,row['status'],status,actor,reason,key)
    conn.execute('UPDATE '+table+' SET status=? WHERE id=?',(status,entity_id))
    if entity_type == 'quote':
        conn.execute('UPDATE quotes SET outcome_updated_at=?,loss_note=?,loss_reason=?,next_follow_up=? WHERE id=?',(utc_now(),reason if status=='lost' else None,(row['loss_reason'] or 'Other') if status=='lost' else None,row['next_follow_up'] if status=='pending' else None,entity_id))
        if row['lead_id']:
            from business.quote_store import sync_lead_status_from_quotes
            sync_lead_status_from_quotes(conn,row['lead_id'],utc_now())
    else:
        conn.execute('UPDATE jobs SET updated_at=? WHERE id=?',(utc_now(),entity_id))
    conn.execute('INSERT INTO revenue_operations VALUES (?,?,?,?)',(key,'milestone',entity_id,digest))
    return {'history':events(conn,entity_type,entity_id),'already_recorded':False}

"""Private notification audit and manual retry; never changes lead business status."""

import time
from business.db import get_db


def notification_states():
    conn = get_db()
    try:
        states = {str(row['lead_id']): dict(row) for row in conn.execute(
            'SELECT * FROM lead_email_notifications ORDER BY updated_at DESC LIMIT 1000')}
        for state in states.values():
            if state['status'] == 'sending' and state['updated_at'] <= time.time() - 120:
                state['status'] = 'pending'
        return states
    finally:
        conn.close()


def deliver(lead, sender):
    """Claim once; concurrent retries and accepted messages are not sent twice.

    A process death after SMTP acceptance but before audit completion can still
    result in a duplicate on a later manual retry. SMTP is not exactly-once.
    """
    conn = get_db()
    try:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT * FROM lead_email_notifications WHERE lead_id=?',
                           (lead['id'],)).fetchone()
        now = time.time()
        if row and (row['status'] == 'accepted' or
                    (row['status'] == 'sending' and row['updated_at'] > now - 120)):
            conn.rollback()
            return {'status': row['status'], 'error_code': row['error_code']}
        conn.execute('''INSERT INTO lead_email_notifications
            (lead_id, status, attempts, updated_at) VALUES (?, 'sending', 1, ?)
            ON CONFLICT(lead_id) DO UPDATE SET status='sending',
            attempts=attempts+1, error_code='', updated_at=excluded.updated_at''',
                     (lead['id'], now))
        conn.commit()
        result = sender(lead)
        conn.execute('''UPDATE lead_email_notifications SET status=?, error_code=?,
                        updated_at=? WHERE lead_id=?''',
                     (result['status'], result['error_code'], time.time(), lead['id']))
        conn.commit()
        return result
    finally:
        conn.close()

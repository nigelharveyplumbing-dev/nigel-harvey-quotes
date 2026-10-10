"""Private canonical origins. Captured evidence is immutable; corrections append."""
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from business.growth_tracking import SOURCES, inferred_source

CHANNELS = ('Website form', 'Phone', 'WhatsApp', 'Email', 'Directory message', 'In person', 'Other', 'Unknown')
KINDS = ('unconfirmed', 'genuine', 'synthetic', 'legacy')
CONTEXT_KEYS = ('landing_page', 'referrer', 'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term')

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def enabled(conn):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone() is not None and conn.execute('SELECT 1 FROM schema_migrations WHERE version=1').fetchone() is not None

def sanitize_context(context):
    out = {}
    for key in CONTEXT_KEYS:
        value = str(context.get(key) or '')[:300]
        if not value:
            continue
        if key == 'landing_page':
            if not value.startswith('/') or value.startswith('//'):
                continue
            value = urlsplit(value).path[:200]
            if not re.fullmatch(r'/[A-Za-z0-9/_-]*', value) or value.startswith(('/app', '/api', '/invoice')):
                continue
        elif key == 'referrer':
            try:
                u = urlsplit(value)
                if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password:
                    continue
                value = u.scheme + '://' + u.hostname.lower()
            except ValueError:
                continue
        elif not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _.-]{0,79}', value) or re.search(r'\d{7,}|@', value):
            continue
        out[key] = value
    return out

def create_origin(conn, *, lead_id=None, source='Unknown', channel='Unknown', context=None,
                  kind='unconfirmed', method='owner_reported', confidence='reported', test_reference=''):
    if source not in SOURCES or channel not in CHANNELS or kind not in KINDS:
        raise ValueError('Choose a valid source, contact channel and record classification')
    clean = sanitize_context(context or {})
    if method == 'website_observed':
        source = inferred_source('website', clean)
        # A search referrer cannot distinguish organic visits from paid clicks.
        if source == 'Google organic search' and not (clean.get('utm_source','').lower()=='google' and clean.get('utm_medium','').lower() in ('organic','seo')):
            source = 'Unknown'
        if source == 'Website/direct' and (clean.get('utm_source') or clean.get('utm_medium')):
            source = 'Other'
        confidence = 'reported' if clean.get('utm_source') else 'limited'
    if source == 'Unknown':
        confidence = 'limited'
    if kind == 'synthetic' and not test_reference.strip():
        raise ValueError('Synthetic Test requires a test reference')
    cursor = conn.execute('''INSERT INTO enquiry_origins
        (lead_id,captured_source,contact_channel,record_kind,evidence_json,method,confidence,captured_at,test_reference)
        VALUES (?,?,?,?,?,?,?,?,?)''', (lead_id,source,channel,kind,json.dumps(clean),method,confidence,utc_now(),test_reference.strip()[:100]))
    return cursor.lastrowid

def origin(conn, origin_id):
    row = conn.execute('SELECT * FROM enquiry_origins WHERE id=?', (origin_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    corrections = [dict(x) for x in conn.execute('SELECT * FROM origin_corrections WHERE origin_id=? ORDER BY revision', (origin_id,))]
    item['history'] = corrections
    item['interactions'] = [dict(x) for x in conn.execute('SELECT * FROM enquiry_interactions WHERE origin_id=? ORDER BY id',(origin_id,))]
    item['captured_channel'] = item['contact_channel']
    item['contact_channel'] = corrections[-1]['new_channel'] if corrections else item['contact_channel']
    item['source'] = corrections[-1]['new_source'] if corrections else item['captured_source']
    item['kind'] = corrections[-1]['new_kind'] if corrections else item['record_kind']
    item['test_reference'] = corrections[-1]['new_test_reference'] if corrections else item['test_reference']
    item['revision'] = len(corrections)
    item['evidence'] = json.loads(item.pop('evidence_json'))
    return item

def correct(conn, origin_id, *, source, kind, reason, expected_revision, actor, test_reference='', channel=''):
    item = origin(conn, origin_id)
    if not item or source not in SOURCES or kind not in KINDS or not reason.strip():
        raise ValueError('Existing origin, valid classification and correction reason required')
    if item['revision'] != expected_revision:
        raise ValueError('Source changed since review; reload its history before correcting')
    channel = channel or item['contact_channel']
    if channel not in CHANNELS:
        raise ValueError('Choose a valid corrected contact channel')
    test_reference = test_reference.strip() or item['test_reference']
    if kind == 'synthetic' and not test_reference:
        raise ValueError('Synthetic Test requires a test reference')
    conn.execute('''INSERT INTO origin_corrections
        (origin_id,revision,old_source,new_source,old_kind,new_kind,reason,actor,recorded_at,new_test_reference,old_channel,new_channel)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''', (origin_id,expected_revision+1,item['source'],source,item['kind'],kind,reason.strip()[:500],actor,utc_now(),test_reference[:100],item['contact_channel'],channel))
    return origin(conn, origin_id)

def inherited(conn, *, lead_id=None, quote_id=None, invoice_id=None):
    ids = set()
    for table, entity_id in (('leads',lead_id), ('quotes',quote_id), ('invoices',invoice_id)):
        if entity_id:
            row = conn.execute('SELECT origin_id FROM '+table+' WHERE id=?', (entity_id,)).fetchone()
            if not row:
                raise ValueError('Linked record not found')
            if row[0]:
                ids.add(row[0])
    if len(ids) > 1:
        raise ValueError('Linked records have different original enquiries; review the links')
    return next(iter(ids), None)

def protect_history(conn, table, entity_id):
    if enabled(conn):
        row = conn.execute('SELECT origin_id FROM '+table+' WHERE id=?', (entity_id,)).fetchone()
        if row and row[0]:
            raise ValueError('Tracked history cannot be deleted; retain the record and close its status instead')

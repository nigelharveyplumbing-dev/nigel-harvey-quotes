"""Private staging call state and encrypted enquiry/outbox; no application DB.

This is not a replacement for any historical spending journal. No audio is
recorded. Transactions serialize call admission, callback retries and stream
ownership, including across processes using the same private SQLite file.
"""
from contextlib import contextmanager, closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

from cryptography.fernet import Fernet
from business.voice_policy import service_scope


class CallConflict(ValueError):
    pass


class PilotStore:
    def __init__(self, root, encryption_key):
        root = Path(root)
        repo = Path(__file__).resolve().parents[1]
        if root.is_symlink() or not root.is_absolute():
            raise ValueError("Explicit private staging directory required")
        self.root = root.resolve()
        if any(self.root == p or p in self.root.parents for p in (repo, Path('/var/data'))) or self.root == Path('/'):
            raise ValueError("Staging storage must be outside repository and production")
        self.cipher = Fernet(encryption_key)
        self.path = self.root / 'private-pilot.sqlite3'
        if self.root.exists() and not self.path.exists() and any(self.root.iterdir()):
            raise ValueError('Use a new or empty dedicated staging directory')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.is_symlink():
            raise ValueError("Staging database must not be a symlink")
        fresh = not self.path.exists()
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        with closing(self.connect()) as db, db:
            if not fresh:
                row = db.execute("SELECT name FROM sqlite_master WHERE name='pilot_identity'").fetchone()
                if not row or db.execute('SELECT version FROM pilot_identity').fetchone()[0] != 1:
                    raise ValueError("Refuse an unrelated database")
            db.executescript('''
            CREATE TABLE IF NOT EXISTS pilot_identity(version INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS pilot_calls(
                sid TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE,
                content TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS pilot_webhooks(
                event_key TEXT PRIMARY KEY, digest TEXT NOT NULL, reply TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS pilot_enquiries(
                sid TEXT PRIMARY KEY, content TEXT NOT NULL, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS pilot_notifications(
                sid TEXT PRIMARY KEY, content TEXT NOT NULL, state TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS pilot_attempts(
                caller_hash TEXT PRIMARY KEY, count INTEGER NOT NULL, started REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS pilot_usage(
                sid TEXT NOT NULL, response_id TEXT NOT NULL, content TEXT NOT NULL,
                PRIMARY KEY(sid,response_id));
            CREATE TABLE IF NOT EXISTS pilot_response_requests(
                sid TEXT NOT NULL, ordinal INTEGER NOT NULL, state TEXT NOT NULL,
                response_id TEXT, PRIMARY KEY(sid,ordinal), UNIQUE(sid,response_id));
            ''')
            if fresh:
                db.execute('INSERT INTO pilot_identity VALUES(1)')
        os.chmod(self.path, 0o600)
        os.chmod(self.root, 0o700)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA secure_delete=ON')
        return db

    def seal(self, value):
        return self.cipher.encrypt(json.dumps(value, sort_keys=True).encode()).decode()

    def unseal(self, value):
        return json.loads(self.cipher.decrypt(value.encode()))

    @contextmanager
    def transaction(self):
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def load(self, db, token, now):
        row = db.execute('SELECT * FROM pilot_calls WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if row is None or now >= row['expires']:
            raise CallConflict('Unknown or expired call context')
        return self.unseal(row['content'])

    def save(self, db, call):
        db.execute('UPDATE pilot_calls SET content=? WHERE sid=?', (self.seal(call), call['sid']))

    def queue(self, db, call, facts, outcome, now):
        # Never reinterpret a provider event as an old simulation VoiceEvent.
        # Enquiry + notification commit together, once per root call. No sender.
        scope = service_scope(facts.get('description', ''), facts.get('urgency', 'routine'))
        payload = {'provider': 'twilio-private-pilot', 'call_sid': call['sid'],
                   'facts': facts, 'outcome': outcome, 'review_required': True,
                   'appointment_confirmed': False, 'attendance_guaranteed': False,
                   'callback_requested': call.get('callback', False),
                   'presented_phone_unconfirmed': call['caller'],
                   'service_scope': scope, 'gas_work_permitted': False,
                   'attendance_request': scope == 'plumbing',
                   'usage_uncertain': call.get('usage_uncertain', False)}
        db.execute('INSERT INTO pilot_enquiries VALUES(?,?,?) ON CONFLICT(sid) DO UPDATE SET content=excluded.content,updated=excluded.updated',
                   (call['sid'], self.seal(payload), now))
        db.execute("INSERT INTO pilot_notifications VALUES(?,?,'pending_review') ON CONFLICT(sid) DO UPDATE SET content=excluded.content",
                   (call['sid'], self.seal(payload)))

    def finish(self, token, facts, outcome, now=None):
        now = time.time() if now is None else now
        with self.transaction() as db:
            # Cleanup must work after a call deadline: expiry only bars admission.
            row = db.execute('SELECT content FROM pilot_calls WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
            if not row:
                raise CallConflict('Unknown call')
            call = self.unseal(row['content'])
            if call.get('final'):
                return
            call.update(final=True, stream_claimed=True, result=outcome)
            self.queue(db, call, facts, outcome, now)
            self.save(db, call)

    def recover_interrupted(self, now=None):
        """Explicit maintenance: expired non-final calls become review requests.

        A crashed media session is never reopened/replayed. No provider retry.
        """
        now = time.time() if now is None else now
        count = 0
        with self.transaction() as db:
            for row in db.execute('SELECT content FROM pilot_calls WHERE expires<=?', (now,)).fetchall():
                call = self.unseal(row['content'])
                if not call.get('final'):
                    call.update(final=True, result='interrupted',
                                usage_uncertain=call.get('stream_claimed', False), stream_claimed=True)
                    self.queue(db, call, {}, 'interrupted', now)
                    self.save(db, call)
                    count += 1
        return count

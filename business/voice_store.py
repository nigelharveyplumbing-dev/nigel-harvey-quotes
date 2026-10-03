"""Transactional voice records, lead reuse, retention and leased notification outbox.

All I/O is SQLite. Notification delivery is explicitly injected by local tests.
"""
import hashlib
import json
import secrets
from datetime import datetime, timezone
from business.db import get_db as app_get_db
from business.phone_numbers import normalise_uk_phone
from business.voice_security import settings, seal, unseal
from business.voice_policy import triage, PRIORITY

TRANSCRIPT_SECONDS = 30 * 86400
CALL_CONTENT_SECONDS = 90 * 86400
NOTIFICATION_SECONDS = 7 * 86400


def get_db():
    conn = app_get_db()
    conn.execute("PRAGMA secure_delete=ON")
    return conn


def init_voice_schema():
    settings()
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS voice_calls (
          id INTEGER PRIMARY KEY, provider TEXT NOT NULL, account TEXT NOT NULL,
          root_call_id TEXT NOT NULL, lead_id INTEGER, sequence INTEGER NOT NULL,
          started_at TEXT NOT NULL, ended_at TEXT, outcome TEXT NOT NULL,
          urgency TEXT NOT NULL, transfer_requested INTEGER NOT NULL DEFAULT 0,
          content TEXT, content_expires REAL NOT NULL, transcript_expires REAL NOT NULL,
          transcript_deleted_at REAL, redacted_at REAL, created_at REAL NOT NULL,
          UNIQUE(provider, account, root_call_id));
        CREATE TABLE IF NOT EXISTS voice_events (
          provider TEXT NOT NULL, account TEXT NOT NULL, event_id TEXT NOT NULL,
          call_id INTEGER NOT NULL, sequence INTEGER NOT NULL, digest TEXT NOT NULL,
          received_at REAL NOT NULL, PRIMARY KEY(provider, account, event_id));
        CREATE TABLE IF NOT EXISTS voice_transcripts (
          call_id INTEGER PRIMARY KEY, ciphertext TEXT NOT NULL, expires_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS voice_nonces (nonce TEXT PRIMARY KEY, expires_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS voice_notifications (
          id INTEGER PRIMARY KEY, call_id INTEGER NOT NULL, revision INTEGER NOT NULL,
          message_id TEXT NOT NULL UNIQUE, payload TEXT, state TEXT NOT NULL,
          attempts INTEGER NOT NULL DEFAULT 0, available_at REAL NOT NULL,
          lease_until REAL, claim_token TEXT, last_error TEXT, expires_at REAL NOT NULL,
          UNIQUE(call_id, revision));
        CREATE INDEX IF NOT EXISTS voice_notifications_due ON voice_notifications(state, available_at);
        """)
    conn.close()


def _customer_match(conn, facts):
    phone = normalise_uk_phone(facts["callback_phone"])
    if not (phone and facts["name_confirmed"] and facts["callback_confirmed"] and facts["name"]):
        return None, "unconfirmed"
    candidates = [row for row in conn.execute("SELECT id,name,phone FROM customers")
                  if normalise_uk_phone(row["phone"]) == phone]
    # A shared household number never silently chooses a person.
    if len(candidates) == 1 and candidates[0]["name"].strip().casefold() == facts["name"].casefold():
        return candidates[0]["id"], "matched"
    return None, "ambiguous" if candidates else "new"


def _lead_values(facts, now):
    context = {"source": "phone/AI", "postcode": facts["postcode"], "urgency": facts["urgency"]}
    details = facts["description"]
    if facts["additional_details"]:
        details += "\nAdditional details: " + facts["additional_details"]
    if facts["appointment_preference"]:
        details += "\nPreferred appointment (not booked): " + facts["appointment_preference"]
    return {"name": facts["name"], "phone": facts["callback_phone"], "address": facts["address"],
            "description": details, "source": "website-context-v1:" + json.dumps(context),
            "updated_at": datetime.fromtimestamp(now, timezone.utc).isoformat()}


def _queue(conn, call_id, sequence, payload, now):
    existing = conn.execute("SELECT id FROM voice_notifications WHERE call_id=? AND state='pending'", (call_id,)).fetchone()
    if existing:
        conn.execute("UPDATE voice_notifications SET payload=? WHERE id=?", (seal(payload), existing["id"]))
    else:
        conn.execute("""INSERT INTO voice_notifications
            (call_id,revision,message_id,payload,state,available_at,expires_at)
            VALUES(?,?,?,?, 'pending', ?, ?)""",
            (call_id, sequence, f"voice-{call_id}-{sequence}", seal(payload), now, now + NOTIFICATION_SECONDS))


def ingest(event, nonce, now=None):
    """One root call produces at most one lead, atomically with its outbox item."""
    settings()
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    payload = event.model_dump(mode="json")
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    key = (event.provider, event.account, event.root_call_id)
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM voice_nonces WHERE expires_at < ?", (now,))
        if conn.execute("SELECT 1 FROM voice_nonces WHERE nonce=?", (nonce,)).fetchone():
            raise PermissionError("Replayed voice authentication")
        conn.execute("INSERT INTO voice_nonces VALUES (?,?)", (nonce, now + 600))
        previous_event = conn.execute("SELECT * FROM voice_events WHERE provider=? AND account=? AND event_id=?",
                                      (event.provider, event.account, event.event_id)).fetchone()
        if previous_event:
            if previous_event["digest"] != digest:
                raise ValueError("Event identity conflicts with stored content")
            row = conn.execute("SELECT id,lead_id FROM voice_calls WHERE id=?", (previous_event["call_id"],)).fetchone()
            conn.commit()
            return {**dict(row), "result": "duplicate"}
        call = conn.execute("SELECT * FROM voice_calls WHERE provider=? AND account=? AND root_call_id=?", key).fetchone()
        if call and call["started_at"] != event.started_at.isoformat():
            raise ValueError("Root call start cannot change")
        if call and event.sequence == call["sequence"]:
            raise ValueError("Sequence already used")
        if call and (event.sequence < call["sequence"] or call["redacted_at"] is not None or now >= call["content_expires"]):
            result = "redacted" if call["redacted_at"] is not None else "expired" if now >= call["content_expires"] else "stale"
        else:
            if call and call["outcome"] != "in_progress":
                raise ValueError("Final call cannot be reopened")
            facts = payload["facts"]
            old_content = unseal(call["content"]) if call and call["content"] else {}
            old_facts = old_content.get("facts", {})
            for field, value in facts.items():
                if value == "" and old_facts.get(field):
                    facts[field] = old_facts[field]
            for field in ("name_confirmed", "callback_confirmed"):
                identity = "name" if field == "name_confirmed" else "callback_phone"
                if facts[identity] == old_facts.get(identity) and old_facts.get(field):
                    facts[field] = True
            # Scan caller facts only; assistant safety words must not raise severity.
            caller_text = " ".join(line.partition(":")[2] for line in event.transcript.splitlines() if line.startswith("Caller:"))
            urgency, guidance, transfer = triage(facts["description"] + " " + facts["additional_details"] + " " + caller_text, facts["urgency"])
            if call and PRIORITY[call["urgency"]] > PRIORITY[urgency]:
                urgency, guidance, transfer = triage("", call["urgency"])
            facts["urgency"] = urgency
            customer_id, match = _customer_match(conn, facts)
            lead_id = call["lead_id"] if call else None
            values = _lead_values(facts, now)
            if facts["description"] and lead_id is None:
                stamp = values["updated_at"]
                cursor = conn.execute("""INSERT INTO leads
                    (name,phone,email,address,job_type,description,status,source,created_at,
                    created_at_sort,updated_at,source_category,customer_id)
                    VALUES(?,?, '', ?, 'small', ?, 'new', ?, ?, ?, ?, 'Other', ?)""",
                    (values["name"], values["phone"], values["address"], values["description"], values["source"],
                     stamp, stamp, stamp, customer_id))
                lead_id = cursor.lastrowid
            elif lead_id:
                saved = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
                if saved is None:
                    raise ValueError("Linked lead was deleted; redact the call before retrying")
                # Only change fields still equal to our last write. Never reset
                # staff changes, workflow status, quote/job links or attribution.
                prior_values = old_content.get("lead_values", {})
                for field in ("name", "phone", "address", "description", "source"):
                    if saved[field] == prior_values.get(field):
                        conn.execute(f"UPDATE leads SET {field}=?, updated_at=? WHERE id=?", (values[field], values["updated_at"], lead_id))
                    else:
                        # Keep the last value WE wrote, so later snapshots also
                        # recognise and preserve the staff-owned edit.
                        values[field] = prior_values.get(field)
                if saved["customer_id"] is None and customer_id is not None:
                    conn.execute("UPDATE leads SET customer_id=? WHERE id=?", (customer_id, lead_id))
            content = {"facts": facts, "normalised_phone": normalise_uk_phone(facts["callback_phone"]),
                       "presented_phone": event.presented_phone or old_content.get("presented_phone", ""),
                       "normalised_presented_phone": normalise_uk_phone(event.presented_phone or old_content.get("presented_phone", "")),
                       "customer_match": match, "guidance": guidance, "lead_values": values,
                       "notice_version": event.notice_version, "prompt_version": event.prompt_version,
                       "model_version": event.model_version, "leg_id": event.leg_id,
                       "review_required": True, "synthetic": True}
            if not call:
                cursor = conn.execute("""INSERT INTO voice_calls
                    (provider,account,root_call_id,lead_id,sequence,started_at,ended_at,outcome,
                    urgency,transfer_requested,content,content_expires,transcript_expires,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (*key, lead_id, event.sequence, event.started_at.isoformat(),
                     event.ended_at.isoformat() if event.ended_at else None, event.outcome,
                     urgency, int(transfer), seal(content), now + CALL_CONTENT_SECONDS, now + TRANSCRIPT_SECONDS, now))
                call_id = cursor.lastrowid
                call = conn.execute("SELECT * FROM voice_calls WHERE id=?", (call_id,)).fetchone()
            else:
                call_id = call["id"]
                conn.execute("""UPDATE voice_calls SET lead_id=?,sequence=?,ended_at=?,outcome=?,urgency=?,
                    transfer_requested=?,content=? WHERE id=?""", (lead_id, event.sequence,
                    event.ended_at.isoformat() if event.ended_at else None, event.outcome, urgency,
                    int(transfer), seal(content), call_id))
            if event.transcript and call["transcript_deleted_at"] is None and now < call["transcript_expires"]:
                conn.execute("INSERT OR REPLACE INTO voice_transcripts VALUES(?,?,?)",
                             (call_id, seal(event.transcript), call["transcript_expires"]))
            if lead_id or urgency != "routine" or (facts["callback_phone"] and event.outcome == "incomplete"):
                _queue(conn, call_id, event.sequence, {"call_id": call_id, "lead_id": lead_id,
                       "urgency": urgency, "outcome": event.outcome, "facts": facts}, now)
            result = "created" if event.sequence == 1 else "updated"
        call_id = call["id"]
        conn.execute("INSERT INTO voice_events VALUES(?,?,?,?,?,?,?)",
                     (event.provider, event.account, event.event_id, call_id, event.sequence, digest, now))
        conn.commit()
        row = conn.execute("SELECT id,lead_id FROM voice_calls WHERE id=?", (call_id,)).fetchone()
        return {**dict(row), "result": result}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_call(call_id, now=None):
    settings()
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM voice_calls WHERE id=?", (call_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["content"] = unseal(row["content"]) if row["content"] and now < row["content_expires"] else None
        if result["content"]:
            result["content"].pop("lead_values", None)
        transcript = conn.execute("SELECT * FROM voice_transcripts WHERE call_id=? AND expires_at>?", (call_id, now)).fetchone()
        result["transcript"] = unseal(transcript["ciphertext"]) if transcript else None
        return result
    finally:
        conn.close()


def delete_transcript(call_id, now=None):
    settings()
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    conn = get_db()
    try:
        with conn:
            conn.execute("DELETE FROM voice_transcripts WHERE call_id=?", (call_id,))
            return conn.execute("UPDATE voice_calls SET transcript_deleted_at=COALESCE(transcript_deleted_at,?) WHERE id=?", (now, call_id)).rowcount > 0
    finally:
        conn.close()


def redact_lead_calls(conn, lead_id, now=None):
    """Called inside existing lead deletion transaction; keep replay tombstones."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='voice_calls'").fetchone():
        return
    conn.execute("PRAGMA secure_delete=ON")
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    ids = [r[0] for r in conn.execute("SELECT id FROM voice_calls WHERE lead_id=?", (lead_id,))]
    for call_id in ids:
        conn.execute("DELETE FROM voice_transcripts WHERE call_id=?", (call_id,))
        conn.execute("UPDATE voice_notifications SET payload=NULL,state='cancelled',claim_token=NULL WHERE call_id=?", (call_id,))
        conn.execute("UPDATE voice_calls SET content=NULL,lead_id=NULL,redacted_at=?,transcript_deleted_at=? WHERE id=?", (now, now, call_id))


def expire(now=None):
    """Explicit maintenance entry point; no scheduler/service is started."""
    settings()
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    conn = get_db()
    try:
        with conn:
            deleted = conn.execute("DELETE FROM voice_transcripts WHERE expires_at<=?", (now,)).rowcount
            conn.execute("UPDATE voice_calls SET transcript_deleted_at=COALESCE(transcript_deleted_at,?) WHERE transcript_expires<=?", (now, now))
            conn.execute("UPDATE voice_calls SET content=NULL WHERE content_expires<=?", (now,))
            conn.execute("UPDATE voice_notifications SET payload=NULL,state=CASE WHEN state='sent' THEN 'sent' ELSE 'expired' END,claim_token=NULL WHERE expires_at<=?", (now,))
            conn.execute("DELETE FROM voice_nonces WHERE expires_at<=?", (now,))
        return {"transcripts_deleted": deleted}
    finally:
        conn.close()


def deliver_one(sender, now=None):
    """At-least-once delivery with bounded retries and a recoverable lease.

    The sender receives a stable message ID and must deduplicate it if possible.
    No SMTP/provider sender is included or started in Phase 2.
    """
    settings()
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    conn = get_db()
    token = secrets.token_hex(16)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE voice_notifications SET state=CASE WHEN attempts>=5 THEN 'failed' ELSE 'pending' END,claim_token=NULL WHERE state='processing' AND lease_until<=?", (now,))
        row = conn.execute("""SELECT * FROM voice_notifications WHERE state='pending' AND available_at<=?
            AND expires_at>? AND attempts<5 ORDER BY id LIMIT 1""", (now, now)).fetchone()
        if row is None:
            conn.commit()
            return "idle"
        conn.execute("UPDATE voice_notifications SET state='processing',attempts=attempts+1,claim_token=?,lease_until=? WHERE id=?", (token, now + 120, row["id"]))
        conn.commit()
        try:
            sender(row["message_id"], unseal(row["payload"]))
        except Exception as exc:
            attempts = row["attempts"] + 1
            with conn:
                conn.execute("""UPDATE voice_notifications SET state=?,available_at=?,claim_token=NULL,
                    lease_until=NULL,last_error=? WHERE id=? AND claim_token=?""",
                    ("failed" if attempts >= 5 else "pending", now + min(3600, 30 * 2 ** attempts),
                     type(exc).__name__, row["id"], token))
            return "failed" if attempts >= 5 else "retry"
        with conn:
            conn.execute("""UPDATE voice_notifications SET state='sent',payload=NULL,claim_token=NULL,
                lease_until=NULL,last_error=NULL WHERE id=? AND claim_token=?""", (row["id"], token))
        return "sent"
    finally:
        conn.close()


def retry_notification(notification_id, now=None):
    settings()
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    conn = get_db()
    try:
        with conn:
            changed = conn.execute("""UPDATE voice_notifications SET state='pending',attempts=0,
                available_at=?,last_error=NULL WHERE id=? AND state='failed' AND expires_at>?
                AND payload IS NOT NULL""", (now, notification_id, now)).rowcount
        return changed > 0
    finally:
        conn.close()

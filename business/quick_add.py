"""Conservative, private message preview and atomic lead/visit creation."""

import re
import json
from datetime import datetime, timedelta

from business.db import get_db
from business.growth_tracking import SOURCES, WORK_TYPES
from business.job_pipeline import APPOINTMENT_STATUSES, validate_appointment
from business.lead_store import get_lead_by_id
from business.models import AppointmentRequest
from business.work_types import validate_work_types

PHONE = re.compile(r"(?<!\d)(?:\+44\s?\(?(?:0)?\)?\s?|0)\d[\d\s-]{8,14}\d(?!\d)")
EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
POSTCODE = re.compile(r"\b(?:GIR\s?0AA|[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2})\b", re.I)
EXPLICIT_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\s+(?:at\s+)?(\d{1,2}):(\d{2})\b", re.I)
NAME = re.compile(r"(?im)^\s*(?:name|from)\s*:\s*([^\n,]{2,80})\s*$")
SIGNOFF = re.compile(
    r"(?:^|\n)\s*(?i:best regards|regards|thanks)\s*,?\s*"
    r"([A-Z][A-Za-z'’-]*(?:\s+[A-Z][A-Za-z'’-]*){1,3})\s*\Z")
ADDRESS = re.compile(r"(?im)\b(?:(?:our|my|the)\s+)?address\s*(?::|is\b)\s*([^\r\n]{3,180})")
STREET = re.compile(
    r"(?im)^\s*(\d{1,4}[A-Za-z]?\s+[^\r\n]{3,160}\b(?:Road|Rd|Street|St|Avenue|Ave|"
    r"Lane|Ln|Close|Drive|Way|Crescent|Place|Terrace|Gardens|Court|Hill|Rise|Mews)\b"
    r"[^\r\n]*\b[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2})\s*$")

WORK_HINTS = (
    ("Tap", re.compile(r"\b(?:replace|repair|fix|install|leaking|dripping)\b.{0,35}\b(?:kitchen\s+|bathroom\s+)?tap\b|\btap\b.{0,35}\b(?:leak|drip|broken|replace|repair|fix|install)\w*\b", re.I)),
    ("Toilet / cistern", re.compile(r"\b(?:fix|repair|replace|install)\b.{0,35}\b(?:toilet|cistern)\b|\b(?:toilet|cistern|flush)\b.{0,45}\b(?:broken|fault|leak|flush|repair|fix|replace|isn't working|not working|doesn't work)\b", re.I)),
    ("Radiator / TRV", re.compile(r"\b(?:fix|repair|replace|install|leaking)\b.{0,35}\b(?:radiator|rad\s+valve|trv)\b|\b(?:radiator|rad\s+valve|trv)\b.{0,45}\b(?:valve|leak|drip|broken|repair|fix|replace|install)\w*\b", re.I)),
)


def suggested_work_types(message):
    # Concrete fixture/plumbing terms only; the preview is always editable.
    return [category for category, pattern in WORK_HINTS if pattern.search(message)]


def suggested_address(message):
    match = ADDRESS.search(message) or STREET.search(message)
    if not match:
        return ""
    address = match[1].strip(" ,.;")
    postcode = POSTCODE.search(address)
    if not postcode and not re.match(r"^(?:\d+[A-Za-z]?\b|flat\s+\d+\b)", address, re.I):
        return ""
    return (address[:postcode.end()] if postcode else address).strip(" ,.;")


def preview(message):
    message = message.strip()[:10000]
    if not message:
        raise ValueError("Paste a customer message first")
    phone = PHONE.search(message)
    email = EMAIL.search(message)
    postcode = POSTCODE.search(message)
    name = NAME.search(message) or SIGNOFF.search(message)
    explicit = EXPLICIT_DATE.search(message)
    starts_at = ends_at = ""
    if explicit:
        try:
            moment = datetime(int(explicit[3]), int(explicit[2]), int(explicit[1]),
                              int(explicit[4]), int(explicit[5]))
            starts_at = moment.strftime("%Y-%m-%dT%H:%M")
            ends_at = (moment + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
        except ValueError:
            pass
    return {"name": name[1].strip() if name else "", "phone": phone[0].strip() if phone else "",
            "email": email[0] if email else "", "address": suggested_address(message),
            "postcode": postcode[0].upper().replace(" ", "") if postcode else "",
            "description": message, "visit_starts_at": starts_at, "visit_ends_at": ends_at,
            "suggested_work_types": suggested_work_types(message),
            "needs_review": True,
            "hint": "Check all details. Dates are suggested only when a full day/month/year and time are explicit."}


def confirm(data, now, format_dt):
    if not 16 <= len(data.idempotency_key) <= 128:
        raise ValueError("Invalid submission key")
    if not data.description.strip() or not (data.name.strip() or data.phone.strip() or data.email.strip()):
        raise ValueError("Provide job details and a customer name, phone or email")
    if data.source_category and data.source_category not in SOURCES:
        raise ValueError("Invalid source")
    if data.work_type and data.work_type not in WORK_TYPES:
        raise ValueError("Invalid work type")
    validate_work_types(data.work_type, data.additional_work_types)
    visit = bool(data.visit_starts_at or data.visit_ends_at)
    if visit:
        if not (data.visit_starts_at and data.visit_ends_at):
            raise ValueError("Visit requires a start and end")
        validate_appointment(AppointmentRequest(lead_id=1, starts_at=data.visit_starts_at,
            ends_at=data.visit_ends_at, status=data.visit_status,
            provisional_follow_up=data.provisional_follow_up))
    elif data.provisional_follow_up:
        raise ValueError("A provisional follow-up requires a visit")
    conn = get_db()
    try:
        existing = conn.execute("SELECT id FROM leads WHERE quick_add_key=?", (data.idempotency_key,)).fetchone()
        if existing:
            return {"lead": get_lead_by_id(existing["id"]), "already_created": True}
        timestamp = now()
        name, phone, address = (data.name.strip()[:180], data.phone.strip()[:80],
                                data.address.strip()[:300])
        customer_id = None
        # A confirmed, identifiable customer can exist before any quote. Use
        # this same transaction so a failed lead/visit never leaves an orphan.
        if name and (phone or address):
            customer = (conn.execute("SELECT id FROM customers WHERE phone=? LIMIT 1", (phone,)).fetchone()
                        if phone else None)
            if not customer and address:
                customer = conn.execute("SELECT id FROM customers WHERE name=? AND address=? LIMIT 1",
                                        (name, address)).fetchone()
            if customer:
                customer_id = customer["id"]
            else:
                customer_id = conn.execute("""INSERT INTO customers
                    (name,address,phone,created_at,updated_at) VALUES (?,?,?,?,?)""",
                    (name, address, phone, timestamp.isoformat(), timestamp.isoformat())).lastrowid
        cur = conn.execute("""INSERT INTO leads
            (name,phone,email,address,job_type,description,status,source,created_at,
             created_at_sort,updated_at,source_category,work_type,additional_work_types,quick_add_key,customer_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (name, phone, data.email.strip()[:180], address, "small", data.description.strip()[:10000],
             "new", "manual", format_dt(timestamp), timestamp.isoformat(),
             timestamp.isoformat(), data.source_category or None, data.work_type or None,
             json.dumps(data.additional_work_types),
             data.idempotency_key, customer_id))
        lead_id = cur.lastrowid
        appointment_id = None
        if visit:
            cur = conn.execute("""INSERT INTO appointments
                (lead_id,kind,status,starts_at,ends_at,provisional_follow_up,notes,created_at,updated_at)
                VALUES (?,'site_visit',?,?,?,?,?,?,?)""",
                (lead_id, data.visit_status, data.visit_starts_at, data.visit_ends_at,
                 data.provisional_follow_up or None, "", timestamp.isoformat(), timestamp.isoformat()))
            appointment_id = cur.lastrowid
        conn.commit()
        return {"lead": get_lead_by_id(lead_id), "appointment_id": appointment_id,
                "already_created": False}
    finally:
        conn.close()

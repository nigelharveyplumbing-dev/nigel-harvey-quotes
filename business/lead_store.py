"""Existing website lead persistence and row presentation."""

from business.db import get_db
from business.models import LeadRequest
from business.growth_tracking import SOURCES, WORK_TYPES, inferred_source
from business.work_types import validate_work_types, read_additional
import json

SOURCE_PREFIX = "website-context-v1:"
CONTEXT_FIELDS = ("postcode", "urgency", "preferred_contact", "landing_page", "referrer",
                  "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")


def lead_source_with_context(data: LeadRequest) -> str:
    source = (data.source or "website").strip() or "website"
    context = {key: (getattr(data, key) or "").strip()[:300] for key in CONTEXT_FIELDS
               if (getattr(data, key) or "").strip()}
    if not context:
        return source
    return SOURCE_PREFIX + json.dumps({"source": source[:120], **context}, ensure_ascii=False,
                                      separators=(",", ":"))


def parse_lead_source(value: str) -> tuple[str, dict]:
    if value.startswith(SOURCE_PREFIX):
        try:
            data = json.loads(value[len(SOURCE_PREFIX):])
            if isinstance(data, dict) and isinstance(data.get("source"), str):
                return data["source"], {key: data[key] for key in CONTEXT_FIELDS
                                         if isinstance(data.get(key), str)}
        except (ValueError, TypeError):
            pass
    return value or "website", {}


def row_to_lead(row):
    source, context = parse_lead_source(row["source"] or "website")
    result = {
        "id": row["id"],
        "customer_id": row["customer_id"],
        "name": row["name"] or "",
        "phone": row["phone"] or "",
        "email": row["email"] or "",
        "address": row["address"] or "",
        "job_type": row["job_type"] or "small",
        "description": row["description"] or "",
        "status": row["status"] or "new",
        "source": source,
        "source_category": row["source_category"] or inferred_source(source, context),
        "work_type": row["work_type"] or "",
        "additional_work_types": read_additional(row["additional_work_types"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    return {**result, **context}


def save_lead(data: LeadRequest, now_uk, format_dt):
    validate_work_types(data.work_type, data.additional_work_types)
    now = now_uk()
    conn = get_db()
    conn.execute(
        """
        INSERT INTO leads (name, phone, email, address, job_type, description, status, source, created_at, created_at_sort, updated_at, source_category, work_type, additional_work_types)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (data.name or "").strip(),
            (data.phone or "").strip(),
            (data.email or "").strip(),
            (data.address or "").strip(),
            (data.job_type or "small").strip() or "small",
            (data.description or "").strip(),
            "new",
            lead_source_with_context(data),
            format_dt(now),
            now.isoformat(),
            now.isoformat(),
            data.source_category if data.source_category in SOURCES else None,
            data.work_type if data.work_type in WORK_TYPES else None,
            json.dumps(data.additional_work_types),
        ),
    )
    lead_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return get_lead_by_id(lead_id)


def get_lead_by_id(lead_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    conn.close()
    return row_to_lead(row) if row else None


def load_leads():
    conn = get_db()
    rows = conn.execute(
        """
        SELECT * FROM leads
        ORDER BY created_at_sort DESC, id DESC
        LIMIT 300
        """
    ).fetchall()
    conn.close()
    return [row_to_lead(r) for r in rows]


def update_lead_status(lead_id: int, status: str, now_uk):
    status = (status or "new").strip().lower()
    if status not in {"new", "contacted", "quoted", "won", "lost"}:
        status = "new"
    conn = get_db()
    cur = conn.execute(
        "UPDATE leads SET status = ?, updated_at = ? WHERE id = ?",
        (status, now_uk().isoformat(), lead_id),
    )
    conn.commit()
    conn.close()
    if cur.rowcount <= 0:
        return None
    return get_lead_by_id(lead_id)


def classify_lead(lead_id, source_category, work_type, now_uk, additional_work_types=None):
    if source_category and source_category not in SOURCES:
        raise ValueError("Invalid lead source")
    if work_type and work_type not in WORK_TYPES:
        raise ValueError("Invalid work type")
    conn = get_db()
    existing = conn.execute("SELECT additional_work_types FROM leads WHERE id=?", (lead_id,)).fetchone()
    if additional_work_types is None:
        additional_work_types = read_additional(existing["additional_work_types"]) if existing else []
        additional_work_types = [item for item in additional_work_types if item != work_type] if work_type else []
    validate_work_types(work_type, additional_work_types)
    cur = conn.execute("UPDATE leads SET source_category = ?, work_type = ?, additional_work_types=?, updated_at = ? WHERE id = ?",
                       (source_category or None, work_type or None, json.dumps(additional_work_types), now_uk().isoformat(), lead_id))
    conn.commit()
    conn.close()
    return get_lead_by_id(lead_id) if cur.rowcount else None


def delete_lead_by_id(lead_id: int):
    conn = get_db()
    if conn.execute("SELECT 1 FROM appointments WHERE lead_id=? LIMIT 1", (lead_id,)).fetchone() or \
       conn.execute("SELECT 1 FROM jobs WHERE lead_id=? LIMIT 1", (lead_id,)).fetchone():
        conn.close()
        raise ValueError("This lead has linked visits or jobs and cannot be deleted from this screen")
    cur = conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted

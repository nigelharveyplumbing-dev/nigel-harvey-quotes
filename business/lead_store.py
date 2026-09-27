"""Existing website lead persistence and row presentation."""

from business.db import get_db
from business.models import LeadRequest
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
        "name": row["name"] or "",
        "phone": row["phone"] or "",
        "email": row["email"] or "",
        "address": row["address"] or "",
        "job_type": row["job_type"] or "small",
        "description": row["description"] or "",
        "status": row["status"] or "new",
        "source": source,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    return {**result, **context}


def save_lead(data: LeadRequest, now_uk, format_dt):
    now = now_uk()
    conn = get_db()
    conn.execute(
        """
        INSERT INTO leads (name, phone, email, address, job_type, description, status, source, created_at, created_at_sort, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def delete_lead_by_id(lead_id: int):
    conn = get_db()
    cur = conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted

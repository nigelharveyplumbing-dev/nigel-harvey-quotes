"""Existing website lead persistence and row presentation."""

from business.db import get_db
from business.models import LeadRequest


def row_to_lead(row):
    return {
        "id": row["id"],
        "name": row["name"] or "",
        "phone": row["phone"] or "",
        "email": row["email"] or "",
        "address": row["address"] or "",
        "job_type": row["job_type"] or "small",
        "description": row["description"] or "",
        "status": row["status"] or "new",
        "source": row["source"] or "website",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


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
            (data.source or "website").strip() or "website",
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

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
    from business.enquiry_attribution import sanitize_context
    attribution = sanitize_context(context)
    context = {**{k:v for k,v in context.items() if k not in ("landing_page","referrer","utm_source","utm_medium","utm_campaign","utm_content","utm_term")},**attribution}
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
    source, context = parse_lead_source(row["source"] or "")
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
    if "origin_id" in row.keys():
        result["origin_id"] = row["origin_id"]
        if row["origin_id"]:
            from business.enquiry_attribution import origin
            with get_db() as c:
                current = origin(c,row["origin_id"])
            result["source_category"] = current["source"]
            result["record_kind"] = current["kind"]
            result["contact_channel"] = current["contact_channel"]
    return {**result, **context}


def save_lead(data: LeadRequest, now_uk, format_dt):
    validate_work_types(data.work_type, data.additional_work_types)
    with get_db() as check:
        from business.enquiry_attribution import enabled
        if enabled(check) and not data.analytics_consent:
            data = data.model_copy(update={key:'' for key in ('referrer','utm_source','utm_medium','utm_campaign','utm_content','utm_term')})
    now = now_uk()
    conn = get_db()
    try:
        from business import enquiry_attribution as attribution
        tracked = attribution.enabled(conn)
        if tracked:
            conn.execute("BEGIN IMMEDIATE")
            if data.submission_key and not 16 <= len(data.submission_key) <= 128:
                conn.close(); raise ValueError("Invalid enquiry submission key")
            old = conn.execute("SELECT id,submission_hash FROM leads WHERE submission_key=?", (data.submission_key,)).fetchone() if data.submission_key else None
            from business.payment_store import request_hash
            digest = request_hash(data.model_dump())
            if old:
                if old[1] != digest:
                    conn.close(); raise ValueError("Submission key reused for different details")
                conn.close(); return get_lead_by_id(old[0])
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
        if tracked:
            context = {key: getattr(data,key) for key in CONTEXT_FIELDS}
            oid = attribution.create_origin(conn,lead_id=lead_id,channel="Website form",context=context,method="website_observed")
            conn.execute("UPDATE leads SET origin_id=?,submission_key=?,submission_hash=? WHERE id=?", (oid,data.submission_key or None,digest,lead_id))
        conn.execute("INSERT INTO lead_email_notifications (lead_id) VALUES (?)", (lead_id,))
        conn.commit()
        conn.close()
        return get_lead_by_id(lead_id)
    finally:
        conn.close()


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
    from business import enquiry_attribution as attribution
    if attribution.enabled(conn):
        current = conn.execute("SELECT origin_id FROM leads WHERE id=?",(lead_id,)).fetchone()
        if current and current[0]:
            effective = attribution.origin(conn,current[0])["source"]
            if source_category and source_category != effective:
                conn.close(); raise ValueError("Use Original source details to correct source with an audit reason")
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


def _exclusive_quick_add_customer(conn, lead):
    """Only clean up a customer created with this exact Quick Add transaction."""
    customer_id = lead["customer_id"]
    if not (customer_id and lead["quick_add_key"]):
        return False
    customer = conn.execute("SELECT created_at FROM customers WHERE id=?", (customer_id,)).fetchone()
    if not customer or customer["created_at"] != lead["created_at_sort"]:
        return False
    return not any(conn.execute(query, parameters).fetchone() for query, parameters in (
        ("SELECT 1 FROM leads WHERE customer_id=? AND id<>? LIMIT 1", (customer_id, lead["id"])),
        ("SELECT 1 FROM quotes WHERE customer_id=? LIMIT 1", (customer_id,)),
        ("SELECT 1 FROM invoices WHERE customer_id=? LIMIT 1", (customer_id,)),
        ("SELECT 1 FROM jobs WHERE customer_id=? LIMIT 1", (customer_id,)),
    ))


def _lead_deletion_info(conn, lead_id):
    lead = conn.execute("SELECT id, customer_id, quick_add_key, created_at_sort FROM leads WHERE id=?",
                        (lead_id,)).fetchone()
    if not lead:
        return None
    reason = ""
    if conn.execute("SELECT 1 FROM quotes WHERE lead_id=? LIMIT 1", (lead_id,)).fetchone():
        reason = "This enquiry has a saved quote. Keep its history and mark it Lost or Expired instead."
    elif conn.execute("SELECT 1 FROM jobs WHERE lead_id=? LIMIT 1", (lead_id,)).fetchone():
        reason = "This enquiry has a plumbing job. Keep its work and invoice history instead of deleting it."
    elif conn.execute("""SELECT 1 FROM appointments WHERE lead_id=?
                         AND (kind!='site_visit' OR job_id IS NOT NULL) LIMIT 1""", (lead_id,)).fetchone():
        reason = "This enquiry has a plumbing job booking. It cannot be deleted from here."
    visits = conn.execute("SELECT COUNT(*) FROM appointments WHERE lead_id=? AND kind='site_visit'",
                          (lead_id,)).fetchone()[0]
    return {"can_delete": not reason, "reason": reason, "site_visit_count": visits,
            "customer_contact_will_be_deleted": not reason and _exclusive_quick_add_customer(conn, lead)}


def lead_deletion_info(lead_id: int):
    conn = get_db()
    try:
        return _lead_deletion_info(conn, lead_id)
    finally:
        conn.close()


def delete_lead_by_id(lead_id: int, confirmed_site_visits: int | None = None):
    conn = get_db()
    try:
        # Recheck inside the write transaction. A quote/job added after the
        # confirmation preview must never be removed or left dangling.
        conn.execute("BEGIN IMMEDIATE")
        from business.enquiry_attribution import protect_history
        protect_history(conn,"leads",lead_id)
        info = _lead_deletion_info(conn, lead_id)
        if not info:
            conn.rollback()
            return False
        if not info["can_delete"]:
            raise ValueError(info["reason"])
        if info["site_visit_count"] and confirmed_site_visits != info["site_visit_count"]:
            raise ValueError("Review and confirm the number of linked site visits before deleting this enquiry.")
        conn.execute("DELETE FROM appointments WHERE lead_id=? AND kind='site_visit' AND job_id IS NULL",
                     (lead_id,))
        customer_id = conn.execute("SELECT customer_id FROM leads WHERE id=?", (lead_id,)).fetchone()[0]
        conn.execute("DELETE FROM leads WHERE id=?", (lead_id,))
        conn.execute("DELETE FROM lead_email_notifications WHERE lead_id=?", (lead_id,))
        if info["customer_contact_will_be_deleted"]:
            conn.execute("DELETE FROM customers WHERE id=?", (customer_id,))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

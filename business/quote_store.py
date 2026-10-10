"""Quote storage and quote-to-invoice conversion.

The app supplies existing backup, customer, clock and invoice lookup boundaries.
"""

import json
from datetime import timedelta

from business.config import PAYMENT_LINK_BASE
from business.db import get_db
from business.growth_tracking import LOSS_REASONS, QUOTE_STATUSES, SOURCES, WORK_TYPES
from business.work_types import read_additional


def row_to_quote(row):
    result = {
        "id": row["id"],
        "customer_id": row["customer_id"],
        "customer_name": row["customer_name"] or "",
        "job": row["job"] or "",
        "total_price": round(row["total_price"] or 0, 2),
        "gross_profit": round(row["gross_profit"] or 0, 2),
        "margin_percent": round(row["margin_percent"] or 0, 2),
        "created_at": row["created_at"],
        "status": row["status"],
        "next_follow_up": row["next_follow_up"] or "",
        "loss_reason": row["loss_reason"] or "",
        "loss_note": row["loss_note"] or "",
        "lead_id": row["lead_id"],
        "source_category": row["source_category"] or "",
        "work_type": row["work_type"] or "",
        "additional_work_types": read_additional(row["additional_work_types"]),
        "origin_id": row["origin_id"] if "origin_id" in row.keys() else None,
        "request": json.loads(row["request_json"]),
        "result": json.loads(row["result_json"]),
    }
    if result['origin_id']:
        from business.enquiry_attribution import origin
        with get_db() as conn:
            current = origin(conn,result['origin_id'])
        result['captured_source_category'] = result['source_category']
        result['source_category'] = current['source']
    return result



def save_quote_intelligence(quote_id: int, result_data: dict, now_uk):
    try:
        conn = get_db()
        conn.execute("""
            INSERT INTO quote_intelligence (
                quote_id, quote_type, job, labour, materials, materials_base,
                procurement_amount, total_price, gross_profit, margin_percent, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            quote_id,
            result_data.get("quote_type", ""),
            result_data.get("job", ""),
            result_data.get("labour", 0),
            result_data.get("materials", 0),
            result_data.get("materials_base", result_data.get("materials", 0)),
            result_data.get("materials_procurement_amount", 0),
            result_data.get("total_price", 0),
            result_data.get("gross_profit", 0),
            result_data.get("margin_percent", 0),
            result_data.get("created_at_sort", now_uk().isoformat()),
        ))
        conn.commit()
        conn.close()
    except Exception:
        pass


def sync_lead_status_from_quotes(conn, lead_id, timestamp):
    """A linked lead reflects the strongest active outcome across its quotes."""
    statuses = {row["status"] for row in conn.execute(
        "SELECT status FROM quotes WHERE lead_id = ?", (lead_id,)).fetchall()}
    if not statuses:
        return
    if "won" in statuses:
        lead_status = "won"
    elif statuses <= {"lost", "expired"}:
        lead_status = "lost"
    else:
        lead_status = "quoted"
    conn.execute("UPDATE leads SET status = ?, updated_at = ? WHERE id = ? AND status != ?",
                 (lead_status, timestamp, lead_id, lead_status))


def save_quote(request_data: dict, result_data: dict, upsert_customer, now_uk):
    from business.enquiry_attribution import enabled
    with get_db() as c:
        if enabled(c):
            from business.revenue_mutations import save_quote as tracked_save
            qid,created = tracked_save(request_data,result_data,now_uk)
            if created:
                save_quote_intelligence(qid,result_data,now_uk)
            return qid
    lead_id = request_data.get("lead_id")
    source = request_data.get("source_category") or None
    work_type = request_data.get("work_type") or None
    additional = request_data.get("additional_work_types") or []
    if lead_id:
        check = get_db()
        found = check.execute("SELECT 1 FROM leads WHERE id = ?", (lead_id,)).fetchone()
        check.close()
        if not found:
            raise ValueError("Linked lead not found")
    customer_id = upsert_customer(
        request_data.get("customer_name", ""),
        request_data.get("customer_address", ""),
        request_data.get("customer_phone", ""),
    )

    conn = get_db()
    conn.execute("""
        INSERT INTO quotes (
            customer_id, customer_name, job, total_price, gross_profit, margin_percent,
            created_at, created_at_sort, request_json, result_json,
            status, lead_id, source_category, work_type, additional_work_types
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        customer_id,
        result_data.get("customer_name", ""),
        result_data.get("job", ""),
        result_data.get("total_price", 0),
        result_data.get("gross_profit", 0),
        result_data.get("margin_percent", 0),
        result_data.get("created_at", ""),
        result_data.get("created_at_sort", ""),
        json.dumps(request_data),
        json.dumps(result_data),
        "pending", lead_id, source, work_type, json.dumps(additional),
    ))
    quote_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    if lead_id:
        sync_lead_status_from_quotes(conn, lead_id, now_uk().isoformat())
    conn.commit()
    conn.close()
    save_quote_intelligence(quote_id, result_data, now_uk)
    return quote_id


def load_quotes():
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM quotes
        ORDER BY created_at_sort DESC, id DESC
        LIMIT 200
    """).fetchall()
    conn.close()
    return [row_to_quote(r) for r in rows]


def get_quote_by_id(quote_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM quotes WHERE id = ?", (quote_id,)).fetchone()
    conn.close()
    return row_to_quote(row) if row else None


def delete_quote_by_id(quote_id: int):
    conn = get_db()
    try:
        from business.enquiry_attribution import protect_history
        protect_history(conn,"quotes",quote_id)
        cur = conn.execute("DELETE FROM quotes WHERE id = ?", (quote_id,))
        conn.commit()
        deleted = cur.rowcount > 0
        conn.close()
        return deleted
    finally:
        conn.close()


def next_invoice_number(now_uk):
    year = now_uk().strftime("%Y")
    conn = get_db()
    row = conn.execute("""
        SELECT COUNT(*) AS cnt
        FROM invoices
        WHERE invoice_number LIKE ?
    """, (f"INV-{year}-%",)).fetchone()
    conn.close()
    seq = (row["cnt"] or 0) + 1
    return f"INV-{year}-{seq:04d}"


def build_payment_link(invoice_number: str):
    if PAYMENT_LINK_BASE:
        return PAYMENT_LINK_BASE.rstrip("/") + "/" + invoice_number
    return ""


def create_invoice_from_quote(quote_id: int, now_uk, format_dt, get_invoice_by_id):
    from business.enquiry_attribution import enabled
    with get_db() as c:
        if enabled(c):
            from business.revenue_mutations import create_invoice
            iid=create_invoice(quote_id,now_uk,format_dt)
            return get_invoice_by_id(iid) if iid else None
    quote = get_quote_by_id(quote_id)
    if not quote:
        return None

    result = quote["result"]
    invoice_number = next_invoice_number(now_uk)
    due_date = (now_uk() + timedelta(days=14)).strftime("%d/%m/%Y")
    payment_link = build_payment_link(invoice_number)

    invoice_payload = {
        "invoice_number": invoice_number,
        "quote_id": quote["id"],
        "customer_name": result.get("customer_name", ""),
        "customer_address": result.get("customer_address", ""),
        "customer_phone": result.get("customer_phone", ""),
        "job": result.get("job", ""),
        "labour": result.get("labour", 0),
        "callout_charge": result.get("callout_charge", 0),
        "travel_charge": result.get("travel_charge", 0),
        "materials": result.get("materials", 0),
        "total_price": result.get("total_price", 0),
        "deposit_percent": result.get("deposit_percent", 0),
        "deposit_amount": result.get("deposit_amount", 0),
        "due_date": due_date,
        "payment_link": payment_link,
        "job_reference": "",
        "status": "unpaid",
        "amount_paid": 0.0,
        "balance_due": result.get("total_price", 0),
    }

    conn = get_db()
    conn.execute("""
        INSERT INTO invoices (
            quote_id, customer_id, invoice_number, customer_name, total_price, amount_paid, balance_due,
            status, due_date, payment_link, job_reference, reminder_email, reminders_enabled, last_reminder_at,
            created_at, created_at_sort, quote_result_json, invoice_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        quote["id"],
        quote["customer_id"],
        invoice_number,
        result.get("customer_name", ""),
        result.get("total_price", 0),
        0.0,
        result.get("total_price", 0),
        "unpaid",
        due_date,
        payment_link,
        "",
        "",
        0,
        "",
        format_dt(now_uk()),
        now_uk().isoformat(),
        json.dumps(result),
        json.dumps(invoice_payload),
    ))
    invoice_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return get_invoice_by_id(invoice_id)


def update_quote_by_id(quote_id: int, request_data: dict, result_data: dict, upsert_customer):
    existing = get_quote_by_id(quote_id)
    if not existing:
        return None

    from business import enquiry_attribution as attribution
    with get_db() as check:
        tracked = attribution.enabled(check)
    if tracked and request_data.get("lead_id") not in (None,existing["lead_id"]):
        raise ValueError("Original enquiry link cannot be changed in a quote edit")
    if tracked:
        if request_data.get('customer_id') not in (None,existing['customer_id']):
            raise ValueError('Customer relationship cannot be changed in a quote edit')
        result_data = {**result_data,"created_at":existing["created_at"],"created_at_sort":existing["result"].get("created_at_sort",existing["created_at"])}
        request_data = {**request_data,"source_category":existing["source_category"]}
    lead_id = request_data.get("lead_id") or existing["lead_id"]
    if lead_id:
        check = get_db()
        found = check.execute("SELECT 1 FROM leads WHERE id = ?", (lead_id,)).fetchone()
        check.close()
        if not found:
            raise ValueError("Linked lead not found")
    customer_id = existing["customer_id"] if tracked else upsert_customer(
        request_data.get("customer_name", ""),
        request_data.get("customer_address", ""),
        request_data.get("customer_phone", ""),
    )

    conn = get_db()
    request_data = {**request_data, "lead_id": lead_id,
                    "source_category": request_data.get("source_category") or existing["source_category"],
                    "work_type": request_data.get("work_type") or existing["work_type"],
                    "additional_work_types": request_data.get("additional_work_types", existing["additional_work_types"])}
    conn.execute("""
        UPDATE quotes
        SET customer_id = ?, customer_name = ?, job = ?, total_price = ?, gross_profit = ?, margin_percent = ?,
            created_at = ?, created_at_sort = ?, request_json = ?, result_json = ?,
            lead_id = ?, source_category = ?, work_type = ?, additional_work_types = ?
        WHERE id = ?
    """, (
        customer_id,
        result_data.get("customer_name", ""),
        result_data.get("job", ""),
        result_data.get("total_price", 0),
        result_data.get("gross_profit", 0),
        result_data.get("margin_percent", 0),
        result_data.get("created_at", existing["created_at"]),
        result_data.get("created_at_sort", existing["result"].get("created_at_sort", existing["created_at"])),
        json.dumps(request_data),
        json.dumps(result_data),
        lead_id, request_data.get("source_category") or existing["source_category"] or None,
        request_data.get("work_type") or existing["work_type"] or None,
        json.dumps(request_data["additional_work_types"]),
        quote_id,
    ))
    conn.commit()
    conn.close()
    return get_quote_by_id(quote_id)


def update_quote_outcome(quote_id, status, next_follow_up, loss_reason, loss_note, now_uk):
    status = status.strip().lower()
    if status not in QUOTE_STATUSES:
        raise ValueError("Invalid quote status")
    if next_follow_up:
        from datetime import date
        try:
            if date.fromisoformat(next_follow_up).isoformat() != next_follow_up:
                raise ValueError
        except ValueError:
            raise ValueError("Use a valid YYYY-MM-DD follow-up date") from None
    if loss_reason and loss_reason not in LOSS_REASONS:
        raise ValueError("Invalid loss reason")
    conn = get_db()
    row = conn.execute("SELECT lead_id,status FROM quotes WHERE id = ?", (quote_id,)).fetchone()
    if not row:
        conn.close()
        return None
    from business.enquiry_attribution import enabled
    if enabled(conn):
        if status == "lost" and not loss_reason:
            conn.close(); raise ValueError("Select a reason for the lost quote")
        if row['status'] in ('won','lost','expired') and row['status'] != status and not (loss_note or loss_reason):
            conn.close(); raise ValueError("Provide an audit note when reopening/changing a decided quote")
        from business.workflow_history import append
        append(conn,"quote",quote_id,row["status"],status,reason=loss_note or loss_reason)
    timestamp = now_uk().isoformat()
    conn.execute("""UPDATE quotes SET status = ?, next_follow_up = ?, loss_reason = ?,
                   loss_note = ?, outcome_updated_at = ? WHERE id = ?""",
                 (status, next_follow_up if status == "pending" else None,
                  loss_reason if status == "lost" else None,
                  loss_note[:500] if status == "lost" else None, timestamp, quote_id))
    if row["lead_id"]:
        sync_lead_status_from_quotes(conn, row["lead_id"], timestamp)
    conn.commit()
    conn.close()
    return get_quote_by_id(quote_id)

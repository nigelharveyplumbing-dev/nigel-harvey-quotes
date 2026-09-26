"""Quote storage and quote-to-invoice conversion.

The app supplies existing backup, customer, clock and invoice lookup boundaries.
"""

import json
from datetime import timedelta

from business.config import PAYMENT_LINK_BASE
from business.db import get_db


def row_to_quote(row):
    return {
        "id": row["id"],
        "customer_id": row["customer_id"],
        "customer_name": row["customer_name"] or "",
        "job": row["job"] or "",
        "total_price": round(row["total_price"] or 0, 2),
        "gross_profit": round(row["gross_profit"] or 0, 2),
        "margin_percent": round(row["margin_percent"] or 0, 2),
        "created_at": row["created_at"],
        "request": json.loads(row["request_json"]),
        "result": json.loads(row["result_json"]),
    }


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


def save_quote(request_data: dict, result_data: dict, upsert_customer, now_uk):
    customer_id = upsert_customer(
        request_data.get("customer_name", ""),
        request_data.get("customer_address", ""),
        request_data.get("customer_phone", ""),
    )

    conn = get_db()
    conn.execute("""
        INSERT INTO quotes (
            customer_id, customer_name, job, total_price, gross_profit, margin_percent,
            created_at, created_at_sort, request_json, result_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    ))
    quote_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
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
    cur = conn.execute("DELETE FROM quotes WHERE id = ?", (quote_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


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

    customer_id = upsert_customer(
        request_data.get("customer_name", ""),
        request_data.get("customer_address", ""),
        request_data.get("customer_phone", ""),
    )

    conn = get_db()
    conn.execute("""
        UPDATE quotes
        SET customer_id = ?, customer_name = ?, job = ?, total_price = ?, gross_profit = ?, margin_percent = ?,
            created_at = ?, created_at_sort = ?, request_json = ?, result_json = ?
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
        quote_id,
    ))
    conn.commit()
    conn.close()
    return get_quote_by_id(quote_id)



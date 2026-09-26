"""Invoice persistence with the existing row presentation supplied by the app."""

import json
import shutil

from business.config import INVOICE_PHOTO_DIR
from business.db import get_db
from business.models import InvoiceEditRequest


def get_invoice_by_id(invoice_id: int, row_to_invoice):
    conn = get_db()
    row = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    conn.close()
    return row_to_invoice(row) if row else None


def load_invoices(row_to_invoice):
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM invoices
        ORDER BY created_at_sort DESC, id DESC
        LIMIT 200
    """).fetchall()
    conn.close()
    return [row_to_invoice(r) for r in rows]


def delete_invoice_by_id(invoice_id: int):
    conn = get_db()
    conn.execute("DELETE FROM invoice_photos WHERE invoice_id = ?", (invoice_id,))
    cur = conn.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    if deleted:
        shutil.rmtree(INVOICE_PHOTO_DIR / str(invoice_id), ignore_errors=True)
    return deleted


def update_invoice_status(invoice_id: int, status: str, amount_paid: float, row_to_invoice, safe_float):
    invoice = get_invoice_by_id(invoice_id, row_to_invoice)
    if not invoice:
        return None

    total = safe_float(invoice["total_price"])
    amount_paid = max(0.0, min(total, safe_float(amount_paid)))
    balance_due = max(0.0, total - amount_paid)

    status = (status or "").lower().strip()
    if status not in {"unpaid", "part paid", "paid"}:
        status = "unpaid"

    if amount_paid <= 0:
        status = "unpaid"
    elif amount_paid >= total:
        status = "paid"
    else:
        status = "part paid"

    invoice_payload = invoice["invoice"]
    invoice_payload["status"] = status
    invoice_payload["amount_paid"] = round(amount_paid, 2)
    invoice_payload["balance_due"] = round(balance_due, 2)

    conn = get_db()
    conn.execute("""
        UPDATE invoices
        SET amount_paid = ?, balance_due = ?, status = ?, invoice_json = ?
        WHERE id = ?
    """, (
        round(amount_paid, 2),
        round(balance_due, 2),
        status,
        json.dumps(invoice_payload),
        invoice_id,
    ))
    conn.commit()
    conn.close()
    return get_invoice_by_id(invoice_id, row_to_invoice)


def update_invoice_by_id(invoice_id: int, data: InvoiceEditRequest, row_to_invoice, safe_float, upsert_customer):
    invoice = get_invoice_by_id(invoice_id, row_to_invoice)
    if not invoice:
        return None

    customer_name = (data.customer_name or "").strip()
    customer_address = (data.customer_address or "").strip()
    customer_phone = (data.customer_phone or "").strip()
    job = (data.job or "").strip()
    due_date = (data.due_date or "").strip() or invoice["due_date"]
    payment_link = (data.payment_link or "").strip()
    job_reference = (data.job_reference or "").strip()
    reminder_email = (data.reminder_email or "").strip()
    reminders_enabled = bool(data.reminders_enabled)

    labour = max(0.0, safe_float(data.labour, 0.0))
    callout_charge = max(0.0, safe_float(data.callout_charge, 0.0))
    travel_charge = max(0.0, safe_float(data.travel_charge, 0.0))
    materials = max(0.0, safe_float(data.materials, 0.0))
    total_price = round(labour + callout_charge + travel_charge + materials, 2)
    amount_paid = max(0.0, min(total_price, safe_float(data.amount_paid, 0.0)))
    balance_due = max(0.0, round(total_price - amount_paid, 2))

    if amount_paid <= 0:
        status = "unpaid"
    elif amount_paid >= total_price:
        status = "paid"
    else:
        status = "part paid"

    customer_id = upsert_customer(customer_name, customer_address, customer_phone)

    quote_result = invoice["quote_result"]
    quote_result["customer_name"] = customer_name
    quote_result["customer_address"] = customer_address
    quote_result["customer_phone"] = customer_phone
    quote_result["job"] = job
    quote_result["labour"] = round(labour, 2)
    quote_result["callout_charge"] = round(callout_charge, 2)
    quote_result["include_callout_charge"] = callout_charge > 0
    quote_result["travel_charge"] = round(travel_charge, 2)
    quote_result["include_travel_charge"] = travel_charge > 0
    quote_result["materials"] = round(materials, 2)
    quote_result["materials_base"] = round(quote_result.get("materials_base", materials), 2)
    quote_result["materials_procurement_amount"] = round(quote_result.get("materials_procurement_amount", 0), 2)
    quote_result["materials_procurement_percent"] = round(quote_result.get("materials_procurement_percent", 0), 2)
    quote_result["total_price"] = round(total_price, 2)
    deposit_percent = safe_float(quote_result.get("deposit_percent", 0), 0)
    quote_result["deposit_amount"] = round(total_price * (deposit_percent / 100.0), 2)
    gross_profit = round(labour + materials - safe_float(quote_result.get("internal_raw_materials", 0), 0), 2)
    quote_result["gross_profit"] = gross_profit
    quote_result["margin_percent"] = round((gross_profit / total_price * 100.0), 2) if total_price > 0 else 0.0

    invoice_payload = invoice["invoice"]
    invoice_payload.update({
        "customer_name": customer_name,
        "customer_address": customer_address,
        "customer_phone": customer_phone,
        "job": job,
        "labour": round(labour, 2),
        "callout_charge": round(callout_charge, 2),
        "travel_charge": round(travel_charge, 2),
        "materials": round(materials, 2),
        "total_price": round(total_price, 2),
        "due_date": due_date,
        "payment_link": payment_link,
        "job_reference": job_reference,
        "status": status,
        "amount_paid": round(amount_paid, 2),
        "balance_due": round(balance_due, 2),
    })

    conn = get_db()
    conn.execute("""
        UPDATE invoices
        SET customer_id = ?, customer_name = ?, total_price = ?, amount_paid = ?, balance_due = ?, status = ?,
            due_date = ?, payment_link = ?, job_reference = ?, reminder_email = ?, reminders_enabled = ?,
            quote_result_json = ?, invoice_json = ?
        WHERE id = ?
    """, (
        customer_id,
        customer_name,
        round(total_price, 2),
        round(amount_paid, 2),
        round(balance_due, 2),
        status,
        due_date,
        payment_link,
        job_reference,
        reminder_email,
        1 if reminders_enabled else 0,
        json.dumps(quote_result),
        json.dumps(invoice_payload),
        invoice_id,
    ))
    conn.commit()
    conn.close()
    return get_invoice_by_id(invoice_id, row_to_invoice)

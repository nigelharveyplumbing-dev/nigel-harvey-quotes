"""Existing customer matching, listing, history and cascade deletion."""

from business.db import get_db


def upsert_customer(name: str, address: str, phone: str, now_uk):
    name = (name or "").strip()
    address = (address or "").strip()
    phone = (phone or "").strip()

    conn = get_db()
    now = now_uk().isoformat()

    if phone:
        row = conn.execute("SELECT * FROM customers WHERE phone = ? LIMIT 1", (phone,)).fetchone()
        if row:
            conn.execute(
                "UPDATE customers SET name = ?, address = ?, updated_at = ? WHERE id = ?",
                (name or row["name"], address or row["address"], now, row["id"])
            )
            conn.commit()
            conn.close()
            return row["id"]

    if name and address:
        row = conn.execute(
            "SELECT * FROM customers WHERE name = ? AND address = ? LIMIT 1",
            (name, address)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE customers SET phone = ?, updated_at = ? WHERE id = ?",
                (phone or row["phone"], now, row["id"])
            )
            conn.commit()
            conn.close()
            return row["id"]

    conn.execute(
        "INSERT INTO customers (name, address, phone, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (name, address, phone, now, now)
    )
    customer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return customer_id


def get_customers():
    conn = get_db()
    rows = conn.execute("""
        SELECT *
        FROM customers
        ORDER BY updated_at DESC, id DESC
        LIMIT 200
    """).fetchall()
    conn.close()

    out = []
    for row in rows:
        out.append({
            "id": row["id"],
            "name": row["name"] or "",
            "address": row["address"] or "",
            "phone": row["phone"] or "",
            "updated_at": row["updated_at"],
        })
    return out


def get_customer_history(customer_id: int, row_to_quote, row_to_invoice):
    conn = get_db()
    customer = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if not customer:
        conn.close()
        return None

    quotes = conn.execute("""
        SELECT * FROM quotes
        WHERE customer_id = ?
        ORDER BY created_at_sort DESC, id DESC
        LIMIT 50
    """, (customer_id,)).fetchall()

    invoices = conn.execute("""
        SELECT * FROM invoices
        WHERE customer_id = ?
        ORDER BY created_at_sort DESC, id DESC
        LIMIT 50
    """, (customer_id,)).fetchall()
    conn.close()

    return {
        "customer": {
            "id": customer["id"],
            "name": customer["name"] or "",
            "address": customer["address"] or "",
            "phone": customer["phone"] or "",
        },
        "quotes": [row_to_quote(r) for r in quotes],
        "invoices": [row_to_invoice(r) for r in invoices],
    }


def delete_customer_by_id(customer_id: int):
    conn = get_db()

    customer = conn.execute(
        "SELECT id FROM customers WHERE id = ?", (customer_id,)
    ).fetchone()

    if not customer:
        conn.close()
        return None

    deleted_invoices = conn.execute(
        "DELETE FROM invoices WHERE customer_id = ?", (customer_id,)
    ).rowcount
    deleted_quotes = conn.execute(
        "DELETE FROM quotes WHERE customer_id = ?", (customer_id,)
    ).rowcount
    deleted_customers = conn.execute(
        "DELETE FROM customers WHERE id = ?", (customer_id,)
    ).rowcount

    conn.commit()
    conn.close()

    return {
        "ok": True,
        "deleted_customers": deleted_customers,
        "deleted_quotes": deleted_quotes,
        "deleted_invoices": deleted_invoices,
    }

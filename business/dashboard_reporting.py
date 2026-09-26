"""Read-only dashboard summaries over the existing quote and invoice tables."""

from datetime import datetime


def get_dashboard(get_db, now_uk):
    now = now_uk()
    month_prefix = now.strftime("%Y-%m")

    conn = get_db()

    q = conn.execute("""
        SELECT
            COUNT(*) AS quote_count,
            COALESCE(SUM(total_price), 0) AS quoted_total,
            COALESCE(SUM(gross_profit), 0) AS gross_profit_total
        FROM quotes
        WHERE substr(created_at_sort, 1, 7) = ?
    """, (month_prefix,)).fetchone()

    i = conn.execute("""
        SELECT
            COUNT(*) AS invoice_count,
            COALESCE(SUM(total_price), 0) AS invoiced_total,
            COALESCE(SUM(amount_paid), 0) AS paid_total,
            COALESCE(SUM(balance_due), 0) AS balance_total
        FROM invoices
        WHERE substr(created_at_sort, 1, 7) = ?
    """, (month_prefix,)).fetchone()

    avg = conn.execute("""
        SELECT COALESCE(AVG(total_price), 0) AS avg_quote
        FROM quotes
        WHERE substr(created_at_sort, 1, 7) = ?
    """, (month_prefix,)).fetchone()

    customers = conn.execute("SELECT COUNT(*) AS customer_count FROM customers").fetchone()

    conn.close()

    return {
        "month_label": now.strftime("%B %Y"),
        "quote_count": q["quote_count"] or 0,
        "quoted_total": round(q["quoted_total"] or 0, 2),
        "gross_profit_total": round(q["gross_profit_total"] or 0, 2),
        "invoice_count": i["invoice_count"] or 0,
        "invoiced_total": round(i["invoiced_total"] or 0, 2),
        "paid_total": round(i["paid_total"] or 0, 2),
        "balance_total": round(i["balance_total"] or 0, 2),
        "avg_quote": round(avg["avg_quote"] or 0, 2),
        "customer_count": customers["customer_count"] or 0,
    }


def get_monthly_profit_series(month_count, get_db, month_labels):
    labels = month_labels(month_count)
    conn = get_db()
    out = []
    for month_prefix in labels:
        row = conn.execute("""
            SELECT
                COALESCE(SUM(total_price), 0) AS revenue,
                COALESCE(SUM(gross_profit), 0) AS profit
            FROM quotes
            WHERE substr(created_at_sort, 1, 7) = ?
        """, (month_prefix,)).fetchone()
        out.append({
            "month_key": month_prefix,
            "label": datetime.strptime(month_prefix + '-01', '%Y-%m-%d').strftime('%b %Y'),
            "revenue": round(row['revenue'] or 0, 2),
            "profit": round(row['profit'] or 0, 2),
        })
    conn.close()
    return out

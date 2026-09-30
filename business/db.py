"""Shared SQLite connection, schema initialization and row counts."""

import sqlite3

from business.config import DB_PATH

def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            address TEXT,
            phone TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            customer_name TEXT,
            job TEXT,
            total_price REAL,
            gross_profit REAL,
            margin_percent REAL,
            created_at TEXT NOT NULL,
            created_at_sort TEXT NOT NULL,
            request_json TEXT NOT NULL,
            result_json TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quote_id INTEGER,
            customer_id INTEGER,
            invoice_number TEXT NOT NULL,
            customer_name TEXT,
            total_price REAL,
            amount_paid REAL,
            balance_due REAL,
            status TEXT NOT NULL,
            due_date TEXT NOT NULL,
            payment_link TEXT,
            job_reference TEXT,
            reminder_email TEXT,
            reminders_enabled INTEGER NOT NULL DEFAULT 0,
            last_reminder_at TEXT,
            created_at TEXT NOT NULL,
            created_at_sort TEXT NOT NULL,
            quote_result_json TEXT NOT NULL,
            invoice_json TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS invoice_photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            category TEXT NOT NULL DEFAULT 'after',
            caption TEXT,
            filename TEXT NOT NULL,
            original_filename TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT,
            email TEXT,
            address TEXT,
            job_type TEXT,
            description TEXT,
            status TEXT NOT NULL,
            source TEXT,
            created_at TEXT NOT NULL,
            created_at_sort TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS material_price_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL UNIQUE,
            name TEXT,
            supplier TEXT,
            last_price REAL,
            last_live_price REAL,
            last_manual_price REAL,
            last_status TEXT NOT NULL,
            times_used INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_checked_at TEXT,
            last_success_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS material_price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_url TEXT NOT NULL,
            name TEXT,
            supplier TEXT,
            price REAL,
            source TEXT NOT NULL,
            checked_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quote_intelligence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quote_id INTEGER,
            quote_type TEXT,
            job TEXT,
            labour REAL,
            materials REAL,
            materials_base REAL,
            procurement_amount REAL,
            total_price REAL,
            gross_profit REAL,
            margin_percent REAL,
            created_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS app_backups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            path TEXT NOT NULL,
            reason TEXT,
            size_bytes INTEGER,
            created_at TEXT NOT NULL
        )
    """)
    existing_invoice_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(invoices)").fetchall()
    }
    if "job_reference" not in existing_invoice_columns:
        conn.execute("ALTER TABLE invoices ADD COLUMN job_reference TEXT")
    if "reminder_email" not in existing_invoice_columns:
        conn.execute("ALTER TABLE invoices ADD COLUMN reminder_email TEXT")
    if "reminders_enabled" not in existing_invoice_columns:
        conn.execute("ALTER TABLE invoices ADD COLUMN reminders_enabled INTEGER NOT NULL DEFAULT 0")
    if "last_reminder_at" not in existing_invoice_columns:
        conn.execute("ALTER TABLE invoices ADD COLUMN last_reminder_at TEXT")

    # Additive migration. Historical quotes keep an unknown outcome; the app
    # must not count them as pending or won without Nigel's confirmation.
    quote_columns = {row["name"] for row in conn.execute("PRAGMA table_info(quotes)")}
    for name, definition in {
        "status": "TEXT NOT NULL DEFAULT 'unclassified'",
        "next_follow_up": "TEXT",
        "loss_reason": "TEXT",
        "loss_note": "TEXT",
        "outcome_updated_at": "TEXT",
        "lead_id": "INTEGER",
        "source_category": "TEXT",
        "work_type": "TEXT",
        "additional_work_types": "TEXT NOT NULL DEFAULT '[]'",
    }.items():
        if name not in quote_columns:
            conn.execute(f"ALTER TABLE quotes ADD COLUMN {name} {definition}")
    lead_columns = {row["name"] for row in conn.execute("PRAGMA table_info(leads)")}
    for name in ("source_category", "work_type"):
        if name not in lead_columns:
            conn.execute(f"ALTER TABLE leads ADD COLUMN {name} TEXT")
    if "additional_work_types" not in lead_columns:
        conn.execute("ALTER TABLE leads ADD COLUMN additional_work_types TEXT NOT NULL DEFAULT '[]'")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_quotes_lead_id ON quotes (lead_id)")

    # Batch 7 records are additive. An appointment may predate any quote, while
    # a job can link to an existing lead, quote or invoice as work progresses.
    conn.execute("""CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL,
        job_id INTEGER,
        kind TEXT NOT NULL,
        status TEXT NOT NULL,
        starts_at TEXT NOT NULL,
        ends_at TEXT NOT NULL,
        provisional_follow_up TEXT,
        notes TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_appointments_start ON appointments(starts_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_appointments_lead ON appointments(lead_id)")
    conn.execute("""CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER,
        quote_id INTEGER,
        invoice_id INTEGER,
        customer_id INTEGER,
        title TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'awaiting_schedule',
        notes TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_lead ON jobs(lead_id)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_quote ON jobs(quote_id) WHERE quote_id IS NOT NULL")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_invoice ON jobs(invoice_id) WHERE invoice_id IS NOT NULL")
    if "quick_add_key" not in {row["name"] for row in conn.execute("PRAGMA table_info(leads)")}:
        conn.execute("ALTER TABLE leads ADD COLUMN quick_add_key TEXT")
    if "customer_id" not in {row["name"] for row in conn.execute("PRAGMA table_info(leads)")}:
        conn.execute("ALTER TABLE leads ADD COLUMN customer_id INTEGER")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_quick_add_key ON leads(quick_add_key) WHERE quick_add_key IS NOT NULL")

    conn.commit()
    conn.close()


def database_counts():
    conn = get_db()
    tables = ["customers", "quotes", "invoices", "leads", "material_price_cache"]
    counts = {}
    for table in tables:
        try:
            counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except Exception:
            counts[table] = None
    conn.close()
    return counts

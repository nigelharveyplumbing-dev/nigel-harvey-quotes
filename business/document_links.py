"""Phased, revocable bearer links. Never print tokens or redirect numbered URLs."""

import os
import logging
import re
import secrets


def mode():
    value = os.getenv("CUSTOMER_DOCUMENT_LINK_MODE", "legacy").strip().lower()
    if value not in {"legacy", "prepare", "secure"}:
        raise RuntimeError("Invalid CUSTOMER_DOCUMENT_LINK_MODE")
    return value


def enabled():
    return mode() != "legacy"


def migrate(conn):
    """Caller owns transaction. NULL means unissued; empty means revoked.

    No schema or data changes in legacy mode. Deployment in prepare/secure
    requires an approved backup and migration, as documented in the runbook.
    """
    if not enabled():
        return
    conn.execute("SAVEPOINT document_links")
    try:
        _migrate(conn)
        conn.execute("RELEASE SAVEPOINT document_links")
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT document_links")
        conn.execute("RELEASE SAVEPOINT document_links")
        raise


def _migrate(conn):
    for table in ("quotes", "invoices"):
        if "share_token" not in {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN share_token TEXT")
        conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_share_token ON {table}(share_token) WHERE share_token != ''")
        for row in conn.execute(f"SELECT id FROM {table} WHERE share_token IS NULL").fetchall():
            issue(conn, table, row["id"])


def issue(conn, table, document_id):
    if table not in {"quotes", "invoices"}:
        raise ValueError("Invalid document kind")
    token = secrets.token_urlsafe(32)
    conn.execute(f"UPDATE {table} SET share_token=? WHERE id=?", (token, document_id))
    return token


def fields(row, kind):
    if not enabled():
        return {}
    token = row["share_token"] or ""
    path = f"/share/{kind}/{token}" if token else ""
    return {"share_pdf_path": path + "/pdf" if path else ""} if kind == "quote" else {"share_path": path}


def resolve(conn, table, token):
    if table not in {"quotes", "invoices"}:
        raise ValueError("Invalid document kind")
    if not enabled() or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        return None
    return conn.execute(f"SELECT id FROM {table} WHERE share_token=?", (token,)).fetchone()


HEADERS = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow, noarchive",
           "Referrer-Policy": "no-referrer"}


class RedactShareTokens(logging.Filter):
    """Uvicorn logs the request path in its args; leave routing scope untouched."""
    def filter(self, record):
        def redact(value):
            return re.sub(r"(/share/(?:invoice|quote)/)[^/?\s]+", r"\1[redacted]", value) if isinstance(value, str) else value
        if isinstance(record.args, tuple):
            record.args = tuple(redact(value) for value in record.args)
        elif isinstance(record.args, dict):
            record.args = {key: redact(value) for key, value in record.args.items()}
        record.msg = redact(record.msg)
        return True


def install_log_redaction():
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, RedactShareTokens) for item in logger.filters):
        logger.addFilter(RedactShareTokens())

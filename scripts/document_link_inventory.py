"""Prepare an owner-review inventory from an explicitly supplied SQLite copy.

No default database path, contacts, tokens, messages or database writes.
Do not commit output made from real records to source control.
"""

import argparse
import json
import sqlite3
from pathlib import Path


def inventory(database):
    path = Path(database).resolve(strict=True)
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Database integrity check failed")
        records = []
        for kind, table in (("quote", "quotes"), ("invoice", "invoices")):
            columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            fields = [name for name in ("id", "status", "balance_due") if name in columns]
            for row in conn.execute(f"SELECT {','.join(fields)} FROM {table} ORDER BY id"):
                records.append({"kind": kind, **dict(row), "previously_shared": "unknown",
                                "recipient_verified": False, "replacement_delivered": False,
                                "customer_access_confirmed": False, "owner_review_required": True})
    return {"source": "explicit_database_copy", "cutover_ready": False, "records": records}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-copy", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(inventory(args.database_copy), indent=2))

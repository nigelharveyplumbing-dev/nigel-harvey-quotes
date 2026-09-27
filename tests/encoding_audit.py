"""Read-only Unicode corruption audit for an explicitly selected SQLite file.

Usage: python tests/encoding_audit.py /path/to/staging/quotes.db
No database path is assumed, and the connection is opened with mode=ro.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sqlite3


# Indicators, not automatic corrections: a legitimate value may need review.
SUSPICIOUS = re.compile(
    r"\ufffd|\u00ef\u00bf\u00bd|\u00c3|\u00c2|"
    r"\u00e2[\u0080-\u00bf\u20ac\u201a-\u201e\u2122]|"
    r"\u00f0\u0178|[\u0080-\u009f]"
)


def hits(text):
    return list(SUSPICIOUS.finditer(text)) if isinstance(text, str) else []


def text_leaves(value, path):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from text_leaves(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from text_leaves(item, f"{path}[{index}]")
    elif isinstance(value, str):
        yield path, value


def scan_database(path, max_examples=12):
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    scanned_rows = Counter()
    scanned_fields = Counter()
    affected_records = Counter()
    affected_fields = Counter()
    examples = []
    try:
        tables = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        for table in tables:
            # Table names come only from sqlite_master, then are quoted for SQL.
            escaped = table.replace('"', '""')
            for row in conn.execute(f'SELECT * FROM "{escaped}"'):
                scanned_rows[table] += 1
                row_affected = False
                record_id = row["id"] if "id" in row.keys() else scanned_rows[table]
                for column in row.keys():
                    raw = row[column]
                    if not isinstance(raw, str):
                        continue
                    value = raw
                    if raw.lstrip().startswith(("{", "[")):
                        try:
                            value = json.loads(raw)
                        except ValueError:
                            pass
                    for field, text in text_leaves(value, column):
                        scanned_fields[table] += 1
                        matches = hits(text)
                        if not matches:
                            continue
                        row_affected = True
                        affected_fields[f"{table}.{field}"] += 1
                        if len(examples) < max_examples:
                            pos = matches[0].start()
                            examples.append({
                                "table": table, "id": record_id, "field": field,
                                "marker": matches[0].group(),
                                "excerpt": text[max(0, pos - 30):pos + 60].replace("\n", " "),
                            })
                if row_affected:
                    affected_records[table] += 1
    finally:
        conn.close()
    return {
        "scanned_rows": dict(scanned_rows),
        "scanned_fields": dict(scanned_fields),
        "affected_records": dict(affected_records),
        "affected_fields": dict(affected_fields),
        "examples": examples,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", help="Explicit path to the database to audit read-only")
    args = parser.parse_args()
    print(json.dumps(scan_database(args.database), ensure_ascii=False, indent=2))

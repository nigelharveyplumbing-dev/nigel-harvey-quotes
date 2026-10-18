"""Back up and rehearse the optional appointment lead migration before live writes."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from uuid import uuid4


def needs_migration(conn):
    return any(row[1] == "lead_id" and row[3]
               for row in conn.execute("PRAGMA table_info(appointments)"))


def _records(conn):
    """Compare records in memory only; never emit private database contents."""
    tables = [row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    result = {}
    for name in tables:
        quoted = '"' + name.replace('"', '""') + '"'
        result[name] = sorted((tuple(row) for row in conn.execute(f"SELECT * FROM {quoted}")), key=repr)
    result["sqlite_sequence"] = sorted(tuple(row) for row in conn.execute("SELECT name,seq FROM sqlite_sequence"))
    return result


def _other_schema(conn):
    return sorted(tuple(row) for row in conn.execute("""SELECT type,name,sql FROM sqlite_master
        WHERE name NOT LIKE 'sqlite_%' AND name!='appointments'"""))


def migrate(conn):
    if not needs_migration(conn):
        return False
    schema = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='appointments'").fetchone()[0]
    if "lead_id INTEGER NOT NULL" not in schema:
        raise RuntimeError("Unexpected appointments schema; optional-lead migration stopped")
    columns = [tuple(row) for row in conn.execute("PRAGMA table_info(appointments)")]
    expected_columns = [tuple(0 if index == 3 and row[1] == "lead_id" else value
                              for index, value in enumerate(row)) for row in columns]
    objects = list(conn.execute("""SELECT sql FROM sqlite_master WHERE tbl_name='appointments'
        AND type IN ('index','trigger') AND sql IS NOT NULL"""))
    sequence = conn.execute("SELECT seq FROM sqlite_sequence WHERE name='appointments'").fetchone()
    before_records, before_schema = _records(conn), _other_schema(conn)
    schema = schema.replace("lead_id INTEGER NOT NULL", "lead_id INTEGER", 1)
    schema = "CREATE TABLE appointments_optional_lead " + schema[schema.index("("):]
    conn.execute("SAVEPOINT optional_appointment_lead")
    try:
        conn.execute(schema)
        names = ",".join('"' + row[1].replace('"', '""') + '"' for row in columns)
        conn.execute(f"INSERT INTO appointments_optional_lead ({names}) SELECT {names} FROM appointments")
        conn.execute("DROP TABLE appointments")
        conn.execute("ALTER TABLE appointments_optional_lead RENAME TO appointments")
        if sequence:
            conn.execute("UPDATE sqlite_sequence SET seq=MAX(seq,?) WHERE name='appointments'", (sequence[0],))
        else:
            conn.execute("DELETE FROM sqlite_sequence WHERE name='appointments'")
        for obj in objects:
            conn.execute(obj[0])
        if ([tuple(row) for row in conn.execute("PRAGMA table_info(appointments)")] != expected_columns
                or _records(conn) != before_records or _other_schema(conn) != before_schema
                or conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok"):
            raise RuntimeError("Appointment migration preservation check failed")
    except Exception:
        conn.execute("ROLLBACK TO optional_appointment_lead")
        conn.execute("RELEASE optional_appointment_lead")
        raise
    conn.execute("RELEASE optional_appointment_lead")
    return True


def preflight(conn, backup_dir):
    """Fail before live schema writes unless a verified backup can be restored and migrated."""
    if not needs_migration(conn):
        return None
    if conn.in_transaction:
        raise RuntimeError("Migration backup must run before database writes")
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    path = backup_dir / f"quotes-backup-{stamp}-{uuid4().hex[:8]}-before-appointment-migration.db"
    # Reserve a private, unique file before SQLite opens it.
    with path.open("xb"):
        path.chmod(0o600)
    backup = sqlite3.connect(path)
    try:
        conn.backup(backup)
    finally:
        backup.close()
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as saved:
        if saved.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Pre-migration backup integrity check failed")
        with tempfile.TemporaryDirectory(prefix="appointment-migration-rehearsal-") as directory:
            restored = sqlite3.connect(Path(directory) / "restored.db")
            try:
                saved.backup(restored)
                if not migrate(restored):
                    raise RuntimeError("Pre-migration backup rehearsal did not run")
                restored.commit()
                if restored.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("Pre-migration rehearsal integrity check failed")
            finally:
                restored.close()
        count = saved.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]
    report = {"backup_file": path.name, "backup_bytes": path.stat().st_size,
              "backup_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "appointments_preserved": count, "backup_integrity": "ok", "restore_rehearsal": "ok"}
    print("PIPELINE_MIGRATION_PREFLIGHT " + json.dumps(report, sort_keys=True), flush=True)
    return report

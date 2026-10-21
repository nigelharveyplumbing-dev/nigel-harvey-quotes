"""Coupled diary/revenue migration rehearsal on disposable synthetic SQLite only.

Uses the authenticated local app's temporary database; does not access Render
or the business's real databases. Rehearses both orderings of migrations,
preserved foreign keys, linked business records, checksum and paired restore.
"""
import hashlib
import sqlite3
import unittest
from pathlib import Path

import test_revenue_tracking as helpers
from business import appointment_migration


class CoupledMigrationRehearsal(unittest.TestCase):
    setUp = helpers.RevenueTests.setUp
    post = helpers.RevenueTests.post
    lead = helpers.RevenueTests.lead
    quote = helpers.RevenueTests.quote
    invoice = helpers.RevenueTests.invoice

    def fixture(self):
        lead = self.lead(source="")
        quote = self.quote(lead)
        invoice = self.invoice(quote)
        self.m.update_invoice_status(invoice["id"], "part paid", 35)
        job = self.post("/api/jobs", {
            "lead_id": lead["id"], "quote_id": quote["id"],
            "invoice_id": invoice["id"], "title": "SYNTHETIC appointment job",
            "status": "awaiting_schedule",
        })
        # Recreate the pre-optional-lead shape ONLY in the disposable DB.
        with self.migration.connect(self.root / "quotes.db") as conn:
            conn.execute("DROP TABLE appointments")
            conn.execute("""CREATE TABLE appointments(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER NOT NULL, job_id INTEGER, kind TEXT NOT NULL,
                status TEXT NOT NULL, starts_at TEXT NOT NULL, ends_at TEXT NOT NULL,
                provisional_follow_up TEXT, notes TEXT, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL)""")
            conn.execute("CREATE INDEX idx_appointments_start ON appointments(starts_at)")
            conn.execute("CREATE INDEX idx_appointments_lead ON appointments(lead_id)")
            conn.execute("""INSERT INTO appointments
                (lead_id,job_id,kind,status,starts_at,ends_at,provisional_follow_up,
                 notes,created_at,updated_at)
                VALUES (?,?,'job','confirmed','2026-11-08T09:00','2026-11-08T17:00',
                        NULL,'SYNTHETIC schedule','2026-10-21T09:00','2026-10-21T09:00')""",
                (lead["id"], job["id"]))
        sidecar = self.root / "city-account-prices.sqlite3"
        with sqlite3.connect(sidecar) as conn:
            conn.execute("CREATE TABLE local_city_cache(sku TEXT PRIMARY KEY, price_pence INTEGER)")
            conn.execute("INSERT INTO local_city_cache VALUES ('SYNTHETIC-15MM',1299)")
        return lead, quote, invoice, job, sidecar

    def verify(self, fixture, original_appointment, original_values):
        lead, quote, invoice, job, sidecar = fixture
        db = self.root / "quotes.db"
        with self.migration.connect(db) as conn:
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(conn.execute(
                "SELECT id,lead_id,job_id,kind,status,starts_at,ends_at,notes FROM appointments"
            ).fetchall()[0][:], original_appointment)
            self.assertFalse(appointment_migration.needs_migration(conn))
            for table, record in original_values.items():
                before_cols, expected_rows = record
                selected = ",".join('"' + col + '"' for col in before_cols)
                actual = [tuple(x) for x in conn.execute(f'SELECT {selected} FROM "{table}" ORDER BY id')]
                self.assertEqual(actual, expected_rows, table)
            oid = conn.execute("SELECT origin_id FROM leads WHERE id=?", (lead["id"],)).fetchone()[0]
            self.assertIsNotNone(oid)
            for table, rid in (("quotes",quote["id"]),("jobs",job["id"]),("invoices",invoice["id"])):
                self.assertEqual(conn.execute(
                    f"SELECT origin_id FROM {table} WHERE id=?", (rid,)
                ).fetchone()[0], oid)
            self.assertEqual(conn.execute(
                "SELECT amount_pence,received_on,entry_type FROM invoice_payments WHERE invoice_id=?",
                (invoice["id"],)
            ).fetchall()[0][:], (3500, None, "legacy_opening_balance"))
            self.assertEqual(conn.execute(
                "SELECT checksum FROM schema_migrations WHERE version=1"
            ).fetchone()[0], self.migration.migration_checksum())
        with sqlite3.connect(sidecar) as c:
            self.assertEqual(c.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(c.execute("SELECT * FROM local_city_cache").fetchall(), [
                ("SYNTHETIC-15MM", 1299)
            ])

    def exercise(self, order):
        fixture = self.fixture()
        primary = self.root / "quotes.db"
        sidecar = fixture[4]
        with self.migration.connect(primary) as conn:
            original_appointment = tuple(conn.execute(
                "SELECT id,lead_id,job_id,kind,status,starts_at,ends_at,notes FROM appointments"
            ).fetchone())
            # Frozen projection of all original business fields, excluding later added columns.
            original_values = {}
            for table in ("leads", "quotes", "jobs", "invoices"):
                cols = [x["name"] for x in conn.execute(f"PRAGMA table_info({table})")]
                selected = ",".join('"' + col + '"' for col in cols)
                rows = [tuple(x) for x in conn.execute(f'SELECT {selected} FROM "{table}" ORDER BY id')]
                original_values[table] = (cols, rows)
            first_hashes = self.migration.hashes(conn, self.migration.inventory(conn))
        # Paired checkpoint and restore are disposable. Do not touch /var/data.
        pbackup = self.root / "before-primary-checkpoint.db"
        sbackup = self.root / "before-city-checkpoint.db"
        for source, destination in ((primary, pbackup), (sidecar, sbackup)):
            with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
                src.backup(dst)
            with sqlite3.connect(f"file:{destination}?mode=ro", uri=True) as chk:
                self.assertEqual(chk.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        if order == "diary_first":
            with self.migration.connect(primary) as conn:
                checkpoint = appointment_migration.preflight(conn, self.root / "isolated_backups")
                self.assertEqual(checkpoint["restore_rehearsal"], "ok")
                self.assertTrue(appointment_migration.migrate(conn))
                conn.commit()
            dry = self.migration.migrate(primary)
            self.assertTrue(dry["dry_run"])
            self.assertFalse(dry["already_applied"])
            self.migration.migrate(primary, apply=True)
        else:
            dry = self.migration.migrate(primary)
            self.assertTrue(dry["dry_run"])
            self.migration.migrate(primary, apply=True)
            with self.migration.connect(primary) as conn:
                checkpoint = appointment_migration.preflight(conn, self.root / "isolated_backups")
                self.assertEqual(checkpoint["restore_rehearsal"], "ok")
                self.assertTrue(appointment_migration.migrate(conn))
                conn.commit()
        self.assertTrue(self.migration.migrate(primary, apply=True)["already_applied"])
        self.verify(fixture, original_appointment, original_values)
        # Simulate a rollback ONLY in isolated restored copies before any new
        # post-migration business transactions. Never use as a live ledger rollback.
        restored_primary = self.root / "verified-restore.db"
        restored_city = self.root / "verified-city.db"
        for src, dst in ((pbackup,restored_primary),(sbackup,restored_city)):
            with sqlite3.connect(src) as a, sqlite3.connect(dst) as b:
                a.backup(b)
            with sqlite3.connect(dst) as check:
                self.assertEqual(check.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        with self.migration.connect(restored_primary) as conn:
            self.assertEqual(first_hashes, self.migration.hashes(conn,self.migration.inventory(conn)))
            self.assertTrue(appointment_migration.needs_migration(conn))
            self.assertNotIn("schema_migrations",self.migration.inventory(conn))
        self.assertEqual(hashlib.sha256(sbackup.read_bytes()).hexdigest(),
                         hashlib.sha256(restored_city.read_bytes()).hexdigest())

    def test_diary_then_enquiry_migration(self):
        self.exercise("diary_first")

    def test_enquiry_then_diary_migration(self):
        self.exercise("enquiry_first")

    def test_failure_before_enquiry_commit_preserves_diary_and_other_records(self):
        fixture = self.fixture()
        db = self.root / "quotes.db"
        with self.migration.connect(db) as conn:
            before = self.migration.inventory(conn)
            hashes = self.migration.hashes(conn, before)
        with self.assertRaisesRegex(RuntimeError, "Injected migration rollback"):
            self.migration.migrate(db, apply=True, fail_after=1)
        with self.migration.connect(db) as conn:
            self.assertEqual(self.migration.inventory(conn), before)
            self.assertEqual(self.migration.hashes(conn,before),hashes)
            self.assertTrue(appointment_migration.needs_migration(conn))
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0],"ok")
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(),[])

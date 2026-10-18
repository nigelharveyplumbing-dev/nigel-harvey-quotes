"""Production startup cannot migrate the diary without a tested SQLite backup."""
import hashlib
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('appointment_migration_under_test',
    Path(__file__).resolve().parents[1] / 'business/appointment_migration.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class AppointmentMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / 'original.db'
        self.backups = self.root / 'backups'
        self.conn = sqlite3.connect(self.path)
        self.addCleanup(self.conn.close)
        self.conn.executescript('''
            CREATE TABLE appointments (id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER NOT NULL, notes TEXT);
            CREATE INDEX existing_notes ON appointments(notes);
            CREATE TABLE other_records (value TEXT);
            INSERT INTO other_records VALUES ('unchanged');
            CREATE TRIGGER existing_trigger AFTER UPDATE ON appointments
                BEGIN INSERT INTO other_records VALUES ('updated'); END;
            INSERT INTO appointments VALUES (7,42,'keep this');
            UPDATE sqlite_sequence SET seq=90 WHERE name='appointments';
        ''')
        self.conn.commit()
        self.original = self.path.read_bytes()

    def test_backup_restores_and_rehearses_before_source_changes(self):
        result = migration.preflight(self.conn, self.backups)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertTrue(migration.needs_migration(self.conn))
        backup_path = self.backups / result['backup_file']
        self.assertEqual(backup_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(hashlib.sha256(backup_path.read_bytes()).hexdigest(), result['backup_sha256'])
        with sqlite3.connect(f'file:{backup_path}?mode=ro', uri=True) as backup:
            self.assertTrue(migration.needs_migration(backup))
            self.assertEqual(backup.execute('SELECT * FROM appointments').fetchall(), [(7,42,'keep this')])
        self.assertTrue(migration.migrate(self.conn))
        self.conn.commit()
        self.assertEqual(self.conn.execute("SELECT seq FROM sqlite_sequence WHERE name='appointments'").fetchone()[0], 90)
        self.conn.execute("UPDATE appointments SET notes='changed' WHERE id=7")
        self.conn.commit()
        self.assertEqual(self.conn.execute('SELECT * FROM other_records').fetchall(), [('unchanged',),('updated',)])
        self.assertIsNone(migration.preflight(self.conn, self.backups))
        self.assertEqual(len(list(self.backups.glob('*.db'))), 1)

    def test_unwritable_backup_destination_keeps_live_schema_and_rows(self):
        self.backups.write_text('this is a file')
        with self.assertRaises(OSError):
            migration.preflight(self.conn, self.backups)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertTrue(migration.needs_migration(self.conn))

    def test_failed_rehearsal_keeps_live_database_unchanged(self):
        with patch.object(migration, 'migrate', side_effect=RuntimeError('rehearsal failed')):
            with self.assertRaisesRegex(RuntimeError, 'rehearsal failed'):
                migration.preflight(self.conn, self.backups)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertTrue(migration.needs_migration(self.conn))

    def test_preservation_failure_rolls_back_live_migration(self):
        original_schema = migration._other_schema(self.conn)
        with patch.object(migration, '_other_schema', side_effect=[original_schema, []]):
            with self.assertRaisesRegex(RuntimeError, 'preservation check'):
                migration.migrate(self.conn)
        self.assertTrue(migration.needs_migration(self.conn))
        self.assertEqual(self.conn.execute('SELECT * FROM appointments').fetchall(), [(7,42,'keep this')])
        self.assertEqual(migration._other_schema(self.conn), original_schema)
        self.assertEqual(self.conn.execute("SELECT name FROM sqlite_master WHERE name='appointments_optional_lead'").fetchall(), [])

    def test_backup_refuses_pending_live_writes(self):
        self.conn.execute("INSERT INTO other_records VALUES ('pending')")
        with self.assertRaisesRegex(RuntimeError, 'before database writes'):
            migration.preflight(self.conn, self.backups)
        self.conn.rollback()
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_empty_diary_without_an_id_sequence_is_preserved(self):
        self.conn.execute('DELETE FROM appointments')
        self.conn.execute("DELETE FROM sqlite_sequence WHERE name='appointments'")
        self.conn.commit()
        self.assertIsNotNone(migration.preflight(self.conn, self.backups))
        self.assertTrue(migration.migrate(self.conn))
        self.conn.commit()
        self.assertEqual(self.conn.execute('SELECT * FROM appointments').fetchall(), [])
        self.assertIsNone(self.conn.execute("SELECT seq FROM sqlite_sequence WHERE name='appointments'").fetchone())

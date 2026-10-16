"""Offline-only regression gates for migration checksums and attribution provenance.

Requires the full repository test helpers; do not run against staging or
production data. No Render, GitHub, email or external API operations.
"""
import sqlite3
import unittest
from unittest.mock import patch
import test_revenue_tracking as helpers


class AuditMetadataTests(unittest.TestCase):
    setUp = helpers.RevenueTests.setUp
    activate = helpers.RevenueTests.activate
    post = helpers.RevenueTests.post
    get = helpers.RevenueTests.get
    lead = helpers.RevenueTests.lead
    quote = helpers.RevenueTests.quote
    invoice = helpers.RevenueTests.invoice
    payment = helpers.RevenueTests.payment
    correction = helpers.RevenueTests.correction
    report = helpers.RevenueTests.report

    def test_checksum_is_deterministic_and_stored_on_migration(self):
        c1 = self.migration.migration_checksum()
        self.assertEqual(c1, self.migration.migration_checksum())
        self.assertEqual(len(c1), 64)
        self.assertFalse(self.migration.migrate(self.root / 'quotes.db')['already_applied'])
        self.assertEqual(self.migration.migrate(self.root / 'quotes.db')['checksum'], c1)
        first = self.activate()
        self.assertEqual(first['checksum'], c1)
        with self.migration.connect(self.root / 'quotes.db') as conn:
            stored = conn.execute('SELECT checksum FROM schema_migrations WHERE version=1').fetchone()[0]
            self.assertEqual(stored, c1)
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())
        second = self.activate()
        self.assertTrue(second['already_applied'])
        self.assertEqual(second['checksum'], c1)

    def test_checksum_mismatch_rejected_without_writes(self):
        self.activate()
        with self.migration.connect(self.root / 'quotes.db') as conn:
            conn.execute("UPDATE schema_migrations SET checksum='bad' WHERE version=1")
        with self.migration.connect(self.root / 'quotes.db') as conn:
            before = self.migration.hashes(conn, self.migration.inventory(conn))
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            self.migration.migrate(self.root / 'quotes.db', apply=True)
        with self.migration.connect(self.root / 'quotes.db') as conn:
            self.assertEqual(before, self.migration.hashes(conn, self.migration.inventory(conn)))

    def test_existing_unchecksummed_v1_stops_for_separate_upgrade(self):
        with self.migration.connect(self.root / 'quotes.db') as conn:
            conn.execute('CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
            conn.execute("INSERT INTO schema_migrations VALUES (1,'2026-10-01T00:00:00Z')")
        with self.assertRaisesRegex(ValueError, 'no checksum'):
            self.migration.migrate(self.root / 'quotes.db', apply=True)

    def test_unknown_migration_version_stops_before_any_changes(self):
        with self.migration.connect(self.root / 'quotes.db') as conn:
            conn.execute('CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
            conn.execute("INSERT INTO schema_migrations VALUES (2,'2026-10-01T00:00:00Z')")
        with self.assertRaisesRegex(ValueError, 'Unexpected migration version'):
            self.migration.migrate(self.root / 'quotes.db', apply=True)

    def test_migration_v1_rollback_does_not_leave_metadata(self):
        self.quote()
        with self.assertRaisesRegex(RuntimeError, 'Injected migration rollback'):
            self.migration.migrate(self.root / 'quotes.db', apply=True, fail_after=1)
        with self.migration.connect(self.root / 'quotes.db') as conn:
            self.assertFalse(self.attribution.enabled(conn))
            self.assertIsNone(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='enquiry_origins'").fetchone())
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_legacy_backfill_explicitly_unversioned_and_paid_amount_preserved(self):
        q = self.quote()
        i = self.invoice(q)
        self.m.update_invoice_status(i['id'], 'part paid', 35)
        self.activate()
        with self.migration.connect(self.root / 'quotes.db') as conn:
            source = conn.execute('SELECT rule_version FROM enquiry_origins WHERE id=(SELECT origin_id FROM quotes WHERE id=?)',(q['id'],)).fetchone()[0]
            self.assertEqual(source, 'legacy-unversioned')
        self.assertEqual(self.get(f"/api/revenue/invoices/{i['id']}/payments")['undated_balance_pence'], 3500)

    def test_captured_and_subsequent_rule_versions_are_preserved(self):
        self.activate()
        lead = self.lead('Referral')
        first = self.get('/api/revenue/origins/' + str(lead['origin_id']))
        self.assertEqual(first['rule_version'], 'attribution-v1')
        self.assertEqual(first['effective_rule_version'], 'attribution-v1')
        amended = self.correction(lead, source='Other')
        self.assertEqual(amended['history'][0]['rule_version'], 'attribution-v1')
        with patch.object(self.attribution, 'ATTRIBUTION_RULE_VERSION', 'attribution-v2'):
            second = self.correction(lead, source='Referral', revision=1)
            self.assertEqual(second['history'][1]['rule_version'], 'attribution-v2')
            self.assertEqual(second['rule_version'], 'attribution-v1')
            self.assertEqual(second['effective_rule_version'], 'attribution-v2')
        with self.migration.connect(self.root / 'quotes.db') as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute('DELETE FROM origin_corrections')

    def test_rule_version_value_does_not_invalidate_existing_v1_checksum(self):
        c1 = self.migration.migration_checksum()
        with patch.object(self.attribution, 'ATTRIBUTION_RULE_VERSION', 'attribution-v2'):
            self.assertEqual(self.migration.migration_checksum(), c1)
        with patch.object(self.migration, 'DDL', self.migration.DDL + ('CREATE TABLE example (x INTEGER)',)):
            self.assertNotEqual(self.migration.migration_checksum(), c1)

    def test_reporting_totals_do_not_change_after_provenance_capture(self):
        self.activate()
        lead = self.lead('Referral')
        quote = self.quote(lead)
        invoice = self.invoice(quote)
        self.payment(invoice, '30.00')
        before = self.report()['totals']
        self.correction(lead, source='Referral')
        self.assertEqual(before, self.report()['totals'])
        self.assertEqual(self.get('/api/revenue/origins/' + str(lead['origin_id']))['rule_version'], 'attribution-v1')


if __name__ == '__main__':
    unittest.main()

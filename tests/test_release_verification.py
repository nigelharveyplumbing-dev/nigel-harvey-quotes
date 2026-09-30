"""Release verification guards and read-only SQLite inspection."""

import os
import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "verify_release", Path(__file__).resolve().parents[1] / "scripts" / "verify_release.py")
verify_release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify_release)


class ReleaseVerificationTests(unittest.TestCase):
    def test_wrong_service_origin_and_mount_fail_before_http(self):
        db = Path("/var/data/quotes.db")
        with patch.dict(os.environ, {"RENDER_SERVICE_ID": "srv-wrong", "PUBLIC_BASE_URL":
                                      verify_release.PRODUCTION_ORIGIN}, clear=True), \
             patch.object(verify_release.os.path, "ismount", return_value=True):
            with self.assertRaisesRegex(ValueError, "Wrong Render service"):
                verify_release.assert_identity("production", db, verify_release.PRODUCTION_ORIGIN)
        with patch.dict(os.environ, {"RENDER_SERVICE_ID": verify_release.SERVICES["production"],
                                      "APP_ENVIRONMENT": "staging"}, clear=True), \
             patch.object(verify_release.os.path, "ismount", return_value=True):
            with self.assertRaisesRegex(ValueError, "Production origin/environment mismatch"):
                verify_release.assert_identity("production", db, verify_release.PRODUCTION_ORIGIN)
        with patch.dict(os.environ, {"RENDER_SERVICE_ID": verify_release.SERVICES["production"]}, clear=True), \
             patch.object(verify_release.os.path, "ismount", return_value=False):
            with self.assertRaisesRegex(ValueError, "mounted"):
                verify_release.assert_identity("production", db, verify_release.PRODUCTION_ORIGIN)

    def test_production_cli_requires_explicit_read_only_flag(self):
        with self.assertRaises(SystemExit) as raised:
            verify_release.main(["--environment", "production"])
        self.assertEqual(raised.exception.code, 2)

    def test_database_inspection_never_writes_and_detects_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "quotes.db"
            connection = sqlite3.connect(db)
            for table in verify_release.TABLES:
                connection.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)")
            connection.execute("CREATE TABLE invoice_photos (id INTEGER PRIMARY KEY)")
            connection.execute("INSERT INTO quotes VALUES (1)")
            connection.commit()
            connection.close()
            before = db.read_bytes()
            result = verify_release.inspect_database(db)
            self.assertEqual(result["integrity"], "ok")
            self.assertEqual(result["counts"]["quotes"], 1)
            self.assertIn("status", result["missing_columns"]["quotes"])
            self.assertEqual(db.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

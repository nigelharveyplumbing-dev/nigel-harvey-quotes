"""Synthetic canonical fixtures; no real account identifiers, prices or secrets."""
import copy
import hashlib
import importlib
import sqlite3
import sys
import tempfile
import unittest
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

_path = list(sys.path)
_existing = {key for key in sys.modules if key == "business" or key.startswith("business.")}
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    pricing = importlib.import_module("business.account_pricing")
    models = importlib.import_module("business.models")
    calculator = importlib.import_module("business.quote_calculation")
finally:
    sys.path[:] = _path
    for _key in list(sys.modules):
        if (_key == "business" or _key.startswith("business.")) and _key not in _existing:
            del sys.modules[_key]

NOW = datetime(2026, 10, 5, 20, 0, tzinfo=timezone.utc)
REF = "a" * 32
OTHER_REF = "b" * 32


def record(supplier="Wolseley", source="account_live", price="10.00", **changes):
    row = dict(supplier=supplier, source_ref=REF if source.startswith("account_") else "",
        supplier_sku="synthetic-sku", name="Synthetic Acme Valve V15 15mm Chrome Angled",
        gtin="", brand="Acme", mpn="V15", pack_quantity=1, price=price,
        vat_basis="inc_vat", vat_rate=None, unit_basis="selling_pack", source_type=source,
        checked_at=(NOW - timedelta(minutes=1)).isoformat(),
        expires_at=(NOW + timedelta(minutes=10)).isoformat(), availability="in_stock", currency="GBP")
    row.update(changes)
    return pricing.record_from_mapping(row, now=NOW)


def compare(*rows, **kwargs):
    return pricing.compare_prices(rows, now=NOW, account_sources=(REF,), **kwargs)["offers"]


class AccountComparisonTests(unittest.TestCase):
    def test_account_live_takes_precedence_over_same_merchant_public_even_if_higher(self):
        account, public = record(price="15"), record(source="public_live", price="10")
        second = record("Toolstation", "public_live", "20")
        a, p, b = compare(account, public, second)
        self.assertTrue(a["preferred_for_supplier"])
        self.assertFalse(p["preferred_for_supplier"])
        self.assertTrue(a["is_best_price"])
        self.assertEqual(b["saving_vs_best"], "5.00")
        self.assertEqual(a["compared_merchants"], 2)

    def test_fresh_account_cached_preferred_but_never_live_winner(self):
        a, p, b = compare(record(source="account_cached", price="1"),
            record(source="public_live", price="10"), record("Toolstation", "public_live", "20"))
        self.assertTrue(a["preferred_for_supplier"])
        self.assertTrue(a["requires_cached_confirmation"])
        self.assertFalse(p["preferred_for_supplier"])
        self.assertFalse(any(o["is_best_price"] for o in (a, p, b)))

    def test_stale_account_does_not_suppress_public_live(self):
        stale = record(source="account_cached", checked_at=(NOW - timedelta(days=8)).isoformat(),
                       expires_at=(NOW + timedelta(days=30)).isoformat())
        a, p, _ = compare(stale, record(source="public_live", price="12"),
                          record("Toolstation", "public_live", "20"))
        self.assertEqual(a["freshness"], "stale")
        self.assertFalse(a["eligible"])
        self.assertTrue(p["is_best_price"])

    def test_unknown_expiry_vat_and_unit_are_not_current_live_candidates(self):
        for changes in ({"expires_at": None}, {"vat_basis": "unknown"},
                        {"vat_basis": "ex_vat", "vat_rate": None}, {"unit_basis": "unknown"}):
            with self.subTest(changes=changes):
                a, _ = compare(record(**changes), record("Toolstation", "public_live"))
                self.assertFalse(a["eligible"])
                self.assertFalse(a["is_best_price"])

    def test_live_age_cap_cannot_be_extended_by_far_future_expiry(self):
        a, _ = compare(record(checked_at=(NOW-timedelta(minutes=16)).isoformat(),
                             expires_at=(NOW+timedelta(days=30)).isoformat()),
                       record("Toolstation", "public_live"))
        self.assertEqual(a["freshness"], "stale")

    def test_expiry_boundary_and_cached_age_are_explicit(self):
        r = record(source="account_cached", expires_at=NOW.isoformat())
        self.assertEqual(r.freshness(NOW), "stale")
        a = compare(record(source="account_cached"))[0]
        self.assertEqual(a["age_seconds"], 60)

    def test_account_scope_is_explicit_not_inferred(self):
        a, p = compare(record(source_ref=OTHER_REF), record(source="public_live"))
        self.assertFalse(a["eligible"])
        self.assertTrue(p["preferred_for_supplier"])

    def test_vat_conversion_requires_explicit_rate_and_keeps_selling_pack(self):
        r = record(price="10.005", vat_basis="ex_vat", vat_rate="0.20", pack_quantity=10)
        self.assertEqual(r.price_inc_vat, "12.01")
        self.assertEqual(r.price, "10.005")
        self.assertEqual(r.pack_quantity, 10)
        self.assertEqual(record(price="10", vat_basis="ex_vat", vat_rate="0").price_inc_vat, "10.00")

    def test_pack_mismatch_never_unit_normalized(self):
        a, b = compare(record(pack_quantity=10), record("Toolstation", "public_live", pack_quantity=1))
        self.assertFalse(a["is_best_price"] or b["is_best_price"])
        self.assertFalse(pricing.exact_match(a["record"], b["record"]))

    def test_matching_gtin_cannot_override_mpn_or_brand_conflict(self):
        a = record(gtin="4006381333931")
        for changes in ({"mpn": "V16"}, {"brand": "Other"}, {"mpn": "V-15"}):
            self.assertFalse(pricing.exact_match(a, record(gtin="4006381333931", **changes)))

    def test_conflicting_gtins_reject_matching_brand_mpn(self):
        self.assertFalse(pricing.exact_match(record(gtin="4006381333931"), record(gtin="5012345678900")))

    def test_gtin_only_can_match_and_sku_only_cannot(self):
        self.assertTrue(pricing.exact_match(record(gtin="4006381333931", brand="", mpn=""),
                                           record(gtin="04006381333931", brand="", mpn="")))
        self.assertFalse(pricing.exact_match(record(brand="", mpn=""), record(brand="", mpn="")))

    def test_explicit_product_specifications_cannot_conflict(self):
        self.assertFalse(pricing.exact_match(record(), record(name="Synthetic Acme Valve V15 22mm Chrome Angled")))

    def test_manual_and_public_cache_are_references_only(self):
        for source in ("manual", "cached_public"):
            a, _ = compare(record(source=source, price="1"), record("Toolstation", "public_live"))
            self.assertFalse(a["eligible"] or a["is_best_price"])

    def test_blocked_stock_cannot_prefer_or_win(self):
        for status in ("out_of_stock", "preorder", "backorder", "unavailable"):
            a, p, _ = compare(record(availability=status), record(source="public_live"),
                              record("Toolstation", "public_live", "12"))
            self.assertFalse(a["eligible"])
            self.assertTrue(p["is_best_price"])

    def test_unknown_stock_is_labelled_without_claiming_confirmed_stock(self):
        a = compare(record(availability="unknown"))[0]
        self.assertFalse(a["stock_confirmed"])

    def test_pts_city_count_as_one_merchant(self):
        a, p = compare(record("PTS"), record("City Plumbing", "public_live", "20"))
        self.assertFalse(a["is_best_price"] or p["is_best_price"])
        self.assertTrue(a["preferred_for_supplier"])

    def test_conflicting_same_time_account_prices_are_not_cheapest_selected(self):
        a, b, _ = compare(record(price="1"), record(price="10"), record("Toolstation", "public_live"))
        self.assertFalse(a["preferred_for_supplier"] or b["preferred_for_supplier"])

    def test_newer_same_source_price_supersedes_older_cheaper_one(self):
        old, new, other = compare(record(price="1", checked_at=(NOW-timedelta(minutes=2)).isoformat()),
            record(price="12"), record("Toolstation", "public_live", "15"))
        self.assertFalse(old["preferred_for_supplier"])
        self.assertTrue(new["is_best_price"])
        self.assertEqual(other["saving_vs_best"], "3.00")

    def test_input_records_and_manual_supplier_are_preserved(self):
        rows = [record(), record("Toolstation", "public_live", "12")]
        original = copy.deepcopy(rows)
        result = pricing.compare_prices(rows, now=NOW, account_sources=(REF,), manual_supplier="Williams")
        self.assertEqual(rows, original)
        self.assertEqual(result["manual_supplier"], "Williams")

    def test_subpenny_normalized_zero_cannot_win(self):
        self.assertFalse(compare(record(price="0.001"))[0]["eligible"])


class CanonicalImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/"account_prices.sqlite"
        pricing.initialize_account_store(self.path)

    def store(self, rows=None, content=b"synthetic canonical evidence", **changes):
        options = dict(content=content, records=rows or [record(source="account_cached")],
            supplier="Wolseley", source_ref=REF, imported_at=NOW.isoformat())
        options.update(changes)
        return pricing.store_validated_import(self.path, **options)

    def counts(self):
        with sqlite3.connect(self.path) as db:
            return tuple(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                         for table in ("account_price_imports", "account_price_records"))

    def test_real_wolseley_csv_guard_no_guessed_columns_or_mutation(self):
        before = self.path.read_bytes()
        with self.assertRaises(pricing.ExportFormatRequired):
            pricing.inspect_wolseley_csv(b"unknown-owner-format")
        self.assertEqual(self.path.read_bytes(), before)

    def test_duplicate_import_is_idempotent_and_does_not_refresh_time(self):
        first = self.store()
        before = self.path.read_bytes()
        second = self.store(imported_at=(NOW+timedelta(days=1)).isoformat())
        self.assertEqual(second["status"], "duplicate")
        self.assertEqual(first["import_id"], second["import_id"])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.counts(), (1, 1))

    def test_exact_duplicate_rows_deduplicate_conflicting_rows_reject_atomically(self):
        r = record(source="account_cached")
        self.assertEqual(self.store([r, r])["rows"], 1)
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "Conflicting duplicate"):
            self.store([r, replace(r, price="12")], content=b"second")
        self.assertEqual(self.path.read_bytes(), before)

    def test_same_file_different_mapping_rejects_without_writing(self):
        self.store()
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "conflicting normalized"):
            self.store([record(source="account_cached", price="2")])
        self.assertEqual(self.path.read_bytes(), before)

    def test_malformed_record_values_rejected_without_writes_or_value_leaks(self):
        for key, value in (("price", "nan"), ("price", "-1"), ("price", True),
                           ("pack_quantity", 1.5), ("pack_quantity", True), ("pack_quantity", 0),
                           ("gtin", "4006381333932"), ("source_ref", "private-account-number"),
                           ("vat_basis", "assumed-ex-vat"), ("currency", "EUR"),
                           ("vat_rate", "NaN"), ("vat_rate", "-0.2"),
                           ("unit_basis", "per-metre"), ("checked_at", "2026-10-05"),
                           ("checked_at", (NOW+timedelta(seconds=1)).isoformat())):
            with self.subTest(key=key, value=value):
                before = self.path.read_bytes()
                raw = asdict(record(source="account_cached")); raw[key] = value
                with self.assertRaises(ValueError) as error:
                    pricing.record_from_mapping(raw, now=NOW)
                self.assertNotIn("private-account-number", str(error.exception))
                self.assertEqual(before, self.path.read_bytes())

    def test_import_cannot_escalate_cache_to_live_or_cross_account(self):
        for r in (record(), record(source="public_live"),
                  record(source="account_cached", source_ref=OTHER_REF), record("Williams", "account_cached")):
            before = self.path.read_bytes()
            with self.assertRaises(ValueError):
                self.store([r])
            self.assertEqual(before, self.path.read_bytes())

    def test_malformed_row_rejects_entire_batch_without_partial_insert(self):
        good = record(source="account_cached")
        bad = replace(good, supplier_sku="malformed-row", price="nan")
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            self.store([good, bad])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.counts(), (0, 0))

    def test_empty_import_and_missing_currency_are_rejected(self):
        with self.assertRaises(ValueError):
            self.store(records=[])
        raw = asdict(record(source="account_cached")); del raw["currency"]
        with self.assertRaisesRegex(ValueError, "currency"):
            pricing.record_from_mapping(raw, now=NOW)
        self.assertEqual(self.counts(), (0, 0))

    def test_revalidates_forged_normalized_gross_price(self):
        self.store([replace(record(source="account_cached"), price_inc_vat="0.01")])
        rows = pricing.read_account_records(self.path, supplier="Wolseley", source_ref=REF, now=NOW)
        self.assertEqual(rows[0].price_inc_vat, "10.00")
        self.assertEqual(rows[0].imported_at, NOW.isoformat())
        self.assertEqual(rows[0].checked_at, (NOW-timedelta(minutes=1)).isoformat())

    def test_read_compare_does_not_mutate_database_or_public_history(self):
        self.store()
        with sqlite3.connect(self.path) as db:
            db.executescript("CREATE TABLE legacy_materials(id INTEGER PRIMARY KEY, body TEXT);"
                "INSERT INTO legacy_materials VALUES(1, 'unchanged');"
                "CREATE TABLE material_price_history(id INTEGER PRIMARY KEY, price TEXT);"
                "INSERT INTO material_price_history VALUES(1, '12.00');")
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        rows = pricing.read_account_records(self.path, supplier="Wolseley", source_ref=REF, now=NOW)
        compare(*rows, record("Toolstation", "public_live", "12"))
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), before)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_latest_full_snapshot_no_old_missing_skus_or_prices_revived(self):
        self.store([record(source="account_cached", price="1"),
                    record(source="account_cached", supplier_sku="old-only")])
        self.store([record(source="account_cached", price="12")], content=b"new snapshot",
                   imported_at=(NOW+timedelta(seconds=1)).isoformat())
        rows = pricing.read_account_records(self.path, supplier="Wolseley", source_ref=REF,
                                           now=NOW+timedelta(seconds=2))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].price, "12")
        self.assertEqual(self.counts(), (2, 3))

    def test_account_read_scope_does_not_leak_other_sources(self):
        self.store()
        self.assertEqual(pricing.read_account_records(self.path, supplier="Wolseley", source_ref=OTHER_REF, now=NOW), [])

    def test_store_creation_cannot_target_existing_quote_database(self):
        before = self.path.read_bytes()
        with self.assertRaises(FileExistsError):
            pricing.initialize_account_store(self.path)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_missing_read_path_cannot_create_database(self):
        missing = Path(self.tmp.name)/"missing.sqlite"
        with self.assertRaises(sqlite3.OperationalError):
            pricing.read_account_records(missing, supplier="Wolseley", source_ref=REF, now=NOW)
        self.assertFalse(missing.exists())

    def test_unknown_price_evidence_is_preserved_not_invented(self):
        self.store([record(source="account_cached", vat_basis="unknown", unit_basis="unknown", expires_at=None)])
        rows = pricing.read_account_records(self.path, supplier="Wolseley", source_ref=REF, now=NOW)
        self.assertIsNone(rows[0].price_inc_vat)
        self.assertEqual(rows[0].freshness(NOW), "unknown")


class QuoteIsolationTests(unittest.TestCase):
    def test_compare_does_not_change_quote_math_quantity_choice_or_25_percent(self):
        request = models.QuoteRequest(labour_cost=100, materials=[models.MaterialItem(name="TRV",
            quantity=2, supplier="City Plumbing", manual_price=23.23, selected_comparison_price=23.23)])
        original = request.model_dump()
        def calculate():
            return calculator.calculate_quote(request,
                fetch_tracked_price=lambda *_: self.fail("Legacy retrieval must not run"),
                safe_float=lambda value, default: float(value) if value is not None else default,
                material_quote_unit_price=lambda _name, full, override: full if override is None else override,
                find_labour_suggestion=lambda *_: {"suggestion": 120, "range": "synthetic"},
                now_uk=lambda: NOW, format_dt=lambda value: value.isoformat())
        before = calculate()
        pricing.compare_prices([record(), record("Toolstation", "public_live", "20")],
                               now=NOW, account_sources=(REF,), manual_supplier="City Plumbing")
        self.assertEqual(calculate(), before)
        self.assertEqual(request.model_dump(), original)
        self.assertEqual(before["materials_procurement_percent"], 25)
        self.assertEqual(before["materials_base"], 46.46)
        self.assertEqual(before["total_price"], 158.07)
        self.assertEqual(before["material_lines"][0]["quantity"], 2)
        self.assertEqual(before["material_lines"][0]["supplier"], "City Plumbing")


if __name__ == "__main__":
    unittest.main()

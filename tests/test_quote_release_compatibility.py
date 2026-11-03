"""Legacy release replay must neither invent full prices nor change quote data."""
import copy
import importlib.util
import sys
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("verify_quote_calculations",
    Path(__file__).resolve().parents[1] / "scripts" / "verify_quote_calculations.py")
verify = importlib.util.module_from_spec(spec)
_original_path = list(sys.path)
_existing_business = {key for key in sys.modules
                      if key == "business" or key.startswith("business.")}
try:
    spec.loader.exec_module(verify)
finally:
    # Keep the pure model/calculator references, but do not preload production
    # package/config modules before baseline tests import their disposable copy.
    sys.path[:] = _original_path
    for _key in list(sys.modules):
        if (_key == "business" or _key.startswith("business.")) and _key not in _existing_business:
            del sys.modules[_key]


class QuoteReleaseCompatibilityTests(unittest.TestCase):
    def test_legacy_missing_full_price_replays_charge_and_preserves_inputs(self):
        request = {"labour_cost": 100, "materials": [{"name": "TRV", "supplier": "City Plumbing",
            "url": "https://www.cityplumbing.co.uk/product", "quantity": 2, "manual_price": 23.23}]}
        saved = {"material_lines": [{**request["materials"][0], "unit_price_used": 23.23,
            "line_total": 46.46, "price_source": "cached"}], "materials_base": 46.46,
            "total_price": 158.07, "materials_procurement_percent": 25}
        originals = copy.deepcopy((request, saved))
        check = verify.replay_saved_quote(request, saved)
        self.assertEqual(check["status"], "pass")
        self.assertEqual(check["material_prices"][0], {"record_kind": "legacy",
            "charge_price": 23.23, "charge_source": "unit_price_used",
            "full_product_price": None, "full_price_source": "unavailable"})
        self.assertEqual((request, saved), originals)

    def test_current_full_price_is_distinct_from_partial_charged_price(self):
        evidence = verify.saved_material_prices({"full_unit_price": 8.99, "unit_price_used": 2})
        self.assertEqual(evidence["record_kind"], "current")
        self.assertEqual(evidence["full_product_price"], 8.99)
        self.assertEqual(evidence["charge_price"], 2)

    def test_missing_unit_price_can_use_actual_line_total_and_quantity(self):
        price = verify.saved_material_prices({"line_total": 6.28, "quantity": 2})
        self.assertEqual(price["charge_price"], 3.14)
        self.assertEqual(price["charge_source"], "line_total/quantity")
        self.assertIsNone(price["full_product_price"])

    def test_unknown_invalid_and_zero_are_distinct(self):
        for line in ({"manual_price": 99}, {"quantity": 0, "line_total": 5},
                     {"unit_price_used": None, "quantity": 1, "line_total": 5},
                     {"unit_price_used": float("nan")}, {"unit_price_used": True}):
            self.assertIsNone(verify.saved_material_prices(line)["charge_price"])
        self.assertEqual(verify.saved_material_prices({"unit_price_used": 0})["charge_price"], 0)

    def test_real_arithmetic_discrepancy_fails(self):
        request = {"materials": [{"name": "TRV", "quantity": 2}]}
        saved = {"material_lines": [{"name": "TRV", "quantity": 2, "supplier": "", "url": "",
            "unit_price_used": 10, "line_total": 20}], "total_price": 24}
        result = verify.replay_saved_quote(request, saved)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["discrepancies"][0]["replayed"], 25)

    def test_unavailable_charge_is_not_assumed_zero_or_manual(self):
        request = {"materials": [{"name": "TRV", "manual_price": 99}]}
        self.assertEqual(verify.replay_saved_quote(request,
            {"material_lines": [{"name": "TRV", "manual_price": 99}]})["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()

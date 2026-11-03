"""Read-only historical arithmetic replay; never import app or fetch live prices.

Legacy charged unit prices are not evidence of a full selling-pack price.
Replay fixes the historical charge in memory and tests the unchanged calculator.
It does not claim to reconstruct a missing historical merchant/full price.
"""

import argparse
import json
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from business.models import QuoteRequest
from business.quote_calculation import calculate_quote


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) and value >= 0 else None


def saved_material_prices(line):
    """Keep record version, charged price and full product-price evidence separate."""
    kind = "current" if "full_unit_price" in line else "legacy"
    full = number(line.get("full_unit_price"))
    charge = number(line.get("unit_price_used"))
    source = "unit_price_used" if charge is not None else "unavailable"
    # Derive a charged unit only when the field was never stored. An invalid
    # explicit value fails closed, rather than being hidden by a fallback.
    if "unit_price_used" not in line:
        total, quantity = number(line.get("line_total")), number(line.get("quantity"))
        if total is not None and quantity is not None and quantity > 0:
            charge, source = total / quantity, "line_total/quantity"
    return {"record_kind": kind, "charge_price": charge, "charge_source": source,
            "full_product_price": full,
            "full_price_source": "full_unit_price" if full is not None else "unavailable"}


METRICS = ("labour", "callout_charge", "travel_charge", "materials", "materials_base",
           "materials_procurement_percent", "materials_procurement_amount", "total_price",
           "deposit_percent", "deposit_amount", "internal_raw_materials",
           "internal_job_multiplier", "internal_after_job_markup", "internal_handling_percent",
           "internal_after_handling", "internal_hidden_uplift", "gross_profit", "margin_percent")


def replay_saved_quote(request, saved):
    """Recompute arithmetic from stored charges without network, cache or DB writes."""
    data = QuoteRequest(**request)
    lines = saved.get("material_lines", [])
    if len(lines) != len(data.materials):
        return {"status": "unavailable", "reason": "material count mismatch"}
    evidence = [saved_material_prices(line) for line in lines]
    if any(e["charge_price"] is None for e in evidence):
        return {"status": "unavailable", "reason": "historical charged price unavailable",
                "material_prices": evidence}
    charges = []
    for item, line, price in zip(data.materials, lines, evidence):
        quantity = number(line.get("quantity"))
        expected_quantity = item.quantity if item.quantity > 0 else 1
        if quantity is None or quantity != expected_quantity or any(
                line.get(key) != getattr(item, key) for key in ("name", "supplier", "url")):
            return {"status": "unavailable", "reason": "saved material identity/quantity mismatch"}
        # This is a replay input only. Missing full product prices remain
        # explicitly unavailable in evidence; they are never called live.
        item.manual_price = price["full_product_price"] or price["charge_price"]
        item.quote_charge_override = price["charge_price"]
        charges.append(price["charge_price"])

    def fetch(url, name, supplier, manual):
        # The calculator only calls this for materials with a URL and without
        # an explicit comparison selection. Index by material instead of fetch
        # count so blank-URL and selected-price rows cannot shift the replay.
        raise AssertionError("Replay must not call a merchant lookup")

    # An in-memory selection routes each replay row around the legacy lookup.
    # For zero charged rows leave its URL blank: zero is valid historical data,
    # but is deliberately not a selectable comparison price in the app model.
    for item, price in zip(data.materials, evidence):
        full = price["full_product_price"]
        if full is not None and full > 0:
            item.selected_comparison_price = full
        elif price["charge_price"] > 0:
            item.selected_comparison_price = price["charge_price"]
        else:
            item.selected_comparison_price = None
            item.url = ""

    charged = iter(charges)
    result = calculate_quote(data, fetch_tracked_price=fetch,
        safe_float=lambda value, default=0: float(value) if value is not None else default,
        material_quote_unit_price=lambda *_: next(charged),
        find_labour_suggestion=lambda *_: {"suggestion": 0, "range": "validation replay"},
        now_uk=lambda: datetime.now(timezone.utc), format_dt=lambda dt: dt.isoformat())
    discrepancies = []
    unavailable = [key for key in METRICS if key not in saved]
    for key in METRICS:
        if key not in saved:
            continue
        expected = number(saved[key])
        actual = number(result[key])
        if expected is None or actual is None or abs(expected - actual) > 0.005:
            discrepancies.append({"field": key, "saved": expected, "replayed": actual})
    for index, (line, actual) in enumerate(zip(lines, result["material_lines"])):
        expected = number(line.get("line_total"))
        if expected is None or abs(expected - actual["line_total"]) > 0.005:
            discrepancies.append({"field": "line_total", "index": index,
                                  "saved": expected, "replayed": actual["line_total"]})
    return {"status": "fail" if discrepancies else "pass", "material_prices": evidence,
            "unavailable_metrics": unavailable, "discrepancies": discrepancies,
            "handling_percent": data.materials_handling_percent,
            "handling_enabled": data.include_materials_handling,
            "scope": "historical charged-price arithmetic; unknown full prices not reconstructed"}


def inspect_quotes(path):
    connection = sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True)
    try:
        rows = connection.execute("SELECT id,request_json,result_json FROM quotes ORDER BY id").fetchall()
        checks = [{"quote_id": ident, **replay_saved_quote(json.loads(request), json.loads(saved))}
                  for ident, request, saved in rows]
        return {"ok": bool(checks) and all(c["status"] == "pass" for c in checks), "quotes": checks}
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()
    result = inspect_quotes(args.database)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

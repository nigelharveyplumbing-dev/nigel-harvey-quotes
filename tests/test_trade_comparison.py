"""Comparison contracts and HTTP integration against disposable storage only."""

import base64
import json
import secrets
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_existing_business_modules = {key for key in sys.modules if key == "business" or key.startswith("business.")}
try:
    from business import trade_comparison as comparison
finally:
    sys.path.pop(0)
    # Keep pure helpers as local references, without preloading the production
    # package before baseline tests import their disposable application copy.
    for _key in list(sys.modules):
        if (_key == "business" or _key.startswith("business.")) and _key not in _existing_business_modules:
            del sys.modules[_key]
from fastapi.testclient import TestClient
from local_browser_server import disposable_app


TITLE = "Acme Valve V15 15mm Chrome Angled"
URL = "https://www.screwfix.com/p/acme/12345"


def page(url=URL, title=TITLE, price="12.00", vat=True, **changes):
    offer = {"@type": "Offer", "price": price, "priceCurrency": "GBP", "url": url,
             "availability": "https://schema.org/InStock",
             "priceSpecification": {"valueAddedTaxIncluded": vat}}
    product = {"@type": "Product", "name": title, "url": url, "brand": {"name": "Acme"},
               "mpn": "V15", "sku": "merchant-sku", "offers": offer}
    product.update(changes)
    return '<h1>' + title + '</h1><script type="application/ld+json">' + json.dumps(product) + '</script>'


def item(supplier="Screwfix", price="12.00", **changes):
    return comparison.inspect_product(page(price=price, **changes), URL, supplier)


class TradeComparisonTests(unittest.TestCase):
    def test_same_model_different_merchant_skus(self):
        a, b = item(), item("Toolstation", "10.00", sku="another-local-code")
        self.assertTrue(comparison.equivalent(a, b))
        result = comparison.annotate([a, b])
        self.assertTrue(result[0]["is_best_price"])
        self.assertEqual(result[0]["supplier"], "Toolstation")
        self.assertEqual(a["saving_vs_best"], 2)

    def test_wrong_brand_same_dimensions_not_equivalent(self):
        a, b = item(), item("Toolstation", "1.00", brand={"name": "Other"})
        self.assertFalse(comparison.equivalent(a, b))
        self.assertFalse(any(x["is_best_price"] for x in comparison.annotate([a, b])))

    def test_wrong_model_same_brand_not_equivalent(self):
        self.assertFalse(comparison.equivalent(item(), item(mpn="V16")))
        self.assertFalse(comparison.equivalent(item(mpn="V-15"), item(mpn="V15")))

    def test_merchant_sku_alone_never_establishes_equivalence(self):
        a, b = item(mpn=""), item("Toolstation", mpn="")
        self.assertFalse(comparison.equivalent(a, b))

    def test_pack_conflicts_never_compared_or_unit_normalised(self):
        a, b = item(), item(title=TITLE + " Pack of 10", numberOfItems=10)
        self.assertFalse(comparison.equivalent(a, b))
        self.assertFalse(any(x["is_best_price"] for x in comparison.annotate([a, b])))
        self.assertIsNone(item(title=TITLE + " Pack of 10", numberOfItems=2)["pack_quantity"])
        self.assertIsNone(item(title=TITLE + " Kit")["pack_quantity"])

    def test_size_finish_connection_and_type_conflicts(self):
        for title in (TITLE.replace("15mm", "22mm"), TITLE.replace("Chrome", "White"),
                      TITLE.replace("Angled", "Straight")):
            self.assertFalse(comparison.equivalent(item(), item(title=title)))
        self.assertFalse(comparison.equivalent(item(title="Acme radiator 600 x 1200 Type 22"),
                                              item(title="Acme radiator 600 x 1200 Type 11")))
        self.assertFalse(comparison.equivalent(item(title="Acme 15mm compression elbow"),
                                              item(title="Acme 15mm endfeed elbow")))
        self.assertFalse(comparison.equivalent(item(title="Acme potable vessel 3 bar"),
                                              item(title="Acme heating vessel 6 bar")))
        self.assertFalse(comparison.equivalent(item(title='Acme 1/2 inch valve'),
                                              item(title='Acme 3/4 inch valve')))

    def test_gtin_checksum_and_conflicting_gtins(self):
        self.assertEqual(comparison.valid_gtin("4006381333931"), "04006381333931")
        self.assertEqual(comparison.valid_gtin("4006381333932"), "")
        self.assertEqual(comparison.valid_gtin("0000000000000"), "")
        self.assertTrue(comparison.equivalent(item(gtin13="4006381333931", brand="", mpn=""),
                                             item(gtin13="4006381333931", brand="", mpn="")))
        self.assertFalse(comparison.equivalent(item(gtin13="4006381333931"), item(gtin13="5012345678900")))

    def test_vat_normalisation_and_ties(self):
        a, b = item(price="12.00"), item("Toolstation", "10.00", vat=False)
        self.assertEqual(b["price_inc_vat"], 12)
        self.assertTrue(all(x["is_best_price"] for x in comparison.annotate([a, b])))

    def test_unknown_vat_is_visible_but_never_ranked(self):
        b = item("Toolstation", "1.00", vat=None)
        self.assertEqual(b["price_provenance"], "public_live")
        self.assertIsNone(b["price_inc_vat"])
        self.assertFalse(any(x["is_best_price"] for x in comparison.annotate([item(), b])))

    def test_vat_label_must_belong_to_the_amount(self):
        parsed = comparison.inspect_product(page(vat=None) + '<p>£12.00 Inc VAT</p><p>£1.00 Ex VAT</p>', URL, "Screwfix")
        self.assertEqual(parsed["vat_basis"], "inc_vat")
        other = comparison.inspect_product(page(vat=None) + '<footer>Prices exclude VAT</footer><p>£1.00 Ex VAT</p>', URL, "Screwfix")
        self.assertEqual(other["vat_basis"], "unknown")

    def test_conflicting_vat_evidence_not_ranked(self):
        parsed = comparison.inspect_product(page(vat=True) + '<p>£12.00 Ex VAT</p>', URL, "Screwfix")
        self.assertEqual(parsed["vat_basis"], "conflict")
        self.assertIsNone(parsed["price_inc_vat"])

    def test_unrelated_lower_page_price_is_not_used(self):
        parsed = comparison.inspect_product(page() + '<aside>Delivery £1.00. Related product £2.00.</aside>', URL, "Screwfix")
        self.assertEqual(parsed["price"], 12)

    def test_aggregate_and_multiple_variant_prices_rejected(self):
        aggregate = {"@type": "AggregateOffer", "lowPrice": "1.00", "priceCurrency": "GBP"}
        self.assertIsNone(item(offers=aggregate)["price"])
        offers = [{"@type": "Offer", "price": price, "priceCurrency": "GBP"} for price in [1, 10]]
        self.assertIsNone(item(offers=offers)["price"])

    def test_non_gbp_and_expired_members_only_prices_rejected(self):
        for fields in ({"priceCurrency": "EUR"}, {"priceValidUntil": "2020-01-01"},
                       {"validForMemberTier": "VIP"}, {"eligibleQuantity": {"value": 10}}):
            offer = {"@type": "Offer", "price": 10, "priceCurrency": "GBP", **fields}
            self.assertIsNone(item(offers=offer)["price"])

    def test_offer_and_product_url_must_match(self):
        self.assertIsNone(item(offers={"price": 1, "priceCurrency": "GBP", "url": "https://www.screwfix.com/p/other/54321"})["price"])
        parsed = comparison.inspect_product(page(url="https://www.screwfix.com/p/other/54321"), URL, "Screwfix")
        self.assertIsNone(parsed["price"])
        variant = comparison.inspect_product(page(url=URL + '?variant=other'), URL + '?variant=chosen', 'Screwfix')
        self.assertIsNone(variant['price'])

    def test_missing_url_only_allowed_when_single_product_matches_heading(self):
        self.assertEqual(item(url="")["price"], 12)
        html = page(url="") + '<script type="application/ld+json">' + json.dumps({"@type": "Product", "name": "Other"}) + '</script>'
        self.assertIsNone(comparison.inspect_product(html, URL, "Screwfix")["price"])

    def test_conflicting_heading_cannot_authenticate_price(self):
        html = page().replace('<h1>' + TITLE + '</h1>', '<h1>Other valve</h1>')
        self.assertIsNone(comparison.inspect_product(html, URL, "Screwfix")["price"])

    def test_out_of_stock_and_preorder_not_best(self):
        for availability in ("OutOfStock", "PreOrder", "BackOrder"):
            offer = {"@type": "Offer", "price": 1, "priceCurrency": "GBP",
                     "availability": "https://schema.org/" + availability,
                     "priceSpecification": {"valueAddedTaxIncluded": True}}
            a, b = item(), item("Toolstation", offers=offer)
            self.assertFalse(any(x["is_best_price"] for x in comparison.annotate([a, b])))

    def test_single_supplier_is_not_comparison(self):
        self.assertFalse(any(x["is_best_price"] for x in comparison.annotate([item(), item(price="10")])) )

    def test_anchor_excludes_different_model_group(self):
        anchor = item()
        other_a, other_b = item(mpn="OTHER"), item("Toolstation", "1", mpn="OTHER")
        self.assertFalse(any(x["is_best_price"] for x in comparison.annotate([anchor, other_a, other_b], anchor)))

    def test_unknown_identity_not_in_best_group(self):
        self.assertFalse(any(x["is_best_price"] for x in comparison.annotate([item(mpn=""), item("Toolstation", mpn="")])))

    def test_invalid_values_rejected(self):
        for value in ("NaN", "Infinity", -1, 0, 100000, None, "bad"):
            self.assertIsNone(comparison.money(value))

    def test_per_length_unit_price_is_not_pack_offer(self):
        offer = {"@type": "Offer", "price": 10, "priceCurrency": "GBP",
                 "priceSpecification": {"valueAddedTaxIncluded": True,
                    "referenceQuantity": {"value": 1, "unitCode": "MTR"}}}
        self.assertIsNone(item(offers=offer)['price'])

    def test_public_url_allowlist(self):
        for url in ("http://www.screwfix.com/p/12345", "https://127.0.0.1/p/12345",
                    "https://screwfix.com.evil.test/p/12345", "https://evil.screwfix.com/p/12345",
                    "https://user:pass@screwfix.com/p/12345", "https://screwfix.com:444/p/12345"):
            self.assertEqual(comparison.supplier_for_url(url), "")
        self.assertEqual(comparison.supplier_for_url(URL), "Screwfix")

    def test_redirect_blocked_before_second_request(self):
        response = SimpleNamespace(status_code=302, headers={"Location": "https://127.0.0.1/private"})
        with patch.object(comparison.requests, "get", return_value=response) as fetch:
            with self.assertRaises(ValueError):
                comparison.fetch_page(URL, "Screwfix")
            fetch.assert_called_once()

    def test_cache_manual_references_dates_and_no_false_winner(self):
        rows = [{"name": TITLE, "supplier": "Screwfix", "url": URL, "last_live_price": 1,
                 "last_manual_price": 0.5, "last_success_at": "2020-01-01", "updated_at": "2021-01-01"},
                {"name": TITLE, "last_price": 0.1, "updated_at": "2022-01-01"}]
        with patch.object(comparison, "_merchant_offers", side_effect=lambda supplier, *_: ([item(supplier, "12")], {"supplier": supplier})):
            result = comparison.compare_prices(TITLE, cache_rows=rows)
        refs = [x for x in result["results"] if x["price_provenance"] != "public_live"]
        self.assertEqual({x["price_provenance"] for x in refs}, {"cached_public", "manual", "cached_unverified"})
        self.assertTrue(all(not x["is_best_price"] and x["saving_vs_best"] is None for x in refs))
        self.assertEqual(next(x for x in refs if x["price_provenance"] == "cached_public")["checked_at"], "2020-01-01")
        self.assertIsNone(next(x for x in refs if x["price_provenance"] == "manual")["checked_at"])
        self.assertFalse(result["account_prices_connected"])

    def test_unconfirmed_anchor_no_badges(self):
        with patch.object(comparison, "_merchant_offers", side_effect=lambda supplier, *_: ([item(supplier)], {"supplier": supplier})):
            result = comparison.compare_prices(TITLE, anchor_url="https://www.screwfix.com/p/missing/99999")
        self.assertFalse(any(x["is_best_price"] for x in result["results"]))

    def test_query_sizes_and_connections_are_not_ignored(self):
        self.assertTrue(comparison.relevant("Acme 15 mm compression elbow", "15mm compression elbow"))
        self.assertFalse(comparison.relevant("Acme 22mm endfeed elbow", "15mm compression elbow"))

    def test_input_bounds_and_invalid_anchor(self):
        for query, url in (("a", ""), ("x" * 221, ""), (TITLE, "https://127.0.0.1/p/12345"),
                           (TITLE, "https://www.screwfix.com/search?q=valve")):
            with self.assertRaises(ValueError):
                comparison.compare_prices(query, anchor_url=url)

    @unittest.skipUnless(shutil.which("node"), "Node is unavailable")
    def test_comparison_ui(self):
        result = subprocess.run(["node", str(Path(__file__).with_suffix(".cjs"))],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class TradeComparisonHTTPTests(unittest.TestCase):
    def test_authenticated_read_only_comparison_and_failed_merchants(self):
        username, password = secrets.token_urlsafe(12), secrets.token_urlsafe(20)
        with disposable_app(username, password) as (app, _), TestClient(app.app) as client:
            auth = {"Authorization": "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()}
            app.upsert_material_price_cache(URL, TITLE, "Screwfix", price=2, manual_price=1, status="live")
            def snapshot():
                connection = app.get_db()
                dump = '\n'.join(connection.iterdump())
                connection.close()
                return dump
            before = snapshot()
            def response(url, **kwargs):
                supplier = comparison.supplier_for_url(url)
                if supplier == "Selco":
                    return SimpleNamespace(status_code=403, text="", headers={})
                config = comparison.merchant_search.LIVE_MERCHANTS[supplier]
                base = 'https://www.' + config["allowed_hosts"][0]
                target = base + ('/p/12345' if supplier != 'Toolstation' else '/acme/p12345')
                if '/search' in url:
                    html = '<script type="application/ld+json">' + json.dumps({"@type": "Product", "name": TITLE, "url": target}) + '</script>'
                else:
                    html = page(url=target, price="10.00" if supplier == 'Toolstation' else "12.00")
                return SimpleNamespace(status_code=200, text=html, headers={})
            with patch.object(comparison.requests, "get", side_effect=response) as fetch:
                self.assertEqual(client.get('/api/best-trade-prices', params={"q": TITLE}).status_code, 401)
                fetch.assert_not_called()
                actual = client.get('/api/best-trade-prices', params={"q": TITLE}, headers=auth)
                self.assertEqual(actual.status_code, 200, actual.text)
                self.assertEqual(actual.headers['cache-control'], 'no-store')
                data = actual.json()
                self.assertEqual([x["supplier"] for x in data["results"] if x["is_best_price"]], ["Toolstation"])
                self.assertEqual(next(x for x in data['merchants'] if x['supplier'] == 'Selco')['status'], 'unavailable')
                self.assertEqual(client.get('/api/best-trade-prices', params={"q": "a"}, headers=auth).status_code, 400)
                self.assertTrue(all(call.kwargs["allow_redirects"] is False for call in fetch.call_args_list))
            self.assertEqual(snapshot(), before, "Comparison altered existing data")

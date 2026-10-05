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
    if not any(word in title.lower() for word in ("pack", "kit", "bundle", "set")):
        product["numberOfItems"] = 1
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
        self.assertIsNone(item(numberOfItems=0)["pack_quantity"])
        self.assertIsNone(item(numberOfItems=-1)["pack_quantity"])

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

    def test_vat_prefix_never_applies_to_preceding_amount(self):
        html = page(price="8.05", vat=None) + '<div>£8.05 ex. VAT £6.71</div>'
        self.assertEqual(comparison.inspect_product(html, URL, 'Screwfix')['vat_basis'], 'unknown')
        html = page(price="6.71", vat=None) + '<div>£8.05 ex. VAT £6.71</div>'
        self.assertEqual(comparison.inspect_product(html, URL, 'Screwfix')['vat_basis'], 'ex_vat')

    def toolstation_page(self, gross="8.05", net="6.71", pack="Each", selected="12212", **changes):
        url = 'https://www.toolstation.com/jg-speedfit-isolating-valve/p12212'
        html = page(url=url, title='JG Speedfit Isolating Valve 15mm', price=gross, vat=None,
                    brand='JG Speedfit', mpn='', sku='12212', numberOfItems=changes.pop('numberOfItems', None), **changes)
        was = changes.pop('was', '')
        html += '<div><span>£' + gross + '</span>' + ('<span>was £' + was + '</span>' if was else '') + '<span>ex. VAT £' + net + '</span></div>'
        html += '<select><option selected value="' + selected + '">15mm - (' + selected + ') - ' + pack + ' - £' + gross + '</option></select>'
        return comparison.inspect_product(html, url, 'Toolstation')

    def test_toolstation_real_dual_vat_layout_is_gross_not_double_taxed(self):
        parsed = self.toolstation_page()
        self.assertEqual(parsed['vat_basis'], 'inc_vat')
        self.assertEqual(parsed['price_inc_vat'], 8.05)
        self.assertEqual(parsed['pack_quantity'], 1)
        self.assertFalse(comparison.annotate([parsed])[0]['is_best_price'])

    def test_toolstation_pack_title_omission_uses_selected_sku_pack(self):
        parsed = self.toolstation_page(gross='1.35', net='1.12', pack='2 Pack')
        self.assertEqual(parsed['pack_quantity'], 2)
        self.assertEqual(parsed['price_inc_vat'], 1.35)

    def test_toolstation_sale_uses_current_selected_price_not_was_price(self):
        parsed = self.toolstation_page(gross='15.59', net='12.99', was='19.49')
        self.assertEqual(parsed['vat_basis'], 'inc_vat')
        self.assertEqual(parsed['price_inc_vat'], 15.59)

    def test_toolstation_wrong_selected_variant_or_implausible_vat_is_unranked(self):
        wrong = self.toolstation_page(selected='39149')
        self.assertIsNone(wrong['pack_quantity'])
        self.assertIsNone(wrong['price_inc_vat'])
        wrong = self.toolstation_page(net='1.00')
        self.assertIsNone(wrong['price_inc_vat'])
        self.assertFalse(comparison.annotate([wrong])[0]['is_best_price'])

    def test_toolstation_selected_pack_conflict_is_rejected(self):
        self.assertIsNone(self.toolstation_page(pack='2 Pack', numberOfItems=1)['pack_quantity'])
        parsed = self.toolstation_page(pack='2 Pack', name='Other product')
        self.assertTrue(parsed['identity_conflict'])
        self.assertIsNone(parsed['price_inc_vat'])

    def test_toolstation_single_variant_requires_bound_main_sku_and_pack(self):
        url = 'https://www.toolstation.com/mcalpine-wm11-washing-machine-trap/p90786'
        html = page(url=url, title='McAlpine WM11 trap', price='14.29', vat=None, sku='90786', numberOfItems=None)
        main = '<main id="main-content"><p>Product code: 90786</p><p>Pack size: Each</p><div>£14.29 ex. VAT £11.91</div></main>'
        parsed = comparison.inspect_product(html + main, url, 'Toolstation')
        self.assertEqual((parsed['pack_quantity'], parsed['price_inc_vat']), (1, 14.29))
        for invalid in (main.replace('90786', '12345'), main.replace('Pack size: Each', 'Pack size: Kit'), main.replace('</main>', '<select></select></main>')):
            self.assertIsNone(comparison.inspect_product(html + invalid, url, 'Toolstation')['pack_quantity'])

    def test_toolstation_review_state_is_not_a_product_variant(self):
        url = 'https://www.toolstation.com/elbow/p77358'
        self.assertEqual(comparison.canonical_url(url + '?bvstate=pg:3/ct:r'), comparison.canonical_url(url))
        self.assertNotEqual(comparison.canonical_url(url + '?variant=other'), comparison.canonical_url(url))
        self.assertNotEqual(comparison.canonical_url(URL + '?bvstate=other'), comparison.canonical_url(URL))

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

    def city_page(self, title='Drayton TRV4 15mm Angled TRV White/Chrome 07 05 0150', price='23.23', sku='818209', brand='Drayton', mpn='07 05 0150', postfix='each, Inc. VAT'):
        url = 'https://www.cityplumbing.co.uk/p/current-product/p/' + sku
        html = page(url=url, title=title, price=price, vat=None, brand='', mpn='', sku=sku, numberOfItems=None)
        html = html.replace(', "availability": "https://schema.org/InStock"', '')
        html += '<div data-test-id="product-code">' + sku + '</div>'
        html += '<div data-test-id="price"><div data-test-id="main-through-price">Was £26.03</div><h2>£' + price + '</h2><div>Log in / register for Trade price</div><span data-test-id="main-price-postfix">' + postfix + '</span><div>VAT: Ex Inc</div></div>'
        html += '<div data-test-id="product-specifications"><span>Supplier Part Number</span><span>' + mpn + '</span><span>Brand Name</span><span>' + brand + '</span></div>'
        return html, url

    def test_city_current_trv_offer_identity_pack_vat(self):
        html, url = self.city_page()
        result = comparison.inspect_product(html, url, 'City Plumbing')
        self.assertEqual((result['brand'], result['mpn'], result['pack_quantity'], result['price_inc_vat']), ('Drayton', '07 05 0150', 1, 23.23))
        self.assertEqual(result['vat_basis'], 'inc_vat')
        self.assertEqual(result['availability'], 'unknown')

    def test_city_current_k2_is_not_k1_or_other_model(self):
        html, url = self.city_page(title='Stelrad Softline Compact K2 Double Panel Radiator 600mm x 1000mm 80602210.', price='101.96', sku='422363', brand='Stelrad', mpn='80602210')
        result = comparison.inspect_product(html, url, 'City Plumbing')
        self.assertEqual((result['mpn'], result['price_inc_vat']), ('80602210', 101.96))
        self.assertFalse(comparison.equivalent(result, {**result, 'mpn':'80601110', 'name':result['name'].replace('K2', 'K1')}))

    def test_city_ex_vat_conversion_requires_own_postfix(self):
        html, url = self.city_page(price='10.00', postfix='each, Ex. VAT')
        self.assertEqual(comparison.inspect_product(html, url, 'City Plumbing')['price_inc_vat'], 12)
        for bad in ('each', 'VAT: Ex Inc', 'Prices exclude VAT'):
            html, url = self.city_page(postfix=bad)
            result = comparison.inspect_product(html, url, 'City Plumbing')
            self.assertIsNone(result['price_inc_vat'])
            self.assertIsNone(result['pack_quantity'])

    def test_city_wrong_code_and_unrelated_toggle_cannot_authenticate(self):
        html, url = self.city_page()
        html = html.replace('<div data-test-id="product-code">818209', '<div data-test-id="product-code">999999')
        result = comparison.inspect_product(html, url, 'City Plumbing')
        self.assertEqual(result['mpn'], '')
        self.assertIsNone(result['price_inc_vat'])

    def test_city_was_price_and_conflicting_vat_rejected(self):
        html, url = self.city_page()
        html = html.replace('<h2>£23.23', '<h2>£26.03')
        self.assertIsNone(comparison.inspect_product(html, url, 'City Plumbing')['price_inc_vat'])
        html, url = self.city_page()
        html += '<p>£23.23 Ex VAT</p>'
        self.assertEqual(comparison.inspect_product(html, url, 'City Plumbing')['vat_basis'], 'conflict')

    def selco_page(self):
        url = 'https://www.selcobw.com/chrome-compression-equal-elbow-15mm'
        title = 'Chrome Compression Equal Elbow 15mm'
        product = {'@type':'Product', 'url':url, 'name':title, 'sku':'344710921', 'offers':{'@type':'Offer','url':url,'price':'3.72','priceCurrency':'GBP','availability':'http://schema.org/InStock','priceValidUntil':'2020-10-05'}}
        html = '<div class="ProductDetail-container-13z"><h1>' + title + '</h1><p class="Sku-root-v0w">Item Code: 344710921</p><div data-test-id="ProductDetail.Actions"><div class="PriceBox-root-RD8 PriceBox-detailVariant-1TS"><span class="PriceBox-itemExVat-skf">£3.10 Ex VAT</span><span class="PriceBox-itemIncVat-vQr">£3.72 Inc VAT</span></div></div></div>'
        html += '<script type="application/ld+json">' + json.dumps(product) + '</script>'
        return html, url

    def test_selco_fresh_price_box_independent_of_expired_schema(self):
        html, url = self.selco_page()
        result = comparison.inspect_product(html, url, 'Selco')
        self.assertEqual((result['price_inc_vat'], result['vat_basis'], result['pack_quantity']), (3.72, 'inc_vat', 1))
        self.assertEqual(result['price_evidence'], 'current_product_price_box')
        self.assertEqual(result['availability'], 'unknown')
        self.assertFalse(comparison.annotate([result])[0]['is_best_price'])

    def test_selco_only_bound_product_pair_can_supply_price(self):
        html, url = self.selco_page()
        for bad in (html.replace('Item Code: 344710921', 'Item Code: 999'), html.replace('£3.10 Ex VAT', '£1.00 Ex VAT'), html.replace('PriceBox-detailVariant-1TS', 'delivery-price'), html.replace('<h1>Chrome Compression Equal Elbow 15mm', '<h1>Different elbow'), html.replace('£3.72 Inc VAT', '£3.72')):
            self.assertIsNone(comparison.inspect_product(bad + '<aside>Delivery £1.00 Inc VAT</aside>', url, 'Selco')['price_inc_vat'])

    def test_fresh_displayed_price_never_revives_unavailable_schema_stock(self):
        html, url = self.selco_page()
        for state in ('OutOfStock', 'SoldOut', 'PreOrder', 'BackOrder'):
            result = comparison.inspect_product(html.replace('InStock', state), url, 'Selco')
            self.assertEqual(result['price_inc_vat'], 3.72)
            result.update(brand='Acme', mpn='V15')
            self.assertFalse(result['is_best_price'] if 'is_best_price' in result else any(x['is_best_price'] for x in comparison.annotate([result, item('Toolstation')], result)))
            self.assertIn(result['availability'], ('out_of_stock', 'preorder', 'backorder'))

    def test_declared_utf8_response_is_not_misdecoded(self):
        content = '<meta charset="utf-8"><p>£3.72 Inc VAT</p>'.encode('utf-8')
        response = SimpleNamespace(status_code=200, headers={}, content=content, text=content.decode('latin-1'))
        with patch.object(comparison.requests, 'get', return_value=response):
            actual, _ = comparison.fetch_page('https://www.selcobw.com/chrome-compression-equal-elbow-15mm', 'Selco')
        self.assertIn('£3.72', actual)
        self.assertNotIn('Â', actual)

    def test_selco_account_bulk_or_other_currency_cannot_fallback(self):
        html, url = self.selco_page()
        for extra in ('"validForMemberTier":"VIP",', '"eligibleQuantity":{"value":10},', '"priceSpecification":{"unitCode":"MTR"},'):
            bad = html.replace('"@type": "Offer",', '"@type": "Offer",' + extra)
            self.assertIsNone(comparison.inspect_product(bad, url, 'Selco')['price_inc_vat'])
        self.assertIsNone(comparison.inspect_product(html.replace('"GBP"', '"EUR"'), url, 'Selco')['price_inc_vat'])

    def test_toolstation_mpn_bound_to_selected_product_accordion(self):
        url = 'https://www.toolstation.com/drayton-trv4/p55827'
        html = page(url=url, title='Drayton TRV4 15mm Angled', price='25.79', vat=None, brand='Drayton', mpn='', sku='55827', numberOfItems=None)
        html += '<main id="main-content"><select><option selected value="55827">15mm Angled - (55827) - Each - £25.79</option></select><div>£25.79 ex. VAT £21.49</div><div id="accordion-content-technical-specification"><table><tr><td>Manufacturer ID</td><td>07 05 0150</td></tr></table></div></main>'
        result = comparison.inspect_product(html, url, 'Toolstation')
        city, city_url = self.city_page()
        other = comparison.inspect_product(city, city_url, 'City Plumbing')
        self.assertTrue(comparison.equivalent(result, other))
        ranked = comparison.annotate([result, other], other)
        self.assertEqual(ranked[0]['supplier'], 'City Plumbing')
        self.assertTrue(ranked[0]['is_best_price'])
        self.assertEqual(result['saving_vs_best'], 2.56)
        bad = html.replace('value="55827"', 'value="61277"')
        self.assertEqual(comparison.inspect_product(bad, url, 'Toolstation')['mpn'], '')

    def test_screwfix_unavailable_does_not_attempt_network(self):
        with patch.object(comparison, 'fetch_page') as fetch:
            offers, status = comparison._merchant_offers('Screwfix', TITLE, URL)
        fetch.assert_not_called()
        self.assertEqual(offers, [])
        self.assertEqual(status['status'], 'unavailable')
        self.assertIn('HTTP 403', status['reason'])

    def test_selected_product_precedes_search_and_navigation_not_inspected(self):
        url = 'https://www.toolstation.com/valve/p12345'
        def fetch(target, *args):
            if target == url:
                return page(url=url, sku='12345', title=TITLE), url
            return '<a href="/plumbing/c15">Plumbing</a>', target
        with patch.object(comparison, 'fetch_page', side_effect=fetch) as mocked:
            offers, status = comparison._merchant_offers('Toolstation', TITLE, url)
        self.assertEqual(mocked.call_args_list[0].args[0], url)
        self.assertEqual(len(offers), 1)
        self.assertEqual(status['status'], 'search_incomplete')
        self.assertEqual(mocked.call_count, 2)

    def test_second_product_url_validated_and_never_establishes_identity(self):
        for value in ('https://127.0.0.1/p/12345', 'https://www.toolstation.com/plumbing/c15', 'https://www.toolstation.com/search?q=valve', 'http://www.toolstation.com/valve/p12345'):
            with self.assertRaises(ValueError):
                comparison.compare_prices(TITLE, anchor_url=URL, comparison_url=value)
        with self.assertRaises(ValueError):
            comparison.compare_prices(TITLE, comparison_url='https://www.toolstation.com/valve/p12345')
        other = 'https://www.toolstation.com/valve/p12345'
        with patch.object(comparison, '_merchant_offers', side_effect=lambda supplier, *_: ([item(supplier, mpn='OTHER' if supplier=='Toolstation' else 'V15')], {'supplier':supplier})):
            result = comparison.compare_prices(TITLE, anchor_url=URL, comparison_url=other)
        self.assertFalse(next(x for x in result['results'] if x['supplier']=='Toolstation')['is_best_price'])

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

    def test_selco_root_slug_can_be_inspected_but_does_not_prove_a_price(self):
        url = 'https://www.selcobw.com/chrome-compression-equal-elbow-15mm'
        with patch.object(comparison, '_merchant_offers', side_effect=lambda supplier, *_: ([], {'supplier': supplier})) as checks:
            result = comparison.compare_prices('Chrome compression equal elbow 15mm', anchor_url=url)
        self.assertEqual(checks.call_count, 4)
        self.assertEqual(result['results'], [])
        for invalid in ('http://www.selcobw.com/chrome-compression-equal-elbow-15mm', 'https://evil.example/chrome-compression-equal-elbow-15mm', url + '#other', 'https://www.selcobw.com/search?q=elbow'):
            with self.assertRaises(ValueError):
                comparison.compare_prices(TITLE, anchor_url=invalid)

    @unittest.skipUnless(shutil.which("node"), "Node is unavailable")
    def test_comparison_ui(self):
        result = subprocess.run(["node", str(Path(__file__).with_suffix(".cjs"))],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class TradeComparisonHTTPTests(unittest.TestCase):
    def test_selected_price_survives_create_edit_without_legacy_lookup(self):
        username, password = secrets.token_urlsafe(12), secrets.token_urlsafe(20)
        with disposable_app(username, password) as (app, _), TestClient(app.app) as client:
            auth = {"Authorization": "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()}
            payload = {"customer_name": "Synthetic comparison test", "materials": [
                {"name": TITLE, "quantity": 3, "supplier": "Screwfix", "url": URL,
                 "manual_price": 12, "selected_comparison_price": 12}]}
            with patch.object(app, "fetch_tracked_price", return_value=(1, "live")) as legacy:
                created = client.post('/api/quote', json=payload, headers=auth)
                self.assertEqual(created.status_code, 200, created.text)
                data = created.json()
                result = data['result']
                line = result['material_lines'][0]
                self.assertEqual(line['full_unit_price'], 12)
                self.assertEqual(line['quantity'], 3)
                self.assertEqual(line['supplier'], 'Screwfix')
                self.assertEqual(line['price_source'], 'selected_public')
                self.assertEqual(result['internal_handling_percent'], 25)
                self.assertEqual(result['total_price'], 45)
                saved = client.get(f"/api/quotes/{data['id']}", headers=auth).json()
                self.assertEqual(saved['request']['materials'][0]['selected_comparison_price'], 12)
                updated = client.put(f"/api/quotes/{data['id']}", json=saved['request'], headers=auth)
                self.assertEqual(updated.status_code, 200, updated.text)
                legacy.assert_not_called()
                payload['materials'][0].pop('selected_comparison_price')
                ordinary = client.post('/api/quote', json=payload, headers=auth)
                self.assertEqual(ordinary.json()['result']['material_lines'][0]['full_unit_price'], 1)
                legacy.assert_called_once()

    def test_invalid_selected_price_rejected(self):
        username, password = secrets.token_urlsafe(12), secrets.token_urlsafe(20)
        with disposable_app(username, password) as (app, _), TestClient(app.app) as client:
            auth = {"Authorization": "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()}
            for amount in (0, -1):
                result = client.post('/api/quote', headers=auth, json={"materials": [
                    {"selected_comparison_price": amount}]})
                self.assertEqual(result.status_code, 422)

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
                target = base + ('/acme/p12345' if supplier == 'Toolstation' else '/p/acme/p/123456' if supplier == 'City Plumbing' else '/p/12345')
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
                self.assertFalse(any(comparison.supplier_for_url(call.args[0]) == 'Screwfix' for call in fetch.call_args_list))
            self.assertEqual(snapshot(), before, "Comparison altered existing data")

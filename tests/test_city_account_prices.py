"""Real supplied product identities, sanitized prices; never owner account data."""
import base64
import copy
import hashlib
import json
import secrets
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from local_browser_server import disposable_app

_path = list(sys.path)
_existing = {key for key in sys.modules if key == "business" or key.startswith("business.")}
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from business import city_account_prices as city
    from business import account_pricing as foundation
    from business.models import MaterialItem
finally:
    # unittest imports every test before running setUpClass. Do not leave the
    # original package cached ahead of another harness's disposable app copy.
    sys.path[:] = _path
    for _key in list(sys.modules):
        if (_key == "business" or _key.startswith("business.")) and _key not in _existing:
            del sys.modules[_key]

NOW = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)


def row(**updates):
    value = dict(city_code="313813", product_name="Wednesbury Plain Copper Tube 15mm × 3m X015L-3",
                 brand="Wednesbury", mpn="X015L-3", gtin="", ex_vat_price="6.00",
                 selling_unit="each", pack_quantity=1, checked_at="2026-10-06", stock_note="Seen in stock at capture only")
    value.update(updates)
    return value


def public(supplier="City Plumbing", **updates):
    value = dict(supplier=supplier, sku="313813" if supplier == "City Plumbing" else "other-sku",
                 name=row()["product_name"], brand="Wednesbury", mpn="X015L-3", gtin="", pack_quantity=1,
                 price_inc_vat=10.80, price_provenance="public_live", availability="in_stock",
                 url="https://www.cityplumbing.co.uk/p/tube/p/313813")
    value.update(updates)
    return value


class CityCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "city.sqlite3"

    def save(self, *rows, now=NOW):
        return city.save(self.path, {"records":list(rows)}, now=now)

    def test_normalization_retains_ex_vat_each_sku_model_and_date_precision(self):
        r = city.capture(row(), now=NOW)
        self.assertEqual((r.price,r.price_inc_vat,r.vat_rate), ("6.00","7.20","0.20"))
        self.assertEqual((r.supplier_sku,r.selling_unit,r.pack_quantity,r.mpn,r.gtin), ("313813","each",1,"X015L-3",""))
        self.assertEqual((r.capture_source,r.checked_precision,r.source_type), (city.SOURCE,"date","account_cached"))
        self.assertEqual(r.checked_at,"2026-10-05T23:00:00+00:00")
        self.assertEqual(r.availability,"unknown")

    def test_rounding_to_penny(self):
        self.assertEqual(city.capture(row(ex_vat_price="0.53"),now=NOW).price_inc_vat,"0.64")

    def test_all_23_real_product_identities_with_sanitized_prices(self):
        fixture = json.loads((Path(__file__).parent / "fixtures/city_owner_capture_sanitized.json").read_text())
        self.assertEqual(len(city.preview(fixture, now=NOW)),23)
        self.assertEqual(city.save(self.path,fixture,now=NOW)["rows"],23)
        records=city.read(self.path,now=NOW)
        self.assertEqual(len(records),23)
        self.assertEqual(sum(not r.mpn for r in records),2)
        self.assertTrue(all(r.gtin == "" and r.price=="6.00" and r.price_inc_vat=="7.20" for r in records))
        self.assertTrue(all(r.source_type=="account_cached" and r.selling_unit=="each" and r.availability=="unknown" for r in records))
        self.assertEqual(city.save(self.path,fixture,now=NOW)["status"],"duplicate")

    def test_superseded_capture_cannot_silently_replace_newer_snapshot(self):
        self.save(row())
        self.save(row(ex_vat_price="7.00"))
        with self.assertRaises(ValueError):self.save(row())
        self.assertEqual(city.read(self.path,now=NOW)[0].price,"7.00")

    def test_preview_and_comparison_do_not_create_or_change_any_database(self):
        city.preview({"records":[row()]},now=NOW)
        self.assertFalse(self.path.exists())
        self.assertEqual(city.read(self.path,now=NOW),[])
        self.save(row())
        before = self.path.read_bytes()
        city.compare(self.path,"313813",[public()],now=NOW)
        self.assertEqual(before,self.path.read_bytes())

    def test_duplicate_row_and_duplicate_update_preserve_age(self):
        self.assertEqual(self.save(row(),row())["rows"],1)
        before = self.path.read_bytes()
        self.assertEqual(self.save(row(),now=NOW+timedelta(hours=1))["status"],"duplicate")
        self.assertEqual(before,self.path.read_bytes())
        self.assertEqual(len(city.read(self.path,now=NOW)),1)

    def test_update_retains_other_products_and_history(self):
        self.save(row(),row(city_code="119745",product_name="Wednesbury Plain Copper Tube 22mm × 3m X022L-3",mpn="X022L-3"))
        self.save(row(ex_vat_price="7.00",checked_at="2026-10-06T12:00:00+00:00"))
        records = city.read(self.path,now=NOW)
        self.assertEqual(len(records),2)
        self.assertEqual(next(r.price for r in records if r.supplier_sku=="313813"),"7.00")
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM account_price_imports').fetchone()[0],2)
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        self.assertEqual(self.path.stat().st_mode & 0o777,0o600)

    def test_malformed_batch_is_atomic_before_first_creation_and_after_save(self):
        for bad in (dict(ex_vat_price="bad"),dict(ex_vat_price="0"),dict(ex_vat_price="NaN"),
                    dict(ex_vat_price="3.001"),dict(city_code="invalid"),dict(selling_unit="metre"),
                    dict(selling_unit="each",pack_quantity=10),dict(checked_at="2027-01-01"),
                    dict(checked_at="2026-10-06T12:00:00"),dict(gtin="12345678"),dict(password="secret")):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.save(row(),row(**bad))
        self.assertFalse(self.path.exists())
        self.save(row())
        before = self.path.read_bytes()
        with self.assertRaises(ValueError): self.save(row(),row(ex_vat_price="bad"))
        self.assertEqual(before,self.path.read_bytes())

    def test_older_capture_and_conflicting_duplicate_are_rejected(self):
        self.save(row())
        with self.assertRaises(ValueError): self.save(row(checked_at="2026-10-05"))
        with self.assertRaises(ValueError): self.save(row(),row(ex_vat_price="9"))

    def test_city_cached_vs_city_toolstation_selco_public_live(self):
        record = city.capture(row(),now=NOW)
        item = city.offer(record,[public(),public("Toolstation",price_inc_vat=12),public("Selco",price_inc_vat=13.20)],now=NOW)
        self.assertTrue(item['cheapest_observed'])
        self.assertEqual([p['saving_using_account'] for p in item['public_comparisons']],["3.60","4.80","6.00"])
        self.assertFalse(item['is_best_price'])
        self.assertFalse(item['stock_confirmed'])
        self.assertTrue(item['selectable'])

    def test_missing_mpn_same_city_sku_requires_exact_description(self):
        record = city.capture(row(brand="",mpn=""),now=NOW)
        self.assertTrue(city.exact_public(record,public(brand="",mpn="")))
        self.assertFalse(city.exact_public(record,public("Toolstation",brand="",mpn="")))
        self.assertFalse(city.exact_public(record,public(name="Different product",brand="",mpn="")))

    def test_pack_mismatch_conflicting_gtin_mpn_and_specs_never_match(self):
        record = city.capture(row(gtin="4006381333931"),now=NOW)
        for change in (dict(pack_quantity=10),dict(mpn="X022L-3"),dict(gtin="05012345678900"),
                       dict(brand="Other"),dict(name="Wednesbury copper 22mm × 3m X015L-3"),dict(identity_conflict=True)):
            with self.subTest(change=change):
                self.assertFalse(city.exact_public(record,public(**{"gtin":record.gtin,**change})))

    def test_gtin_exact_match_never_overrides_conflicting_mpn(self):
        record = city.capture(row(gtin="4006381333931"),now=NOW)
        self.assertTrue(city.exact_public(record,public("Toolstation",gtin=record.gtin)))
        self.assertFalse(city.exact_public(record,public("Toolstation",gtin=record.gtin,mpn="other")))

    def test_stale_price_reference_only_and_no_winner(self):
        record = city.capture(row(checked_at="2026-09-28"),now=NOW)
        item = city.offer(record,[public()],now=NOW)
        self.assertEqual(item['freshness'],'stale')
        self.assertFalse(item['selectable'] or item['cheapest_observed'] or item['is_best_price'])

    def test_unavailable_and_manual_offers_do_not_prove_savings(self):
        record = city.capture(row(),now=NOW)
        for change in (dict(availability="out_of_stock"),dict(availability="preorder"),dict(price_provenance="manual"),dict(price_inc_vat=None)):
            self.assertEqual(city.offer(record,[public(**change)],now=NOW)['public_comparisons'],[])

    def test_saved_snapshot_is_validated_and_bound_to_city_material(self):
        record = city.capture(row(),now=NOW)
        snapshot = city.selection(record)
        value = dict(name=record.name,supplier="City Plumbing",manual_price=7.2,selected_account_price=snapshot)
        self.assertIsNotNone(MaterialItem(**value).selected_account_price)
        for changes in (dict(name="Other"),dict(supplier="Toolstation"),dict(manual_price=1),dict(selected_comparison_price=7.2),
                        dict(selected_account_price={**snapshot,"price_inc_vat":"1"}),
                        dict(selected_account_price={**snapshot,"source_type":"account_live"}),
                        dict(url="https://www.cityplumbing.co.uk/p/other/p/119745")):
            with self.subTest(changes=changes),self.assertRaises(ValueError):MaterialItem(**{**value,**changes})


class CityAccountHTTPTests(unittest.TestCase):
    def test_auth_csrf_preview_atomic_save_read_only_and_quote_create_reopen_edit(self):
        username,password=secrets.token_urlsafe(12),secrets.token_urlsafe(20)
        with disposable_app(username,password) as (app,root),TestClient(app.app) as client:
            auth={'Authorization':'Basic '+base64.b64encode(f'{username}:{password}'.encode()).decode()}
            price_row=row(checked_at=datetime.now(ZoneInfo('Europe/London')).date().isoformat())
            payload={'records':[price_row]}
            path=app.city_account_store_path()
            for url in ('/api/city-account-prices','/api/city-account-prices/preview'):
                self.assertEqual(client.post(url,json=payload).status_code,401)
            self.assertEqual(client.get('/api/city-account-prices').status_code,401)
            self.assertEqual(client.post('/api/city-account-prices',json=payload,headers={**auth,'Origin':'https://evil.example'}).status_code,403)
            preview=client.post('/api/city-account-prices/preview',json=payload,headers=auth)
            self.assertEqual(preview.status_code,200,preview.text)
            self.assertFalse(path.exists())
            self.assertEqual(client.post('/api/city-account-prices',json=payload,headers=auth).json()['status'],'saved')
            self.assertEqual(client.post('/api/city-account-prices',json=payload,headers=auth).json()['status'],'duplicate')
            before_account=path.read_bytes()
            before_quote=app.DB_PATH.read_bytes()
            with patch.object(app.trade_comparison,'compare_prices',return_value={'results':[public()], 'note':'Public', 'merchants':[]}):
                result=client.get('/api/best-trade-prices',params={'q':'313813'},headers=auth)
                self.assertEqual(result.status_code,200,result.text)
                item=result.json()['account_results'][0]
                self.assertFalse(item['is_best_price'])
            self.assertEqual(before_account,path.read_bytes())
            self.assertEqual(before_quote,app.DB_PATH.read_bytes())
            listed=client.get('/api/city-account-prices?q=313813',headers=auth)
            self.assertEqual(listed.headers['cache-control'],'no-store')
            snapshot=listed.json()['results'][0]['selection']
            quote_payload={'customer_name':'Synthetic City capture customer','materials':[dict(name=price_row['product_name'],
                quantity=2,supplier='City Plumbing',url='',manual_price=7.2,selected_account_price=snapshot)]}
            with patch.object(app,'fetch_tracked_price',return_value=(99,'live')) as legacy:
                created=client.post('/api/quote',json=quote_payload,headers=auth)
                self.assertEqual(created.status_code,200,created.text)
                data=created.json();result=data['result'];line=result['material_lines'][0]
                self.assertEqual((line['quantity'],line['full_unit_price'],line['price_source']),(2,7.2,'account_cached'))
                self.assertFalse(line['live_price_used'])
                self.assertEqual((result['internal_handling_percent'],result['total_price']),(25,18))
                saved=client.get('/api/quotes/'+str(data['id']),headers=auth).json()
                self.assertEqual(saved['request']['materials'][0]['selected_account_price'],snapshot)
                # Future owner refresh cannot silently replace a saved quote selection.
                client.post('/api/city-account-prices',json={'records':[dict(price_row,ex_vat_price='9.00')]},headers=auth)
                saved['request']['materials'][0]['quantity']=3
                updated=client.put('/api/quotes/'+str(data['id']),json=saved['request'],headers=auth)
                self.assertEqual(updated.status_code,200,updated.text)
                self.assertEqual(updated.json()['result']['total_price'],27)
                self.assertEqual(updated.json()['result']['material_lines'][0]['full_unit_price'],7.2)
                legacy.assert_not_called()
            with sqlite3.connect(path) as conn:self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(client.get('/api/quotes/'+str(data['id'])+'/pdf',headers=auth).status_code,200)

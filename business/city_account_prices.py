"""Owner-triggered City captures. No merchant login, scraping, feed or startup DDL."""
import hashlib
import json
import re
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from business import account_pricing as foundation
from business import trade_comparison as public

SOURCE_REF = hashlib.sha256(b"local-owner-city-captures-v1").hexdigest()[:32]
SOURCE = "city_app_owner_capture"
FIELDS = {"city_code", "product_name", "brand", "mpn", "gtin", "ex_vat_price",
          "selling_unit", "pack_quantity", "checked_at", "stock_note"}


def capture(row, *, now):
    if not isinstance(row, dict) or set(row) - FIELDS:
        raise ValueError("Unsupported owner-capture fields")
    sku = foundation.text(row.get("city_code"), "City product code")
    if not re.fullmatch(r"\d{6}", sku):
        raise ValueError("City product code must be six digits")
    checked_text = foundation.text(row.get("checked_at"), "checked date/time")
    precision = "date" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", checked_text) else "time"
    if precision == "date":
        checked = datetime.fromisoformat(checked_text).replace(tzinfo=ZoneInfo("Europe/London")).astimezone(timezone.utc)
    else:
        checked = foundation.timestamp(checked_text)
    unit, pack = row.get("selling_unit"), row.get("pack_quantity", 1)
    if unit not in {"each", "pack"} or (unit == "each" and pack != 1):
        raise ValueError("Use each (quantity 1) or an explicitly sized selling pack")
    amount = foundation.decimal(row.get("ex_vat_price"), "ex-VAT price", minimum=foundation.Decimal("0.01"))
    if amount.as_tuple().exponent < -2:
        raise ValueError("Enter an ex-VAT price with at most two decimal places")
    return foundation.record_from_mapping(dict(supplier="City Plumbing", source_ref=SOURCE_REF,
        supplier_sku=sku, name=row.get("product_name"), brand=row.get("brand", ""),
        mpn=row.get("mpn", ""), gtin=row.get("gtin", ""), pack_quantity=pack,
        price=str(amount), vat_basis="ex_vat", vat_rate="0.20", unit_basis="selling_pack",
        source_type="account_cached", checked_at=checked.isoformat(),
        expires_at=(checked + timedelta(days=7)).isoformat(), currency="GBP", availability="unknown",
        selling_unit=unit, capture_source=SOURCE, checked_precision=precision,
        stock_note=row.get("stock_note", "")), now=now)


def validate_batch(payload, *, now):
    if not isinstance(payload, dict) or set(payload) != {"records"}:
        raise ValueError("Supply an owner-capture records list")
    rows = payload["records"]
    if not isinstance(rows, list) or not 0 < len(rows) <= 500:
        raise ValueError("Supply between 1 and 500 captures")
    records = {}
    for index, row in enumerate(rows, 1):
        try:
            record = capture(row, now=now)
        except ValueError as error:
            raise ValueError(f"Capture row {index}: {error}") from None
        previous = records.get(record.supplier_sku)
        if previous and previous != record:
            raise ValueError("Conflicting duplicate City code")
        records[record.supplier_sku] = record
    return list(records.values())


def read(path, *, now):
    if not Path(path).exists():
        return []
    return foundation.read_account_records(path, supplier="City Plumbing", source_ref=SOURCE_REF, now=now)


def preview(payload, *, now):
    return [offer(row, (), now=now) for row in validate_batch(payload, now=now)]


def save(path, payload, *, now):
    # Validate the entire batch before even creating the sidecar. Existing
    # quote/public databases are never opened here. SQLite serializes updates
    # across workers; merge the latest full snapshot inside the write lock.
    incoming = validate_batch(payload, now=now)
    path = Path(path)
    # POSIX lock covers first creation too, including multiple Render workers.
    # No lock or data file is created by reads or previews.
    import fcntl
    import os
    descriptor = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, "wb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _save_locked(path, incoming, now=now)


def _save_locked(path, incoming, *, now):
    if not path.exists():
        try:
            foundation.initialize_account_store(path)
        except FileExistsError:
            pass
    import sqlite3
    with sqlite3.connect(path.resolve().as_uri() + "?mode=rw", uri=True, timeout=15) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN IMMEDIATE")
        latest = connection.execute("SELECT id FROM account_price_imports WHERE supplier=? AND source_ref=? ORDER BY imported_at DESC, id DESC LIMIT 1",
                                    ("City Plumbing", SOURCE_REF)).fetchone()
        rows = connection.execute("SELECT record_json FROM account_price_records WHERE import_id=?", (latest[0],)).fetchall() if latest else []
        records = {r.supplier_sku:r for r in (foundation.record_from_mapping(json.loads(x[0]), now=now) for x in rows)}
        for row in incoming:
            previous = records.get(row.supplier_sku)
            if previous and foundation.timestamp(row.checked_at) < foundation.timestamp(previous.checked_at):
                raise ValueError("An older capture cannot replace a newer City price")
            records[row.supplier_sku] = row
        normalized_rows = [asdict(replace(records[key], imported_at=None)) for key in sorted(records)]
        content = json.dumps(normalized_rows, sort_keys=True, separators=(",", ":")).encode()
        digest = hashlib.sha256(content).hexdigest()
        previous = connection.execute("SELECT id FROM account_price_imports WHERE supplier=? AND source_ref=? AND content_sha256=?",
                                      ("City Plumbing", SOURCE_REF, digest)).fetchone()
        if previous:
            # Identical refresh is not new evidence and cannot reset age.
            if not latest or previous[0] != latest[0]:
                raise ValueError("Capture matches superseded evidence; recheck the price and checked time")
            return {"status":"duplicate", "rows":len(records), "updated_rows":len(incoming)}
        cursor = connection.execute("INSERT INTO account_price_imports (supplier,source_ref,content_sha256,normalized_sha256,imported_at,row_count) VALUES (?,?,?,?,?,?)",
                                    ("City Plumbing", SOURCE_REF, digest, digest, now.isoformat(), len(records)))
        connection.executemany("INSERT INTO account_price_records (import_id,supplier_sku,record_json) VALUES (?,?,?)",
            [(cursor.lastrowid, key, json.dumps(asdict(replace(records[key], imported_at=now.isoformat())), sort_keys=True)) for key in sorted(records)])
        return {"status":"saved", "rows":len(records), "updated_rows":len(incoming)}


def selection(record):
    # Safe, private quote snapshot; no merchant account ID, opaque store ref or credentials.
    return {key:value for key,value in asdict(record).items() if key in {
        "supplier_sku", "name", "brand", "mpn", "gtin", "pack_quantity", "price",
        "vat_basis", "vat_rate", "price_inc_vat", "selling_unit", "source_type",
        "checked_at", "checked_precision", "capture_source", "stock_note"}}


def exact_public(record, item):
    if item.get("identity_conflict") or item.get("pack_quantity") != record.pack_quantity:
        return False
    identity = record.identity()
    if public.equivalent(identity, item):
        # equivalent's GTIN fast-path must never override brand/MPN conflicts.
        return all(not getattr(record, key) or not item.get(key) or normalize(getattr(record, key)) == normalize(item[key])
                   for key, normalize in (("brand", public.normal), ("mpn", public.identifier)))
    # Merchant code is meaningful only within City/PTS, with exact descriptive
    # identity when manufacturer identifiers are missing. Not a cross-merchant SKU match.
    return (item.get("supplier") in {"City Plumbing", "PTS"}
            and str(item.get("sku")) == record.supplier_sku
            and public.normal(item.get("name")) == public.normal(record.name)
            and not (record.gtin and item.get("gtin") and record.gtin != item["gtin"])
            and all(not getattr(record,key) or not item.get(key) or normalize(getattr(record,key)) == normalize(item[key])
                    for key,normalize in (("brand",public.normal),("mpn",public.identifier))))


def offer(record, public_offers, *, now):
    matches = [p for p in public_offers if p.get("price_provenance") == "public_live"
               and p.get("price_inc_vat") and p.get("availability") not in foundation.BLOCKED_STOCK
               and exact_public(record,p)]
    fresh = record.freshness(now)
    gross = foundation.Decimal(record.price_inc_vat)
    comparisons = [{"supplier":p["supplier"], "price_inc_vat":p["price_inc_vat"], "url":p.get("url", ""),
                    "saving_using_account":str((foundation.Decimal(str(p["price_inc_vat"])) - gross).quantize(foundation.Decimal("0.01")))} for p in matches]
    return {**selection(record), "supplier":"City Plumbing", "price_provenance":"account_cached",
            "label":"City Plumbing account price — cached", "freshness":fresh,
            "age_seconds":max(0,int((now-foundation.timestamp(record.checked_at)).total_seconds())),
            "is_best_price":False, "stock_confirmed":False, "availability":"unknown",
            "selectable":fresh == "current", "public_comparisons":comparisons,
            "cheapest_observed":bool(matches) and fresh == "current" and all(gross <= foundation.Decimal(str(p["price_inc_vat"])) for p in matches),
            "selection":selection(record), "imported_at":record.imported_at}


def compare(path, query, public_offers, *, now):
    return [offer(r,public_offers,now=now) for r in read(path,now=now)
            if query == r.supplier_sku or public.relevant(r.name,query) or any(exact_public(r,p) for p in public_offers)]

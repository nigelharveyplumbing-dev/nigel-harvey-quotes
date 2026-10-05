"""Dormant Phase 2 foundation; no app imports, routes, network calls or startup DDL.

Canonical records are NOT a guessed merchant CSV schema. A real export and
approved mapping are required before implementing any merchant file reader.
"""

import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Protocol, Sequence

from business.trade_comparison import equivalent, identifier, normal, valid_gtin


SOURCE_TYPES = frozenset({"account_live", "account_cached", "public_live", "cached_public", "manual"})
ACCOUNT_SUPPLIERS = frozenset({"Wolseley", "City Plumbing", "PTS", "Williams"})
BLOCKED_STOCK = frozenset({"out_of_stock", "preorder", "backorder", "unavailable"})


@dataclass(frozen=True)
class FreshnessPolicy:
    # Internal conservative limits, not claims about merchant validity periods.
    max_live_age_seconds: int = 900
    max_account_cache_age_seconds: int = 604800


def merchant_key(supplier):
    # PTS and City share their website: do not count them as two merchants.
    return "City Plumbing" if supplier == "PTS" else supplier


class ExportFormatRequired(ValueError):
    """An owner export must be inspected before a merchant parser can exist."""


def inspect_wolseley_csv(_content: bytes):
    # Intentionally no CSV reader, column guesses, VAT guesses or DB writes.
    raise ExportFormatRequired("Owner-provided My Prices export and approved column mapping required")


class ReadOnlyAccountConnector(Protocol):
    """Internal interface, NOT the merchant's HTTP endpoints/response schema.

    Implement only after approval and inspection of merchant documentation.
    Supplier SKU plus opaque local source_ref scopes the authorized account.
    No ordering, payments, account creation or merchant-write methods exist.
    """

    def read_prices_and_stock(self, supplier_skus: Sequence[str], *, source_ref: str) -> Sequence[dict]:
        ...


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Timezone-aware timestamp required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Invalid timestamp") from None
    if parsed.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")
    return parsed.astimezone(timezone.utc)


def text(value, field, *, optional=False):
    if optional and value in (None, ""):
        return ""
    if not isinstance(value, str) or not value.strip() or len(value) > 500 or any(ord(c) < 32 for c in value):
        raise ValueError(f"Invalid {field}")
    return value.strip()


def decimal(value, field, *, minimum=Decimal("0"), maximum=Decimal("100000")):
    try:
        if value is None or isinstance(value, bool):
            raise ValueError()
        result = Decimal(str(value))
        if not result.is_finite() or not minimum <= result < maximum:
            raise ValueError()
        return result
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"Invalid {field}") from None


@dataclass(frozen=True)
class PriceRecord:
    supplier: str
    source_ref: str
    supplier_sku: str
    name: str
    gtin: str
    brand: str
    mpn: str
    pack_quantity: int
    price: str
    vat_basis: str
    vat_rate: str | None
    price_inc_vat: str | None
    unit_basis: str
    source_type: str
    checked_at: str
    expires_at: str | None
    availability: str
    currency: str
    imported_at: str | None = None

    def identity(self):
        return {key: getattr(self, key) for key in ("name", "gtin", "brand", "mpn", "pack_quantity")}

    def freshness(self, now, policy=FreshnessPolicy()):
        checked = timestamp(self.checked_at)
        if checked > now:
            return "unknown"
        if self.expires_at is None:
            return "unknown"
        limit = policy.max_account_cache_age_seconds if self.source_type == "account_cached" else policy.max_live_age_seconds
        if (now - checked).total_seconds() >= limit:
            return "stale"
        return "current" if now < timestamp(self.expires_at) else "stale"


def record_from_mapping(row, *, now):
    """Validate a normalized adapter record, preserving unknown VAT/unit/expiry."""
    if not isinstance(row, dict):
        raise ValueError("Record must be a mapping")
    supplier = text(row.get("supplier"), "supplier")
    source = row.get("source_type")
    if source not in SOURCE_TYPES:
        raise ValueError("Invalid source type")
    source_ref = text(row.get("source_ref"), "source reference", optional=not source.startswith("account_"))
    # Random local identifier, never a merchant account number or an email.
    if source_ref and not re.fullmatch(r"[a-f0-9]{32}", source_ref):
        raise ValueError("Opaque local source reference required")
    if source.startswith("account_") and supplier not in ACCOUNT_SUPPLIERS:
        raise ValueError("Unsupported account supplier")
    name = text(row.get("name"), "product name")
    sku = text(row.get("supplier_sku"), "supplier SKU")
    brand, mpn = (text(row.get(key), key, optional=True) for key in ("brand", "mpn"))
    raw_gtin = text(row.get("gtin"), "GTIN", optional=True)
    gtin = valid_gtin(raw_gtin)
    if raw_gtin and not gtin:
        raise ValueError("Invalid GTIN checksum")
    # SKU-only rows may be retained as unconfirmed references, never matched.
    pack = row.get("pack_quantity")
    if type(pack) is not int or not 0 < pack <= 100000:
        raise ValueError("Explicit positive selling-pack quantity required")
    amount = decimal(row.get("price"), "price", minimum=Decimal("0.000001"))
    basis, unit = row.get("vat_basis"), row.get("unit_basis")
    if basis not in {"inc_vat", "ex_vat", "unknown"} or unit not in {"selling_pack", "unknown"}:
        raise ValueError("Invalid VAT or unit basis")
    rate = None if row.get("vat_rate") is None else decimal(row["vat_rate"], "VAT rate", maximum=Decimal("1.01"))
    gross = amount if basis == "inc_vat" else amount * (1 + rate) if basis == "ex_vat" and rate is not None else None
    if unit != "selling_pack":
        gross = None
    checked = timestamp(row.get("checked_at"))
    if checked > now:
        raise ValueError("Price check time is in the future")
    expires = timestamp(row["expires_at"]) if row.get("expires_at") is not None else None
    if expires is not None and expires <= checked:
        raise ValueError("Expiry must follow check time")
    stock = row.get("availability", "unknown")
    if stock not in BLOCKED_STOCK | {"in_stock", "unknown"}:
        raise ValueError("Invalid availability")
    if row.get("currency") != "GBP":
        raise ValueError("Explicit GBP currency required")
    imported = timestamp(row["imported_at"]) if row.get("imported_at") is not None else None
    if imported is not None and (imported < checked or imported > now):
        raise ValueError("Invalid import time")
    return PriceRecord(supplier, source_ref, sku, name, gtin, brand, mpn, pack,
        str(amount), basis, str(rate) if rate is not None else None,
        str(gross.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) if gross is not None else None,
        unit, source, checked.isoformat(), expires.isoformat() if expires else None, stock, "GBP",
        imported.isoformat() if imported else None)


def exact_match(left, right):
    # Matching GTIN cannot override explicit brand/MPN conflicts.
    for key, normalize in (("brand", normal), ("mpn", identifier)):
        if getattr(left, key) and getattr(right, key) and normalize(getattr(left, key)) != normalize(getattr(right, key)):
            return False
    return equivalent(left.identity(), right.identity())


def compare_prices(records, *, now, account_sources=(), manual_supplier=None, policy=FreshnessPolicy()):
    """Pure projection: no I/O, original records/forms remain untouched.

    Account source refs must be explicitly authorized by the caller. A fresh
    account cache can be the preferred merchant reference, NEVER a live winner.
    Unknown/stale records cannot suppress a current public offer.
    """
    authorized = frozenset(account_sources)
    output, groups = [], []
    for record in records:
        freshness = record.freshness(now, policy)
        eligible = (freshness == "current" and record.price_inc_vat is not None
                    and Decimal(record.price_inc_vat) > 0
                    and record.availability not in BLOCKED_STOCK
                    and exact_match(record, record)
                    and (not record.source_type.startswith("account_") or record.source_ref in authorized)
                    and record.source_type in {"account_live", "account_cached", "public_live"})
        item = {"record": record, "freshness": freshness,
                "imported_at": record.imported_at,
                "age_seconds": max(0, int((now - timestamp(record.checked_at)).total_seconds())),
                "eligible": eligible, "preferred_for_supplier": False, "is_best_price": False,
                "saving_vs_best": None, "compared_merchants": 0,
                "requires_cached_confirmation": record.source_type == "account_cached",
                "stock_confirmed": record.availability == "in_stock"}
        output.append(item)
        if eligible:
            group = next((g for g in groups if all(exact_match(record, o["record"]) for o in g)), None)
            if group is None:
                group = []
                groups.append(group)
            group.append(item)
    priority = {"account_live": 0, "account_cached": 1, "public_live": 2}
    for group in groups:
        preferred = []
        for supplier in sorted({merchant_key(o["record"].supplier) for o in group}):
            candidates = [o for o in group if merchant_key(o["record"].supplier) == supplier]
            rank = min(priority[o["record"].source_type] for o in candidates)
            candidates = [o for o in candidates if priority[o["record"].source_type] == rank]
            newest = max(timestamp(o["record"].checked_at) for o in candidates)
            candidates = [o for o in candidates if timestamp(o["record"].checked_at) == newest]
            # Conflicting same-time feeds/accounts are not resolved by cheapest.
            if len({o["record"] for o in candidates}) != 1:
                continue
            chosen = candidates[0]
            chosen["preferred_for_supplier"] = True
            preferred.append(chosen)
        live = [o for o in preferred if o["record"].source_type in {"account_live", "public_live"}]
        if len(live) >= 2:
            best = min(Decimal(o["record"].price_inc_vat) for o in live)
            for item in live:
                item["compared_merchants"] = len(live)
                item["is_best_price"] = Decimal(item["record"].price_inc_vat) == best
                item["saving_vs_best"] = str(Decimal(item["record"].price_inc_vat) - best)
    return {"offers": output, "manual_supplier": manual_supplier}


SCHEMA = """
CREATE TABLE account_price_imports (
    id INTEGER PRIMARY KEY, supplier TEXT NOT NULL, source_ref TEXT NOT NULL,
    content_sha256 TEXT NOT NULL, normalized_sha256 TEXT NOT NULL,
    imported_at TEXT NOT NULL, row_count INTEGER NOT NULL,
    UNIQUE(supplier, source_ref, content_sha256)
);
CREATE TABLE account_price_records (
    id INTEGER PRIMARY KEY, import_id INTEGER NOT NULL REFERENCES account_price_imports(id),
    supplier_sku TEXT NOT NULL, record_json TEXT NOT NULL,
    UNIQUE(import_id, supplier_sku)
);
"""


def initialize_account_store(path):
    """Explicit create-new private sidecar only; cannot migrate/open existing DB."""
    path = Path(path).resolve()
    # Exclusive file creation prevents accidentally targeting the quote DB.
    with path.open("xb"):
        pass
    try:
        path.chmod(0o600)
        with sqlite3.connect(path) as connection:
            connection.executescript(SCHEMA)
    except Exception:
        path.unlink()
        raise


def store_validated_import(path, *, content, records, supplier, source_ref, imported_at):
    """Atomic, idempotent canonical import; NOT a CSV parser or upload route.

    Files/mappings validated by a future inspected merchant adapter. Every row
    is revalidated here; imported_at does not refresh the original check time.
    """
    moment = timestamp(imported_at)
    if not isinstance(content, bytes) or not 0 < len(content) <= 10 * 1024 * 1024:
        raise ValueError("Invalid import content size")
    if not records or len(records) > 50000:
        raise ValueError("Invalid import row count")
    checked = [record_from_mapping(asdict(row), now=moment) for row in records]
    unique = {}
    for row in checked:
        if (row.supplier, row.source_ref, row.source_type) != (supplier, source_ref, "account_cached"):
            raise ValueError("Import must contain one account source and cached prices only")
        if row.supplier_sku in unique and unique[row.supplier_sku] != row:
            raise ValueError("Conflicting duplicate supplier SKU")
        unique[row.supplier_sku] = row
    serialized = [json.dumps(asdict(replace(unique[sku], imported_at=None)), sort_keys=True, separators=(",", ":")) for sku in sorted(unique)]
    digest = hashlib.sha256(content).hexdigest()
    normalized = hashlib.sha256("\n".join(serialized).encode()).hexdigest()
    # mode=rw: a typo cannot silently create a new empty database.
    with sqlite3.connect(Path(path).resolve().as_uri() + "?mode=rw", uri=True) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN IMMEDIATE")
        previous = connection.execute("SELECT id, normalized_sha256 FROM account_price_imports WHERE supplier=? AND source_ref=? AND content_sha256=?",
                                      (supplier, source_ref, digest)).fetchone()
        if previous:
            if previous[1] != normalized:
                raise ValueError("Same file has conflicting normalized evidence")
            return {"import_id": previous[0], "status": "duplicate", "rows": len(unique)}
        cursor = connection.execute("INSERT INTO account_price_imports (supplier, source_ref, content_sha256, normalized_sha256, imported_at, row_count) VALUES (?, ?, ?, ?, ?, ?)",
                                    (supplier, source_ref, digest, normalized, moment.isoformat(), len(unique)))
        connection.executemany("INSERT INTO account_price_records (import_id, supplier_sku, record_json) VALUES (?, ?, ?)",
                               [(cursor.lastrowid, sku, json.dumps(asdict(replace(unique[sku], imported_at=moment.isoformat())), sort_keys=True))
                                for sku in sorted(unique)])
        return {"import_id": cursor.lastrowid, "status": "imported", "rows": len(unique)}


def read_account_records(path, *, supplier, source_ref, now):
    """Read-only latest full snapshot for this source. Never revive older offers."""
    with sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        latest = connection.execute("SELECT id FROM account_price_imports WHERE supplier=? AND source_ref=? ORDER BY imported_at DESC, id DESC LIMIT 1",
                                    (supplier, source_ref)).fetchone()
        if not latest:
            return []
        rows = connection.execute("SELECT record_json FROM account_price_records WHERE import_id=? ORDER BY supplier_sku", (latest[0],)).fetchall()
        return [record_from_mapping(json.loads(row[0]), now=now) for row in rows]

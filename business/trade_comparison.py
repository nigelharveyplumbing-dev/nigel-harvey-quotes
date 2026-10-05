"""Read-only public price comparison. Never calls legacy pricing or cache writes.

Merchant SKUs are not manufacturer identifiers. Only a validated GTIN or brand
plus MPN can establish an exact product; package/spec conflicts still reject it.
"""

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import parse_qsl, quote_plus, urlencode, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from business import merchant_search


NOTE = ("Best Trade Price compares confirmed equivalent products at public prices "
        "checked now, including 20% VAT where explicitly excluded. These are not "
        "your account prices. Delivery, collection costs and branch stock are not "
        "included. Cached and manual prices are references only. Confirm before ordering.")
HEADERS = {"User-Agent": "NigelHarveyLtd/1.0 (+https://www.nigelharveyplumbing.co.uk)",
           "Accept-Language": "en-GB,en;q=0.9"}


def money(value):
    try:
        number = Decimal(str(value).replace("£", "").replace(",", ""))
        if number.is_finite() and 0 < number < 100000:
            return number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        pass
    return None


def normal(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def identifier(value):
    # Manufacturer part punctuation can be significant; never collapse it.
    return str(value or "").strip().casefold()


def canonical_url(url):
    parsed = urlsplit(str(url or ""))
    query = urlencode(sorted((key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                             if not key.lower().startswith("utm_") and key.lower() not in {"gclid", "fbclid"}))
    return (f"https://{parsed.hostname}{parsed.path.rstrip('/')}" + ("?" + query if query else "")) if parsed.hostname else ""


def supplier_for_url(url):
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
            return ""
        for name, config in merchant_search.LIVE_MERCHANTS.items():
            if parsed.hostname in {host for base in config["allowed_hosts"] for host in (base, "www." + base)}:
                return name
    except ValueError:
        pass
    return ""


def fetch_page(url, supplier, deadline=None):
    """Validate every redirect before sending another request; no login/session."""
    for _ in range(3):
        if supplier_for_url(url) != supplier:
            raise ValueError("Unsupported merchant URL")
        remaining = deadline - time.monotonic() if deadline else 9
        if remaining <= 0:
            raise ValueError("Merchant check timed out")
        response = requests.get(url, headers=HEADERS, timeout=(min(3, remaining / 2), min(6, remaining / 2)), allow_redirects=False)
        if response.status_code in (301, 302, 303, 307, 308):
            url = urljoin(url, response.headers.get("Location", ""))
            continue
        if response.status_code != 200 or not response.text:
            raise ValueError("Merchant page unavailable")
        if len(response.text) > 4_000_000:
            raise ValueError("Merchant page too large")
        return response.text, url
    raise ValueError("Too many redirects")


def valid_gtin(value):
    value = str(value or "")
    if not value.isdigit() or len(value) not in (8, 12, 13, 14) or not int(value):
        return ""
    total = sum(int(digit) * (3 if index % 2 == 0 else 1)
                for index, digit in enumerate(reversed(value[:-1])))
    return value.zfill(14) if (10 - total % 10) % 10 == int(value[-1]) else ""


def product_nodes(soup):
    output = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            stack = [json.loads(script.get_text())]
        except (ValueError, TypeError):
            continue
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                types = node.get("@type", [])
                types = types if isinstance(types, list) else [types]
                if "Product" in types:
                    output.append(node)
                # Do not treat nested recommendations as the main product.
                if "@graph" in node:
                    stack.append(node["@graph"])
    return output


def _vat_for_amount(soup, amount):
    # Require VAT text attached to THIS amount, never a footer VAT toggle.
    text = soup.get_text(" ", strip=True)
    bases = set()
    pattern = r"£\s*(\d+(?:,\d{3})*(?:\.\d{1,2})?)\s*(?:each\s*[,·]?\s*)?(inc(?:l(?:uding)?)?|ex(?:cl(?:uding)?)?)\.?\s*VAT"
    for price, kind in re.findall(pattern, text, re.I):
        if money(price) == amount:
            bases.add("inc_vat" if kind.lower().startswith("inc") else "ex_vat")
    return bases.pop() if len(bases) == 1 else "unknown"


def _package(product, title):
    counts = set()
    value = product.get("numberOfItems")
    if isinstance(value, dict):
        value = value.get("value")
    if value is not None:
        try:
            count = int(str(value))
            if count <= 0:
                return None
            counts.add(count)
        except ValueError:
            return None
    for pattern in (r"\bpack\s*(?:of\s*)?(\d+)\b", r"\b(\d+)\s*(?:pack|pk)\b"):
        counts.update(int(n) for n in re.findall(pattern, title, re.I))
    if re.search(r"\btwin\s*pack\b", title, re.I):
        counts.add(2)
    if 0 in counts or len(counts) > 1 or (not counts and re.search(r"\b(pack|bundle|kit|set|multipack)\b", title, re.I)):
        return None
    return next(iter(counts), 1)


def inspect_product(html, url, supplier):
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.select_one("h1")
    title = merchant_search._clean_product_title(heading.get_text(" ", strip=True) if heading else "")
    nodes = product_nodes(soup)
    exact = [node for node in nodes if canonical_url(node.get("url", "")) == canonical_url(url)]
    if len(exact) == 1:
        product = exact[0]
    elif len(nodes) == 1 and not nodes[0].get("url") and title and normal(nodes[0].get("name")) == normal(title):
        product = nodes[0]
    else:
        product = {}
    if not title:
        title = merchant_search._clean_product_title(product.get("name", ""))
    # Conflicting heading/structured identity must not authenticate a price.
    title_conflict = bool(product.get("name") and title and normal(product["name"]) != normal(title))
    brand = product.get("brand") or product.get("manufacturer") or ""
    if isinstance(brand, dict):
        brand = brand.get("name", "")
    brand = str(brand) if isinstance(brand, (str, int)) else ""
    mpn = str(product.get("mpn") or "")
    gtin = next((valid_gtin(product.get(key)) for key in ("gtin14", "gtin13", "gtin12", "gtin8", "gtin")
                 if valid_gtin(product.get(key))), "")
    pack = _package(product, title)
    offers = product.get("offers") or []
    offers = offers if isinstance(offers, list) else [offers]
    amounts = []
    availability = "unknown"
    for offer in offers:
        if not isinstance(offer, dict) or offer.get("@type") == "AggregateOffer":
            continue
        if offer.get("url") and canonical_url(offer["url"]) != canonical_url(url):
            continue
        expires = offer.get("priceValidUntil")
        if expires is not None and (not isinstance(expires, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", expires)
                                    or expires < datetime.now(timezone.utc).date().isoformat()):
            continue
        if offer.get("validForMemberTier"):
            continue
        quantity = offer.get("eligibleQuantity")
        if quantity and (not isinstance(quantity, dict) or str(quantity.get("value")) != "1"):
            continue
        amount = money(offer.get("price"))
        currency = offer.get("priceCurrency")
        if not amount or currency != "GBP":
            continue
        basis = _vat_for_amount(soup, amount)
        specification = offer.get("priceSpecification") or {}
        if isinstance(specification, dict):
            if specification.get("validForMemberTier"):
                continue
            unit = specification.get("referenceQuantity") or specification
            if isinstance(unit, dict):
                code = str(unit.get("unitCode") or unit.get("unitText") or "").upper()
                if code and code not in {"C62", "H87", "EA", "EACH"}:
                    continue
                if unit is not specification and str(unit.get("value")) != "1":
                    continue
            vat = specification.get("valueAddedTaxIncluded")
            explicit = "inc_vat" if vat is True else "ex_vat" if vat is False else "unknown"
            if explicit != "unknown":
                basis = explicit if basis in (explicit, "unknown") else "conflict"
        amounts.append((amount, basis))
        state = str(offer.get("availability", "")).split("/")[-1]
        availability = {"InStock": "in_stock", "OutOfStock": "out_of_stock",
                        "Discontinued": "out_of_stock", "PreOrder": "preorder",
                        "BackOrder": "backorder"}.get(state, "unknown")
    distinct = set(amounts)
    amount, basis = next(iter(distinct)) if len(distinct) == 1 and not title_conflict else (None, "unknown")
    gross = amount if basis == "inc_vat" else (amount * Decimal("1.20")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if amount and basis == "ex_vat" else None
    return {"name": title, "supplier": supplier, "url": url, "brand": brand, "mpn": mpn,
            "gtin": gtin, "pack_quantity": pack, "price": float(amount) if amount else None,
            "vat_basis": basis, "price_inc_vat": float(gross) if gross else None,
            "currency": "GBP" if amount else "unknown", "availability": availability,
            "price_provenance": "public_live" if amount else "unavailable",
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "identity_conflict": title_conflict, "sku": str(product.get("sku") or "")}


def equivalent(left, right):
    if left.get("identity_conflict") or right.get("identity_conflict"):
        return False
    if left.get("pack_quantity") is None or left.get("pack_quantity") != right.get("pack_quantity"):
        return False
    if left.get("gtin") and right.get("gtin") and left["gtin"] != right["gtin"]:
        return False
    # Explicit specifications cannot contradict even when identifiers match.
    for pattern in (r"\btype\s*\d+\b", r"\d+(?:\.\d+)?\s*(?:mm|ml|litres?|l|m)\b",
                    r"\d+\s*[x×]\s*\d+(?:\s*[x×]\s*\d+)?",
                    r"\b(?:white|chrome|black|anthracite)\b", r"\b(?:angled|straight)\b",
                    r"\b(?:compression|endfeed|pushfit)\b", r"\d+(?:\.\d+)?\s*bar\b",
                    r'\b\d+\s*/\s*\d+\s*(?:inch|in\b|bsp|\")',
                    r"\b(?:potable|heating)\b", r"\b(?:plastic|brass|copper|steel)\b"):
        a = {normal(x) for x in re.findall(pattern, left.get("name", ""), re.I)}
        b = {normal(x) for x in re.findall(pattern, right.get("name", ""), re.I)}
        if a and b and a != b:
            return False
    if left.get("gtin") and left.get("gtin") == right.get("gtin"):
        return True
    return bool(normal(left.get("brand")) and normal(left.get("brand")) == normal(right.get("brand"))
                and identifier(left.get("mpn")) and identifier(left.get("mpn")) == identifier(right.get("mpn")))


def relevant(title, query):
    # Every requested word/size matters. No fuzzy score establishes equivalence.
    tokens = re.findall(r"[a-z0-9]+", re.sub(r"(\d)\s+(mm|cm|ml|m|l)\b", r"\1\2", query.lower()))
    wanted = {word for word in tokens if word not in {"x", "the", "a", "for", "and"}}
    actual = set(re.findall(r"[a-z0-9]+", re.sub(r"(\d)\s+(mm|cm|ml|m|l)\b", r"\1\2", title.lower())))
    return bool(wanted) and wanted <= actual


def annotate(offers, anchor=None):
    groups = []
    for offer in offers:
        offer.update(is_best_price=False, saving_vs_best=None, comparison_group=None)
        if offer.get("price_provenance") != "public_live" or not offer.get("price_inc_vat"):
            offer["comparison_reason"] = "Reference price or VAT/price not confirmed"
            continue
        if offer.get("availability") in ("out_of_stock", "preorder", "backorder"):
            offer["comparison_reason"] = "Not currently available to buy"
            continue
        if not equivalent(offer, offer) or (anchor and not equivalent(anchor, offer)):
            offer["comparison_reason"] = "Exact product and pack equivalence not confirmed"
            continue
        group = next((group for group in groups if all(equivalent(offer, other) for other in group)), None)
        if group is None:
            group = []
            groups.append(group)
        group.append(offer)
    for index, group in enumerate(groups):
        merchant_count = len({offer["supplier"] for offer in group})
        best = min(money(offer["price_inc_vat"]) for offer in group)
        for offer in group:
            offer["comparison_group"] = index + 1
            offer["comparison_reason"] = "Same manufacturer product and pack" if merchant_count > 1 else "Only one confirmed merchant price"
            offer["compared_merchants"] = merchant_count
            if merchant_count > 1:
                price = money(offer["price_inc_vat"])
                offer["is_best_price"] = price == best
                offer["saving_vs_best"] = float(price - best)
    return sorted(offers, key=lambda item: (not item.get("is_best_price"),
                  item.get("comparison_group") or 999, item.get("price_inc_vat") or 999999,
                  item.get("supplier", ""), item.get("url", "")))


def _merchant_offers(supplier, query, anchor_url=""):
    config = merchant_search.LIVE_MERCHANTS[supplier]
    urls = []
    if supplier_for_url(anchor_url) == supplier:
        urls.append(anchor_url)
    status = "unavailable"
    deadline = time.monotonic() + 22
    search_urls = list(config["search_urls"][:1])
    category = merchant_search._toolstation_radiator_category_url(query) if supplier == "Toolstation" else ""
    if category:
        search_urls.insert(0, category)
    for template in search_urls:
        try:
            html, page_url = fetch_page(template.format(query=quote_plus(query)), supplier, deadline)
            products = merchant_search._extract_search_page_products(
                html, page_url, supplier, config["allowed_hosts"],
                safe_float=lambda value, default=0: float(money(value) or default), normalize_material_url=lambda value: value)
            urls.extend(product["url"] for product in products[:3]
                        if supplier_for_url(product["url"]) == supplier)
            status = "checked"
            if products:
                break
        except (requests.RequestException, ValueError):
            continue
    output, seen = [], set()
    for url in urls[:4]:
        key = canonical_url(url)
        if key in seen:
            continue
        seen.add(key)
        try:
            html, final_url = fetch_page(url, supplier, deadline)
            offer = inspect_product(html, final_url, supplier)
            if relevant(offer["name"], query) or key == canonical_url(anchor_url):
                output.append(offer)
        except (requests.RequestException, ValueError):
            continue
    return output, {"supplier": supplier, "status": status, "products_checked": len(output),
                    "search_url": config["search_urls"][0].format(query=quote_plus(query))}


def compare_prices(query, *, anchor_url="", cache_rows=()):
    query = re.sub(r"\s+", " ", query).strip()
    if len(query) < 3 or len(query) > 220:
        raise ValueError("Enter a product description between 3 and 220 characters.")
    if anchor_url and (not supplier_for_url(anchor_url) or not merchant_search._looks_like_product_url(anchor_url, supplier_for_url(anchor_url))):
        raise ValueError("Use a supported merchant's HTTPS product URL.")
    suppliers = list(merchant_search.LIVE_MERCHANTS)
    with ThreadPoolExecutor(max_workers=4) as pool:
        batches = list(pool.map(lambda supplier: _merchant_offers(supplier, query, anchor_url), suppliers))
    offers = [offer for batch, _ in batches for offer in batch]
    anchor = next((offer for offer in offers if canonical_url(offer["url"]) == canonical_url(anchor_url)), None)
    for row in cache_rows:
        if not relevant(row.get("name", ""), query):
            continue
        # Preserve separately recorded values; a manual entry is never live.
        for field, provenance, date in (("last_live_price", "cached_public", "last_success_at"),
                                        ("last_manual_price", "manual", "updated_at")):
            amount = money(row.get(field))
            if amount:
                offers.append({"name": row.get("name", ""), "supplier": row.get("supplier", ""),
                               "url": row.get("url", ""), "price": float(amount),
                               "price_provenance": provenance,
                               "checked_at": row.get(date) if provenance == "cached_public" else None,
                               "record_updated_at": row.get("updated_at"),
                               "vat_basis": "unknown", "price_inc_vat": None, "currency": "unknown"})
        if not money(row.get("last_live_price")) and not money(row.get("last_manual_price")) and money(row.get("last_price")):
            offers.append({"name": row.get("name", ""), "supplier": row.get("supplier", ""),
                           "url": row.get("url", ""), "price": float(money(row["last_price"])),
                           "price_provenance": "cached_unverified", "checked_at": None,
                           "record_updated_at": row.get("updated_at"),
                           "vat_basis": "unknown", "price_inc_vat": None, "currency": "unknown"})
    ranked = annotate(offers, anchor)
    if anchor_url and anchor is None:
        for offer in ranked:
            offer.update(is_best_price=False, saving_vs_best=None, comparison_group=None,
                         comparison_reason="Selected product could not be confirmed")
    return {"query": query, "anchor_url": anchor_url, "results": ranked,
            "merchants": [status for _, status in batches], "note": NOTE,
            "account_prices_connected": False}

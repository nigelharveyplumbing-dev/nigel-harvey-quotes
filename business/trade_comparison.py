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
                             if not key.lower().startswith("utm_") and key.lower() not in {"gclid", "fbclid"}
                             and not (parsed.hostname in {"toolstation.com", "www.toolstation.com"} and key.lower() == "bvstate")))
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
            raise ValueError(f"Merchant page unavailable (HTTP {response.status_code})")
        if len(response.text) > 4_000_000:
            raise ValueError("Merchant page too large")
        # Requests defaults text/html without a charset to Latin-1. Selco's
        # current HTML explicitly declares UTF-8; honour that declaration.
        content = getattr(response, 'content', b'')
        if re.search(br'<meta\s+charset=[\"\x27]?utf-8', content[:4096], re.I):
            return content.decode("utf-8"), url
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
    texts = {node.get_text(" ", strip=True) for node in soup.find_all(["p", "span", "div", "dd", "dt", "td", "strong"])
             if len(node.get_text(" ", strip=True)) <= 250}
    bases = set()
    amount_pattern = r"(\d+(?:,\d{3})*(?:\.\d{1,2})?)"
    kind_pattern = r"(inc(?:l(?:uding)?)?|ex(?:cl(?:uding)?)?)\.?\s*VAT"
    # A label followed by another amount belongs to that following amount.
    # E.g. Toolstation: £8.05 ex. VAT £6.71, not £8.05 excluding VAT.
    pattern = r"£\s*" + amount_pattern + r"\s*(?:each\s*[,·]?\s*)?" + kind_pattern + r"(?!\s*£)"
    for text in texts:
        for price, kind in re.findall(pattern, text, re.I):
            if money(price) == amount:
                bases.add("inc_vat" if kind.lower().startswith("inc") else "ex_vat")
        for kind, price in re.findall(kind_pattern + r"\s*£\s*" + amount_pattern, text, re.I):
            if money(price) == amount:
                bases.add("inc_vat" if kind.lower().startswith("inc") else "ex_vat")
    return bases.pop() if len(bases) == 1 else "unknown"


def _toolstation_variant(soup, product, amount=None):
    """Bind visible selected selling pack/price to this merchant SKU, not siblings."""
    selected = soup.select('select option[selected]')
    sku = str(product.get("sku") or "")
    if selected:
        if len(selected) != 1 or not sku or selected[0].get("value") != sku:
            return None, "unknown"
        text = selected[0].get_text(" ", strip=True)
        match = re.search(r"\(\s*" + re.escape(sku) + r"\s*\)\s*-\s*(Each|\d+\s+Pack)\s*-\s*£\s*(\d+\.\d{2})\s*$", text, re.I)
        if not match:
            return None, "unknown"
        pack_text, gross = match[1], money(match[2])
    else:
        # Single-variant pages have no selector. Require the main product's
        # visible SKU and unambiguous selling-pack label; never read sidebars.
        main = soup.select_one('#main-content')
        if not main or main.select('select') or not sku:
            return None, "unknown"
        labels = {node.get_text(" ", strip=True) for node in main.find_all(['p', 'span'])}
        codes = {m[1] for value in labels if (m := re.fullmatch(r'Product code:\s*(\d+)', value))}
        packs = {m[1] for value in labels if (m := re.fullmatch(r'Pack size:\s*(Each|\d+\s+Pack)', value, re.I))}
        if codes != {sku} or len(packs) != 1:
            return None, "unknown"
        pack_text, gross = next(iter(packs)), amount
    pack = 1 if pack_text.lower() == "each" else int(pack_text.split()[0])
    if pack <= 0:
        return None, "unknown"
    if amount is None or amount != gross:
        return pack, "unknown"
    # The selected gross and labelled net must appear together in a small price
    # container. Do not infer VAT from the site's footer or unrelated products.
    for node in soup.find_all(["div", "p", "span"]):
        value = node.get_text(" ", strip=True)
        if len(value) > 100:
            continue
        pair = re.fullmatch(r"£\s*(\d+\.\d{2})(?:\s+was\s+£\s*\d+\.\d{2})?\s+ex\.?\s*VAT\s+£\s*(\d+\.\d{2})", value, re.I)
        if pair and money(pair[1]) == gross:
            net = money(pair[2])
            if net and abs(net * Decimal("1.20") - gross) <= Decimal("0.01"):
                return pack, "inc_vat"
    return pack, "unknown"


def _package(product, title, display_pack=None):
    counts = {display_pack} if display_pack is not None else set()
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


def _city_details(soup, product, amount=None):
    """Current PDP code, specification and price/postfix, never the VAT toggle."""
    sku = str(product.get("sku") or "")
    codes = {n.get_text(strip=True) for n in soup.select('[data-test-id="product-code"]')}
    if not sku or codes != {sku}:
        return {}
    details = {}
    specs = soup.select('[data-test-id="product-specifications"]')
    if len(specs) == 1:
        children = specs[0].find_all('span', recursive=False)
        values = {}
        for index in range(0, len(children) - 1, 2):
            key, value = (n.get_text(' ', strip=True) for n in children[index:index + 2])
            values.setdefault(key, set()).add(value)
        for field, label in (("brand", "Brand Name"), ("mpn", "Supplier Part Number")):
            found = values.get(label, set())
            if len(found) == 1:
                details[field] = next(iter(found))
    blocks = soup.select('[data-test-id="price"]')
    if len(blocks) != 1:
        return details
    prices = blocks[0].select('h2')
    postfix = blocks[0].select('[data-test-id="main-price-postfix"]')
    if len(prices) != 1 or len(postfix) != 1:
        return details
    current = re.fullmatch(r'£\s*(\d+(?:,\d{3})*\.\d{2})', prices[0].get_text(' ', strip=True))
    unit = re.fullmatch(r'each,\s*(Inc|Ex)\.?\s*VAT', postfix[0].get_text(' ', strip=True), re.I)
    details['pack'] = 1 if unit else None
    if current and unit and amount == money(current[1]):
        details['vat'] = 'inc_vat' if unit[1].lower() == 'inc' else 'ex_vat'
    return details


def _toolstation_mpn(soup, product):
    # The technical accordion belongs to the selected SKU, not hasVariant.
    pack, _ = _toolstation_variant(soup, product)
    if pack is None:
        return ''
    specs = soup.select('#main-content #accordion-content-technical-specification')
    if len(specs) != 1:
        return ''
    models = set()
    for row in specs[0].select('tr'):
        cells = row.find_all('td', recursive=False)
        if len(cells) == 2 and cells[0].get_text(strip=True) == 'Manufacturer ID':
            models.add(cells[1].get_text(' ', strip=True))
    return next(iter(models)) if len(models) == 1 else ''


def _selco_current_offer(soup, product):
    """Fresh displayed main offer, independent of Selco's expired JSON-LD offer.

    Require the current product title/code and its detail price box with both
    explicitly labelled VAT amounts. An expired schema offer supplies neither
    price nor stock to this fallback.
    """
    offer = product.get('offers')
    if not isinstance(offer, dict) or offer.get('@type') != 'Offer' or offer.get('priceCurrency') != 'GBP' or offer.get('validForMemberTier') or offer.get('eligibleQuantity') or offer.get('priceSpecification'):
        return None
    containers = soup.select('[class*="ProductDetail-container-"]')
    if len(containers) != 1 or not product.get('sku'):
        return None
    main = containers[0]
    headings = main.select('h1')
    codes = {n.get_text(' ', strip=True) for n in main.select('p[class*="Sku-root-"]')}
    if len(headings) != 1 or normal(headings[0].get_text()) != normal(product.get('name')) or codes != {'Item Code: ' + str(product['sku'])}:
        return None
    actions = main.select('[data-test-id="ProductDetail.Actions"]')
    if len(actions) != 1:
        return None
    boxes = actions[0].select('[class*="PriceBox-detailVariant-"]')
    if len(boxes) != 1:
        return None
    values = {}
    for field, label in (('gross', 'Inc'), ('net', 'Ex')):
        nodes = boxes[0].select('[class*="PriceBox-item' + label + 'Vat-"]')
        if len(nodes) != 1:
            return None
        match = re.fullmatch(r'£\s*(\d+\.\d{2})\s*' + label + r'\s+VAT', nodes[0].get_text(' ', strip=True), re.I)
        values[field] = money(match[1]) if match else None
    if not all(values.values()) or abs(values['net'] * Decimal('1.20') - values['gross']) > Decimal('0.01'):
        return None
    return values['gross']


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
    city = _city_details(soup, product) if supplier == 'City Plumbing' and product else {}
    display_mpn = city.get('mpn', '') if supplier == 'City Plumbing' else _toolstation_mpn(soup, product) if supplier == 'Toolstation' else ''
    display_brand = city.get('brand', '')
    if (brand and display_brand and normal(brand) != normal(display_brand)) or (mpn and display_mpn and identifier(mpn) != identifier(display_mpn)):
        title_conflict = True
    brand, mpn = brand or display_brand, mpn or display_mpn
    gtin = next((valid_gtin(product.get(key)) for key in ("gtin14", "gtin13", "gtin12", "gtin8", "gtin")
                 if valid_gtin(product.get(key))), "")
    display_pack = _toolstation_variant(soup, product)[0] if supplier == "Toolstation" else city.get('pack')
    pack = _package(product, title, display_pack)
    # A Toolstation title often omits its multi-pack. Without a selected SKU
    # selling-unit control, do not silently assume a single item.
    if supplier == "Toolstation" and display_pack is None and not product.get("numberOfItems"):
        pack = None
    if 'pack' in city and display_pack is None:
        pack = None
    offers = product.get("offers") or []
    offers = offers if isinstance(offers, list) else [offers]
    amounts = []
    availability = "unknown"
    blocked_availability = ''
    for offer in offers:
        if not isinstance(offer, dict) or offer.get("@type") == "AggregateOffer":
            continue
        if offer.get("url") and canonical_url(offer["url"]) != canonical_url(url):
            continue
        state = str(offer.get('availability', '')).split('/')[-1]
        blocked_availability = {'OutOfStock':'out_of_stock', 'SoldOut':'out_of_stock',
                                'Discontinued':'out_of_stock', 'PreOrder':'preorder',
                                'BackOrder':'backorder'}.get(state, blocked_availability)
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
        if supplier == 'City Plumbing':
            city_basis = _city_details(soup, product, amount).get('vat', 'unknown')
            if city_basis != 'unknown':
                basis = city_basis if basis in (city_basis, 'unknown') else 'conflict'
        if supplier == "Toolstation":
            _, variant_basis = _toolstation_variant(soup, product, amount)
            if variant_basis != "unknown":
                basis = variant_basis if basis in (variant_basis, "unknown") else "conflict"
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
                        "Discontinued": "out_of_stock", "SoldOut": "out_of_stock", "PreOrder": "preorder",
                        "BackOrder": "backorder"}.get(state, "unknown")
    price_evidence = 'structured_offer'
    if supplier == 'Selco' and product and not title_conflict:
        displayed = _selco_current_offer(soup, product)
        if displayed:
            # A fresh displayed offer does not revive expired schema stock.
            if not amounts:
                amounts.append((displayed, 'inc_vat'))
                price_evidence = 'current_product_price_box'
            elif any(value != displayed or vat not in ('unknown', 'inc_vat') for value, vat in amounts):
                amounts = [(displayed, 'conflict')]
            else:
                amounts = [(displayed, 'inc_vat')]
    if blocked_availability:
        availability = blocked_availability
    distinct = set(amounts)
    amount, basis = next(iter(distinct)) if len(distinct) == 1 and not title_conflict else (None, "unknown")
    gross = amount if basis == "inc_vat" else (amount * Decimal("1.20")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if amount and basis == "ex_vat" else None
    return {"name": title, "supplier": supplier, "url": url, "brand": brand, "mpn": mpn,
            "gtin": gtin, "pack_quantity": pack, "price": float(amount) if amount else None,
            "vat_basis": basis, "price_inc_vat": float(gross) if gross else None,
            "currency": "GBP" if amount else "unknown", "availability": availability,
            "price_provenance": "public_live" if amount else "unavailable",
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "identity_conflict": title_conflict, "sku": str(product.get("sku") or ""),
            "price_evidence": price_evidence if amount else None}


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


def product_url_allowed(url):
    supplier = supplier_for_url(url)
    path = urlsplit(url).path
    if urlsplit(url).fragment:
        return False
    if supplier == 'Toolstation':
        return bool(re.fullmatch(r'/[^/]+/p\d{4,8}/?', path))
    if supplier == 'City Plumbing':
        return bool(re.fullmatch(r'/p/[^/]+/p/\d{5,}/?', path))
    if supplier == 'Selco':
        return bool(re.fullmatch(r'/[a-z0-9]+(?:-[a-z0-9]+){2,}/?', path) or merchant_search._looks_like_product_url(url, supplier))
    return bool(supplier and merchant_search._looks_like_product_url(url, supplier))


def _merchant_offers(supplier, query, anchor_url="", comparison_url=""):
    config = merchant_search.LIVE_MERCHANTS[supplier]
    if supplier == 'Screwfix':
        # Staging receives CloudFront HTTP 403. No permitted reliable live
        # source established; do not probe alternative clients or routes.
        return [], {'supplier': supplier, 'status': 'unavailable', 'products_checked': 0,
                    'search_url': '', 'reason': 'Live comparison unavailable: public retrieval is not reliably permitted (staging HTTP 403).'}
    urls = [url for url in (anchor_url, comparison_url) if url and supplier_for_url(url) == supplier]
    status = "unavailable"
    deadline = time.monotonic() + 22
    output, seen = [], set()
    failures = []

    def check_product(url, explicit=False):
        key = canonical_url(url)
        if key in seen or not product_url_allowed(url):
            return
        seen.add(key)
        try:
            html, final_url = fetch_page(url, supplier, deadline)
            offer = inspect_product(html, final_url, supplier)
            if relevant(offer['name'], query) or explicit:
                output.append(offer)
        except (requests.RequestException, ValueError, UnicodeError) as error:
            failures.append(str(error) if isinstance(error, ValueError) else 'Merchant request failed')

    # Selected pages must not lose their budget to client-rendered searches or
    # unrelated category/navigation links returned by the legacy discovery.
    for url in urls:
        check_product(url, explicit=True)
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
            products = [p for p in products if supplier_for_url(p['url']) == supplier and product_url_allowed(p['url'])]
            urls = [p['url'] for p in products[:3]]
            status = "checked" if products else "search_incomplete"
            if products:
                break
        except (requests.RequestException, ValueError, UnicodeError):
            continue
    for url in urls[:4]:
        check_product(url)
    return output, {"supplier": supplier, "status": status, "products_checked": len(output),
                    "reason": '; '.join(dict.fromkeys(failures))[:240] if failures else 'Search supplies no reliable product links' if status == 'search_incomplete' else '',
                    "search_url": config["search_urls"][0].format(query=quote_plus(query))}


def compare_prices(query, *, anchor_url="", comparison_url="", cache_rows=()):
    query = re.sub(r"\s+", " ", query).strip()
    if len(query) < 3 or len(query) > 220:
        raise ValueError("Enter a product description between 3 and 220 characters.")
    for value in (anchor_url, comparison_url):
        if value and (len(value) > 2000 or not product_url_allowed(value)):
            raise ValueError("Use a supported merchant's HTTPS product URL.")
    if comparison_url and not anchor_url:
        raise ValueError('Enter the selected product URL before another merchant URL.')
    suppliers = list(merchant_search.LIVE_MERCHANTS)
    with ThreadPoolExecutor(max_workers=4) as pool:
        batches = list(pool.map(lambda supplier: _merchant_offers(supplier, query, anchor_url, comparison_url), suppliers))
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

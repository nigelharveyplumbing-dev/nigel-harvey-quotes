"""Merchant product search, parsing and live price inspection.

Database updates and quote pricing remain owned by app.py and are passed in explicitly.
"""

import json
import re
from datetime import datetime
from urllib.parse import quote_plus, urlencode, urljoin, urlparse
import requests
from bs4 import BeautifulSoup

def scrape_live_price(url: str, *, safe_float):
    if not url:
        return None

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; NigelHarveyLtd/1.0; +https://www.nigelharveyplumbing.co.uk)",
            "Accept-Language": "en-GB,en;q=0.9",
            "Cache-Control": "no-cache",
        }
        r = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        if r.status_code != 200 or not r.text:
            return None

        soup = BeautifulSoup(r.text, "html.parser")

        # Structured/meta price data first
        meta_candidates = []
        for selector, attr in [
            ('meta[property="product:price:amount"]', "content"),
            ('meta[property="og:price:amount"]', "content"),
            ('meta[itemprop="price"]', "content"),
            ('span[itemprop="price"]', "content"),
            ('span[itemprop="price"]', "data-price"),
        ]:
            tag = soup.select_one(selector)
            if tag and tag.get(attr):
                meta_candidates.append(tag.get(attr))
            elif tag and tag.get_text(strip=True):
                meta_candidates.append(tag.get_text(strip=True))

        # JSON-LD product offers
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                payload = json.loads(script.get_text(strip=True))
                items = payload if isinstance(payload, list) else [payload]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    offers = item.get("offers")
                    offers_list = offers if isinstance(offers, list) else [offers]
                    for offer in offers_list:
                        if isinstance(offer, dict):
                            val = offer.get("price") or offer.get("lowPrice")
                            if val is not None:
                                meta_candidates.append(str(val))
            except Exception:
                pass

        for value in meta_candidates:
            price = safe_float(str(value).replace("£", "").replace(",", ""), None)
            if price and 0 < price < 100000:
                return round(price, 2)

        page_text = soup.get_text(" ", strip=True)
        lower_url = url.lower()
        domain_patterns = []

        if "cityplumbing" in lower_url:
            domain_patterns = [
                r'£\s?(\d+(?:,\d{3})*(?:\.\d{2})?)\s*each,\s*Inc\.?\s*VAT',
                r'£\s?(\d+(?:,\d{3})*(?:\.\d{2})?)\s*Inc\.?\s*VAT',
                r'£\s?(\d+(?:,\d{3})*(?:\.\d{2})?)\s*each',
                r'Inc\.?\s*VAT\s*£\s?(\d+(?:,\d{3})*(?:\.\d{2})?)',
            ]
        elif "toppstiles" in lower_url:
            domain_patterns = [
                r'£\s?(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:per m2|/m2|m2)',
                r'£\s?(\d+(?:,\d{3})*(?:\.\d{2})?)'
            ]
        else:
            domain_patterns = [
                r'£\s?(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:each|inc\.?\s*vat)?'
            ]

        for pattern in domain_patterns:
            matches = re.findall(pattern, page_text, re.IGNORECASE)
            for match in matches:
                price = safe_float(str(match).replace(",", ""), None)
                if price and 0 < price < 100000:
                    return round(price, 2)

        generic_matches = re.findall(r'£\s?(\d+(?:,\d{3})*(?:\.\d{2})?)', page_text)
        prices = []
        for match in generic_matches:
            price = safe_float(str(match).replace(",", ""), None)
            if price and 0 < price < 100000:
                prices.append(price)

        if prices:
            return round(min(prices), 2)

    except Exception:
        return None

    return None


LIVE_MERCHANTS = {
    "City Plumbing": {
        "search_urls": [
            "https://www.cityplumbing.co.uk/search?q={query}",
            "https://www.cityplumbing.co.uk/search?text={query}",
        ],
        "allowed_hosts": ["cityplumbing.co.uk"],
    },
    "Screwfix": {
        "search_urls": [
            "https://www.screwfix.com/search?search={query}",
            "https://www.screwfix.com/search?query={query}",
        ],
        "allowed_hosts": ["screwfix.com"],
    },
    "Toolstation": {
        "search_urls": ["https://www.toolstation.com/search?q={query}"],
        "allowed_hosts": ["toolstation.com"],
    },
    "Selco": {
        "search_urls": [
            "https://www.selcobw.com/search?q={query}",
            "https://www.selcobw.com/catalogsearch/result/?q={query}",
        ],
        "allowed_hosts": ["selcobw.com"],
    },
}


def _clean_product_title(value: str):
    value = BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True)
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"\s*[|\-–]\s*(City Plumbing|Screwfix|Toolstation|Selco).*$", "", value, flags=re.I)
    return value[:220]


def _merchant_host_allowed(url: str, allowed_hosts):
    host = (urlparse(url).netloc or "").lower()
    return any(host == allowed or host.endswith("." + allowed) for allowed in allowed_hosts)


def _looks_like_product_url(url: str, merchant_name: str):
    lower = (url or "").lower()
    if any(part in lower for part in [
        "/search", "catalogsearch", "/category/", "/categories/", "/help/",
        "/stores", "/login", "/basket", "/checkout", "javascript:", "#",
    ]):
        return False
    if merchant_name == "Screwfix":
        return "/p/" in lower or re.search(r"/\d{4,8}$", lower) is not None
    if merchant_name == "Toolstation":
        return "/p" in lower or re.search(r"/\d{4,8}$", lower) is not None
    if merchant_name == "City Plumbing":
        return "/p/" in lower or "/product/" in lower or re.search(r"/\d{5,}$", lower) is not None
    if merchant_name == "Selco":
        return "/products/" in lower or "/product/" in lower or re.search(r"/\d{5,}$", lower) is not None
    return True


def _toolstation_radiator_category_url(query: str):
    """
    Toolstation's free-text search page can be client-rendered, while filtered
    radiator category pages normally contain server-readable product cards.
    Build a filtered category URL when dimensions and panel type are known.
    """
    intent = _product_search_intent(query)
    if intent.get("product_type") != "radiator":
        return ""

    dims = list(intent.get("dimensions") or [])
    if len(dims) != 2:
        return ""

    # Radiator descriptions may be written W x H or H x W.
    # Toolstation filters use explicit height and width fields.
    numbers = sorted((int(value) for value in dims))
    height = numbers[0]
    width = numbers[1]

    params = [
        ("ts_height", f"{height}mm"),
        ("ts_width", f"{width}mm"),
    ]
    radiator_type = intent.get("radiator_type")
    if radiator_type:
        params.append(("type", f"Type {radiator_type}"))

    return (
        "https://www.toolstation.com/central-heating-supplies/"
        "central-heating-radiators/c318?"
        + urlencode(params)
    )


def _extract_toolstation_products(html: str, page_url: str, *, safe_float, normalize_material_url):
    """
    Extract Toolstation product cards from category/search HTML, embedded JSON,
    and product links. This parser accepts both 1200 x 600 and 600 x 1200.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    candidates = []

    def add_candidate(name="", url="", price=0, sku="", image_url=""):
        clean_url = normalize_material_url(urljoin(page_url, str(url or "")))
        if not clean_url or not _merchant_host_allowed(clean_url, ["toolstation.com"]):
            return
        if not _looks_like_product_url(clean_url, "Toolstation"):
            return
        clean_name = _clean_product_title(name)
        if len(clean_name) < 5:
            return
        candidates.append({
            "name": clean_name,
            "url": clean_url,
            "price": round(safe_float(price, 0), 2),
            "sku": str(sku or ""),
            "image_url": str(image_url or ""),
        })

    # 1. JSON-LD and other embedded JSON objects.
    for script in soup.select("script"):
        raw = script.string or script.get_text(" ", strip=True)
        if not raw or len(raw) < 20:
            continue

        payloads = []
        if script.get("type") == "application/ld+json":
            try:
                payloads.append(json.loads(raw))
            except Exception:
                pass
        elif any(token in raw for token in ['"productCode"', '"productId"', '"sku"', '"price"', '/p']):
            # Some pages contain JSON in application state scripts.
            try:
                payloads.append(json.loads(raw))
            except Exception:
                # Pull individual product-looking JSON objects without failing
                # the whole page when the script contains JavaScript wrappers.
                for match in re.finditer(
                    r'\{[^{}]{0,2500}"(?:productCode|productId|sku)"[^{}]{0,2500}\}',
                    raw,
                    re.I | re.S,
                ):
                    try:
                        payloads.append(json.loads(match.group(0)))
                    except Exception:
                        continue

        stack = list(payloads)
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
                continue
            if not isinstance(item, dict):
                continue
            stack.extend(value for value in item.values() if isinstance(value, (dict, list)))

            name = (
                item.get("name")
                or item.get("productName")
                or item.get("title")
                or item.get("displayName")
                or ""
            )
            url = (
                item.get("url")
                or item.get("productUrl")
                or item.get("pdpUrl")
                or item.get("canonicalUrl")
                or ""
            )
            sku = (
                item.get("sku")
                or item.get("productCode")
                or item.get("productId")
                or item.get("code")
                or ""
            )
            price_value = (
                item.get("price")
                or item.get("sellingPrice")
                or item.get("currentPrice")
                or item.get("formattedPrice")
                or 0
            )
            if isinstance(price_value, dict):
                price_value = (
                    price_value.get("value")
                    or price_value.get("amount")
                    or price_value.get("incVat")
                    or price_value.get("gross")
                    or 0
                )
            if isinstance(price_value, str):
                price_match = re.search(r"£?\s*(\d+(?:\.\d{1,2})?)", price_value)
                price_value = price_match.group(1) if price_match else 0

            image = item.get("image") or item.get("imageUrl") or item.get("primaryImage") or ""
            if isinstance(image, list):
                image = image[0] if image else ""
            if isinstance(image, dict):
                image = image.get("url") or image.get("src") or ""

            if name and url:
                add_candidate(name, url, price_value, sku, image)

    # 2. Product-card anchors. Read the surrounding card text for title, code and price.
    for anchor in soup.select('a[href*="/p"]'):
        href = anchor.get("href") or ""
        target = urljoin(page_url, href)
        if not _looks_like_product_url(target, "Toolstation"):
            continue

        card = anchor
        for _ in range(6):
            parent = getattr(card, "parent", None)
            if not parent:
                break
            card = parent
            card_text = re.sub(r"\s+", " ", card.get_text(" ", strip=True))
            if "product code" in card_text.lower() or "£" in card_text:
                break

        card_text = re.sub(r"\s+", " ", card.get_text(" ", strip=True))
        title = (
            anchor.get("aria-label")
            or anchor.get("title")
            or anchor.get_text(" ", strip=True)
        )
        if len(_clean_product_title(title)) < 8:
            heading = card.select_one("h1, h2, h3, h4, [class*='title'], [class*='name']")
            if heading:
                title = heading.get_text(" ", strip=True)

        price = 0
        price_match = re.search(r"£\s*(\d+(?:\.\d{1,2})?)", card_text)
        if price_match:
            price = safe_float(price_match.group(1), 0)

        sku = ""
        sku_match = re.search(r"product\s*code\s*:?\s*(\d{4,8})", card_text, re.I)
        if sku_match:
            sku = sku_match.group(1)
        else:
            url_sku = re.search(r"/p(\d{4,8})(?:[/?#]|$)", target, re.I)
            if url_sku:
                sku = url_sku.group(1)

        image_url = ""
        image = card.select_one("img[src], img[data-src]")
        if image:
            image_url = urljoin(page_url, image.get("src") or image.get("data-src") or "")

        add_candidate(title, target, price, sku, image_url)

    # 3. Last-resort regex for product paths embedded in page source.
    for match in re.finditer(
        r'(?P<url>/[a-z0-9][a-z0-9\-_/]*?/p(?P<sku>\d{4,8}))',
        html or "",
        re.I,
    ):
        target = urljoin(page_url, match.group("url"))
        start = max(0, match.start() - 1200)
        end = min(len(html), match.end() + 1200)
        nearby = BeautifulSoup((html or "")[start:end], "html.parser").get_text(" ", strip=True)
        nearby = re.sub(r"\s+", " ", nearby)

        title_match = re.search(
            r"([A-Z][A-Za-z0-9&+\-()' ]{15,180}(?:Radiator|Convector)[A-Za-z0-9&+\-()' ]{0,100})",
            nearby,
            re.I,
        )
        if not title_match:
            continue

        price_match = re.search(r"£\s*(\d+(?:\.\d{1,2})?)", nearby)
        add_candidate(
            title_match.group(1),
            target,
            price_match.group(1) if price_match else 0,
            match.group("sku"),
            "",
        )

    output, seen = [], set()
    for item in candidates:
        key = normalize_material_url(item.get("url", "")).split("?")[0].rstrip("/")
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(item)

    return output[:20]


def _extract_search_page_products(html: str, search_url: str, merchant_name: str, allowed_hosts, *, safe_float, normalize_material_url):
    if merchant_name == "Toolstation":
        toolstation_items = _extract_toolstation_products(html, search_url, safe_float=safe_float, normalize_material_url=normalize_material_url)
        if toolstation_items:
            return toolstation_items

    soup = BeautifulSoup(html or "", "html.parser")
    candidates = []

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(script.get_text(strip=True))
        except Exception:
            continue
        stack = payload if isinstance(payload, list) else [payload]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
                continue
            if not isinstance(item, dict):
                continue
            stack.extend(value for value in item.values() if isinstance(value, (dict, list)))
            if str(item.get("@type", "")).lower() not in ("product", "listitem"):
                continue
            target = item.get("url") or item.get("item")
            if isinstance(target, dict):
                target = target.get("url")
            if not target:
                continue
            target = urljoin(search_url, str(target))
            if not _merchant_host_allowed(target, allowed_hosts) or not _looks_like_product_url(target, merchant_name):
                continue
            offers = item.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            price = safe_float((offers.get("price") or offers.get("lowPrice") or 0) if isinstance(offers, dict) else 0, 0)
            candidates.append({
                "name": _clean_product_title(item.get("name") or item.get("title") or ""),
                "url": target,
                "price": round(price, 2) if price else 0,
            })

    for anchor in soup.select("a[href]"):
        target = urljoin(search_url, anchor.get("href") or "")
        if not _merchant_host_allowed(target, allowed_hosts) or not _looks_like_product_url(target, merchant_name):
            continue
        title = _clean_product_title(anchor.get("aria-label") or anchor.get("title") or anchor.get_text(" ", strip=True))
        if len(title) >= 5:
            candidates.append({"name": title, "url": target, "price": 0})

    output, seen = [], set()
    for item in candidates:
        clean_url = normalize_material_url(item.get("url", ""))
        key = clean_url.split("?")[0].rstrip("/")
        if not key or key in seen:
            continue
        seen.add(key)
        item["url"] = clean_url
        output.append(item)
        if len(output) >= 8:
            break
    return output


def _read_product_page_details(product, merchant_name, *, safe_float, normalize_material_url, scrape_live_price):
    url = normalize_material_url(product.get("url", ""))
    name = product.get("name", "")
    price = safe_float(product.get("price", 0), 0)
    availability = ""
    image_url = str(product.get("image_url") or "")
    sku = str(product.get("sku") or "")
    checked_at = datetime.now().isoformat(timespec="seconds")
    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; NigelHarveyLtd/1.0; +https://www.nigelharveyplumbing.co.uk)",
                "Accept-Language": "en-GB,en;q=0.9",
            },
            timeout=9,
            allow_redirects=True,
        )
        if response.status_code == 200 and response.text:
            url = normalize_material_url(response.url or url)
            soup = BeautifulSoup(response.text, "html.parser")
            og_title = soup.select_one('meta[property="og:title"]')
            og_image = soup.select_one('meta[property="og:image"]')
            page_h1 = soup.select_one("h1")
            if og_title and og_title.get("content"):
                name = _clean_product_title(og_title.get("content"))
            elif page_h1:
                name = _clean_product_title(page_h1.get_text(" ", strip=True))
            if og_image and og_image.get("content"):
                image_url = urljoin(url, og_image.get("content"))
            for script in soup.select('script[type="application/ld+json"]'):
                try:
                    payload = json.loads(script.get_text(strip=True))
                except Exception:
                    continue
                stack = payload if isinstance(payload, list) else [payload]
                while stack:
                    item = stack.pop()
                    if isinstance(item, list):
                        stack.extend(item)
                        continue
                    if not isinstance(item, dict):
                        continue
                    stack.extend(v for v in item.values() if isinstance(v, (dict, list)))
                    if str(item.get("@type", "")).lower() == "product":
                        sku = str(item.get("sku") or item.get("mpn") or item.get("productID") or sku or "")
                        image = item.get("image")
                        if not image_url:
                            if isinstance(image, list) and image:
                                image_url = str(image[0])
                            elif isinstance(image, str):
                                image_url = image
            body_text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
            if not sku:
                m = re.search(r"(?:product\s*code|item\s*code|sku|part\s*number)\s*[:#]?\s*([A-Z0-9\-]{4,30})", body_text, re.I)
                if m:
                    sku = m.group(1)
                elif merchant_name == "Toolstation":
                    m = re.search(r"/p(\d{4,8})(?:[/?#]|$)", url, re.I)
                    if m:
                        sku = m.group(1)

            if not price and merchant_name == "Toolstation":
                # Toolstation commonly exposes the VAT-inclusive selling price
                # as visible text even when generic metadata is incomplete.
                price_patterns = [
                    r"£\s*(\d+(?:\.\d{1,2})?)\s*ex\.\s*VAT",
                    r"(?:price|sellingPrice|currentPrice)[^0-9£]{0,30}£?\s*(\d+(?:\.\d{1,2})?)",
                    r"£\s*(\d+(?:\.\d{1,2})?)",
                ]
                for pattern in price_patterns:
                    m = re.search(pattern, body_text, re.I)
                    if m:
                        candidate_price = safe_float(m.group(1), 0)
                        if candidate_price > 0:
                            price = candidate_price
                            break

            if not price:
                price = safe_float(scrape_live_price(url), 0)
            page_text = soup.get_text(" ", strip=True).lower()
            if any(word in page_text for word in ["in stock", "available for delivery", "available to collect"]):
                availability = "Available"
            elif any(word in page_text for word in ["out of stock", "currently unavailable"]):
                availability = "Unavailable"
    except Exception:
        pass

    return {
        "name": name or "Merchant product",
        "supplier": merchant_name,
        "url": url,
        "default_price": round(price, 2) if price else 0,
        "live_price": round(price, 2) if price else 0,
        "price_source": "live" if price else "unavailable",
        "availability": availability,
        "image_url": image_url,
        "sku": sku,
        "checked_at": checked_at,
    }


def _product_search_intent(query: str):
    q = re.sub(r"\s+", " ", (query or "").lower()).strip()
    dims = re.search(r"(\d{3,4})\s*[x×]\s*(\d{3,4})", q)
    dimensions = set(dims.groups()) if dims else set()
    radiator_type = ""
    radiator_style = ""
    type_match = re.search(r"\btype\s*(11|21|22)\b", q)
    if type_match:
        radiator_type = type_match.group(1)

    if any(term in q for term in ["towel radiator", "towelrad", "heated towel"]):
        radiator_style = "towel"
    elif "vertical radiator" in q:
        radiator_style = "vertical"
    elif "designer radiator" in q:
        radiator_style = "designer"
    elif "column radiator" in q:
        radiator_style = "column"
    elif "like for like radiator" in q:
        radiator_style = "like_for_like"
    elif "panel radiator" in q or radiator_type:
        radiator_style = "panel"

    if "radiator" in q or "convector" in q:
        product_type = "radiator"
    elif "trv" in q or "thermostatic radiator valve" in q:
        product_type = "trv"
    elif "lockshield" in q:
        product_type = "lockshield"
    elif "radiator valve" in q or "valve set" in q:
        product_type = "radiator_valve_set"
    elif "toilet" in q or "wc" in q:
        product_type = "toilet"
    elif "tap" in q:
        product_type = "tap"
    else:
        product_type = "general"
    return {"query": q, "dimensions": dimensions, "radiator_type": radiator_type, "radiator_style": radiator_style, "product_type": product_type}


def _strict_product_match(name: str, query: str):
    intent = _product_search_intent(query)
    title = re.sub(r"\s+", " ", (name or "").lower()).strip()
    if not title:
        return 0, False, "Missing product title"

    category_noise = [
        "painting & decorating", "power tools", "bricks & blocks", "air bricks",
        "plumbing fittings", "building materials", "work tools", "category",
        "central heating radiators", "search results", "shop all",
    ]
    if any(term in title for term in category_noise):
        return 0, False, "Category or unrelated page"

    ptype = intent["product_type"]
    score = 35
    required_terms = []
    forbidden_terms = []

    if ptype == "radiator":
        required_terms = ["radiator"]
        forbidden_terms = ["electric", "panel heater"]
        style = intent.get("radiator_style", "")

        is_towel = any(term in title for term in ["towel radiator", "towelrad", "heated towel"])
        is_vertical = "vertical" in title
        is_designer = "designer" in title
        is_column = "column radiator" in title or "column" in title
        is_panel = any(term in title for term in ["convector", "panel radiator", "type 11", "type 21", "type 22"])

        if style == "towel":
            if not is_towel:
                return 0, False, "Not a towel radiator"
            score += 25
        elif style == "vertical":
            if not is_vertical:
                return 0, False, "Not a vertical radiator"
            score += 25
        elif style == "designer":
            if not is_designer:
                return 0, False, "Not a designer radiator"
            score += 25
        elif style == "column":
            if not is_column:
                return 0, False, "Not a column radiator"
            score += 25
        elif style == "panel":
            if not is_panel or is_towel:
                return 0, False, "Not the selected panel radiator type"
            score += 22
        elif style == "like_for_like":
            if is_towel and "towel" not in intent["query"]:
                return 0, False, "Existing radiator style still needs confirmation"
            score += 8
        else:
            # No style must never silently promote a Type 11/21/22 result.
            return 0, False, "Radiator type has not been selected"

        if "white" in intent["query"] and "white" in title:
            score += 5
    elif ptype == "trv":
        required_terms = ["trv"] if "trv" in title else ["thermostatic", "radiator", "valve"]
        forbidden_terms = ["radiator", "heater"] if "valve" not in title else []
    elif ptype == "lockshield":
        required_terms = ["lockshield", "valve"]
    elif ptype == "radiator_valve_set":
        required_terms = ["radiator", "valve"]
    elif ptype == "toilet":
        required_terms = ["toilet"]
    elif ptype == "tap":
        required_terms = ["tap"]

    if required_terms and not all(term in title for term in required_terms):
        return 0, False, "Wrong product type"
    if any(term in title for term in forbidden_terms):
        return 0, False, "Wrong product subtype"
    score += 25 if required_terms else 0

    if intent["dimensions"]:
        title_numbers = set(re.findall(r"\b\d{3,4}\b", title))
        if intent["dimensions"].issubset(title_numbers):
            score += 28
        else:
            return 0, False, "Dimensions do not match"

    if intent["radiator_type"]:
        type_no = intent["radiator_type"]
        if re.search(rf"\btype\s*{type_no}\b", title):
            score += 12
        else:
            return 0, False, "Radiator type does not match"

    query_terms = {x for x in re.findall(r"[a-z0-9]+", intent["query"]) if len(x) > 2}
    title_terms = set(re.findall(r"[a-z0-9]+", title))
    score += min(12, len(query_terms & title_terms) * 2)
    return min(99, score), score >= 72, ""


def search_live_merchant_products(query: str, suppliers=None, per_supplier: int = 5, *, safe_float, normalize_material_url, scrape_live_price, upsert_material_price_cache):
    query = re.sub(r"\s+", " ", (query or "")).strip()
    if len(query) < 3:
        return []

    selected = suppliers or list(LIVE_MERCHANTS.keys())
    results = []

    for merchant_name in selected:
        merchant = LIVE_MERCHANTS.get(merchant_name)
        if not merchant:
            continue

        merchant_candidates = []
        search_urls = list(merchant["search_urls"])

        if merchant_name == "Toolstation":
            category_url = _toolstation_radiator_category_url(query)
            if category_url:
                search_urls.insert(0, category_url)

        for url_template in search_urls:
            search_url = (
                url_template.format(query=quote_plus(query))
                if "{query}" in url_template
                else url_template
            )
            try:
                response = requests.get(
                    search_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; NigelHarveyLtd/1.0; +https://www.nigelharveyplumbing.co.uk)",
                        "Accept-Language": "en-GB,en;q=0.9",
                    },
                    timeout=10,
                    allow_redirects=True,
                )
                if response.status_code == 200 and response.text:
                    merchant_candidates = _extract_search_page_products(
                        response.text, response.url, merchant_name, merchant["allowed_hosts"],
                        safe_float=safe_float, normalize_material_url=normalize_material_url
                    )

                    # Toolstation sometimes supplies a category/search response
                    # whose product cards are only partly rendered. Product URLs
                    # found in the raw response are still valid candidates and
                    # are opened individually for title and live-price checking.
                    if merchant_name == "Toolstation" and not merchant_candidates:
                        for match in re.finditer(r'href=["\']([^"\']*/p\d{4,8}[^"\']*)', response.text, re.I):
                            product_url = urljoin(response.url, match.group(1))
                            merchant_candidates.append({
                                "name": "Toolstation product",
                                "url": product_url,
                                "price": 0,
                            })

                    if merchant_candidates:
                        break
            except Exception:
                continue

        accepted = 0
        for product in merchant_candidates:
            detailed = _read_product_page_details(product, merchant_name, safe_float=safe_float, normalize_material_url=normalize_material_url, scrape_live_price=scrape_live_price)
            score, is_match, rejection = _strict_product_match(detailed.get("name", ""), query)
            if not is_match:
                continue
            detailed["match_score"] = score
            detailed["search_only"] = False
            detailed["strict_match"] = True
            if detailed["url"]:
                upsert_material_price_cache(
                    detailed["url"], detailed["name"], detailed["supplier"],
                    price=detailed["live_price"] or None, manual_price=0,
                    status=detailed["price_source"],
                )
            results.append(detailed)
            accepted += 1
            if accepted >= max(1, per_supplier):
                break

        if accepted == 0:
            results.append({
                "name": f"Search {merchant_name} for {query}",
                "supplier": merchant_name,
                "url": merchant["search_urls"][0].format(query=quote_plus(query)),
                "default_price": 0,
                "live_price": 0,
                "price_source": "merchant_search",
                "availability": "",
                "search_only": True,
                "strict_match": False,
                "match_score": 0,
            })

    # Best-price comparison metadata. Only strict product matches with a
    # positive live price participate. Public merchant pages are deliberately
    # labelled public_live: authenticated/account-specific prices must never be
    # implied unless a future merchant integration can prove that provenance.
    comparable = [
        item for item in results
        if not item.get("search_only")
        and item.get("strict_match")
        and safe_float(item.get("live_price", 0), 0) > 0
    ]
    best_price = min(
        (safe_float(item.get("live_price", 0), 0) for item in comparable),
        default=0,
    )
    for item in results:
        price = safe_float(item.get("live_price", 0), 0)
        item["price_provenance"] = "public_live" if price > 0 and not item.get("search_only") else "unavailable"
        item["is_best_price"] = bool(best_price and price > 0 and abs(price - best_price) < 0.005)
        item["saving_vs_best"] = round(max(0, price - best_price), 2) if best_price and price > 0 else 0

    # Put confirmed priced matches first, cheapest first. Match score remains
    # the tie-breaker; strict matching above prevents price from promoting an
    # incompatible product.
    results.sort(key=lambda item: (
        1 if item.get("search_only") else 0,
        0 if safe_float(item.get("live_price", 0), 0) > 0 else 1,
        safe_float(item.get("live_price", 0), 0) or 999999,
        -safe_float(item.get("match_score", 0), 0),
    ))
    return results[:20]

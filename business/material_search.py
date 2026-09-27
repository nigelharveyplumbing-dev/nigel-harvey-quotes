"""Read-only material search library and deterministic name matching."""

import re

def get_material_search_library(*, material_library, get_db, safe_float):
    items = []

    for item in material_library:
        row = dict(item)
        row["source"] = "built-in"
        items.append(row)

    try:
        conn = get_db()
        rows = conn.execute("""
            SELECT url, name, supplier, last_price, last_live_price, last_manual_price,
                   last_status, times_used, updated_at, last_success_at
            FROM material_price_cache
            WHERE COALESCE(name, '') != ''
            ORDER BY times_used DESC, updated_at DESC
            LIMIT 500
        """).fetchall()
        conn.close()

        seen = set((item.get("name", "").lower(), item.get("supplier", "").lower(), item.get("url", "")) for item in items)

        for row in rows:
            name = row["name"] or ""
            supplier = row["supplier"] or ""
            url = row["url"] or ""
            key = (name.lower(), supplier.lower(), url)
            if key in seen:
                continue

            price = row["last_live_price"] or row["last_price"] or row["last_manual_price"] or 0
            items.append({
                "name": name,
                "supplier": supplier,
                "url": url,
                "default_price": round(safe_float(price, 0), 2),
                "last_status": row["last_status"],
                "times_used": row["times_used"],
                "source": "saved",
            })
            seen.add(key)
    except Exception:
        pass

    return items


def _material_match_normalise(value: str) -> str:
    text_value = (value or "").lower()
    text_value = re.sub(r"https?://\S+", " ", text_value)
    text_value = re.sub(r"(\d+)\s*mm\b", r"\1mm", text_value)
    text_value = re.sub(r"\bend[\s-]?feed\b", "endfeed", text_value)
    text_value = re.sub(r"\b90\s*(?:degree|degrees|deg)\b", " ", text_value)
    text_value = re.sub(
        r"\b(plumbright|plumbfix|regin|kudox|stelrad|city plumbing|screwfix|toolstation|selco|topps tiles)\b",
        " ",
        text_value,
    )
    text_value = re.sub(
        r"\b(white|chrome plated|chrome|copper|each|single|individual|pack of|pack|fitting|fittings|connector|connectors)\b",
        " ",
        text_value,
    )
    text_value = re.sub(r"[^a-z0-9/.\- ]+", " ", text_value)
    return re.sub(r"\s+", " ", text_value).strip()


def _material_match_family(value: str) -> str:
    cleaned = _material_match_normalise(value)
    if re.search(r"\breducing tee\b|\btee\b", cleaned):
        return "tee"
    if re.search(r"\belbow\b|\bbend\b", cleaned):
        return "elbow"
    if re.search(r"\bcoupler\b|\bcoupling\b", cleaned):
        return "coupler"
    if re.search(r"\bcopper pipe\b|\bpipe 3m\b", cleaned):
        return "pipe"
    if "radiator valve set" in cleaned:
        return "radiator valve set"
    if re.search(r"\btrv\b|thermostatic radiator valve", cleaned):
        return "trv"
    if "lockshield" in cleaned:
        return "lockshield"
    if "inhibitor" in cleaned:
        return "inhibitor"
    if "ptfe" in cleaned:
        return "ptfe"
    if "radiator" in cleaned:
        return "radiator"
    return ""


def _material_match_sizes(value: str) -> list[int]:
    return sorted(set(int(number) for number in re.findall(r"\b(\d{1,4})\s*mm\b", (value or "").lower())))


def _material_match_score(query: str, item: dict, *, safe_float) -> int:
    query_clean = _material_match_normalise(query)
    item_clean = _material_match_normalise(item.get("name", ""))
    query_tokens = [token for token in query_clean.split() if token]
    item_tokens = [token for token in item_clean.split() if token]
    if not query_tokens or not item_tokens:
        return 0

    query_family = _material_match_family(query)
    item_family = _material_match_family(item.get("name", ""))
    if query_family and item_family and query_family != item_family:
        return 0

    query_sizes = _material_match_sizes(query)
    item_sizes = _material_match_sizes(item.get("name", ""))
    if query_sizes and item_sizes and query_sizes != item_sizes:
        return 0

    shared = set(query_tokens).intersection(item_tokens)
    score = int((len(shared) / max(len(set(query_tokens)), len(set(item_tokens)))) * 70)
    if query_family and query_family == item_family:
        score += 20
    if query_sizes and item_sizes:
        score += 10
    if item.get("url"):
        score += 4
    if safe_float(item.get("default_price", 0), 0) > 0:
        score += 4
    if "live" in str(item.get("last_status", "")).lower():
        score += 2
    return min(100, score)

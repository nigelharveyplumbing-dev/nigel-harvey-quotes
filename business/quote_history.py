"""Read-only quote history and supplier intelligence with explicit storage dependencies."""

import re


STOP_WORDS = {
    "the", "and", "for", "with", "from", "into", "onto", "this", "that", "then", "than",
    "pipe", "pipes", "plumbing", "work", "works", "supply", "fit", "install", "repair",
    "replace", "new", "old", "existing", "including", "include", "test", "testing",
    "customer", "job", "to", "of", "in", "on", "a", "an"
}



def learning_tokens(text: str):
    words = re.findall(r"[a-zA-Z0-9]+", (text or "").lower())
    return [w for w in words if len(w) >= 3 and w not in STOP_WORDS]



def quote_similarity_score(query_tokens, quote: dict):
    if not query_tokens:
        return 0

    job = quote.get("job", "") or ""
    result = quote.get("result", {}) or {}
    request = quote.get("request", {}) or {}

    material_names = []
    for line in result.get("material_lines", []) or []:
        material_names.append(str(line.get("name", "")))

    haystack = " ".join([
        job,
        result.get("quote_type", ""),
        request.get("quote_type", ""),
        " ".join(material_names),
    ]).lower()

    score = 0
    for token in query_tokens:
        if token in haystack:
            score += 3
        # crude plural/singular help
        if token.endswith("s") and token[:-1] in haystack:
            score += 1
        if (token + "s") in haystack:
            score += 1

    job_tokens = set(learning_tokens(job))
    score += len(set(query_tokens) & job_tokens) * 2
    return score



def analyse_similar_quotes(query: str, quote_type: str = "", *, load_quotes, safe_float, material_alias_info):
    query_tokens = learning_tokens(query)
    if not query_tokens:
        return {
            "query": query,
            "similar_count": 0,
            "similar_quotes": [],
            "common_materials": [],
            "averages": {},
            "message": "Type a job description to learn from previous quotes."
        }

    quotes = load_quotes()
    scored = []
    for quote in quotes:
        if quote_type and quote_type != "all":
            q_type = (quote.get("result", {}) or {}).get("quote_type") or (quote.get("request", {}) or {}).get("quote_type")
            if q_type and q_type != quote_type:
                continue

        score = quote_similarity_score(query_tokens, quote)
        if score > 0:
            scored.append((score, quote))

    scored.sort(key=lambda x: (x[0], x[1].get("id", 0)), reverse=True)
    matches = [q for _score, q in scored[:12]]

    if not matches:
        return {
            "query": query,
            "similar_count": 0,
            "similar_quotes": [],
            "common_materials": [],
            "averages": {},
            "message": "No similar quotes found yet. Once you quote jobs like this, the app will start learning."
        }

    labour_values = []
    material_values = []
    total_values = []
    material_counter = {}

    for quote in matches:
        result = quote.get("result", {}) or {}
        labour_values.append(safe_float(result.get("labour", 0), 0))
        material_values.append(safe_float(result.get("materials", 0), 0))
        total_values.append(safe_float(result.get("total_price", 0), 0))

        for line in result.get("material_lines", []) or []:
            name = (line.get("name") or "").strip()
            if not name:
                continue
            alias = material_alias_info(name)
            key = alias["canonical"]
            entry = material_counter.setdefault(key, {
                "name": alias["canonical"],
                "example_name": name,
                "category": alias.get("category", "other"),
                "alias_matched": alias.get("matched", False),
                "count": 0,
                "quantity_total": 0,
                "unit_prices": [],
                "suppliers": {},
                "urls": {},
                "source_types": {},
            })
            entry["count"] += 1
            entry["quantity_total"] += safe_float(line.get("quantity", 1), 1)
            unit = safe_float(line.get("unit_price_used", 0), 0)
            if unit > 0:
                entry["unit_prices"].append(unit)
            supplier = line.get("supplier") or ""
            if supplier:
                entry["suppliers"][supplier] = entry["suppliers"].get(supplier, 0) + 1
            url = line.get("url") or ""
            if url:
                entry["urls"][url] = entry["urls"].get(url, 0) + 1
            source = line.get("price_source") or ("live" if line.get("live_price_used") else "manual")
            entry["source_types"][source] = entry["source_types"].get(source, 0) + 1

    common_materials = []
    for entry in material_counter.values():
        avg_qty = entry["quantity_total"] / max(entry["count"], 1)
        avg_unit = sum(entry["unit_prices"]) / len(entry["unit_prices"]) if entry["unit_prices"] else 0
        supplier = max(entry["suppliers"], key=entry["suppliers"].get) if entry["suppliers"] else "City Plumbing"
        url = max(entry["urls"], key=entry["urls"].get) if entry["urls"] else ""
        source = max(entry["source_types"], key=entry["source_types"].get) if entry["source_types"] else "manual"

        used_percent = round((entry["count"] / len(matches)) * 100, 0)
        if used_percent >= 80:
            bundle_status = "essential"
        elif used_percent >= 40:
            bundle_status = "common"
        else:
            bundle_status = "optional"

        common_materials.append({
            "name": entry["name"],
            "example_name": entry.get("example_name", entry["name"]),
            "category": entry.get("category", "other"),
            "alias_matched": entry.get("alias_matched", False),
            "used_count": entry["count"],
            "used_percent": used_percent,
            "average_quantity": round(avg_qty, 2),
            "average_unit_price": round(avg_unit, 2),
            "supplier": supplier,
            "url": url,
            "price_source": source,
            "bundle_status": bundle_status,
        })

    common_materials.sort(key=lambda x: (x["used_count"], x["used_percent"]), reverse=True)

    def avg(values):
        values = [safe_float(v, 0) for v in values if safe_float(v, 0) > 0]
        return round(sum(values) / len(values), 2) if values else 0


    suggested_bundle = {
        "name": "Suggested bundle from previous quotes",
        "essential": [m for m in common_materials if m.get("bundle_status") == "essential"],
        "common": [m for m in common_materials if m.get("bundle_status") == "common"],
        "optional": [m for m in common_materials if m.get("bundle_status") == "optional"][:8],
    }

    similar_quotes = []
    for quote in matches[:6]:
        result = quote.get("result", {}) or {}
        similar_quotes.append({
            "id": quote.get("id"),
            "created_at": quote.get("created_at"),
            "job": quote.get("job", ""),
            "labour": round(safe_float(result.get("labour", 0), 0), 2),
            "materials": round(safe_float(result.get("materials", 0), 0), 2),
            "total_price": round(safe_float(result.get("total_price", 0), 0), 2),
        })

    return {
        "query": query,
        "similar_count": len(matches),
        "similar_quotes": similar_quotes,
        "common_materials": common_materials[:20],
        "suggested_bundle": suggested_bundle,
        "averages": {
            "labour": avg(labour_values),
            "materials": avg(material_values),
            "total_price": avg(total_values),
        },
        "message": f"Found {len(matches)} similar previous quote(s)."
    }



def labour_intelligence_for_job(job_text: str = "", quote_type: str = "", current_labour: float = 0, *, analyse_similar_quotes, safe_float):
    analysis = analyse_similar_quotes(job_text or "", quote_type or "")
    averages = analysis.get("averages", {}) or {}
    similar = analysis.get("similar_quotes", []) or []

    labour_values = []
    for item in similar:
        labour = safe_float(item.get("labour", 0), 0)
        if labour > 0:
            labour_values.append(labour)

    avg_labour = safe_float(averages.get("labour", 0), 0)
    if not avg_labour and labour_values:
        avg_labour = sum(labour_values) / len(labour_values)

    if labour_values:
        low = min(labour_values)
        high = max(labour_values)
    elif avg_labour:
        low = avg_labour * 0.85
        high = avg_labour * 1.20
    else:
        low = 0
        high = 0

    current = safe_float(current_labour, 0)
    warning = ""
    status = "unknown"

    if avg_labour > 0 and current > 0:
        if current < avg_labour * 0.85:
            status = "too_low"
            warning = f"Labour looks low. Similar jobs average £{avg_labour:.2f}."
        elif current > avg_labour * 1.35:
            status = "high"
            warning = f"Labour is higher than your usual average of £{avg_labour:.2f}."
        else:
            status = "ok"
            warning = "Labour is within your usual range."

    return {
        "job": job_text,
        "quote_type": quote_type,
        "current_labour": round(current, 2),
        "average_labour": round(avg_labour, 2),
        "low_range": round(low, 2),
        "high_range": round(high, 2),
        "similar_count": analysis.get("similar_count", 0),
        "status": status,
        "warning": warning,
        "similar_quotes": similar[:6],
    }



FORGOTTEN_ITEM_RULES = [
    {
        "trigger": ["outside tap", "hose union bib tap", "wall plate elbow"],
        "missing": ["15mm isolating valve", "double check valve 15mm", "pipe clips 15mm", "drain off cock 15mm"],
        "job_keywords": ["outside tap", "garden tap", "external tap"],
        "reason": "Outside taps usually need isolation, backflow protection, pipe clips and a drain off where freezing is possible."
    },
    {
        "trigger": ["trv", "thermostatic radiator valve", "angled trv"],
        "missing": ["angled lockshield valve", "radiator valve tail", "ptfe tape", "15mm copper olive", "central heating inhibitor"],
        "job_keywords": ["trv", "radiator valve", "heating"],
        "reason": "TRV jobs often need a matching lockshield, tails, olives, PTFE and inhibitor if draining/refilling."
    },
    {
        "trigger": ["radiator", "radiator replacement"],
        "missing": ["angled trv", "angled lockshield valve", "radiator valve tail", "central heating inhibitor", "radiator bleed valve"],
        "job_keywords": ["radiator", "rad"],
        "reason": "Radiator replacements commonly need valves, tails, inhibitor and bleed parts."
    },
    {
        "trigger": ["filling loop", "braided filling loop"],
        "missing": ["15mm isolating valve", "double check valve 15mm", "central heating inhibitor"],
        "job_keywords": ["filling loop", "pressure", "low pressure", "repressurise"],
        "reason": "Filling loop jobs often need isolation/check valve parts and inhibitor if system is topped up/refilled."
    },
    {
        "trigger": ["basin waste", "bottle trap", "p trap"],
        "missing": ["32mm waste pipe", "32mm waste pipe clips", "32mm solvent weld bend", "silicone"],
        "job_keywords": ["basin", "waste", "trap"],
        "reason": "Basin waste jobs often need pipe, clips, bends and sealant."
    },
    {
        "trigger": ["kitchen sink waste", "sink waste"],
        "missing": ["40mm waste pipe", "40mm waste pipe clips", "40mm solvent weld bend", "appliance waste spigot"],
        "job_keywords": ["kitchen sink", "sink waste", "waste"],
        "reason": "Kitchen sink waste jobs often need 40mm pipe, clips, bends and sometimes appliance spigots."
    },
    {
        "trigger": ["tap", "kitchen tap", "basin tap"],
        "missing": ["15mm isolating valve", "flexi hose 300mm", "ptfe tape"],
        "job_keywords": ["tap", "kitchen tap", "basin tap"],
        "reason": "Tap replacements often need isolation valves, flexis and PTFE/sundries."
    },
    {
        "trigger": ["toilet", "replace toilet", "toilet replacement"],
        "missing": ["straight pan connector", "toilet fixing kit", "15mm isolating valve", "15mm x 1/2 flexi hose", "doughnut washer"],
        "job_keywords": ["toilet", "wc"],
        "reason": "Toilet jobs often need pan connector, fixings, isolation/flexi and close-coupling seals."
    },
]



def detect_forgotten_items(job_text: str, materials: list, *, canonical_material_name):
    job = (job_text or "").lower()
    material_names = []
    canonical_names = []

    for m in materials or []:
        if hasattr(m, "dict"):
            data = m.dict()
        elif isinstance(m, dict):
            data = m
        else:
            continue
        name = data.get("name", "")
        if not name:
            continue
        material_names.append(name.lower())
        canonical_names.append(canonical_material_name(name))

    hay = " ".join(material_names + canonical_names + [job])
    results = []

    for rule in FORGOTTEN_ITEM_RULES:
        trigger_hit = any(t in hay for t in rule.get("trigger", [])) or any(k in job for k in rule.get("job_keywords", []))
        if not trigger_hit:
            continue

        missing_now = []
        for item in rule.get("missing", []):
            item_can = canonical_material_name(item)
            exists = any(item_can == c or item_can in c or c in item_can for c in canonical_names)
            if not exists:
                missing_now.append(item)

        if missing_now:
            results.append({
                "reason": rule.get("reason", ""),
                "missing": missing_now,
                "trigger": rule.get("trigger", []),
            })

    # De-duplicate by missing item name
    seen = set()
    clean = []
    for r in results:
        unique_missing = []
        for m in r.get("missing", []):
            key = canonical_material_name(m)
            if key not in seen:
                seen.add(key)
                unique_missing.append(m)
        if unique_missing:
            r["missing"] = unique_missing
            clean.append(r)

    return clean



def supplier_preference_for_material(material_name: str, *, load_quotes, canonical_material_name, safe_float):
    canonical = canonical_material_name(material_name)
    supplier_counts = {}
    price_by_supplier = {}

    for quote in load_quotes():
        result = quote.get("result", {}) or {}
        for line in result.get("material_lines", []) or []:
            name = line.get("name", "")
            if canonical_material_name(name) != canonical:
                continue

            supplier = (line.get("supplier") or "").strip() or "Unknown"
            supplier_counts[supplier] = supplier_counts.get(supplier, 0) + 1

            unit = safe_float(line.get("full_unit_price", line.get("unit_price_used", 0)), 0)
            if unit > 0:
                price_by_supplier.setdefault(supplier, []).append(unit)

    if not supplier_counts:
        return {
            "material": canonical,
            "preferred_supplier": "",
            "supplier_counts": {},
            "average_prices": {},
            "source": "none",
            "message": "No supplier history yet."
        }

    preferred = max(supplier_counts, key=supplier_counts.get)
    average_prices = {
        supplier: round(sum(values) / len(values), 2)
        for supplier, values in price_by_supplier.items()
        if values
    }

    return {
        "material": canonical,
        "preferred_supplier": preferred,
        "supplier_counts": supplier_counts,
        "average_prices": average_prices,
        "source": "history",
        "message": f"Preferred supplier from history: {preferred}"
    }



def supplier_preferences_summary(*, load_quotes, canonical_material_name, safe_float):
    summary = {}
    for quote in load_quotes():
        result = quote.get("result", {}) or {}
        for line in result.get("material_lines", []) or []:
            name = line.get("name", "")
            if not name:
                continue
            canonical = canonical_material_name(name)
            supplier = (line.get("supplier") or "").strip() or "Unknown"
            entry = summary.setdefault(canonical, {
                "material": canonical,
                "supplier_counts": {},
                "average_prices": {},
                "total_uses": 0,
            })
            entry["supplier_counts"][supplier] = entry["supplier_counts"].get(supplier, 0) + 1
            entry["total_uses"] += 1
            unit = safe_float(line.get("full_unit_price", line.get("unit_price_used", 0)), 0)
            if unit > 0:
                entry.setdefault("_prices", {}).setdefault(supplier, []).append(unit)

    rows = []
    for item in summary.values():
        counts = item.get("supplier_counts", {})
        preferred = max(counts, key=counts.get) if counts else ""
        prices = item.pop("_prices", {})
        item["preferred_supplier"] = preferred
        item["average_prices"] = {
            s: round(sum(v) / len(v), 2)
            for s, v in prices.items()
            if v
        }
        rows.append(item)

    rows.sort(key=lambda x: x.get("total_uses", 0), reverse=True)
    return rows[:100]

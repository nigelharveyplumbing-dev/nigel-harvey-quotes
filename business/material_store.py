"""Local material cache persistence and deterministic charge rules."""

from business.db import get_db


def normalize_material_url(url: str):
    return (url or "").strip()


def upsert_material_price_cache(url: str, name: str = "", supplier: str = "", price=None, manual_price=None, status: str = "live", *, now_uk, safe_float):
    url = normalize_material_url(url)
    if not url:
        return

    now = now_uk().isoformat()
    price_value = safe_float(price, None) if price is not None else None
    manual_value = safe_float(manual_price, None) if manual_price is not None else None

    existing = get_cached_material_price(url)
    conn = get_db()
    if existing:
        last_price = price_value if price_value is not None else existing.get("last_price")
        last_live_price = price_value if status == "live" and price_value is not None else existing.get("last_live_price")
        last_manual_price = manual_value if manual_value is not None and manual_value > 0 else existing.get("last_manual_price")
        last_success_at = now if status == "live" and price_value is not None else existing.get("last_success_at")

        conn.execute("""
            UPDATE material_price_cache
            SET name = COALESCE(NULLIF(?, ''), name),
                supplier = COALESCE(NULLIF(?, ''), supplier),
                last_price = ?,
                last_live_price = ?,
                last_manual_price = ?,
                last_status = ?,
                times_used = times_used + 1,
                updated_at = ?,
                last_checked_at = ?,
                last_success_at = ?
            WHERE url = ?
        """, (
            name or "",
            supplier or "",
            last_price,
            last_live_price,
            last_manual_price,
            status,
            now,
            now,
            last_success_at,
            url,
        ))
    else:
        conn.execute("""
            INSERT INTO material_price_cache (
                url, name, supplier, last_price, last_live_price, last_manual_price,
                last_status, times_used, created_at, updated_at, last_checked_at, last_success_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            url,
            name or "",
            supplier or "",
            price_value if price_value is not None else manual_value,
            price_value if status == "live" and price_value is not None else None,
            manual_value if manual_value is not None and manual_value > 0 else None,
            status,
            1,
            now,
            now,
            now,
            now if status == "live" and price_value is not None else None,
        ))

    history_price = price_value if price_value is not None else manual_value
    try:
        conn.execute("""
            INSERT INTO material_price_history (material_url, name, supplier, price, source, checked_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (url, name or "", supplier or "", history_price, status, now))
    except Exception:
        pass

    conn.commit()
    conn.close()


def get_cached_material_price(url: str):
    url = normalize_material_url(url)
    if not url:
        return None
    try:
        conn = get_db()
        row = conn.execute("SELECT * FROM material_price_cache WHERE url = ?", (url,)).fetchone()
        conn.close()
        if not row:
            return None
        return dict(row)
    except Exception:
        return None


def get_material_charging_rule(name: str, canonical_material_name, charging_rules):
    canonical = canonical_material_name(name)
    return charging_rules.get(canonical, {
        "material_type": "chargeable",
        "charge_method": "full",
        "default_charge": None,
        "customer_label": canonical,
        "note": "Full chargeable material."
    })


def material_quote_unit_price(name: str, full_price: float, override_price=None, *, get_material_charging_rule, safe_float):
    if override_price is not None:
        override = safe_float(override_price, None)
        if override is not None:
            return override
    rule = get_material_charging_rule(name)
    if rule.get("charge_method") in ("partial", "small_part") and rule.get("default_charge") is not None:
        return safe_float(rule.get("default_charge"), full_price)
    return full_price


def list_material_price_cache():
    conn = get_db()
    rows = conn.execute("""
        SELECT id, url, name, supplier, last_price, last_live_price, last_manual_price,
               last_status, times_used, created_at, updated_at, last_checked_at, last_success_at
        FROM material_price_cache
        ORDER BY updated_at DESC, id DESC
        LIMIT 500
    """).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_material_price_cache(material_id, data, now_uk, safe_float):
    now = now_uk().isoformat()
    conn = get_db()
    cur = conn.execute("""
        UPDATE material_price_cache
        SET name = ?, supplier = ?, url = ?, last_manual_price = ?, updated_at = ?
        WHERE id = ?
    """, (
        data.name.strip(),
        data.supplier.strip(),
        normalize_material_url(data.url),
        safe_float(data.manual_price, 0),
        now,
        material_id,
    ))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def delete_material_price_cache(material_id):
    conn = get_db()
    cur = conn.execute("DELETE FROM material_price_cache WHERE id = ?", (material_id,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0

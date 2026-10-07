"""Original quote arithmetic with merchant lookup and app helpers supplied by the caller."""

from business.models import QuoteRequest


def find_labour_suggestion(quote_type: str, job_description: str, labour_hints):
    text = (job_description or "").lower()
    rules = labour_hints.get(quote_type, [])
    for rule in rules:
        if any(keyword in text for keyword in rule["keywords"]):
            return rule

    if quote_type == "bathroom":
        return {"suggestion": 2000, "range": "£1,600 - £2,800"}
    if quote_type == "heating":
        return {"suggestion": 180, "range": "£150 - £300"}
    return {"suggestion": 120, "range": "£90 - £180"}


def calculate_quote(data: QuoteRequest, *, fetch_tracked_price, safe_float,
                    material_quote_unit_price, find_labour_suggestion, now_uk, format_dt):
    raw_materials = 0.0
    material_lines = []

    for item in data.materials:
        url = item.url.strip() if item.url else ""
        if item.selected_account_price is not None:
            tracked_price, price_source = float(item.selected_account_price.price_inc_vat), "account_cached"
        elif item.selected_comparison_price is not None:
            tracked_price, price_source = item.selected_comparison_price, "selected_public"
        else:
            tracked_price, price_source = fetch_tracked_price(url, item.name, item.supplier, item.manual_price) if url else (None, "manual")

        # Full product price is remembered separately.
        full_unit_price = safe_float(tracked_price, None) if tracked_price is not None else safe_float(item.manual_price, 0)

        # Quote unit price may be a smaller allowance for consumables/sundries.
        unit_price = material_quote_unit_price(item.name, full_unit_price, item.quote_charge_override)

        # Quantity must be included in the maths.
        quantity = safe_float(item.quantity, 1)
        if quantity <= 0:
            quantity = 1

        line_total = unit_price * quantity
        raw_materials += line_total

        material_lines.append({
            "name": item.name,
            "quantity": quantity,
            "supplier": item.supplier,
            "url": item.url,
            "manual_price": round(safe_float(item.manual_price, 0), 2),
            "full_unit_price": round(full_unit_price, 2),
            "unit_price_used": round(unit_price, 2),
            "line_total": round(line_total, 2),
            "live_price_used": price_source in ("live", "cached"),
            "price_source": price_source,
            "material_type": item.material_type,
            "charge_method": item.charge_method,
            "quantity_source": getattr(item, "quantity_source", "rule"),
            "learned_average_quantity": getattr(item, "learned_average_quantity", None),
            "learned_used_count": getattr(item, "learned_used_count", None),
        })
        if item.selected_comparison_price is not None:
            material_lines[-1]["selected_comparison_price"] = item.selected_comparison_price
        if item.selected_account_price is not None:
            material_lines[-1]["selected_account_price"] = item.selected_account_price.model_dump(mode="json")

    tiling_extra_materials = 0.0
    if data.quote_type == "bathroom" and data.tiling and not data.customer_supplies_tiles:
        wall_multiplier = 1.2 if data.wall_height == "full" else 1.0
        wall_materials = data.wall_tiling_m2 * 20 * wall_multiplier
        floor_materials = data.floor_tiling_m2 * 15
        tiling_extra_materials += wall_materials + floor_materials

    raw_materials_with_tiling = raw_materials + tiling_extra_materials

    job_multiplier = 1.0
    if data.quote_type == "bathroom":
        job_multiplier = 1.5
    elif data.quote_type == "heating":
        job_multiplier = 1.3

    materials_after_job_markup = raw_materials_with_tiling * job_multiplier

    handling_percent = 0.0
    handling_multiplier = 1.0
    if data.include_materials_handling:
        handling_percent = data.materials_handling_percent
        handling_multiplier = 1 + (handling_percent / 100.0)

    quoted_materials = materials_after_job_markup * handling_multiplier
    labour_total = data.labour_cost
    callout_charge = max(0.0, safe_float(data.callout_charge, 0.0)) if data.include_callout_charge else 0.0
    travel_charge = max(0.0, safe_float(data.travel_charge, 0.0)) if data.include_travel_charge else 0.0
    total_price = labour_total + callout_charge + travel_charge + quoted_materials

    deposit_percent = max(0.0, min(100.0, data.deposit_percent or 0))
    deposit_amount = total_price * (deposit_percent / 100.0)

    job_text = data.job_description.strip()
    if data.tiling and data.quote_type == "bathroom":
        job_text = f"{job_text} + Tiling" if job_text else "Bathroom works + Tiling"

    hidden_uplift = quoted_materials - raw_materials_with_tiling
    gross_profit = (quoted_materials - raw_materials_with_tiling) + labour_total + callout_charge + travel_charge
    margin_percent = (gross_profit / total_price * 100.0) if total_price > 0 else 0.0

    labour_hint = find_labour_suggestion(data.quote_type, data.job_description)
    now = now_uk()

    return {
        "quote_type": data.quote_type,
        "customer_name": data.customer_name,
        "customer_address": data.customer_address,
        "customer_phone": data.customer_phone,
        "job": job_text,
        "labour": round(labour_total, 2),
        "include_callout_charge": bool(data.include_callout_charge),
        "callout_charge": round(callout_charge, 2),
        "include_travel_charge": bool(data.include_travel_charge),
        "travel_charge": round(travel_charge, 2),
        "materials": round(quoted_materials, 2),
        "materials_base": round(materials_after_job_markup, 2),
        "materials_procurement_percent": round(handling_percent, 2),
        "materials_procurement_amount": round(quoted_materials - materials_after_job_markup, 2),
        "total_price": round(total_price, 2),
        "deposit_percent": round(deposit_percent, 2),
        "deposit_amount": round(deposit_amount, 2),
        "created_at": format_dt(now),
        "created_at_sort": now.isoformat(),
        "material_lines": material_lines,
        "internal_raw_materials": round(raw_materials_with_tiling, 2),
        "internal_job_multiplier": round(job_multiplier, 2),
        "internal_after_job_markup": round(materials_after_job_markup, 2),
        "internal_handling_percent": round(handling_percent, 2),
        "internal_after_handling": round(quoted_materials, 2),
        "internal_hidden_uplift": round(hidden_uplift, 2),
        "gross_profit": round(gross_profit, 2),
        "margin_percent": round(margin_percent, 2),
        "labour_suggestion": labour_hint["suggestion"],
        "labour_range_hint": labour_hint["range"],
    }

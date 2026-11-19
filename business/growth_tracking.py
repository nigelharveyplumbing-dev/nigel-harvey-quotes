"""Conservative attribution and read-only business outcomes over existing records."""

from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from business.db import get_db

SOURCES = ("Google Business Profile", "Google organic search", "Website/direct",
           "Referral", "Repeat customer", "MyBuilder", "Locally", "Bing", "Yell",
           "Checkatrade", "TrustATrader", "Other", "Unknown")
WORK_TYPES = ("Leak / repair", "Tap", "Toilet / cistern", "Shower", "Bathroom plumbing",
              "Radiator / TRV", "Outside tap", "Pipework", "Power/heating-system flush",
              "Cylinder / tank", "Other")
LOSS_REASONS = ("Price", "Customer chose another contractor", "Customer cancelled work",
                "No response", "Timing / availability", "Job not suitable", "Other")
QUOTE_STATUSES = ("pending", "won", "lost", "expired", "unclassified")


def inferred_source(source, context):
    """Infer only when context is clear; keep raw UTMs/referrer intact."""
    src = (context.get("utm_source") or "").strip().lower()
    medium = (context.get("utm_medium") or "").strip().lower()
    ref = (context.get("referrer") or "").strip().lower()
    direct = (source or "").strip().lower()
    if direct in {"manual", "unknown", ""} and not src and not medium and not ref:
        return "Unknown"
    if src in {"google_business_profile", "google-business-profile", "gbp", "gmb"}:
        return "Google Business Profile"
    if src == "google" and medium in {"organic", "seo"}:
        return "Google organic search"
    if src in {"mybuilder", "locally", "bing", "yell", "checkatrade", "trustatrader"}:
        return {"mybuilder": "MyBuilder", "locally": "Locally", "bing": "Bing",
                "yell": "Yell", "checkatrade": "Checkatrade", "trustatrader": "TrustATrader"}[src]
    if direct in {item.lower() for item in SOURCES}:
        return next(item for item in SOURCES if item.lower() == direct)
    host = urlparse(ref).hostname or ""
    if host == "google.com" or host.endswith(".google.com") or host.startswith("www.google.co."):
        return "Google organic search" if medium == "organic" else "Other"
    if host == "bing.com" or host.endswith(".bing.com"):
        return "Bing"
    if src or medium or (host and host not in {"nigelharveyplumbing.co.uk", "www.nigelharveyplumbing.co.uk"}):
        return "Other"
    return "Website/direct"


def business_report():
    conn = get_db()
    leads = conn.execute("SELECT id, source, source_category FROM leads").fetchall()
    quotes = conn.execute("SELECT id, customer_name, lead_id, status, source_category, total_price, gross_profit, "
                          "next_follow_up, outcome_updated_at FROM quotes").fetchall()
    invoices = conn.execute("SELECT quote_id, total_price, amount_paid FROM invoices").fetchall()
    from business.lead_store import parse_lead_source
    lead_sources = {}
    by_source = {}
    for lead in leads:
        raw, context = parse_lead_source(lead["source"] or "website")
        source = lead["source_category"] or inferred_source(raw, context)
        lead_sources[lead["id"]] = source
        by_source.setdefault(source, {"enquiries": 0, "quotes": 0, "wins": 0,
                                      "won_value": 0, "invoiced_value": 0, "paid_value": 0})["enquiries"] += 1
    counts = {status: 0 for status in QUOTE_STATUSES}
    values = {status: 0.0 for status in QUOTE_STATUSES}
    quote_sources = {}
    follow_ups = []
    today = datetime.now(ZoneInfo("Europe/London")).date().isoformat()
    for quote in quotes:
        status = quote["status"] if quote["status"] in counts else "unclassified"
        price = quote["total_price"] or 0
        counts[status] += 1
        values[status] += price
        source = quote["source_category"] or lead_sources.get(quote["lead_id"])
        if source:
            item = by_source.setdefault(source, {"enquiries": 0, "quotes": 0, "wins": 0,
                                                "won_value": 0, "invoiced_value": 0, "paid_value": 0})
            item["quotes"] += 1
            if status == "won":
                item["wins"] += 1
                item["won_value"] += price
            quote_sources[quote["id"]] = source
        if status == "pending" and quote["next_follow_up"]:
            follow_ups.append({"id": quote["id"], "date": quote["next_follow_up"],
                               "overdue": quote["next_follow_up"] < today,
                               "due": quote["next_follow_up"] <= today})
    for invoice in invoices:
        source = quote_sources.get(invoice["quote_id"])
        if source:
            by_source[source]["invoiced_value"] += invoice["total_price"] or 0
            by_source[source]["paid_value"] += invoice["amount_paid"] or 0
    conn.close()
    for item in by_source.values():
        for field in ("won_value", "invoiced_value", "paid_value"):
            item[field] = round(item[field], 2)
    decisions = counts["won"] + counts["lost"]
    recent = sorted(quotes, key=lambda q: q["outcome_updated_at"] or "", reverse=True)

    def recent_quotes(status):
        return [{"id": q["id"], "customer_name": q["customer_name"] or "",
                 "total_price": round(q["total_price"] or 0, 2)}
                for q in recent if q["status"] == status][:5]

    return {
        "enquiries": len(leads), "quotes_saved": len(quotes), "status_counts": counts,
        "quoted_value": round(sum(values.values()), 2),
        "status_values": {key: round(value, 2) for key, value in values.items()},
        "win_rate_percent": round(100 * counts["won"] / decisions, 1) if decisions else None,
        "win_rate_denominator": decisions,
        "estimated_gross_profit_won": round(sum((q["gross_profit"] or 0) for q in quotes
                                                 if q["status"] == "won"), 2),
        "follow_ups": sorted(follow_ups, key=lambda row: row["date"]),
        "by_source": by_source,
        "recent_won": recent_quotes("won"),
        "recent_lost": recent_quotes("lost"),
    }

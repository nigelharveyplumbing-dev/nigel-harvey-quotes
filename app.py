# -*- coding: utf-8 -*-
from fastapi import FastAPI, HTTPException, Response, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.routing import Match
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup
import re
import json
import sqlite3
import os
import shutil
import io
import base64
import binascii
import hmac
import ssl
import smtplib
import mimetypes
import subprocess
import tempfile
import textwrap
import threading
import time
import gc
from html import escape
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse, urlsplit, urlencode
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email import encoders
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

try:
    import qrcode
    QRCODE_AVAILABLE = True
except ImportError:
    qrcode = None
    QRCODE_AVAILABLE = False

app = FastAPI(title="Nigel Harvey Ltd Business App")

@app.on_event("startup")
def start_optional_overdue_reminder_worker():
    if AUTO_OVERDUE_REMINDERS:
        threading.Thread(target=_overdue_reminder_worker, daemon=True).start()

from fastapi import Request
import base64

APP_USERNAME = os.getenv("APP_USERNAME", "").strip()
APP_PASSWORD = os.getenv("APP_PASSWORD", "")

# Only these exact method/route-template pairs bypass staff authentication.
PUBLIC_ROUTE_KEYS = frozenset({
    ("GET", "/"),
    ("GET", "/new-home"),
    ("GET", "/request-quote"),
    ("GET", "/robots.txt"),
    ("GET", "/sitemap.xml"),
    ("GET", "/plumber-{area_slug}"),
    ("GET", "/{service_slug}-{area_slug}"),
    ("GET", "/{service_slug}"),
    ("POST", "/api/leads"),
    ("GET", "/invoice/{invoice_id}"),
    ("GET", "/api/invoices/{invoice_id}/pdf"),
    ("GET", "/api/invoices/{invoice_id}/payment-qr"),
    ("GET", "/api/invoices/{invoice_id}/photos/{photo_id}"),
    ("GET", "/api/quotes/{quote_id}/pdf"),
})


def check_basic_auth(request: Request):
    if not APP_USERNAME or not APP_PASSWORD:
        return False
    auth = request.headers.get("authorization", "")
    try:
        scheme, encoded = auth.split(" ", 1)
        if scheme.lower() != "basic":
            return False
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
        user, pwd = decoded.split(":", 1)
        return hmac.compare_digest(user, APP_USERNAME) & hmac.compare_digest(pwd, APP_PASSWORD)
    except (ValueError, TypeError, UnicodeError, binascii.Error):
        return False


def is_public_route(request: Request):
    # Resolve the route before deciding. This preserves public dynamic SEO 404s
    # without treating an entire URL prefix as public.
    for route in app.router.routes:
        match, _ = route.matches(request.scope)
        if match == Match.FULL:
            return (request.method, route.path) in PUBLIC_ROUTE_KEYS
    return False


def is_cross_site_write(request: Request):
    # This GET currently refreshes cached prices, so treat it like a write.
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"} and not (
        request.method == "GET" and request.url.path == "/api/live-product-refresh"
    ):
        return False
    origin = request.headers.get("origin")
    if origin:
        parsed = urlparse(origin)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != request.headers.get("host", "").lower():
            return True
    fetch_site = request.headers.get("sec-fetch-site")
    return bool(fetch_site and fetch_site not in {"same-origin", "none"})


@app.middleware("http")
async def protect_app_routes(request: Request, call_next):
    if is_public_route(request):
        return await call_next(request)
    if not check_basic_auth(request):
        headers = {"WWW-Authenticate": "Basic"}
        if request.url.path.startswith("/api/"):
            return JSONResponse(
                status_code=401, headers=headers,
                content={"detail": "Authentication required"},
            )
        return Response(status_code=401, headers=headers, content="Authentication required")
    if is_cross_site_write(request):
        if request.url.path.startswith("/api/"):
            return JSONResponse(status_code=403, content={"detail": "Cross-site request blocked"})
        return Response(status_code=403, content="Cross-site request blocked")
    return await call_next(request)


from business.config import (
    APP_VERSION,
    DB_PATH,
    DB_BACKUP_DIR,
    UK_TZ,
    COMPANY_NAME,
    COMPANY_ADDRESS,
    COMPANY_PHONE,
    COMPANY_PHONE_TEL,
    COMPANY_EMAIL,
    BANK_NAME,
    BANK_ACCOUNT_NAME,
    BANK_SORT_CODE,
    BANK_ACCOUNT_NUMBER,
    SHOW_BANK_DETAILS_ON_QUOTES,
    AUTO_OVERDUE_REMINDERS,
    OVERDUE_REMINDER_INTERVAL_HOURS,
    DEFAULT_COMPANY_LOGO_URL,
    COMPANY_LOGO_URL,
    GOOGLE_RATING_VALUE,
    GOOGLE_REVIEW_COUNT,
    GOOGLE_REVIEWS_URL,
    GOOGLE_REVIEW_1_TEXT,
    GOOGLE_REVIEW_1_AUTHOR,
    GOOGLE_REVIEW_2_TEXT,
    GOOGLE_REVIEW_2_AUTHOR,
    GOOGLE_REVIEW_3_TEXT,
    GOOGLE_REVIEW_3_AUTHOR,
    GOOGLE_PLACES_API_KEY,
    GOOGLE_PLACE_ID,
    PAYMENT_LINK_BASE,
    EMAIL_ENABLED,
    EMAIL_HOST,
    EMAIL_PORT,
    EMAIL_USER,
    EMAIL_PASS,
    EMAIL_FROM_NAME
)
_GOOGLE_PLACE_ID_RUNTIME = ""


def _google_place_id():
    """Resolve the Google Place ID. Place IDs may be stored; review content is not cached."""
    global _GOOGLE_PLACE_ID_RUNTIME
    if GOOGLE_PLACE_ID:
        return GOOGLE_PLACE_ID
    if _GOOGLE_PLACE_ID_RUNTIME:
        return _GOOGLE_PLACE_ID_RUNTIME
    if not GOOGLE_PLACES_API_KEY:
        print("Google Places lookup skipped: GOOGLE_PLACES_API_KEY is not set", flush=True)
        return ""
    try:
        print("Google Places lookup: searching for Nigel Harvey Plumbing Guildford Surrey", flush=True)
        response = requests.post(
            "https://places.googleapis.com/v1/places:searchText",
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
                "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress",
            },
            json={
                "textQuery": "Nigel Harvey Plumbing Guildford Surrey",
                "regionCode": "GB",
                "languageCode": "en",
                "maxResultCount": 1,
            },
            timeout=8,
        )
        if not response.ok:
            print(f"Google Places lookup HTTP {response.status_code}: {response.text[:1000]}", flush=True)
            response.raise_for_status()
        payload = response.json()
        places = payload.get("places") or []
        if places:
            _GOOGLE_PLACE_ID_RUNTIME = (places[0].get("id") or "").strip()
            print(f"Google Places lookup succeeded: found place ID ending ...{_GOOGLE_PLACE_ID_RUNTIME[-8:] if _GOOGLE_PLACE_ID_RUNTIME else 'EMPTY'}", flush=True)
        else:
            print(f"Google Places lookup returned no places. Response: {str(payload)[:1000]}", flush=True)
    except Exception as exc:
        print(f"Google Places lookup failed: {type(exc).__name__}: {exc}", flush=True)
    return _GOOGLE_PLACE_ID_RUNTIME


def _google_reviews_html():
    """Build the live Google rating/review section. Falls back cleanly if Google is unavailable."""
    fallback = (
        '<div class="stars">★★★★★</div>'
        '<h2>Customer reviews</h2>'
        '<p class="muted">See feedback from customers on Google, or leave a review after Nigel has completed your plumbing work.</p>'
        f'<a class="btn" href="{escape(GOOGLE_REVIEWS_URL, quote=True)}" target="_blank" rel="noopener">Read Google Reviews</a>'
    )
    if not GOOGLE_PLACES_API_KEY:
        print("Google reviews fallback: GOOGLE_PLACES_API_KEY is not set", flush=True)
        return fallback
    place_id = _google_place_id()
    if not place_id:
        print("Google reviews fallback: no Google Place ID could be resolved", flush=True)
        return fallback
    try:
        print(f"Google reviews: requesting Place Details for place ID ending ...{place_id[-8:]}", flush=True)
        response = requests.get(
            f"https://places.googleapis.com/v1/places/{quote_plus(place_id)}",
            headers={
                "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
                "X-Goog-FieldMask": "displayName,rating,userRatingCount,reviews,googleMapsLinks.reviewsUri",
            },
            params={"languageCode": "en", "regionCode": "GB"},
            timeout=8,
        )
        if not response.ok:
            print(f"Google reviews HTTP {response.status_code}: {response.text[:1500]}", flush=True)
            response.raise_for_status()
        data = response.json()
        rating = data.get("rating")
        count = data.get("userRatingCount")
        reviews = data.get("reviews") or []
        reviews_url = ((data.get("googleMapsLinks") or {}).get("reviewsUri") or GOOGLE_REVIEWS_URL).strip()
        print(f"Google reviews response: rating={rating!r}, userRatingCount={count!r}, reviews={len(reviews)}", flush=True)
        if rating is None and not reviews:
            print(f"Google reviews fallback: response contained no rating/reviews. Keys: {list(data.keys())}", flush=True)
            return fallback

        rating_text = f"{float(rating):.1f}" if rating is not None else ""
        count_text = f"{int(count):,} Google review" + ("" if int(count) == 1 else "s") if count is not None else "Google reviews"
        cards = []
        for review in reviews[:3]:
            author = review.get("authorAttribution") or {}
            author_name = escape(author.get("displayName") or "Google customer")
            author_uri = escape(author.get("uri") or review.get("googleMapsUri") or reviews_url, quote=True)
            photo_uri = escape(author.get("photoUri") or "", quote=True)
            review_uri = escape(review.get("googleMapsUri") or reviews_url, quote=True)
            review_text = escape(((review.get("text") or {}).get("text") or "").strip())
            relative_time = escape(review.get("relativePublishTimeDescription") or "")
            stars = max(0, min(5, int(round(float(review.get("rating") or 0)))))
            avatar = (f'<a href="{author_uri}" target="_blank" rel="noopener"><img class="review-avatar" src="{photo_uri}" alt="{author_name}"></a>' if photo_uri else '<div class="review-avatar review-avatar-fallback">G</div>')
            body = f'<p class="review-text">{review_text}</p>' if review_text else ""
            cards.append(
                '<article class="google-review-card">'
                f'<div class="review-author">{avatar}<div><a href="{author_uri}" target="_blank" rel="noopener"><strong>{author_name}</strong></a><div class="review-meta"><span class="mini-stars">{"★" * stars}{"☆" * (5-stars)}</span> {relative_time}</div></div></div>'
                f'{body}<a class="review-source" href="{review_uri}" target="_blank" rel="noopener">View on Google</a>'
                '</article>'
            )

        cards_html = '<div class="google-review-grid">' + ''.join(cards) + '</div>' if cards else ''
        summary = f'<div class="google-rating"><strong>{rating_text}</strong><span class="stars">★★★★★</span><span>{escape(count_text)}</span></div>' if rating_text else ''
        return (
            '<div class="google-brand"><img src="https://www.gstatic.com/images/branding/googlelogo/1x/googlelogo_color_74x24dp.png" alt="Google"></div>'
            '<h2>Customer reviews</h2>'
            f'{summary}{cards_html}'
            "<p class=\"review-note\">Reviews supplied by Google and shown in Google’s relevance order.</p>"
            f'<a class="btn" href="{escape(reviews_url, quote=True)}" target="_blank" rel="noopener">Read all Google Reviews</a>'
        )
    except Exception as exc:
        print(f"Google Places reviews failed: {type(exc).__name__}: {exc}", flush=True)
        return fallback


def get_company_logo_value():
    return os.getenv("COMPANY_LOGO_URL", "").strip() or DEFAULT_COMPANY_LOGO_URL


def _pdf_logo_reader():
    logo_value = get_company_logo_value()
    if not logo_value:
        return None
    try:
        if logo_value.startswith("data:image"):
            header, encoded = logo_value.split(",", 1)
            return ImageReader(io.BytesIO(base64.b64decode(encoded)))
        return ImageReader(logo_value)
    except Exception:
        return None


from business import quote_rules, quote_calculation


QUOTE_TERMS = [
    "Includes labour, supplied materials and materials procurement where selected.",
    "Materials procurement covers sourcing, collection, transportation, supplier coordination and warranty handling.",
    "Payment due as agreed.",
    "Late payment fee may be applied after 14 days.",
    "Materials remain the property of Nigel Harvey Ltd until paid in full.",
    "Deposit required before works begin where applicable.",
    "Quote subject to site conditions and any unforeseen issues.",
]

INVOICE_TERMS = [
    "Materials procurement covers sourcing, collection, transportation, supplier coordination and warranty handling.",
    "Please pay by the due date shown above.",
    "Late payment fee may be applied after 14 days.",
    "Materials remain the property of Nigel Harvey Ltd until paid in full.",
    "Deposit required before works begin where applicable.",
]

MATERIAL_LIBRARY = [
    {"name": "15mm Copper Pipe 3m", "supplier": "City Plumbing", "default_price": 18.00},
    {"name": "22mm Copper Pipe 3m", "supplier": "City Plumbing", "default_price": 32.00},
    {"name": "15mm Copper Elbow", "supplier": "Screwfix", "default_price": 1.20},
    {"name": "22mm Copper Elbow", "supplier": "Screwfix", "default_price": 2.10},
    {"name": "15mm Copper Tee", "supplier": "Screwfix", "default_price": 1.80},
    {"name": "22mm Copper Tee", "supplier": "Screwfix", "default_price": 3.20},
    {"name": "15mm Straight Coupler", "supplier": "Toolstation", "default_price": 1.10},
    {"name": "22mm Straight Coupler", "supplier": "Toolstation", "default_price": 1.90},
    {"name": "15mm Isolating Valve", "supplier": "Toolstation", "default_price": 3.50},
    {"name": "22mm Isolating Valve", "supplier": "Toolstation", "default_price": 5.50},
    {"name": "Flexible Tap Connector", "supplier": "Screwfix", "default_price": 6.50},
    {"name": "Sink Waste Kit", "supplier": "City Plumbing", "default_price": 22.00},
    {"name": "Basin Waste", "supplier": "City Plumbing", "default_price": 14.00},
    {"name": "Pop Up Basin Waste", "supplier": "City Plumbing", "default_price": 18.00},
    {"name": "P Trap 1.5in", "supplier": "Toolstation", "default_price": 7.50},
    {"name": "Bottle Trap Chrome", "supplier": "City Plumbing", "default_price": 24.00},
    {"name": "Outside Tap Kit", "supplier": "Screwfix", "default_price": 18.00},
    {"name": "Washing Machine Valve", "supplier": "Toolstation", "default_price": 6.00},
    {"name": "Service Valve", "supplier": "Screwfix", "default_price": 4.00},
    {"name": "Compression Coupler 15mm", "supplier": "Toolstation", "default_price": 1.80},
    {"name": "Compression Coupler 22mm", "supplier": "Toolstation", "default_price": 2.90},
    {"name": "Hep2O 15mm Pipe Coil", "supplier": "City Plumbing", "default_price": 65.00},
    {"name": "Hep2O 22mm Pipe Coil", "supplier": "City Plumbing", "default_price": 95.00},
    {"name": "Hep2O 15mm Straight Coupler", "supplier": "City Plumbing", "default_price": 4.50},
    {"name": "Hep2O 22mm Straight Coupler", "supplier": "City Plumbing", "default_price": 6.80},
    {"name": "Hep2O 15mm Elbow", "supplier": "City Plumbing", "default_price": 5.20},
    {"name": "Hep2O 22mm Elbow", "supplier": "City Plumbing", "default_price": 7.20},
    {"name": "Hep2O 15mm Tee", "supplier": "City Plumbing", "default_price": 6.00},
    {"name": "Hep2O 22mm Tee", "supplier": "City Plumbing", "default_price": 8.50},
    {"name": "Speedfit 15mm Pipe Coil", "supplier": "Screwfix", "default_price": 58.00},
    {"name": "Speedfit 22mm Pipe Coil", "supplier": "Screwfix", "default_price": 90.00},
    {"name": "Speedfit 15mm Straight Coupler", "supplier": "Screwfix", "default_price": 4.20},
    {"name": "Speedfit 22mm Straight Coupler", "supplier": "Screwfix", "default_price": 6.20},
    {"name": "Speedfit 15mm Elbow", "supplier": "Screwfix", "default_price": 5.00},
    {"name": "Speedfit 22mm Elbow", "supplier": "Screwfix", "default_price": 7.00},
    {"name": "Speedfit 15mm Tee", "supplier": "Screwfix", "default_price": 5.80},
    {"name": "Speedfit 22mm Tee", "supplier": "Screwfix", "default_price": 8.00},
    {"name": "Kitchen Mixer Tap", "supplier": "City Plumbing", "default_price": 85.00},
    {"name": "Basin Mixer Tap", "supplier": "City Plumbing", "default_price": 65.00},
    {"name": "Bath Mixer Tap", "supplier": "City Plumbing", "default_price": 95.00},
    {"name": "Thermostatic Shower Valve", "supplier": "City Plumbing", "default_price": 140.00},
    {"name": "Toilet Fill Valve", "supplier": "Screwfix", "default_price": 12.00},
    {"name": "Toilet Flush Valve", "supplier": "Screwfix", "default_price": 18.00},
    {"name": "Silicone", "supplier": "Toolstation", "default_price": 8.00},
    {"name": "Tile Adhesive 20kg", "supplier": "Topps Tiles", "default_price": 22.00},
    {"name": "Tile Grout 5kg", "supplier": "Topps Tiles", "default_price": 14.00},
    {"name": "Tile Trim 2.5m", "supplier": "Topps Tiles", "default_price": 9.00},
    {"name": "Ceramic Wall Tile per m2", "supplier": "Topps Tiles", "default_price": 25.00},
    {"name": "Porcelain Floor Tile per m2", "supplier": "Topps Tiles", "default_price": 35.00},
    {"name": "TRV Valve", "supplier": "Screwfix", "default_price": 14.00},
    {"name": "Lockshield Valve", "supplier": "Screwfix", "default_price": 8.00},
    {"name": "Radiator Valve Set", "supplier": "Screwfix", "default_price": 20.00},
    {"name": "Motorised Valve", "supplier": "City Plumbing", "default_price": 65.00},
    {"name": "Magnetic Filter", "supplier": "City Plumbing", "default_price": 95.00},
    {"name": "Inhibitor 1L", "supplier": "Toolstation", "default_price": 16.00},
    {"name": "Filling Loop", "supplier": "Toolstation", "default_price": 14.00},
]

FAVOURITE_MATERIALS = [
    {"name": "15mm Copper Pipe 3m", "supplier": "City Plumbing", "default_price": 18.00},
    {"name": "22mm Copper Pipe 3m", "supplier": "City Plumbing", "default_price": 32.00},
    {"name": "15mm Copper Elbow", "supplier": "Screwfix", "default_price": 1.20},
    {"name": "15mm Copper Tee", "supplier": "Screwfix", "default_price": 1.80},
    {"name": "15mm Isolating Valve", "supplier": "Toolstation", "default_price": 3.50},
    {"name": "Flexible Tap Connector", "supplier": "Screwfix", "default_price": 6.50},
    {"name": "Basin Waste", "supplier": "City Plumbing", "default_price": 14.00},
    {"name": "Outside Tap Kit", "supplier": "Screwfix", "default_price": 18.00},
    {"name": "Silicone", "supplier": "Toolstation", "default_price": 8.00},
    {"name": "TRV Valve", "supplier": "Screwfix", "default_price": 14.00},
]

JOB_TEMPLATES = quote_rules.JOB_TEMPLATES



MATERIAL_ALIAS_RULES = quote_rules.MATERIAL_ALIAS_RULES


def clean_material_name_for_matching(name: str):
    return quote_rules.clean_material_name_for_matching(name)


def material_alias_info(name: str):
    return quote_rules.material_alias_info(name, MATERIAL_ALIAS_RULES)


def canonical_material_name(name: str):
    return quote_rules.canonical_material_name(name, MATERIAL_ALIAS_RULES)



MASTER_MATERIAL_LIBRARY = [
    {
        "canonical": "15mm copper pipe",
        "category": "pipework",
        "default_supplier": "City Plumbing",
        "typical_quantity": 2,
        "aliases": ["15mm copper", "copper pipe 15mm", "15mm copper tube"],
        "use_cases": ["outside tap", "sink install", "tap replacement", "pipe repair"],
    },
    {
        "canonical": "22mm copper pipe",
        "category": "pipework",
        "default_supplier": "City Plumbing",
        "typical_quantity": 2,
        "aliases": ["22mm copper", "copper pipe 22mm"],
        "use_cases": ["main feeds", "heating", "cylinder work"],
    },
    {
        "canonical": "15mm endfeed elbow",
        "category": "fittings",
        "default_supplier": "City Plumbing",
        "typical_quantity": 4,
        "aliases": ["15mm elbow", "endfeed elbow 15"],
        "use_cases": ["general pipework", "outside tap", "sink install"],
    },
    {
        "canonical": "15mm endfeed tee",
        "category": "fittings",
        "default_supplier": "City Plumbing",
        "typical_quantity": 2,
        "aliases": ["15mm tee", "endfeed tee 15"],
        "use_cases": ["branch pipework", "outside tap"],
    },
    {
        "canonical": "15mm compression coupler",
        "category": "fittings",
        "default_supplier": "City Plumbing",
        "typical_quantity": 2,
        "aliases": ["15mm coupler", "compression coupling 15"],
        "use_cases": ["repairs", "extensions"],
    },
    {
        "canonical": "15mm isolating valve",
        "category": "valves",
        "default_supplier": "City Plumbing",
        "typical_quantity": 2,
        "aliases": ["service valve", "iso valve"],
        "use_cases": ["tap installs", "appliance feeds"],
    },
    {
        "canonical": "double check valve 15mm",
        "category": "valves",
        "default_supplier": "City Plumbing",
        "typical_quantity": 1,
        "aliases": ["dcv", "double check"],
        "use_cases": ["outside taps"],
    },
    {
        "canonical": "drain off cock 15mm",
        "category": "valves",
        "default_supplier": "City Plumbing",
        "typical_quantity": 1,
        "aliases": ["drain cock", "drain valve"],
        "use_cases": ["outside taps", "winter drain down"],
    },
    {
        "canonical": "wall plate elbow 15mm x 1/2",
        "category": "fittings",
        "default_supplier": "City Plumbing",
        "typical_quantity": 1,
        "aliases": ["wallplate elbow", "back plate elbow"],
        "use_cases": ["outside taps", "fixed tap points"],
    },
    {
        "canonical": "hose union bib tap",
        "category": "taps",
        "default_supplier": "City Plumbing",
        "typical_quantity": 1,
        "aliases": ["outside tap", "garden tap"],
        "use_cases": ["outside taps"],
    },
    {
        "canonical": "32mm waste pipe",
        "category": "waste",
        "default_supplier": "Screwfix",
        "typical_quantity": 1,
        "aliases": ["32mm solvent waste"],
        "use_cases": ["basins", "condensate"],
    },
    {
        "canonical": "40mm waste pipe",
        "category": "waste",
        "default_supplier": "Screwfix",
        "typical_quantity": 1,
        "aliases": ["40mm solvent waste"],
        "use_cases": ["sinks", "showers"],
    },
    {
        "canonical": "pan connector",
        "category": "toilet",
        "default_supplier": "City Plumbing",
        "typical_quantity": 1,
        "aliases": ["wc connector", "toilet connector"],
        "use_cases": ["toilet install"],
    },
    {
        "canonical": "flexible tap connector",
        "category": "taps",
        "default_supplier": "Toolstation",
        "typical_quantity": 2,
        "aliases": ["tap flexi", "flexi hose"],
        "use_cases": ["tap replacement"],
    },
    {
        "canonical": "ptfe tape",
        "category": "consumables",
        "default_supplier": "Toolstation",
        "typical_quantity": 1,
        "aliases": ["thread tape"],
        "use_cases": ["all threaded fittings"],
    },
    {
        "canonical": "silicone",
        "category": "consumables",
        "default_supplier": "Toolstation",
        "typical_quantity": 1,
        "aliases": ["sealant", "sanitary silicone"],
        "use_cases": ["sanitary sealing"],
    },
]


def get_master_material(canonical_name: str):
    canonical_name = (canonical_name or "").strip().lower()
    for item in MASTER_MATERIAL_LIBRARY:
        if item["canonical"].lower() == canonical_name:
            return item
    return None


def get_materials_by_category(category: str):
    return [
        item for item in MASTER_MATERIAL_LIBRARY
        if item.get("category", "").lower() == (category or "").lower()
    ]


MATERIAL_CHARGING_RULES = quote_rules.MATERIAL_CHARGING_RULES


def get_material_charging_rule(name: str):
    return material_store.get_material_charging_rule(name, canonical_material_name, MATERIAL_CHARGING_RULES)

def material_quote_unit_price(name: str, full_price: float, override_price=None):
    return material_store.material_quote_unit_price(name, full_price, override_price,
                                                    get_material_charging_rule=get_material_charging_rule,
                                                    safe_float=safe_float)


SMART_QUANTITY_RULES = quote_rules.SMART_QUANTITY_RULES


def suggest_material_quantity(name: str, job_text: str = ""):
    return quote_rules.suggest_material_quantity(
        name, job_text, canonical_material_name=canonical_material_name, rules=SMART_QUANTITY_RULES)


def learned_material_quantity_from_quotes(material_name: str, job_text: str = "", quote_type: str = ""):
    canonical = canonical_material_name(material_name)
    analysis = analyse_similar_quotes(job_text or material_name, quote_type or "")
    similar_count = safe_float(analysis.get("similar_count", 0), 0)

    for item in analysis.get("common_materials", []) or []:
        if canonical_material_name(item.get("name", "")) == canonical:
            avg_qty = safe_float(item.get("average_quantity", 0), 0)
            used_count = safe_float(item.get("used_count", 0), 0)
            if avg_qty > 0 and used_count >= 1:
                return {
                    "quantity": round(avg_qty, 2),
                    "rounded_quantity": max(1, round(avg_qty)),
                    "source": "learned",
                    "used_count": int(used_count),
                    "similar_count": int(similar_count),
                    "used_percent": item.get("used_percent", 0),
                }

    return {
        "quantity": suggest_material_quantity(material_name, job_text),
        "rounded_quantity": suggest_material_quantity(material_name, job_text),
        "source": "rule",
        "used_count": 0,
        "similar_count": int(similar_count),
        "used_percent": 0,
    }


TRADE_JOB_LIBRARY = quote_rules.TRADE_JOB_LIBRARY


def get_all_job_templates():
    return quote_rules.get_all_job_templates(JOB_TEMPLATES, TRADE_JOB_LIBRARY)


LABOUR_HINTS = quote_rules.LABOUR_HINTS


from business.models import (
    MaterialItem, QuoteRequest, AIQuoteDraftRequest, InvoiceStatusRequest, PaymentLinkUpdateRequest, SendInvoiceEmailRequest, LeadRequest, LeadStatusRequest, InvoiceEditRequest
)


def now_uk():
    return datetime.now(UK_TZ)


def format_dt(dt: datetime):
    return dt.strftime("%d/%m/%Y %H:%M")



def normalize_material_dict(item):
    if not isinstance(item, dict):
        item = {}

    item.setdefault("quantity_source", "rule")
    item.setdefault("learned_average_quantity", None)
    item.setdefault("learned_used_count", None)
    item.setdefault("charge_method", item.get("charge_method", "full"))

    return item



def clean_materials_for_storage(materials):
    cleaned = []
    for m in materials or []:
        if hasattr(m, "dict"):
            data = m.dict()
        elif isinstance(m, dict):
            data = dict(m)
        else:
            continue

        cleaned.append({
            "name": data.get("name", ""),
            "quantity": data.get("quantity", 1),
            "supplier": data.get("supplier", ""),
            "url": data.get("url", ""),
            "manual_price": data.get("manual_price", 0),
            "price": data.get("price", 0),
            "grouped_name": data.get("grouped_name", ""),
            "charge_method": data.get("charge_method", "full"),
            "quantity_source": data.get("quantity_source", "rule"),
            "learned_average_quantity": data.get("learned_average_quantity"),
            "learned_used_count": data.get("learned_used_count"),
        })
    return cleaned


def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def month_labels(count=6):
    now = now_uk()
    labels = []
    year = now.year
    month = now.month
    for _ in range(count):
        labels.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    labels.reverse()
    return labels


from business.db import get_db, init_db, database_counts
from business import quote_store, invoice_store, material_store
from business import customer_store, lead_store, invoice_photo_store
from business.material_store import normalize_material_url, get_cached_material_price
from business.quote_store import row_to_quote, load_quotes, get_quote_by_id, delete_quote_by_id, build_payment_link


def create_db_backup(reason: str = "manual"):
    """Create a physical SQLite backup file in persistent Render storage."""
    DB_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    if not DB_PATH.exists():
        return None

    timestamp = now_uk().strftime("%Y%m%d-%H%M%S")
    safe_reason = re.sub(r"[^a-zA-Z0-9_-]+", "-", reason or "manual").strip("-")[:40] or "manual"
    filename = f"quotes-backup-{timestamp}-{safe_reason}.db"
    backup_path = DB_BACKUP_DIR / filename

    # Use SQLite backup API where possible for a cleaner copy.
    src_conn = sqlite3.connect(DB_PATH)
    dst_conn = sqlite3.connect(backup_path)
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()

    size_bytes = backup_path.stat().st_size if backup_path.exists() else 0
    created_at = now_uk().isoformat()

    try:
        conn = get_db()
        conn.execute("""
            INSERT INTO app_backups (filename, path, reason, size_bytes, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (filename, str(backup_path), reason, size_bytes, created_at))
        conn.commit()
        conn.close()
    except Exception:
        pass

    prune_old_backups(keep=30)
    return {
        "filename": filename,
        "path": str(backup_path),
        "reason": reason,
        "size_bytes": size_bytes,
        "created_at": created_at,
    }


def prune_old_backups(keep: int = 30):
    try:
        backups = sorted(DB_BACKUP_DIR.glob("quotes-backup-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in backups[keep:]:
            try:
                old.unlink()
            except Exception:
                pass
    except Exception:
        pass


def list_db_backups():
    DB_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    for path in sorted(DB_BACKUP_DIR.glob("quotes-backup-*.db"), key=lambda p: p.stat().st_mtime, reverse=True):
        items.append({
            "filename": path.name,
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "created_at": datetime.fromtimestamp(path.stat().st_mtime, UK_TZ).isoformat(),
        })
    return items


@app.on_event("startup")
def startup():
    init_db()


def upsert_material_price_cache(url: str, name: str = "", supplier: str = "", price=None, manual_price=None, status: str = "live"):
    return material_store.upsert_material_price_cache(url, name, supplier, price, manual_price, status,
                                                      now_uk=now_uk, safe_float=safe_float)

def scrape_live_price(url: str):
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


def fetch_tracked_price(url: str, name: str = "", supplier: str = "", manual_price: float = 0):
    url = normalize_material_url(url)
    if not url:
        return None, "manual"

    live_price = scrape_live_price(url)
    if live_price is not None:
        upsert_material_price_cache(url, name, supplier, price=live_price, manual_price=manual_price, status="live")
        return live_price, "live"

    cached = get_cached_material_price(url)
    if cached:
        cached_price = cached.get("last_live_price") or cached.get("last_price")
        cached_price = safe_float(cached_price, None)
        if cached_price is not None and cached_price > 0:
            upsert_material_price_cache(url, name, supplier, price=cached_price, manual_price=manual_price, status="cached")
            return cached_price, "cached"

    # Keep the URL in the database even if the live scrape fails today.
    if manual_price and manual_price > 0:
        upsert_material_price_cache(url, name, supplier, price=None, manual_price=manual_price, status="manual")

    return None, "manual"


def fetch_price(url: str):
    price, _source = fetch_tracked_price(url)
    return price

def find_labour_suggestion(quote_type: str, job_description: str):
    return quote_calculation.find_labour_suggestion(quote_type, job_description, LABOUR_HINTS)


def calculate_quote(data: QuoteRequest):
    return quote_calculation.calculate_quote(
        data, fetch_tracked_price=fetch_tracked_price, safe_float=safe_float,
        material_quote_unit_price=material_quote_unit_price,
        find_labour_suggestion=find_labour_suggestion, now_uk=now_uk, format_dt=format_dt)

def upsert_customer(name: str, address: str, phone: str):
    return customer_store.upsert_customer(name, address, phone, now_uk)



PHOTO_CATEGORIES = invoice_photo_store.PHOTO_CATEGORIES


def normalise_photo_category(value: str) -> str:
    return invoice_photo_store.normalise_photo_category(value)


def invoice_photo_folder(invoice_id: int) -> Path:
    return invoice_photo_store.invoice_photo_folder(invoice_id)


def load_invoice_photos(invoice_id: int):
    return invoice_photo_store.load_invoice_photos(invoice_id)


def save_invoice_photo_record(invoice_id: int, category: str, caption: str,
                              filename: str, original_filename: str):
    return invoice_photo_store.save_invoice_photo_record(
        invoice_id, category, caption, filename, original_filename, now_uk)


def prepare_invoice_photo(source_path: Path, output_path: Path):
    return invoice_photo_store.prepare_invoice_photo(source_path, output_path)


def delete_invoice_photo_record(invoice_id: int, photo_id: int):
    return invoice_photo_store.delete_invoice_photo_record(invoice_id, photo_id)


def invoice_photo_path(invoice_id: int, photo_id: int):
    return invoice_photo_store.invoice_photo_path(invoice_id, photo_id)



def bank_payment_reference(item: dict) -> str:
    return str(item.get("invoice_number", "") or "").strip()


def bank_payment_text(item: dict) -> str:
    return "\n".join([
        "BANK TRANSFER DETAILS",
        f"Bank: {BANK_NAME}",
        f"Account name: {BANK_ACCOUNT_NAME}",
        f"Sort code: {BANK_SORT_CODE}",
        f"Account number: {BANK_ACCOUNT_NUMBER}",
        f"Amount due: {pounds_text(item.get('balance_due', 0))}",
        f"Reference: {bank_payment_reference(item)}",
    ])


def bank_payment_qr_png(item: dict) -> bytes:
    if not QRCODE_AVAILABLE:
        raise RuntimeError(
            "QR code support is not installed. Add qrcode[pil] to requirements.txt."
        )

    qr = qrcode.QRCode(version=None, box_size=7, border=2)
    qr.add_data(bank_payment_text(item))
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def invoice_due_date_object(item: dict):
    try:
        return datetime.strptime(item.get("due_date", ""), "%d/%m/%Y").date()
    except Exception:
        return None


def invoice_is_overdue(item: dict) -> bool:
    due = invoice_due_date_object(item)
    return bool(
        due
        and due < now_uk().date()
        and str(item.get("status", "")).lower() != "paid"
        and safe_float(item.get("balance_due", 0), 0) > 0
    )


def invoice_paid_watermark(c):
    c.saveState()
    try:
        c.setFillAlpha(0.16)
    except Exception:
        pass
    c.setFillColorRGB(0.15, 0.55, 0.22)
    c.setFont("Helvetica-Bold", 72)
    c.translate(A4[0] / 2, A4[1] / 2)
    c.rotate(32)
    c.drawCentredString(0, 0, "PAID")
    c.restoreState()


def update_invoice_reminder_timestamp(invoice_id: int):
    conn = get_db()
    conn.execute("UPDATE invoices SET last_reminder_at = ? WHERE id = ?", (now_uk().isoformat(), invoice_id))
    conn.commit()
    conn.close()


def send_overdue_reminder_now(item: dict):
    email = (item.get("reminder_email") or "").strip()
    if not email:
        raise RuntimeError("No reminder email is saved on this invoice.")
    if not invoice_is_overdue(item):
        raise RuntimeError("This invoice is not currently overdue.")
    message = (
        f"This is a payment reminder for invoice {item['invoice_number']}"
        f"{f' (Job Ref {item.get("job_reference")})' if item.get("job_reference") else ''}. "
        f"The outstanding balance is {pounds_text(item.get('balance_due', 0))}. "
        f"Please use {item['invoice_number']} as the bank-transfer reference."
    )
    send_invoice_email_now(item, email, message)
    update_invoice_reminder_timestamp(item["id"])
    return get_invoice_by_id(item["id"])


def process_overdue_invoice_reminders():
    sent, skipped = [], []
    for item in load_invoices():
        if not item.get("reminders_enabled") or not invoice_is_overdue(item):
            continue
        if not item.get("reminder_email"):
            skipped.append({"id": item["id"], "reason": "No reminder email"})
            continue
        last_value = item.get("last_reminder_at") or ""
        if last_value:
            try:
                last_dt = datetime.fromisoformat(last_value)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=UK_TZ)
                if (now_uk() - last_dt).total_seconds() < OVERDUE_REMINDER_INTERVAL_HOURS * 3600:
                    continue
            except Exception:
                pass
        try:
            send_overdue_reminder_now(item)
            sent.append(item["id"])
        except Exception as exc:
            skipped.append({"id": item["id"], "reason": str(exc)})
    return {"sent": sent, "skipped": skipped}


def _overdue_reminder_worker():
    while True:
        try:
            if AUTO_OVERDUE_REMINDERS:
                process_overdue_invoice_reminders()
        except Exception:
            pass
        time.sleep(max(3600, OVERDUE_REMINDER_INTERVAL_HOURS * 3600))


def row_to_invoice(row):
    return {
        "id": row["id"],
        "quote_id": row["quote_id"],
        "customer_id": row["customer_id"],
        "invoice_number": row["invoice_number"],
        "customer_name": row["customer_name"] or "",
        "total_price": round(row["total_price"] or 0, 2),
        "amount_paid": round(row["amount_paid"] or 0, 2),
        "balance_due": round(row["balance_due"] or 0, 2),
        "status": row["status"],
        "due_date": row["due_date"],
        "payment_link": row["payment_link"] or "",
        "job_reference": row["job_reference"] or "",
        "reminder_email": row["reminder_email"] or "",
        "reminders_enabled": bool(row["reminders_enabled"] or 0),
        "last_reminder_at": row["last_reminder_at"] or "",
        "created_at": row["created_at"],
        "quote_result": json.loads(row["quote_result_json"]),
        "invoice": json.loads(row["invoice_json"]),
        "photos": load_invoice_photos(row["id"]),
        "qr_available": QRCODE_AVAILABLE,
    }


def save_quote(request_data: dict, result_data: dict):
    create_db_backup("before-save-quote")
    return quote_store.save_quote(request_data, result_data, upsert_customer, now_uk)


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


def analyse_similar_quotes(query: str, quote_type: str = ""):
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


def next_invoice_number():
    return quote_store.next_invoice_number(now_uk)

def create_invoice_from_quote(quote_id: int):
    create_db_backup("before-create-invoice")
    return quote_store.create_invoice_from_quote(quote_id, now_uk, format_dt, get_invoice_by_id)

def get_invoice_by_id(invoice_id: int):
    return invoice_store.get_invoice_by_id(invoice_id, row_to_invoice)

def load_invoices():
    return invoice_store.load_invoices(row_to_invoice)

def delete_invoice_by_id(invoice_id: int):
    return invoice_store.delete_invoice_by_id(invoice_id)

def update_invoice_status(invoice_id: int, status: str, amount_paid: float):
    return invoice_store.update_invoice_status(invoice_id, status, amount_paid, row_to_invoice, safe_float)

def update_quote_by_id(quote_id: int, request_data: dict, result_data: dict):
    create_db_backup("before-update-quote")
    return quote_store.update_quote_by_id(quote_id, request_data, result_data, upsert_customer)

def update_invoice_by_id(invoice_id: int, data: InvoiceEditRequest):
    return invoice_store.update_invoice_by_id(invoice_id, data, row_to_invoice, safe_float, upsert_customer)

def get_dashboard():
    now = now_uk()
    month_prefix = now.strftime("%Y-%m")

    conn = get_db()

    q = conn.execute("""
        SELECT
            COUNT(*) AS quote_count,
            COALESCE(SUM(total_price), 0) AS quoted_total,
            COALESCE(SUM(gross_profit), 0) AS gross_profit_total
        FROM quotes
        WHERE substr(created_at_sort, 1, 7) = ?
    """, (month_prefix,)).fetchone()

    i = conn.execute("""
        SELECT
            COUNT(*) AS invoice_count,
            COALESCE(SUM(total_price), 0) AS invoiced_total,
            COALESCE(SUM(amount_paid), 0) AS paid_total,
            COALESCE(SUM(balance_due), 0) AS balance_total
        FROM invoices
        WHERE substr(created_at_sort, 1, 7) = ?
    """, (month_prefix,)).fetchone()

    avg = conn.execute("""
        SELECT COALESCE(AVG(total_price), 0) AS avg_quote
        FROM quotes
        WHERE substr(created_at_sort, 1, 7) = ?
    """, (month_prefix,)).fetchone()

    customers = conn.execute("SELECT COUNT(*) AS customer_count FROM customers").fetchone()

    conn.close()

    return {
        "month_label": now.strftime("%B %Y"),
        "quote_count": q["quote_count"] or 0,
        "quoted_total": round(q["quoted_total"] or 0, 2),
        "gross_profit_total": round(q["gross_profit_total"] or 0, 2),
        "invoice_count": i["invoice_count"] or 0,
        "invoiced_total": round(i["invoiced_total"] or 0, 2),
        "paid_total": round(i["paid_total"] or 0, 2),
        "balance_total": round(i["balance_total"] or 0, 2),
        "avg_quote": round(avg["avg_quote"] or 0, 2),
        "customer_count": customers["customer_count"] or 0,
    }


def get_monthly_profit_series(month_count: int = 6):
    labels = month_labels(month_count)
    conn = get_db()
    out = []
    for month_prefix in labels:
        row = conn.execute("""
            SELECT
                COALESCE(SUM(total_price), 0) AS revenue,
                COALESCE(SUM(gross_profit), 0) AS profit
            FROM quotes
            WHERE substr(created_at_sort, 1, 7) = ?
        """, (month_prefix,)).fetchone()
        out.append({
            "month_key": month_prefix,
            "label": datetime.strptime(month_prefix + '-01', '%Y-%m-%d').strftime('%b %Y'),
            "revenue": round(row['revenue'] or 0, 2),
            "profit": round(row['profit'] or 0, 2),
        })
    conn.close()
    return out


def get_customers():
    return customer_store.get_customers()


def get_customer_history(customer_id: int):
    return customer_store.get_customer_history(customer_id, row_to_quote, row_to_invoice)




def pounds_text(value):
    return f"£{safe_float(value, 0):.2f}"


def get_public_base_url(request: Request | None = None) -> str:
    production_origin = "https://www.nigelharveyplumbing.co.uk"
    configured = (os.getenv("PUBLIC_BASE_URL") or "").strip()
    staging = (os.getenv("APP_ENVIRONMENT") or "").strip().lower() == "staging"
    if not configured:
        if staging:
            raise ValueError("PUBLIC_BASE_URL is required in staging")
        return production_origin
    origin = configured.rstrip("/")
    parts = urlsplit(origin)
    try:
        _ = parts.port
    except ValueError as exc:
        raise ValueError("PUBLIC_BASE_URL has an invalid port") from exc
    if (parts.scheme not in {"http", "https"} or not parts.hostname or
            parts.username is not None or parts.password is not None or
            parts.path or parts.query or
            parts.fragment or any(ch.isspace() or ch in {"<", ">", '"', "'", "`", "\\"}
                                  for ch in parts.netloc)):
        raise ValueError("PUBLIC_BASE_URL must be an HTTP(S) origin without a path")
    if staging and parts.hostname.lower() in {
            "www.nigelharveyplumbing.co.uk", "nigelharveyplumbing.co.uk"}:
        raise ValueError("Staging PUBLIC_BASE_URL cannot be the live website")
    return origin


# Fail startup before generating customer links with an invalid staging origin.
get_public_base_url()


def absolute_url(path: str, request: Request | None = None) -> str:
    clean_path = path if path.startswith("/") else f"/{path}"
    base = get_public_base_url(request)
    return f"{base}{clean_path}" if base else clean_path


def build_invoice_public_url(invoice_id: int, request: Request | None = None):
    return absolute_url(f"/invoice/{invoice_id}", request)


from business import pdf_render


def _pdf_context():
    from types import SimpleNamespace
    return SimpleNamespace(
        pdf_logo_reader=_pdf_logo_reader,
        company_name=COMPANY_NAME, company_address=COMPANY_ADDRESS,
        company_phone=COMPANY_PHONE, company_email=COMPANY_EMAIL,
        pounds_text=pounds_text, safe_float=safe_float,
        invoice_photo_path=invoice_photo_path,
        bank_name=BANK_NAME, bank_account_name=BANK_ACCOUNT_NAME,
        bank_sort_code=BANK_SORT_CODE, bank_account_number=BANK_ACCOUNT_NUMBER,
        bank_payment_reference=bank_payment_reference,
        bank_payment_qr_png=bank_payment_qr_png,
        invoice_paid_watermark=invoice_paid_watermark,
        qrcode_available=QRCODE_AVAILABLE,
        invoice_terms=INVOICE_TERMS, quote_terms=QUOTE_TERMS,
    )


def generate_invoice_pdf_bytes(item: dict):
    return pdf_render.generate_invoice_pdf_bytes(item, _pdf_context())


def generate_quote_pdf_bytes(item: dict):
    return pdf_render.generate_quote_pdf_bytes(item, _pdf_context())




















from business import document_sharing


def send_invoice_email_now(item: dict, to_email: str, extra_message: str = ""):
    if not EMAIL_ENABLED or not EMAIL_USER or not EMAIL_PASS:
        raise RuntimeError("Email sending is not configured yet. Set EMAIL_ENABLED=1, EMAIL_USER and EMAIL_PASS.")

    from types import SimpleNamespace
    msg = document_sharing.prepare_invoice_email(item, to_email, extra_message, SimpleNamespace(
        build_invoice_public_url=build_invoice_public_url,
        company_name=COMPANY_NAME, company_phone=COMPANY_PHONE, company_email=COMPANY_EMAIL,
        pounds_text=pounds_text, get_company_logo_value=get_company_logo_value,
        generate_invoice_pdf_bytes=generate_invoice_pdf_bytes,
        from_header=f"{EMAIL_FROM_NAME} <{EMAIL_USER}>",
    ))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(EMAIL_HOST, EMAIL_PORT, context=context) as server:
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, [to_email.strip()], msg.as_string())

def row_to_lead(row):
    return lead_store.row_to_lead(row)


def save_lead(data: LeadRequest):
    return lead_store.save_lead(data, now_uk, format_dt)


def get_lead_by_id(lead_id: int):
    return lead_store.get_lead_by_id(lead_id)


def load_leads():
    return lead_store.load_leads()


def update_lead_status(lead_id: int, status: str):
    return lead_store.update_lead_status(lead_id, status, now_uk)


def delete_lead_by_id(lead_id: int):
    return lead_store.delete_lead_by_id(lead_id)


def send_lead_notification_email(lead: dict):
    if not EMAIL_ENABLED or not EMAIL_USER or not EMAIL_PASS:
        return
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"New quote request - {lead.get('name') or 'Website lead'}"
        msg["From"] = f"{EMAIL_FROM_NAME} <{EMAIL_USER}>"
        msg["To"] = EMAIL_USER
        public_url = get_public_base_url() if (os.getenv("PUBLIC_BASE_URL") or "").strip() else ""
        plain = (
            f"New website lead\n\n"
            f"Name: {lead.get('name','')}\n"
            f"Phone: {lead.get('phone','')}\n"
            f"Email: {lead.get('email','')}\n"
            f"Address: {lead.get('address','')}\n"
            f"Job type: {lead.get('job_type','')}\n"
            f"Description: {lead.get('description','')}\n\n"
            f"Open app: {public_url}\n"
        )
        html = (
            '<html><body style="font-family:Arial,sans-serif;">'
            '<h2>New website lead</h2>'
            f"<p><strong>Name:</strong> {escape(lead.get('name',''))}<br>"
            f"<strong>Phone:</strong> {escape(lead.get('phone',''))}<br>"
            f"<strong>Email:</strong> {escape(lead.get('email',''))}<br>"
            f"<strong>Address:</strong> {escape(lead.get('address',''))}<br>"
            f"<strong>Job type:</strong> {escape(lead.get('job_type',''))}</p>"
            f"<p><strong>Description:</strong><br>{escape(lead.get('description','')).replace(chr(10), '<br>')}</p>"
            '</body></html>'
        )
        msg.attach(MIMEText(plain, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(EMAIL_HOST, EMAIL_PORT, context=context) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, [EMAIL_USER], msg.as_string())
    except Exception:
        return



def build_homepage_faq_schema() -> str:
    faq_items = [
        {
            "@type": "Question",
            "name": "Do you cover all of Surrey?",
            "acceptedAnswer": {
                "@type": "Answer",
                "text": "Nigel Harvey Ltd covers Guildford, Woking, Farnham, Godalming, Camberley, Aldershot, Leatherhead, Epsom and surrounding Surrey areas. If you are nearby, get in touch and ask."
            }
        },
        {
            "@type": "Question",
            "name": "Can I request an emergency plumber?",
            "acceptedAnswer": {
                "@type": "Answer",
                "text": "Yes. The site includes an emergency plumbing page and quote request form so customers can send details quickly for urgent plumbing issues in Surrey."
            }
        },
        {
            "@type": "Question",
            "name": "What type of plumbing work do you do?",
            "acceptedAnswer": {
                "@type": "Answer",
                "text": "General plumbing, bathroom plumbing, leaks, toilets, taps, sinks, wastes, pipework changes, radiators and similar domestic plumbing jobs."
            }
        },
    ]
    return json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": faq_items}, ensure_ascii=False)


def build_homepage_business_schema(canonical_home: str) -> str:
    schema = {
        "@context": "https://schema.org",
        "@type": "Plumber",
        "name": COMPANY_NAME,
        "telephone": COMPANY_PHONE,
        "email": COMPANY_EMAIL,
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "125 Bushy Hill Drive",
            "addressLocality": "Guildford",
            "postalCode": "GU1 2UG",
            "addressCountry": "GB",
        },
        "areaServed": ["Guildford", "Woking", "Farnham", "Godalming", "Camberley", "Aldershot", "Leatherhead", "Epsom", "Weybridge", "Cobham", "Surrey"],
        "url": canonical_home,
        "description": "Plumbing services in Surrey and surrounding areas including emergency plumbing, general plumbing, bathroom plumbing, leaks, pipework and domestic plumbing repairs.",
    }
    if GOOGLE_RATING_VALUE and GOOGLE_REVIEW_COUNT:
        schema["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": GOOGLE_RATING_VALUE,
            "reviewCount": GOOGLE_REVIEW_COUNT,
            "bestRating": "5",
            "worstRating": "1",
        }
    reviews = []
    for text_value, author in [
        (GOOGLE_REVIEW_1_TEXT, GOOGLE_REVIEW_1_AUTHOR),
        (GOOGLE_REVIEW_2_TEXT, GOOGLE_REVIEW_2_AUTHOR),
        (GOOGLE_REVIEW_3_TEXT, GOOGLE_REVIEW_3_AUTHOR),
    ]:
        if text_value and author:
            reviews.append({
                "@type": "Review",
                "author": {"@type": "Person", "name": author},
                "reviewBody": text_value,
                "reviewRating": {"@type": "Rating", "ratingValue": "5", "bestRating": "5", "worstRating": "1"},
            })
    if reviews:
        schema["review"] = reviews
    return json.dumps(schema, ensure_ascii=False)


def build_reviews_badge_html() -> str:
    if GOOGLE_RATING_VALUE and GOOGLE_REVIEW_COUNT:
        reviews_link = escape(GOOGLE_REVIEWS_URL, quote=True)
        return f'<a href="{reviews_link}" target="_blank" rel="noopener noreferrer">Google rating {escape(GOOGLE_RATING_VALUE)}/5</a><span>{escape(GOOGLE_REVIEW_COUNT)} Google reviews</span>'
    return '<span>Trusted local Surrey plumber</span><span>Ask about recent customer feedback</span>'


def build_reviews_section_html() -> str:
    if GOOGLE_RATING_VALUE and GOOGLE_REVIEW_COUNT:
        cards = []
        for text_value, author in [
            (GOOGLE_REVIEW_1_TEXT, GOOGLE_REVIEW_1_AUTHOR),
            (GOOGLE_REVIEW_2_TEXT, GOOGLE_REVIEW_2_AUTHOR),
            (GOOGLE_REVIEW_3_TEXT, GOOGLE_REVIEW_3_AUTHOR),
        ]:
            if text_value and author:
                cards.append(
                    f'<div class="card faq"><h3>{escape(author)}</h3><p>“{escape(text_value)}”</p></div>'
                )
        if not cards:
            cards.append('<div class="card faq"><h3>Google customer feedback</h3><p>Strong review signals help build trust with both customers and search engines. Add your three best Google reviews here to strengthen the homepage further.</p></div>')
        reviews_link = escape(GOOGLE_REVIEWS_URL, quote=True)
        return (
            '<div class="wrap section"><h2>Google reviews</h2>'
            f'<p class="copy">Nigel Harvey Ltd currently shows a Google rating of {escape(GOOGLE_RATING_VALUE)}/5 from {escape(GOOGLE_REVIEW_COUNT)} reviews. '
            f'<a href="{reviews_link}" target="_blank" rel="noopener noreferrer">Read the latest Google reviews</a>.</p>'
            f'<div class="grid3">{"".join(cards)}</div></div>'
        )
    return (
        '<div class="wrap section"><h2>Trusted local plumber in Surrey</h2>'
        '<p class="copy">Nigel Harvey Ltd is a local plumbing and heating company serving Surrey and surrounding areas. We focus on providing reliable service, clear communication and quality workmanship on every job.</p></div>'
    )



LANDING_PAGE_HTML = r'''
<!doctype html>
<html lang="en-GB">
<head>
<meta name="google-site-verification" content="Dw_MXa0LZioT3zkorUaBVFc1NAgnlecAcVVaaNY_Jdw" />
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Plumber in Surrey | Emergency Plumber & General Plumbing | Nigel Harvey Ltd</title>
<meta name="description" content="Local plumber in Surrey covering Guildford, Woking, Farnham and surrounding areas. Emergency plumbing, leaks, bathroom plumbing, repairs and installations. Call Nigel Harvey Ltd for a fast response.">
<meta name="keywords" content="plumber Surrey, emergency plumber Surrey, plumber Guildford, plumber Woking, plumber Farnham, bathroom plumbing Surrey, general plumbing Surrey">
<link rel="canonical" href="__CANONICAL_HOME__">
<script type="application/ld+json">__BUSINESS_SCHEMA_JSON__
document.addEventListener('input', function(e) {
  if (e.target && e.target.classList && e.target.classList.contains('m-name')) {
    updateChargingNotes();
    updateForgottenItemWarnings();
    updateSupplierPreferenceNotes();
  if (typeof updateQuantityLearningNotes === 'function') if (typeof updateQuantityLearningNotes === 'function') updateQuantityLearningNotes();
  }
});


function updateQuantityLearningNotes() {
  try {
    document.querySelectorAll("#materials .material-row").forEach(row => {
      const nameInput = row.querySelector(".m-name");
      const noteBox = row.querySelector(".quantity-learning-note");
      if (!nameInput || !noteBox) return;

      if (typeof suggestMaterialQuantityInfo !== "function") {
        noteBox.innerHTML = "";
        return;
      }

      const info = suggestMaterialQuantityInfo(nameInput.value || "");
      if (info && info.source === "learned" && Number(info.used_count || 0) > 0) {
        noteBox.innerHTML = `Quantity learned from history: avg ${Number(info.average_quantity || 0).toFixed(2)} used ${info.used_count} time(s). Suggested ${info.quantity}.`;
      } else {
        noteBox.innerHTML = "";
      }
    });
  } catch (e) {
    // Never let a display helper break quote/customer actions.
  }
}


</script>
<script type="application/ld+json">__FAQ_SCHEMA_JSON__</script>
<style>
:root{--bg:#f5f7fb;--card:#ffffff;--text:#101828;--muted:#667085;--brand:#111827;--accent:#065f46;--accent2:#1d4ed8;--border:#e5e7eb;--shadow:0 10px 30px rgba(0,0,0,.06);--radius:22px}
*{box-sizing:border-box}
body{margin:0;font-family:Arial,sans-serif;background:var(--bg);color:var(--text)}
a{text-decoration:none;color:inherit}
.wrap{max-width:1160px;margin:0 auto;padding:0 16px}
.top{position:sticky;top:0;background:rgba(245,247,251,.94);backdrop-filter:blur(10px);border-bottom:1px solid var(--border);z-index:10}
.nav{display:flex;justify-content:space-between;align-items:center;padding:14px 0;gap:12px;flex-wrap:wrap}
.brand{font-size:22px;font-weight:800}
.brand small{display:block;font-size:12px;color:var(--muted);margin-top:3px}
.nav-actions{display:flex;gap:12px;flex-wrap:wrap}
.btn{display:inline-block;padding:14px 20px;border-radius:999px;font-weight:700}
.btn-primary{background:var(--brand);color:#fff}
.btn-green{background:var(--accent);color:#fff}
.btn-light{background:#fff;border:1px solid var(--border)}
.hero{padding:38px 0 20px}
.hero-grid{display:grid;grid-template-columns:1.15fr .85fr;gap:22px;align-items:stretch}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);box-shadow:var(--shadow)}
.hero-copy{padding:34px}
.hero-copy h1{font-size:clamp(34px,5vw,58px);line-height:1.03;margin:0 0 14px}
.lead{font-size:18px;color:var(--muted);max-width:46rem;margin:0 0 18px;line-height:1.6}
.tag{display:inline-block;padding:7px 12px;border-radius:999px;background:#dbeafe;color:#1d4ed8;font-weight:800;font-size:12px;margin-bottom:12px}
.hero-actions{display:flex;gap:12px;flex-wrap:wrap;margin:20px 0 16px}
.trust{display:flex;gap:18px;flex-wrap:wrap;color:var(--muted);font-weight:700;font-size:14px}
.panel{padding:24px}
.panel h2,.section h2{margin:0 0 12px;font-size:30px}
.panel p,.section p.copy{margin:0 0 18px;color:var(--muted);line-height:1.65}
.check{padding:14px 15px;border:1px solid var(--border);border-radius:14px;background:#f8fafc;font-weight:700;margin-bottom:10px}
.stats{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin-top:14px}
.stat{padding:16px;border-radius:16px;background:#f8fafc;border:1px solid var(--border)}
.stat strong{display:block;font-size:20px;margin-bottom:4px}
.section{padding:18px 0}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
.item{padding:22px}
.item h3{margin:0 0 8px;font-size:20px}
.item p{margin:0;color:var(--muted);line-height:1.55}
.link-grid,.pill-links{display:grid;gap:18px}
.link-grid{grid-template-columns:repeat(4,1fr)}
.pill-links{grid-template-columns:repeat(4,1fr)}
.link-grid a,.pill-links a{display:flex;align-items:center;justify-content:center;min-height:56px;padding:18px;background:#fff;border:1px solid var(--border);border-radius:16px;box-shadow:var(--shadow);font-weight:700;line-height:1.35;text-align:center}
.link-grid a:hover,.pill-links a:hover{border-color:#cbd5e1}
ul.clean{margin:0;padding-left:18px;color:var(--muted);line-height:1.7}ul.clean li{margin-bottom:10px}ul.clean li a,.section ul li a{display:inline-flex;align-items:center;min-height:44px;padding:8px 0;line-height:1.45}
.cta{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;padding:26px;margin:26px 0 20px}
.footer{padding:20px 0 36px;color:var(--muted)}
.footer-inner{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;border-top:1px solid var(--border);padding-top:18px}
.logo-box{margin-bottom:14px}
.logo-box img{max-width:240px;max-height:90px;object-fit:contain}
.faq-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
.faq{padding:20px}
.faq h3{margin:0 0 8px;font-size:19px}
.faq p{margin:0;color:var(--muted);line-height:1.6}
.reviews-wrap{margin-top:22px}
@media (max-width: 960px){
  .hero-grid,.grid3,.faq-grid,.link-grid,.pill-links{grid-template-columns:1fr 1fr}
}
@media (max-width: 720px){
  .hero-grid,.grid3,.faq-grid,.link-grid,.pill-links,.stats{grid-template-columns:1fr}
  .hero-copy{padding:26px}
  .panel h2,.section h2{font-size:26px}
}

.sticky-call{position:fixed;left:0;right:0;bottom:0;width:100%;background:#064e3b;color:#fff;text-align:center;padding:16px 18px;font-size:18px;font-weight:800;line-height:1.35;text-decoration:none;z-index:9999;box-shadow:0 -2px 12px rgba(0,0,0,.18)}
body{padding-bottom:72px}
</style>
</head>
<body>
  <div class="top">
    <div class="wrap nav">
      <div class="brand">Nigel Harvey Ltd<small>Plumbing in Surrey</small></div>
      <div class="nav-actions">
        <a class="btn btn-light" href="tel:__COMPANY_PHONE_TEL__">Call Now</a>
        <a class="btn btn-primary" href="/request-quote">Get a Fast Quote</a>
        <a class="btn btn-light" href="/app">Open App</a>
      </div>
    </div>
  </div>

  <main>
  <div class="hero">
    <div class="wrap hero-grid">
      <div class="card hero-copy">
        <div class="logo-box">__COMPANY_LOGO_HTML__</div>
        <span class="tag">Trusted local plumber across Surrey</span>
        <h1>Reliable Plumber in Surrey</h1>
        <p class="lead">Need a plumber in Guildford, Woking, Farnham or nearby? Nigel Harvey Ltd provides fast, reliable plumbing services across Surrey, including emergency plumbing, leaks, pipework repairs, bathroom plumbing and general plumbing work with a straightforward service you can trust.</p>
        <div class="hero-actions">
          <a class="btn btn-green" href="tel:__COMPANY_PHONE_TEL__">Call __COMPANY_PHONE__</a>
          <a class="btn btn-primary" href="/request-quote">Get a Fast Quote</a>
        </div>
        <div class="trust">
          <span>Fast response across Surrey</span>
          <span>Clear communication</span>
          <span>Professional finish</span>
        </div>
        <div class="reviews-wrap">__REVIEWS_BADGE_HTML__</div>
      </div>

      <div class="card panel">
        <h2>Local Plumbing Experts in Surrey</h2>
        <p>We are a local Surrey plumbing company focused on clear communication, fair pricing and tidy workmanship. From small repairs to bathroom plumbing and pipework upgrades, every job is handled with care and attention to detail.</p>
        <div class="check">Emergency plumbing services</div>
        <div class="check">Leaks, pipework repairs and general plumbing</div>
        <div class="check">Bathroom plumbing and installations</div>
        <div class="check">Covering Surrey towns and nearby areas</div>
        <div class="stats">
          <div class="stat"><strong>Surrey coverage</strong><span>Guildford, Woking, Farnham and surrounding areas.</span></div>
          <div class="stat"><strong>Simple process</strong><span>Call, request a quote online, or open the app.</span></div>
        </div>
      </div>
    </div>
  </div>

  <div class="wrap">
    <div class="section">
      <h2>Our Surrey plumbing services</h2>
      <p class="copy">From urgent leaks to planned bathroom plumbing work, we provide practical domestic plumbing services that help homeowners and landlords across Surrey get the job sorted properly.</p>
      <div class="pill-links">
        <a href="/emergency-plumber-surrey">Emergency Plumber Surrey</a>
        <a href="/general-plumbing-surrey">General Plumbing Surrey</a>
        <a href="/bathroom-plumbing-surrey">Bathroom Plumbing Surrey</a>
        <a href="/heating-repairs-surrey">Heating Repairs Surrey</a>
      </div>
    </div>

    <div class="section">
      <h2>Areas we cover</h2>
      <p class="copy">We provide plumbing services across Surrey including Guildford, Woking, Farnham, Godalming, Camberley, Aldershot, Leatherhead and Epsom. Select your area below to learn more about our local plumbing services.</p>
      <div class="link-grid">
        <a href="/plumber-guildford">Plumber in Guildford</a>
        <a href="/plumber-woking">Plumber in Woking</a>
        <a href="/plumber-farnham">Plumber in Farnham</a>
        <a href="/plumber-godalming">Plumber in Godalming</a>
        <a href="/plumber-camberley">Plumber in Camberley</a>
      <li><a href="/plumber-chilworth">Plumber in Chilworth</a></li>
  <li><a href="/plumber-shalford">Plumber in Shalford</a></li>
  <li><a href="/plumber-burpham">Plumber in Burpham</a></li>
  <li><a href="/plumber-merrow">Plumber in Merrow</a></li>
  <li><a href="/plumber-worplesdon">Plumber in Worplesdon</a></li>
  <li><a href="/plumber-fairlands">Plumber in Fairlands</a></li>
        <a href="/plumber-aldershot">Plumber in Aldershot</a>
        <a href="/plumber-leatherhead">Plumber in Leatherhead</a>
        <a href="/plumber-epsom">Plumber in Epsom</a>
      </div>
    </div>

    <div class="section">
      <h2>Why choose Nigel Harvey Ltd</h2>
      <div class="grid3">
        <div class="card item">
          <h3>Local Surrey coverage</h3>
          <p>We focus on Surrey and nearby areas, allowing us to respond quickly and provide a reliable local service.</p>
        </div>
        <div class="card item">
          <h3>Clear communication</h3>
          <p>We keep things simple, honest and straightforward from first contact to job completion.</p>
        </div>
        <div class="card item">
          <h3>Professional service</h3>
          <p>Clean, tidy work with a focus on quality and long-term solutions.</p>
        </div>
      </div>
    </div>

    <div class="card cta">
      <div>
        <h2>Need a plumber in Surrey?</h2>
        <p class="copy" style="margin-bottom:0">If you need a reliable plumber for an emergency, repair or installation, get in touch today.</p>
      </div>
      <div class="nav-actions">
        <a class="btn btn-green" href="tel:__COMPANY_PHONE_TEL__">Call __COMPANY_PHONE__</a>
        <a class="btn btn-primary" href="/request-quote">Get a fast quote online</a>
      </div>
    </div>

    __REVIEWS_SECTION_HTML__
<div class="wrap section">
  <h2>Plumbing Services Across Surrey</h2>
<p>We provide trusted plumbing services across Surrey, covering Guildford, Woking, Farnham, Godalming and Camberley.</p>

<ul>
  <li><a href="/plumber-guildford">Plumbing services in Guildford</a></li>
  <li><a href="/plumber-woking">Emergency plumber in Woking</a></li>
  <li><a href="/plumber-farnham">Local plumber in Farnham</a></li>
  <li><a href="/plumber-godalming">Plumbing repairs in Godalming</a></li>
  <li><a href="/plumber-camberley">Trusted plumber in Camberley</a></li>
</ul>

<p>Our experienced plumbers are available across Surrey for emergency callouts, repairs and installations, with fast response times in all listed areas.</p>

<div class="section">
      <h2>Frequently asked questions</h2>
      <div class="faq-grid">
        <div class="card faq">
          <h3>Do you offer emergency plumbing in Surrey?</h3>
          <p>Yes, we provide emergency plumbing services across Surrey and aim to respond as quickly as possible.</p>
        </div>
        <div class="card faq">
          <h3>What areas do you cover?</h3>
          <p>We cover Guildford, Woking, Farnham, Godalming, Camberley, Aldershot, Leatherhead, Epsom and surrounding areas.</p>
        </div>
        <div class="card faq">
          <h3>What type of plumbing work do you do?</h3>
          <p>We handle general plumbing, leaks, pipework repairs, bathroom plumbing and more.</p>
        </div>
      </div>
    </div>

    <div class="footer">
      <div class="footer-inner">
        <div><strong>Nigel Harvey Ltd</strong><br>Plumbing &amp; Heating in Surrey</div>
        <div>Phone: __COMPANY_PHONE__<br>Email: __COMPANY_EMAIL__<br>Guildford, Surrey and surrounding areas</div>
      </div>
    </div>
  </div>
  </main>
<a href="tel:__COMPANY_PHONE_TEL__" class="sticky-call">📞 Call Now: __COMPANY_PHONE__</a>
</body>
</html>
'''

SEO_CSS = '''
:root{--bg:#f5f7fb;--card:#ffffff;--text:#101828;--muted:#667085;--brand:#111827;--accent:#065f46;--border:#e5e7eb;--shadow:0 10px 30px rgba(0,0,0,.06);--radius:22px}
*{box-sizing:border-box} body{margin:0;font-family:Arial,sans-serif;background:var(--bg);color:var(--text)} a{text-decoration:none;color:inherit}
.wrap{max-width:1100px;margin:0 auto;padding:0 16px}
.top{position:sticky;top:0;background:rgba(245,247,251,.94);backdrop-filter:blur(10px);border-bottom:1px solid var(--border);z-index:10}
.nav{display:flex;justify-content:space-between;align-items:center;padding:14px 0;gap:12px;flex-wrap:wrap}.brand{font-size:22px;font-weight:800}.brand small{display:block;font-size:12px;color:var(--muted);margin-top:3px}
.nav-actions{display:flex;gap:12px;flex-wrap:wrap}.btn{display:inline-block;padding:14px 20px;border-radius:999px;font-weight:700}.btn-primary{background:var(--brand);color:#fff}.btn-green{background:var(--accent);color:#fff}.btn-light{background:#fff;border:1px solid var(--border)}
.hero{padding:36px 0 18px}.hero-card,.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);box-shadow:var(--shadow)}
.hero-card{padding:30px}.eyebrow{display:inline-block;padding:7px 12px;border-radius:999px;background:#dbeafe;color:#1d4ed8;font-weight:800;font-size:12px;margin-bottom:12px} h1{font-size:clamp(32px,5vw,54px);line-height:1.05;margin:0 0 14px} .lead{font-size:18px;color:var(--muted);line-height:1.6;margin:0 0 18px}
.section{padding:18px 0}.section h2{margin:0 0 12px;font-size:30px}.section p{color:var(--muted);line-height:1.7;margin:0 0 16px}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.item{padding:22px}.item h3{margin:0 0 8px;font-size:20px}.item p{margin:0}
.pill-links{display:grid;grid-template-columns:repeat(4,1fr);gap:18px}.pill-links a{display:flex;align-items:center;justify-content:center;min-height:56px;padding:18px;background:#fff;border:1px solid var(--border);border-radius:16px;box-shadow:var(--shadow);font-weight:700;line-height:1.35;text-align:center}
.list{margin:0;padding-left:18px;color:var(--muted);line-height:1.8}.list li{margin:0 0 10px}.list li a,.section ul li a{display:inline-flex;align-items:center;min-height:44px;padding:8px 0;line-height:1.45}.section ul li{margin-bottom:10px}
.cta{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;padding:24px;margin:26px 0 40px}
.footer{padding:20px 0 36px;color:var(--muted)} .footer-inner{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;border-top:1px solid var(--border);padding-top:18px}
.logo{max-width:240px;max-height:90px;object-fit:contain}
.sticky-call{position:fixed;left:0;right:0;bottom:0;width:100%;background:#064e3b;color:#fff;text-align:center;padding:16px 18px;font-size:18px;font-weight:800;line-height:1.35;text-decoration:none;z-index:9999;box-shadow:0 -2px 12px rgba(0,0,0,.18)}body{padding-bottom:72px}
@media (max-width:900px){.grid3,.pill-links{grid-template-columns:1fr 1fr}.hero-card,.item,.cta{padding:20px}.section h2{font-size:26px}}
@media (max-width:640px){.grid3,.pill-links{grid-template-columns:1fr}}
'''

LOCATION_PAGES = [
    {"slug":"guildford","name":"Guildford"},
    {"slug":"woking","name":"Woking"},
    {"slug":"farnham","name":"Farnham"},
    {"slug":"godalming","name":"Godalming"},
    {"slug":"camberley","name":"Camberley"},
    {"slug":"aldershot","name":"Aldershot"},
    {"slug":"leatherhead","name":"Leatherhead"},
    {"slug":"epsom","name":"Epsom"},
    {"slug":"fairlands","name":"Fairlands"},
    {"slug":"worplesdon","name":"Worplesdon"},
    {"slug":"merrow","name":"Merrow"},
    {"slug":"burpham","name":"Burpham"},
    {"slug":"shalford","name":"Shalford"},
]

SERVICE_PAGES = [
    {"slug":"emergency-plumber-surrey","title":"Emergency Plumber Surrey","meta":"Emergency plumber in Surrey covering Guildford, Woking, Farnham, Godalming, Camberley and surrounding areas. Fast help for leaks, toilets, taps, pipework and urgent plumbing issues.","heading":"Emergency Plumber in Surrey","intro":"Need an emergency plumber in Surrey? Nigel Harvey Ltd provides responsive local plumbing help for urgent leaks, toilet problems, burst pipe issues, faulty taps, waste pipe problems and other domestic plumbing faults that need sorting quickly.","body":"This page helps customers searching for an emergency plumber in Surrey understand the type of urgent plumbing work covered, while also supporting nearby searches such as emergency plumber Guildford, emergency plumber Woking and similar local terms across Surrey.","keywords":"emergency plumber Surrey, emergency plumber Guildford, emergency plumber Woking"},
    {"slug":"general-plumbing-surrey","title":"General Plumbing Surrey","meta":"General plumbing services in Surrey from Nigel Harvey Ltd. Taps, toilets, sinks, wastes, leaks, outside taps and domestic plumbing repairs across Guildford and surrounding areas.","heading":"General Plumbing in Surrey","intro":"Nigel Harvey Ltd provides general plumbing services across Surrey for everyday domestic plumbing jobs. This includes tap repairs, toilet issues, sink plumbing, leaks, traps, wastes, outside taps and practical small plumbing jobs.","body":"This service page supports plumber Surrey, local plumber Surrey and general plumbing Surrey searches while giving customers a clear overview of the domestic plumbing work available.","keywords":"general plumbing Surrey, plumber Surrey, local plumber Surrey"},
    {"slug":"bathroom-plumbing-surrey","title":"Bathroom Plumbing Surrey","meta":"Bathroom plumbing in Surrey including bathroom refurbishments, sanitaryware connections, first fix and second fix plumbing. Covering Guildford, Woking and surrounding areas.","heading":"Bathroom Plumbing in Surrey","intro":"For bathroom plumbing in Surrey, Nigel Harvey Ltd helps with bathroom refurbishments, sanitaryware fitting, pipework changes, first fix plumbing, second fix plumbing and general bathroom plumbing works.","body":"This page is designed to strengthen bathroom plumbing Surrey related local search relevance across Guildford and surrounding towns while giving customers a clearer idea of the bathroom plumbing work available.","keywords":"bathroom plumbing Surrey, bathroom plumber Guildford, bathroom plumbing Woking"},
    {"slug":"heating-repairs-surrey","title":"Heating Repairs Surrey","meta":"Heating repairs in Surrey including radiators, valves, controls and plumbing-related heating work. Nigel Harvey Ltd covers Guildford and surrounding areas.","heading":"Heating Repairs in Surrey","intro":"Nigel Harvey Ltd provides plumbing-related heating repairs in Surrey, including radiators, valves, controls, pipework adjustments and practical heating jobs for domestic properties.","body":"The page targets heating repairs Surrey, radiator repairs Surrey and similar local plumbing and heating search terms for the business.","keywords":"heating repairs Surrey, radiator repairs Surrey, heating plumber Guildford"},
]

def get_company_logo_html(logo_value: str) -> str:
    return f'<img src="{logo_value}" alt="Nigel Harvey Ltd logo" class="logo" width="240" height="90">' if logo_value else ''

def render_location_page(location_name: str, logo_html: str, request: Request | None = None) -> str:
    related = ''.join(
        f'<a href="/plumber-{escape(item["slug"])}">Plumber in {escape(item["name"])}</a>'
        for item in LOCATION_PAGES if item['name'] != location_name
    )
    slug = location_name.lower()
    canonical = absolute_url(f"/plumber-{slug}", request)
    is_guildford = slug == "guildford"

    title = (
        "Plumber in Guildford | Local Plumbing Services | Nigel Harvey Plumbing"
        if is_guildford else
        f"Plumber in {location_name} | Reliable Local Plumbing Services | Nigel Harvey Ltd"
    )
    meta_description = (
        "Local plumber in Guildford for leaks, toilets, taps, radiators, bathroom plumbing and general plumbing repairs. Deal directly with Nigel Harvey Plumbing and request a clear quote online."
        if is_guildford else
        f"Looking for a plumber in {location_name}? Nigel Harvey Ltd provides leaks, bathroom plumbing and general plumbing services in {location_name} and surrounding Surrey areas."
    )

    breadcrumb_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": absolute_url("/", request)},
            {"@type": "ListItem", "position": 2, "name": f"Plumber in {location_name}", "item": canonical},
        ],
    }, ensure_ascii=False)
    local_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "Plumber",
        "name": "Nigel Harvey Plumbing",
        "url": canonical,
        "telephone": COMPANY_PHONE,
        "email": COMPANY_EMAIL,
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "125 Bushy Hill Drive",
            "addressLocality": "Guildford",
            "postalCode": "GU1 2UG",
            "addressCountry": "GB",
        },
        "areaServed": [location_name, "Guildford", "Surrey"],
        "serviceType": ["General plumbing", "Bathroom plumbing", "Leak repairs", "Toilet repairs", "Radiator and valve plumbing"],
        "description": f"Local plumber serving {location_name} and surrounding Surrey areas for domestic plumbing repairs and installations.",
    }, ensure_ascii=False)

    blue_location_css = r"""
:root{--navy:#0b2032;--blue:#1263a5;--pale:#f3f7fa;--gold:#e2b353;--text:#142b3e;--muted:#60717e;--border:#dfe7ec}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;font-family:Arial,Helvetica,sans-serif;color:var(--text);line-height:1.55;background:#fff}a{text-decoration:none;color:inherit}.wrap{width:min(1120px,92%);margin:auto}
.topbar{background:var(--navy);color:#fff;font-size:14px}.topbar .wrap{padding:9px 0;display:flex;justify-content:space-between;gap:20px}
.site-header{background:#fff;position:sticky;top:0;z-index:20;box-shadow:0 2px 18px #00000012}.site-nav{display:flex;align-items:center;justify-content:space-between;padding:15px 0}.brand{font-size:23px;font-weight:800;letter-spacing:-.5px}.brand small{display:block;color:var(--blue);font-size:11px;letter-spacing:2.5px}.navlinks{display:flex;align-items:center;gap:24px;font-weight:700;font-size:14px}.btn{display:inline-block;background:var(--blue);color:#fff;padding:13px 21px;border-radius:7px;font-weight:800}.btn.white{background:#fff;color:var(--navy)}
.guildford-hero{min-height:570px;display:grid;align-items:center;color:#fff;background:linear-gradient(90deg,#071827f2 0%,#071827d9 48%,#07182762 80%),url('https://images.unsplash.com/photo-1585704032915-c3400ca199e7?auto=format&fit=crop&w=1800&q=85') center/cover}.hero-copy{max-width:760px;padding:82px 0}.eyebrow{color:#f0c66e;text-transform:uppercase;letter-spacing:2px;font-size:13px;font-weight:800}.guildford-hero h1{font-size:clamp(43px,6vw,67px);line-height:1.02;letter-spacing:-2px;margin:14px 0 20px}.guildford-hero p{font-size:20px;max-width:680px;color:#e5edf3}.actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:28px}
.trust{box-shadow:0 10px 30px #0000000c}.trustgrid{display:grid;grid-template-columns:repeat(4,1fr);text-align:center}.trustgrid div{padding:23px 10px;border-right:1px solid #e3e9ed}.trustgrid div:last-child{border:0}.trustgrid strong{display:block;font-size:17px}.trustgrid span{color:var(--muted);font-size:13px}
section{padding:72px 0}.section-pale{background:var(--pale)}.section-dark{background:var(--navy);color:#fff}.intro{text-align:center;max-width:780px;margin:0 auto 38px}.intro.left{text-align:left;margin-left:0}.intro h2,.content-title{font-size:39px;line-height:1.12;letter-spacing:-1px;margin:0 0 14px}.intro p,.muted{color:var(--muted)}.section-dark .intro p{color:#cbd7df}
.service-links{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.service-links a,.area-links a{background:#fff;border:1px solid var(--border);border-radius:11px;padding:17px;font-weight:800;color:var(--navy);text-align:center;transition:.15s}.service-links a:hover,.area-links a:hover{border-color:var(--blue);color:var(--blue);transform:translateY(-1px)}
.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.card{background:#fff;border-radius:13px;padding:28px;box-shadow:0 8px 25px #0b20320c}.section-pale .card{border:1px solid #e6edf1}.card h3{margin:0 0 9px}.card p{font-size:14px;color:var(--muted);margin:0}.section-dark .card{color:var(--text)}
.review-section{background:#f5f8fa}.reviewbox{max-width:1040px;margin:auto;text-align:center;background:#fff;padding:46px;border-radius:15px;box-shadow:0 10px 30px #0b20320d}.google-brand{font-size:20px;font-weight:800;margin-bottom:8px}.google-rating{display:flex;justify-content:center;align-items:center;gap:12px;margin:8px 0 24px}.google-rating strong{font-size:24px;color:var(--text)}.google-rating .stars{font-size:22px}.google-review-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;text-align:left;margin:0 0 24px}.google-review-card{border:1px solid #e3e9ed;border-radius:12px;padding:20px;background:#fff}.review-author{display:flex;gap:11px;align-items:center}.review-author a{color:var(--text);text-decoration:none}.review-avatar{width:42px;height:42px;border-radius:50%;object-fit:cover}.review-avatar-fallback{display:flex;align-items:center;justify-content:center;background:#eef3f6;color:var(--blue);font-weight:900}.review-meta{font-size:12px;color:var(--muted);margin-top:3px}.mini-stars{color:#e3a923;letter-spacing:1px}.review-text{font-size:14px;line-height:1.55;color:#46545f;margin:15px 0}.review-source{font-size:12px;font-weight:800;color:var(--blue);text-decoration:none}.review-note{font-size:12px;color:var(--muted);margin:0 0 20px}
.area-links{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.faq-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.faq-grid .card{border:1px solid var(--border)}
.cta-blue{background:var(--blue);color:#fff}.cta-blue .wrap{display:flex;justify-content:space-between;align-items:center;gap:30px}.cta-blue h2{margin:0;font-size:37px}.cta-blue p{margin:7px 0 0;color:#e8f2f8}
footer{background:#071827;color:#c8d3dc;padding:38px 0;font-size:14px}.foot{display:flex;justify-content:space-between;gap:30px}.foot strong{color:#fff}.mobile-call{display:none}
@media(max-width:800px){.navlinks a:not(.btn){display:none}.topbar .wrap{justify-content:center}.topbar span:last-child{display:none}.guildford-hero{min-height:540px;background:linear-gradient(#071827c9,#071827e6),url('https://images.unsplash.com/photo-1585704032915-c3400ca199e7?auto=format&fit=crop&w=1000&q=80') center/cover}.hero-copy{padding:62px 0}.guildford-hero h1{font-size:44px}.guildford-hero p{font-size:18px}.trustgrid{grid-template-columns:1fr 1fr}.trustgrid div:nth-child(2){border-right:0}.cards,.google-review-grid,.faq-grid{grid-template-columns:1fr}.service-links,.area-links{grid-template-columns:1fr 1fr}.cta-blue .wrap,.foot{display:block}.cta-blue .btn{margin-top:20px}.mobile-call{display:block;position:fixed;bottom:14px;left:4%;right:4%;z-index:25;background:var(--blue);color:#fff;padding:15px;border-radius:10px;text-align:center;font-weight:900;box-shadow:0 5px 22px #0005}section{padding:56px 0}.intro h2,.content-title{font-size:33px}}
@media(max-width:520px){.service-links,.area-links{grid-template-columns:1fr}}
"""

    if is_guildford:
        faq_items = [
            ("What plumbing work do you cover in Guildford?", "Nigel Harvey Plumbing covers domestic plumbing including leaks, taps, toilets, sinks, wastes, radiators and valves, bathroom plumbing, pipework changes and other general plumbing repairs."),
            ("Can I request a plumbing quote online?", "Yes. Send the job details through the online quote form, including photos where useful, and Nigel can review what is required before arranging the next step."),
            ("Do you cover areas around Guildford as well?", "Yes. The business is based in Guildford and also covers nearby Surrey areas including Godalming, Woking, Farnham, Fairlands, Worplesdon, Merrow, Burpham and Shalford."),
        ]
        faq_schema = json.dumps({
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faq_items
            ],
        }, ensure_ascii=False)
        faq_html = ''.join(
            f'<div class="card faq"><h3>{escape(q)}</h3><p>{escape(a)}</p></div>'
            for q, a in faq_items
        )
        local_service_links = ''.join([
            '<a href="/leak-repair-guildford">Leak Repair in Guildford</a>',
            '<a href="/toilet-repair-guildford">Toilet Repairs in Guildford</a>',
            '<a href="/bathroom-plumbing-guildford">Bathroom Plumbing in Guildford</a>',
            '<a href="/emergency-plumber-guildford">Urgent Plumbing in Guildford</a>',
        ])
        reviews_html = _google_reviews_html()
        guildford_css = r"""
:root{--navy:#0b2032;--blue:#1263a5;--pale:#f3f7fa;--gold:#e2b353;--text:#142b3e;--muted:#60717e;--border:#dfe7ec}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;font-family:Arial,Helvetica,sans-serif;color:var(--text);line-height:1.55;background:#fff}a{text-decoration:none;color:inherit}.wrap{width:min(1120px,92%);margin:auto}
.topbar{background:var(--navy);color:#fff;font-size:14px}.topbar .wrap{padding:9px 0;display:flex;justify-content:space-between;gap:20px}
.site-header{background:#fff;position:sticky;top:0;z-index:20;box-shadow:0 2px 18px #00000012}.site-nav{display:flex;align-items:center;justify-content:space-between;padding:15px 0}.brand{font-size:23px;font-weight:800;letter-spacing:-.5px}.brand small{display:block;color:var(--blue);font-size:11px;letter-spacing:2.5px}.navlinks{display:flex;align-items:center;gap:24px;font-weight:700;font-size:14px}.btn{display:inline-block;background:var(--blue);color:#fff;padding:13px 21px;border-radius:7px;font-weight:800}.btn.white{background:#fff;color:var(--navy)}
.guildford-hero{min-height:570px;display:grid;align-items:center;color:#fff;background:linear-gradient(90deg,#071827f2 0%,#071827d9 48%,#07182762 80%),url('https://images.unsplash.com/photo-1585704032915-c3400ca199e7?auto=format&fit=crop&w=1800&q=85') center/cover}.hero-copy{max-width:760px;padding:82px 0}.eyebrow{color:#f0c66e;text-transform:uppercase;letter-spacing:2px;font-size:13px;font-weight:800}.guildford-hero h1{font-size:clamp(43px,6vw,67px);line-height:1.02;letter-spacing:-2px;margin:14px 0 20px}.guildford-hero p{font-size:20px;max-width:680px;color:#e5edf3}.actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:28px}
.trust{box-shadow:0 10px 30px #0000000c}.trustgrid{display:grid;grid-template-columns:repeat(4,1fr);text-align:center}.trustgrid div{padding:23px 10px;border-right:1px solid #e3e9ed}.trustgrid div:last-child{border:0}.trustgrid strong{display:block;font-size:17px}.trustgrid span{color:var(--muted);font-size:13px}
section{padding:72px 0}.section-pale{background:var(--pale)}.section-dark{background:var(--navy);color:#fff}.intro{text-align:center;max-width:780px;margin:0 auto 38px}.intro.left{text-align:left;margin-left:0}.intro h2,.content-title{font-size:39px;line-height:1.12;letter-spacing:-1px;margin:0 0 14px}.intro p,.muted{color:var(--muted)}.section-dark .intro p{color:#cbd7df}
.service-links{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.service-links a,.area-links a{background:#fff;border:1px solid var(--border);border-radius:11px;padding:17px;font-weight:800;color:var(--navy);text-align:center;transition:.15s}.service-links a:hover,.area-links a:hover{border-color:var(--blue);color:var(--blue);transform:translateY(-1px)}
.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.card{background:#fff;border-radius:13px;padding:28px;box-shadow:0 8px 25px #0b20320c}.section-pale .card{border:1px solid #e6edf1}.card h3{margin:0 0 9px}.card p{font-size:14px;color:var(--muted);margin:0}.section-dark .card{color:var(--text)}
.review-section{background:#f5f8fa}.reviewbox{max-width:1040px;margin:auto;text-align:center;background:#fff;padding:46px;border-radius:15px;box-shadow:0 10px 30px #0b20320d}.google-brand{font-size:20px;font-weight:800;margin-bottom:8px}.google-rating{display:flex;justify-content:center;align-items:center;gap:12px;margin:8px 0 24px}.google-rating strong{font-size:24px;color:var(--text)}.google-rating .stars{font-size:22px}.google-review-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;text-align:left;margin:0 0 24px}.google-review-card{border:1px solid #e3e9ed;border-radius:12px;padding:20px;background:#fff}.review-author{display:flex;gap:11px;align-items:center}.review-author a{color:var(--text);text-decoration:none}.review-avatar{width:42px;height:42px;border-radius:50%;object-fit:cover}.review-avatar-fallback{display:flex;align-items:center;justify-content:center;background:#eef3f6;color:var(--blue);font-weight:900}.review-meta{font-size:12px;color:var(--muted);margin-top:3px}.mini-stars{color:#e3a923;letter-spacing:1px}.review-text{font-size:14px;line-height:1.55;color:#46545f;margin:15px 0}.review-source{font-size:12px;font-weight:800;color:var(--blue);text-decoration:none}.review-note{font-size:12px;color:var(--muted);margin:0 0 20px}
.area-links{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.faq-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.faq-grid .card{border:1px solid var(--border)}
.cta-blue{background:var(--blue);color:#fff}.cta-blue .wrap{display:flex;justify-content:space-between;align-items:center;gap:30px}.cta-blue h2{margin:0;font-size:37px}.cta-blue p{margin:7px 0 0;color:#e8f2f8}
footer{background:#071827;color:#c8d3dc;padding:38px 0;font-size:14px}.foot{display:flex;justify-content:space-between;gap:30px}.foot strong{color:#fff}.mobile-call{display:none}
@media(max-width:800px){.navlinks a:not(.btn){display:none}.topbar .wrap{justify-content:center}.topbar span:last-child{display:none}.guildford-hero{min-height:540px;background:linear-gradient(#071827c9,#071827e6),url('https://images.unsplash.com/photo-1585704032915-c3400ca199e7?auto=format&fit=crop&w=1000&q=80') center/cover}.hero-copy{padding:62px 0}.guildford-hero h1{font-size:44px}.guildford-hero p{font-size:18px}.trustgrid{grid-template-columns:1fr 1fr}.trustgrid div:nth-child(2){border-right:0}.cards,.google-review-grid,.faq-grid{grid-template-columns:1fr}.service-links,.area-links{grid-template-columns:1fr 1fr}.cta-blue .wrap,.foot{display:block}.cta-blue .btn{margin-top:20px}.mobile-call{display:block;position:fixed;bottom:14px;left:4%;right:4%;z-index:25;background:var(--blue);color:#fff;padding:15px;border-radius:10px;text-align:center;font-weight:900;box-shadow:0 5px 22px #0005}section{padding:56px 0}.intro h2,.content-title{font-size:33px}}
@media(max-width:520px){.service-links,.area-links{grid-template-columns:1fr}}
"""
        return f"""<!doctype html>
<html lang="en-GB"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title><meta name="description" content="{escape(meta_description)}"><meta name="robots" content="index,follow,max-image-preview:large"><link rel="canonical" href="{escape(canonical)}">
<meta property="og:type" content="website"><meta property="og:title" content="{escape(title)}"><meta property="og:description" content="{escape(meta_description)}"><meta property="og:url" content="{escape(canonical)}">
<script type="application/ld+json">{breadcrumb_schema}</script><script type="application/ld+json">{local_schema}</script><script type="application/ld+json">{faq_schema}</script><style>{guildford_css}</style></head><body>
<div class="topbar"><div class="wrap"><span>Local plumber serving Guildford &amp; Surrey</span><span>Call Nigel: {escape(COMPANY_PHONE)} &nbsp; · &nbsp; {escape(COMPANY_EMAIL)}</span></div></div>
<header class="site-header"><div class="wrap site-nav"><div class="brand">Nigel Harvey <small>PLUMBING</small></div><div class="navlinks"><a href="#services">Services</a><a href="#about">About</a><a href="#reviews">Reviews</a><a href="#areas">Areas</a><a class="btn" href="/request-quote">Get a Quote</a></div></div></header>
<section class="guildford-hero"><div class="wrap"><div class="hero-copy"><div class="eyebrow">Nigel Harvey Plumbing · Guildford</div><h1>Plumber in Guildford</h1><p>Local domestic plumbing for leaks, taps, toilets, bathrooms, showers, radiators and pipework. From first enquiry to finished job, you deal directly with me, Nigel.</p><div class="actions"><a class="btn" href="/request-quote">Get a Quote</a><a class="btn white" href="tel:{escape(COMPANY_PHONE_TEL)}">Call {escape(COMPANY_PHONE)}</a></div></div></div></section>
<div class="trust"><div class="wrap trustgrid"><div><strong>Local &amp; independent</strong><span>Based in Guildford</span></div><div><strong>Clear communication</strong><span>Deal directly with Nigel</span></div><div><strong>Clear quotes</strong><span>Work &amp; charges explained</span></div><div><strong>Surrey coverage</strong><span>Guildford &amp; nearby areas</span></div></div></div>
<section id="services"><div class="wrap"><div class="intro"><h2>Plumbing services in Guildford</h2><p>Whether you have a leaking fitting, a toilet that is not working properly, a radiator or valve problem, or planned bathroom plumbing, send the details directly to Nigel. Photos and a short description can help establish what may be required before the visit.</p></div><div class="service-links">{local_service_links}</div></div></section>
<section class="section-pale"><div class="wrap"><div class="intro"><h2>Domestic plumbing work I can help with</h2><p>Practical plumbing repairs and planned work for homes and landlords across Guildford.</p></div><div class="cards"><div class="card"><h3>Leaks, taps &amp; toilets</h3><p>Repairs to leaking pipework and fittings, taps, toilet mechanisms, wastes, traps and other everyday plumbing problems.</p></div><div class="card"><h3>Bathrooms &amp; showers</h3><p>Bathroom plumbing, sanitaryware connections, shower pipework, first and second fix work and practical plumbing alterations.</p></div><div class="card"><h3>Radiators &amp; pipework</h3><p>Radiators, TRVs and valves, towel radiators, pipework alterations and plumbing-related heating work.</p></div></div></div></section>
<section class="section-dark" id="about"><div class="wrap"><div class="intro"><h2>A local Guildford plumber you deal with directly</h2><p>Nigel Harvey Plumbing is based in Guildford. When you enquire, you deal directly with Nigel rather than a call centre or salesperson. The aim is straightforward communication, a clear quotation and a practical plan for getting the work completed.</p></div><div class="cards"><div class="card"><h3>Direct contact</h3><p>Speak directly with the person who will be carrying out the plumbing work.</p></div><div class="card"><h3>Clear quotations</h3><p>Work and relevant charges can be set out before you decide whether to proceed.</p></div><div class="card"><h3>Local coverage</h3><p>Based in Guildford and covering surrounding towns and villages across Surrey.</p></div></div></div></section>
<section class="review-section" id="reviews"><div class="wrap"><div class="intro"><h2>Customer reviews</h2><p>Recent independent Google feedback from plumbing customers.</p></div><div class="reviewbox">{reviews_html}</div></div></section>
<section id="areas"><div class="wrap"><div class="intro"><h2>Areas near Guildford</h2><p>As well as Guildford itself, plumbing work is available across nearby Surrey areas. Use the local pages below for more information.</p></div><div class="area-links">{related}</div></div></section>
<section class="section-pale"><div class="wrap"><div class="intro"><h2>Frequently asked questions</h2></div><div class="faq-grid">{faq_html}</div></div></section>
<section class="cta-blue"><div class="wrap"><div><h2>Need a plumber in Guildford?</h2><p>Send your postcode, a short description and photos if useful, or call Nigel directly.</p></div><div class="actions"><a class="btn white" href="tel:{escape(COMPANY_PHONE_TEL)}">Call Nigel</a><a class="btn white" href="/request-quote">Get a Quote</a></div></div></section>
<footer><div class="wrap foot"><div><strong>Nigel Harvey Plumbing</strong><br>Nigel Harvey Ltd · Guildford, Surrey</div><div>{escape(COMPANY_PHONE)}<br>{escape(COMPANY_EMAIL)}</div></div></footer><a class="mobile-call" href="tel:{escape(COMPANY_PHONE_TEL)}">Call Nigel · {escape(COMPANY_PHONE)}</a></body></html>"""

    faq_items = [
        (f"What plumbing work do you cover in {location_name}?", f"I cover domestic plumbing in {location_name}, including leaks, taps, toilets, sinks, wastes, radiators and valves, bathroom plumbing, pipework changes and other general plumbing repairs."),
        ("Can I request a plumbing quote online?", "Yes. Send me the job details through the online quote form, including photos where useful, and I can review what is required before arranging the next step."),
        (f"Do you cover areas around {location_name} as well?", f"Yes. I am based in Guildford and cover {location_name} as well as other nearby Surrey towns and villages."),
    ]
    faq_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faq_items
        ],
    }, ensure_ascii=False)
    faq_html = ''.join(
        f'<div class="card faq"><h3>{escape(q)}</h3><p>{escape(a)}</p></div>'
        for q, a in faq_items
    )
    local_service_links = ''.join([
        f'<a href="/leak-repair-{escape(slug)}">Leak Repair in {escape(location_name)}</a>',
        f'<a href="/toilet-repair-{escape(slug)}">Toilet Repairs in {escape(location_name)}</a>',
        f'<a href="/bathroom-plumbing-{escape(slug)}">Bathroom Plumbing in {escape(location_name)}</a>',
        f'<a href="/emergency-plumber-{escape(slug)}">Urgent Plumbing in {escape(location_name)}</a>',
    ])
    reviews_html = _google_reviews_html()
    return f"""<!doctype html>
<html lang="en-GB"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title><meta name="description" content="{escape(meta_description)}"><meta name="robots" content="index,follow,max-image-preview:large"><link rel="canonical" href="{escape(canonical)}">
<meta property="og:type" content="website"><meta property="og:title" content="{escape(title)}"><meta property="og:description" content="{escape(meta_description)}"><meta property="og:url" content="{escape(canonical)}">
<script type="application/ld+json">{breadcrumb_schema}</script><script type="application/ld+json">{local_schema}</script><script type="application/ld+json">{faq_schema}</script><style>{blue_location_css}</style></head><body>
<div class="topbar"><div class="wrap"><span>Local plumber serving {escape(location_name)} &amp; Surrey</span><span>Call Nigel: {escape(COMPANY_PHONE)} &nbsp; · &nbsp; {escape(COMPANY_EMAIL)}</span></div></div>
<header class="site-header"><div class="wrap site-nav"><a class="brand" href="/">Nigel Harvey <small>PLUMBING</small></a><div class="navlinks"><a href="#services">Services</a><a href="#about">About</a><a href="#reviews">Reviews</a><a href="#areas">Areas</a><a class="btn" href="/request-quote">Get a Quote</a></div></div></header>
<section class="guildford-hero"><div class="wrap"><div class="hero-copy"><div class="eyebrow">Nigel Harvey Plumbing · {escape(location_name)}</div><h1>Plumber in {escape(location_name)}</h1><p>Reliable domestic plumbing for leaks, taps, toilets, bathrooms, showers, radiators and pipework in {escape(location_name)} and surrounding Surrey areas. From first enquiry to finished job, you deal directly with me, Nigel.</p><div class="actions"><a class="btn" href="/request-quote">Get a Quote</a><a class="btn white" href="tel:{escape(COMPANY_PHONE_TEL)}">Call {escape(COMPANY_PHONE)}</a></div></div></div></section>
<div class="trust"><div class="wrap trustgrid"><div><strong>Local &amp; independent</strong><span>Based in Guildford</span></div><div><strong>Clear communication</strong><span>Deal directly with me</span></div><div><strong>Clear quotes</strong><span>Work &amp; charges explained</span></div><div><strong>Surrey coverage</strong><span>{escape(location_name)} &amp; nearby areas</span></div></div></div>
<section id="services"><div class="wrap"><div class="intro"><h2>Plumbing services in {escape(location_name)}</h2><p>Whether you have a leaking fitting, a toilet that is not working properly, a radiator or valve problem, or planned bathroom plumbing, send the details directly to me. Photos and a short description can help me establish what may be required before the visit.</p></div><div class="service-links">{local_service_links}</div></div></section>
<section class="section-pale"><div class="wrap"><div class="intro"><h2>Domestic plumbing work I can help with</h2><p>I provide practical domestic plumbing services across {escape(location_name)} and nearby Surrey areas.</p></div><div class="cards"><div class="card"><h3>Leaks, taps &amp; toilets</h3><p>Repairs to leaking pipework and fittings, taps, toilet mechanisms, wastes, traps and other everyday plumbing problems.</p></div><div class="card"><h3>Bathrooms &amp; showers</h3><p>Bathroom plumbing, sanitaryware connections, shower pipework, first and second fix work and practical plumbing alterations.</p></div><div class="card"><h3>Radiators &amp; pipework</h3><p>Radiators, TRVs and valves, towel radiators, pipework alterations and plumbing-related heating work.</p></div></div></div></section>
<section id="about"><div class="wrap"><div class="intro left"><h2>A local plumber you deal with directly</h2><p>When you contact Nigel Harvey Plumbing, you deal directly with me, Nigel — not a call centre or salesperson. I am based in Guildford and cover {escape(location_name)} and surrounding Surrey areas.</p></div><div class="cards"><div class="card"><h3>Direct contact</h3><p>Speak directly with me, the person carrying out the plumbing work.</p></div><div class="card"><h3>Clear quotations</h3><p>I set out the work and relevant charges before you decide whether to proceed.</p></div><div class="card"><h3>Local coverage</h3><p>Based in Guildford and covering {escape(location_name)} and surrounding Surrey towns and villages.</p></div></div></div></section>
<section class="review-section" id="reviews"><div class="wrap"><div class="reviewbox">{reviews_html}</div></div></section>
<section id="areas"><div class="wrap"><div class="intro"><h2>Areas I cover near {escape(location_name)}</h2><p>I also cover nearby areas across Surrey. Use the links below for local service information.</p></div><div class="area-links">{related}</div></div></section>
<section class="section-pale"><div class="wrap"><div class="intro"><h2>Frequently asked questions</h2></div><div class="faq-grid">{faq_html}</div></div></section>
<section class="cta-blue"><div class="wrap"><div><h2>Need a plumber in {escape(location_name)}?</h2><p>Send your postcode, a short description and photos if useful, or call me directly.</p></div><div class="actions"><a class="btn white" href="tel:{escape(COMPANY_PHONE_TEL)}">Call Nigel</a><a class="btn white" href="/request-quote">Get a Quote</a></div></div></section>
<footer><div class="wrap foot"><div><strong>Nigel Harvey Plumbing</strong><br>Nigel Harvey Ltd · Guildford, Surrey</div><div>{escape(COMPANY_PHONE)}<br>{escape(COMPANY_EMAIL)}</div></div></footer><a class="mobile-call" href="tel:{escape(COMPANY_PHONE_TEL)}">Call Nigel · {escape(COMPANY_PHONE)}</a></body></html>"""

def render_service_page(service: dict, logo_html: str, request: Request | None = None) -> str:
    service_links = ''.join(f'<a href="/{escape(item["slug"])}">{escape(item["title"])}</a>' for item in SERVICE_PAGES if item['slug'] != service['slug'])
    location_links = ''.join(f'<a href="/plumber-{escape(item["slug"])}">Plumber in {escape(item["name"])}</a>' for item in LOCATION_PAGES)
    canonical = absolute_url(f"/{service['slug']}", request)
    breadcrumb_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": absolute_url("/", request)},
            {"@type": "ListItem", "position": 2, "name": service["title"], "item": canonical},
        ],
    }, ensure_ascii=False)
    service_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "Service",
        "name": service["title"],
        "serviceType": service["heading"],
        "provider": {"@type": "Plumber", "name": COMPANY_NAME, "telephone": COMPANY_PHONE},
        "areaServed": [item["name"] for item in LOCATION_PAGES] + ["Surrey"],
        "url": canonical,
        "description": service["meta"],
    }, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="en-GB"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{escape(service['title'])} | Nigel Harvey Ltd</title><meta name="description" content="{escape(service['meta'])}"><meta name="keywords" content="{escape(service['keywords'])}"><link rel="canonical" href="{escape(canonical)}"><script type="application/ld+json">{breadcrumb_schema}</script><script type="application/ld+json">{service_schema}</script><style>{SEO_CSS}</style></head>
<body><div class="top"><div class="wrap nav"><div class="brand">Nigel Harvey Ltd<small>{escape(service['title'])}</small></div><div class="nav-actions"><a class="btn btn-light" href="tel:{escape(COMPANY_PHONE_TEL)}">Call Now</a><a class="btn btn-primary" href="/request-quote">Get a Fast Quote</a><a class="btn btn-light" href="/">Home</a></div></div></div>
<main>
<div class="wrap hero"><div class="hero-card"><div>{logo_html}</div><div class="eyebrow">Surrey plumbing service</div><h1>{escape(service['heading'])}</h1><p class="lead">{escape(service['intro'])}</p><div class="nav-actions"><a class="btn btn-green" href="tel:{escape(COMPANY_PHONE_TEL)}">Call {escape(COMPANY_PHONE)}</a><a class="btn btn-primary" href="/request-quote">Get a Fast Quote</a></div></div></div>
<div class="wrap section"><h2>Why customers choose this service</h2><p>{escape(service['body'])}</p><div class="grid3"><div class="card item"><h3>Local Surrey coverage</h3><p>We cover Guildford, Woking, Farnham, Godalming, Camberley, Aldershot, Leatherhead, Epsom and surrounding Surrey areas.</p></div><div class="card item"><h3>Clear pricing and communication</h3><p>Use the quote form to send job details and get a practical response without the runaround.</p></div><div class="card item"><h3>Domestic plumbing focus</h3><p>Our service pages are written for real customer searches and practical domestic plumbing jobs.</p></div></div></div>
<div class="wrap section"><h2>Areas covered for {escape(service['heading']).lower()}</h2><p>We also cover nearby towns for customers searching for this service in Surrey.</p><div class="pill-links">{location_links}</div></div>
<div class="wrap section"><h2>Related plumbing services</h2><div class="pill-links">{service_links}</div></div>
<div class="wrap section"><h2>Frequently asked questions</h2><div class="faq-grid"><div class="card faq"><h3>Do you cover this service across Surrey?</h3><p>Yes. Nigel Harvey Ltd covers Guildford, Woking, Farnham and nearby Surrey towns for this service.</p></div><div class="card faq"><h3>Can I request a quote online?</h3><p>Yes. Send your details through the online quote form for a fast response.</p></div><div class="card faq"><h3>Do you also cover nearby plumbing work?</h3><p>Yes. We also handle related plumbing jobs, which is why the site links service pages and area pages together.</p></div></div></div>
<div class="wrap"><div class="hero-card cta"><div><h2 style="margin:0 0 8px">Need help with {escape(service['heading']).lower()}?</h2><div style="color:var(--muted)">Call now or send your job details online for a fast response.</div></div><div class="nav-actions"><a class="btn btn-green" href="tel:{escape(COMPANY_PHONE_TEL)}">Call Now</a><a class="btn btn-primary" href="/request-quote">Get a Fast Quote</a></div></div></div>
<div class="footer"><div class="wrap footer-inner"><div><strong>Nigel Harvey Ltd</strong><br>Plumbing services in Surrey</div><div>{escape(COMPANY_PHONE)}<br>{escape(COMPANY_EMAIL)}<br>Guildford, Surrey and surrounding areas</div></div></div><a href="tel:{escape(COMPANY_PHONE_TEL)}" class="sticky-call">📞 Call Now: {escape(COMPANY_PHONE)}</a></body></html>"""




# Full-scale local service pages for SEO.
# These create pages like:
# /emergency-plumber-guildford
# /toilet-repair-guildford
# /leak-repair-guildford
# /bathroom-plumbing-guildford
# /blocked-drains-guildford
LOCAL_SERVICE_PAGES = [
    {
        "slug": "emergency-plumber",
        "title": "Emergency Plumber",
        "heading": "Emergency Plumber in {area}",
        "intro": "Need an emergency plumber in {area}? Nigel Harvey Ltd provides fast local help for urgent leaks, burst pipes, overflowing toilets, faulty taps and other plumbing problems that need sorting quickly.",
        "service": "emergency plumbing",
        "keywords": "emergency plumber {area}, urgent plumber {area}, plumber {area}",
        "problems": ["Burst pipes", "Leaks", "Overflowing toilets", "Faulty taps", "Urgent pipework repairs"],
    },
    {
        "slug": "toilet-repair",
        "title": "Toilet Repair",
        "heading": "Toilet Repairs in {area}",
        "intro": "We provide toilet repairs in {area}, including leaks, flushing problems, running toilets, blockages, faulty cisterns and replacement parts.",
        "service": "toilet repair",
        "keywords": "toilet repair {area}, toilet plumber {area}, plumber {area}",
        "problems": ["Toilets not flushing", "Running toilets", "Leaking toilets", "Blocked toilets", "Faulty cistern parts"],
    },
    {
        "slug": "leak-repair",
        "title": "Leak Repair",
        "heading": "Leak Repairs in {area}",
        "intro": "Nigel Harvey Ltd helps with leak repairs in {area}, from visible pipe leaks and dripping fittings to hidden plumbing leaks that need careful investigation.",
        "service": "leak repair",
        "keywords": "leak repair {area}, leaking pipe {area}, plumber {area}",
        "problems": ["Leaking pipes", "Dripping fittings", "Water damage concerns", "Hidden leaks", "Bathroom and kitchen leaks"],
    },
    {
        "slug": "bathroom-plumbing",
        "title": "Bathroom Plumbing",
        "heading": "Bathroom Plumbing in {area}",
        "intro": "We provide bathroom plumbing in {area}, including pipework changes, toilet fitting, basin plumbing, shower connections and bathroom repair work.",
        "service": "bathroom plumbing",
        "keywords": "bathroom plumbing {area}, bathroom plumber {area}, plumber {area}",
        "problems": ["Toilet fitting", "Basin plumbing", "Shower pipework", "Bath connections", "Bathroom leaks"],
    },
    {
        "slug": "blocked-drains",
        "title": "Blocked Drains",
        "heading": "Blocked Drains and Waste Pipes in {area}",
        "intro": "We help with blocked drains and waste pipe issues in {area}, including slow-draining sinks, blocked wastes, toilet blockages and drainage-related plumbing problems.",
        "service": "blocked drains and waste pipes",
        "keywords": "blocked drains {area}, blocked sink {area}, plumber {area}",
        "problems": ["Blocked sinks", "Slow drains", "Blocked wastes", "Toilet blockages", "Kitchen and bathroom drainage issues"],
    },
]

def render_local_service_location_page(service: dict, location: dict, logo_html: str, request: Request | None = None) -> str:
    area = location["name"]
    area_slug = location["slug"]
    service_slug = service["slug"]
    title = service["title"]
    heading = service["heading"].format(area=area)
    intro = service["intro"].format(area=area)
    keywords = service["keywords"].format(area=area)
    canonical = absolute_url(f"/{service_slug}-{area_slug}", request)
    problem_items = "".join(f"<li>{escape(item)}</li>" for item in service["problems"])
    related_locations = "".join(
        f'<a href="/{escape(service_slug)}-{escape(item["slug"])}">{escape(title)} in {escape(item["name"])}</a>'
        for item in LOCATION_PAGES if item["slug"] != area_slug
    )
    related_services = "".join(
        f'<a href="/{escape(item["slug"])}-{escape(area_slug)}">{escape(item["title"])} in {escape(area)}</a>'
        for item in LOCAL_SERVICE_PAGES if item["slug"] != service_slug
    )
    breadcrumb_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": absolute_url("/", request)},
            {"@type": "ListItem", "position": 2, "name": f"{title} in {area}", "item": canonical},
        ],
    }, ensure_ascii=False)
    service_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "Service",
        "name": f"{title} in {area}",
        "provider": {
            "@type": "Plumber",
            "name": COMPANY_NAME,
            "telephone": COMPANY_PHONE,
            "email": COMPANY_EMAIL,
        },
        "areaServed": [area, "Surrey"],
        "serviceType": service["service"],
        "url": canonical,
        "description": intro,
    }, ensure_ascii=False)

    return f"""<!doctype html>
<html lang="en-GB"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} in {escape(area)} | Nigel Harvey Ltd</title>
<meta name="description" content="{escape(intro)} Call Nigel Harvey Ltd on {escape(COMPANY_PHONE)} for reliable local plumbing help.">
<meta name="keywords" content="{escape(keywords)}">
<link rel="canonical" href="{escape(canonical)}">
<script type="application/ld+json">{breadcrumb_schema}</script>
<script type="application/ld+json">{service_schema}</script>
<style>{SEO_CSS}</style></head>
<body>
<div class="top"><div class="wrap nav"><div class="brand">Nigel Harvey Ltd<small>{escape(title)} in {escape(area)}</small></div><div class="nav-actions"><a class="btn btn-light" href="tel:{escape(COMPANY_PHONE_TEL)}">Call Now</a><a class="btn btn-primary" href="/request-quote">Get a Fast Quote</a><a class="btn btn-light" href="/">Home</a></div></div></div>
<main>
<div class="wrap hero"><div class="hero-card"><div>{logo_html}</div><div class="eyebrow">Local plumbing help in {escape(area)}</div><h1>{escape(heading)}</h1><p class="lead">{escape(intro)}</p><div class="nav-actions"><a class="btn btn-green" href="tel:{escape(COMPANY_PHONE_TEL)}">Call Now: {escape(COMPANY_PHONE)}</a><a class="btn btn-primary" href="/request-quote">Request a Quote</a></div></div></div>

<div class="wrap section"><h2>{escape(title)} Services in {escape(area)}</h2><p>If you are looking for {escape(service["service"])} in {escape(area)}, we provide practical, reliable help for local homes, landlords and small businesses.</p><ul class="list">{problem_items}</ul></div>

<div class="wrap section"><div class="grid3">
<div class="card item"><h3>Fast Local Response</h3><p>We cover {escape(area)} and nearby Surrey areas for urgent and planned plumbing work.</p></div>
<div class="card item"><h3>Clear Communication</h3><p>You get straightforward advice and a clear explanation of the work needed.</p></div>
<div class="card item"><h3>Trusted Local Plumber</h3><p>Nigel Harvey Ltd provides dependable domestic plumbing services across Guildford and Surrey.</p></div>
</div></div>

<div class="wrap section"><h2>Other Plumbing Services in {escape(area)}</h2><div class="pill-links">{related_services}</div></div>
<div class="wrap section"><h2>Nearby Areas We Cover</h2><div class="pill-links">{related_locations}</div></div>

<div class="wrap cta card"><div><h2>Need {escape(title.lower())} in {escape(area)}?</h2><p>Call now or request a fast quote online.</p></div><div class="nav-actions"><a class="btn btn-green" href="tel:{escape(COMPANY_PHONE_TEL)}">Call Now: {escape(COMPANY_PHONE)}</a><a class="btn btn-primary" href="/request-quote">Get a Fast Quote</a></div></div>
</main>
<div class="footer"><div class="wrap footer-inner"><div><strong>Nigel Harvey Ltd</strong><br>Plumbing services in Surrey</div><div>{escape(COMPANY_PHONE)}<br>{escape(COMPANY_EMAIL)}<br>{escape(area)}, Surrey and surrounding areas</div></div></div>
<a href="tel:{escape(COMPANY_PHONE_TEL)}" class="sticky-call">📞 Call Now: {escape(COMPANY_PHONE)}</a>
</body></html>"""


LEAD_FORM_HTML = r'''<!doctype html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Request a Quote - Nigel Harvey Ltd</title>
<style>
body{font-family:Arial,sans-serif;background:#f5f5f5;margin:0;color:#111;padding:14px;}
.wrap{max-width:760px;margin:0 auto;}
.card{background:#fff;border-radius:18px;padding:22px;box-shadow:0 8px 24px rgba(0,0,0,.08);margin-bottom:14px;}
h1{margin:0 0 8px 0;font-size:30px;}
.sub{color:#666;margin-bottom:18px;}
label{display:block;font-weight:700;margin:14px 0 6px;}
input,textarea,select{width:100%;box-sizing:border-box;padding:14px;border:1px solid #d1d5db;border-radius:12px;font-size:16px;background:#fff;}
textarea{min-height:120px;resize:vertical;}
button{width:100%;padding:15px;border:none;border-radius:12px;background:#111;color:#fff;font-size:17px;font-weight:700;cursor:pointer;margin-top:18px;}
.small{font-size:14px;color:#666;}
.ok{display:none;margin-top:14px;background:#edf9ed;border:1px solid #b7ddb7;color:#14532d;padding:12px;border-radius:12px;}
.err{display:none;margin-top:14px;background:#fff4f4;border:1px solid #e8bcbc;color:#9b1c1c;padding:12px;border-radius:12px;}
.logo{max-height:76px;max-width:220px;display:block;margin:0 0 12px auto;}
.quick-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;}
.quick-btn{padding:12px;border-radius:12px;border:1px solid #d1d5db;background:#fafafa;text-align:center;font-weight:700;cursor:pointer;}
@media (max-width:640px){.quick-grid{grid-template-columns:1fr;}}
</style>
</head>
<body>
<main>
<div class="wrap">
  <div class="card">
    <div style="text-align:right;">__COMPANY_LOGO_HTML__</div>
    <h1>Request a Quote</h1>
    <div class="sub">Send Nigel Harvey Ltd your job details and get a callback or quote.</div>
    <div class="small" style="margin-bottom:12px;">Phone: __COMPANY_PHONE__ · Email: __COMPANY_EMAIL__</div>
    <div class="quick-grid" style="margin-bottom:10px;">
      <div class="quick-btn" onclick="setJobType('small','Tap / toilet / leak / waste repair')">Small plumbing job</div>
      <div class="quick-btn" onclick="setJobType('bathroom','Bathroom install / refurb')">Bathroom</div>
      <div class="quick-btn" onclick="setJobType('heating','Heating / radiator / system work')">Heating</div>
      <div class="quick-btn" onclick="setJobType('small','Outside tap / general plumbing')">Outside tap / general</div>
    </div>
    <label>Name</label><input id="lead_name" placeholder="Your name">
    <label>Phone</label><input id="lead_phone" placeholder="Your phone">
    <label>Email (optional)</label><input id="lead_email" placeholder="Your email">
    <label>Address</label><textarea id="lead_address" placeholder="Job address"></textarea>
    <label>Job type</label>
    <select id="lead_job_type">
      <option value="small">Small plumbing job</option>
      <option value="bathroom">Bathroom</option>
      <option value="heating">Heating</option>
    </select>
    <label>Describe the job</label><textarea id="lead_description" placeholder="Tell us what needs doing"></textarea>
    <button type="button" onclick="submitLead()">Send quote request</button>
    <div id="lead_ok" class="ok">Thanks — your quote request has been sent. Nigel Harvey Ltd will get back to you shortly.</div>
    <div id="lead_err" class="err"></div>
  </div>
</div>
</main>
<script>

if (typeof updateQuantityLearningNotes !== "function") {
  function updateQuantityLearningNotes() {
    // Safe fallback. Quantity learning display should never break edit/delete actions.
  }
}
window.addEventListener("error", function(event) {
  if (event && event.message && event.message.includes("updateQuantityLearningNotes")) {
    event.preventDefault();
    return false;
  }
});

function setJobType(type, text){document.getElementById('lead_job_type').value=type; if(!document.getElementById('lead_description').value.trim()){document.getElementById('lead_description').value=text;}}
async function submitLead(){
  const err=document.getElementById('lead_err'); const ok=document.getElementById('lead_ok');
  err.style.display='none'; ok.style.display='none';
  const payload={
    name:document.getElementById('lead_name').value,
    phone:document.getElementById('lead_phone').value,
    email:document.getElementById('lead_email').value,
    address:document.getElementById('lead_address').value,
    job_type:document.getElementById('lead_job_type').value,
    description:document.getElementById('lead_description').value,
    source:'website'
  };
  if(!payload.name.trim() || !payload.phone.trim() || !payload.description.trim()){
    err.textContent='Please add your name, phone number and a short job description.'; err.style.display='block'; return;
  }
  try{
    const res=await fetch('/api/leads',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const data=await res.json();
    if(!res.ok) throw new Error(data.detail || 'Could not send quote request.');
    ok.style.display='block';
    ['lead_name','lead_phone','lead_email','lead_address','lead_description'].forEach(id=>document.getElementById(id).value='');
    document.getElementById('lead_job_type').value='small';
  }catch(e){err.textContent=String(e); err.style.display='block';}
}
</script>
</body>
</html>'''


# Keep the original inline response: there are no additional browser requests or routes.
APP_UI_ROOT = Path(__file__).resolve().parent
HTML = (APP_UI_ROOT / "templates" / "app.html").read_text(encoding="utf-8")
HTML = HTML.replace("__APP_CSS__", (APP_UI_ROOT / "static" / "app.css").read_text(encoding="utf-8"))
HTML = HTML.replace("__APP_JS__", (APP_UI_ROOT / "static" / "app.js").read_text(encoding="utf-8"))


@app.get("/request-quote", response_class=HTMLResponse)
def request_quote_page(request: Request):
    logo_value = get_company_logo_value()
    logo_html = f'<img src="{logo_value}" alt="Nigel Harvey Ltd logo" class="logo" width="240" height="90">' if logo_value else ""
    html = LEAD_FORM_HTML.replace("__COMPANY_LOGO_HTML__", logo_html)
    html = html.replace("__COMPANY_PHONE__", COMPANY_PHONE)
    html = html.replace("__COMPANY_PHONE_TEL__", COMPANY_PHONE_TEL)
    html = html.replace("__COMPANY_EMAIL__", COMPANY_EMAIL)
    html = html.replace("__CANONICAL_HOME__", absolute_url("/", request))
    return HTMLResponse(content=html, media_type="text/html; charset=utf-8")


@app.get("/api/leads")
def api_leads():
    return load_leads()


@app.post("/api/leads")
def api_create_lead(data: LeadRequest):
    lead = save_lead(data)
    send_lead_notification_email(lead)
    return JSONResponse(content=lead)


@app.put("/api/leads/{lead_id}/status")
def api_update_lead_status(lead_id: int, data: LeadStatusRequest):
    lead = update_lead_status(lead_id, data.status)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@app.delete("/api/leads/{lead_id}")
def api_delete_lead(lead_id: int):
    if not delete_lead_by_id(lead_id):
        raise HTTPException(status_code=404, detail="Lead not found")
    return {"ok": True}


@app.get("/app", response_class=HTMLResponse)
def home_app():
    html = HTML.replace("__MATERIAL_LIBRARY__", json.dumps(get_material_search_library()))
    html = html.replace("__FAVOURITE_MATERIALS__", json.dumps(FAVOURITE_MATERIALS))
    html = html.replace("__JOB_TEMPLATES__", json.dumps(get_all_job_templates()))
    html = html.replace("__MATERIAL_ALIAS_RULES__", json.dumps(MATERIAL_ALIAS_RULES))
    logo_value = get_company_logo_value()
    logo_html = f'<img src="{logo_value}" alt="Logo">' if logo_value else ""
    html = html.replace("__COMPANY_LOGO_HTML__", logo_html)
    return HTMLResponse(content=html, media_type="text/html; charset=utf-8")



NEW_HOMEPAGE_PREVIEW_HTML = r"""
<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Plumber in Guildford & Surrey | Nigel Harvey Plumbing</title>
<meta name="description" content="Local plumber in Guildford serving Surrey for leaks, bathrooms, radiators, toilets, taps, pipework and general plumbing. Clear quotes and direct contact with Nigel Harvey Plumbing.">
<link rel="canonical" href="__PUBLIC_HOME_URL__">
<meta name="robots" content="index,follow,max-image-preview:large">
<meta property="og:title" content="Plumber in Guildford & Surrey | Nigel Harvey Plumbing">
<meta property="og:description" content="Local Guildford plumber serving Surrey for general plumbing, leaks, bathrooms, radiators, toilets, taps and pipework.">
<meta property="og:type" content="website">
<meta property="og:url" content="__PUBLIC_HOME_URL__">
<style>
:root{--navy:#0b2032;--blue:#1263a5;--pale:#f3f7fa;--gold:#e2b353;--text:#142b3e;--muted:#60717e}
*{box-sizing:border-box}body{margin:0;font-family:Arial,Helvetica,sans-serif;color:var(--text);line-height:1.55;background:#fff}a{text-decoration:none;color:inherit}
.wrap{width:min(1120px,92%);margin:auto}.top{background:var(--navy);color:#fff;font-size:14px}.top .wrap{padding:9px 0;display:flex;justify-content:space-between;gap:20px}
header{background:#fff;position:sticky;top:0;z-index:20;box-shadow:0 2px 18px #00000012}.nav{display:flex;align-items:center;justify-content:space-between;padding:15px 0}
.brand{font-size:23px;font-weight:800;letter-spacing:-.5px;display:flex;align-items:center}.brand small{display:block;color:var(--blue);font-size:11px;letter-spacing:2.5px}.navlinks{display:flex;align-items:center;gap:24px;font-weight:700;font-size:14px}
.btn{display:inline-block;background:var(--blue);color:#fff;padding:13px 21px;border-radius:7px;font-weight:800}.btn.white{background:#fff;color:var(--navy)}
.hero{min-height:620px;display:grid;align-items:center;color:#fff;background:linear-gradient(90deg,#071827f2 0%,#071827cf 45%,#0718274d 78%),url('https://images.unsplash.com/photo-1585704032915-c3400ca199e7?auto=format&fit=crop&w=1800&q=85') center/cover}
.hero-copy{max-width:700px;padding:90px 0}.eyebrow{color:#f0c66e;text-transform:uppercase;letter-spacing:2px;font-size:13px;font-weight:800}
h1{font-size:clamp(43px,6vw,69px);line-height:1.02;letter-spacing:-2px;margin:14px 0 20px}.hero p{font-size:20px;max-width:620px;color:#e5edf3}
.actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:28px}.trust{box-shadow:0 10px 30px #0000000c}.trustgrid{display:grid;grid-template-columns:repeat(4,1fr);text-align:center}
.trustgrid div{padding:23px 10px;border-right:1px solid #e3e9ed}.trustgrid div:last-child{border:0}.trustgrid strong{display:block;font-size:17px}.trustgrid span{color:var(--muted);font-size:13px}
section{padding:78px 0}.intro{text-align:center;max-width:760px;margin:0 auto 42px}h2{font-size:39px;line-height:1.12;letter-spacing:-1px;margin:0 0 14px}.intro p,p.muted{color:var(--muted)}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:18px}.card{background:var(--pale);border-radius:13px;padding:28px;min-height:260px;display:flex;flex-direction:column;box-shadow:0 8px 25px #0b20320c}.icon{font-size:29px;margin-bottom:auto}.card h3{margin:22px 0 8px}.card p{font-size:14px;color:var(--muted);margin:0}
.split{display:grid;grid-template-columns:1fr 1fr;gap:60px;align-items:center}.photo{min-height:480px;border-radius:15px;background:url('https://images.unsplash.com/photo-1607472586893-edb57bdc0e39?auto=format&fit=crop&w=1200&q=85') center/cover}
.ticks{display:grid;gap:12px;margin:25px 0}.tick:before{content:"✓";color:var(--blue);font-weight:900;margin-right:10px}.dark{background:var(--navy);color:#fff}.dark .intro p{color:#cbd7df}
.jobs{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.job{background:#fff;color:var(--text);padding:29px;border-radius:13px}.job small{color:var(--blue);font-weight:900;text-transform:uppercase}.job p{color:var(--muted)}
.review{background:#f5f8fa}.reviewbox{max-width:1040px;margin:auto;text-align:center;background:#fff;padding:46px;border-radius:15px;box-shadow:0 12px 35px #0000000c}.stars{color:#e3a923;font-size:25px;letter-spacing:3px}.google-brand img{height:24px;width:auto;margin-bottom:12px}.google-rating{display:flex;justify-content:center;align-items:center;gap:12px;flex-wrap:wrap;margin:10px 0 28px;color:var(--muted)}.google-rating strong{font-size:30px;color:var(--text)}.google-rating .stars{font-size:22px}.google-review-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;text-align:left;margin:0 0 24px}.google-review-card{border:1px solid #e3e9ed;border-radius:12px;padding:20px;background:#fff}.review-author{display:flex;gap:11px;align-items:center}.review-author a{color:var(--text);text-decoration:none}.review-avatar{width:42px;height:42px;border-radius:50%;object-fit:cover}.review-avatar-fallback{display:flex;align-items:center;justify-content:center;background:#eef3f6;color:var(--blue);font-weight:900}.review-meta{font-size:12px;color:var(--muted);margin-top:3px}.mini-stars{color:#e3a923;letter-spacing:1px}.review-text{font-size:14px;line-height:1.55;color:#46545f;margin:15px 0}.review-source{font-size:12px;font-weight:800;color:var(--blue);text-decoration:none}.review-note{font-size:12px;color:var(--muted);margin:0 0 20px}
.area{background:#fff}.area-intro{max-width:760px;margin-bottom:28px}.area-links{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:24px 0 34px}.area-link{display:block;border:1px solid #dfe7ec;border-radius:10px;padding:15px 17px;font-weight:800;color:var(--navy);background:#fff;transition:.15s}.area-link:hover{border-color:var(--blue);color:var(--blue);transform:translateY(-1px)}.area-note{background:var(--pale);border-radius:13px;padding:24px 26px;display:flex;align-items:center;justify-content:space-between;gap:24px}.area-note p{margin:5px 0 0}.cta{background:var(--blue);color:#fff}.cta .wrap{display:flex;justify-content:space-between;align-items:center;gap:30px}.cta h2{margin:0}.cta p{margin:7px 0 0;color:#e8f2f8}
footer{background:#071827;color:#c8d3dc;padding:38px 0;font-size:14px}.foot{display:flex;justify-content:space-between;gap:30px}.foot strong{color:#fff}.mobile-call{display:none}
.preview{position:fixed;right:15px;bottom:15px;background:#e2b353;color:#152536;padding:8px 12px;border-radius:6px;font-size:12px;font-weight:900;z-index:30}
@media(max-width:800px){.navlinks a:not(.btn){display:none}.top .wrap{justify-content:center}.top span:last-child{display:none}.hero{min-height:570px;background:linear-gradient(#071827c9,#071827e6),url('https://images.unsplash.com/photo-1585704032915-c3400ca199e7?auto=format&fit=crop&w=1000&q=80') center/cover}.hero-copy{padding:65px 0}h1{font-size:44px}.hero p{font-size:18px}.trustgrid{grid-template-columns:1fr 1fr}.trustgrid div:nth-child(2){border-right:0}.cards,.jobs,.split,.google-review-grid{grid-template-columns:1fr}.area-links{grid-template-columns:1fr 1fr}.area-note{display:block}.area-note .btn{margin-top:18px}.card{min-height:205px}.photo{min-height:350px;order:-1}.cta .wrap,.foot{display:block}.cta .btn{margin-top:20px}.mobile-call{display:block;position:fixed;bottom:14px;left:4%;right:4%;z-index:25;background:var(--blue);color:#fff;padding:15px;border-radius:10px;text-align:center;font-weight:900;box-shadow:0 5px 22px #0005}.preview{bottom:76px}section{padding:58px 0}h2{font-size:33px}}
</style></head>
<body>
<div class="top"><div class="wrap"><span>Local plumber serving Guildford & Surrey</span><span>Call Nigel: __COMPANY_PHONE__ &nbsp; · &nbsp; __COMPANY_EMAIL__</span></div></div>
<header><div class="wrap nav"><div class="brand"><span>Nigel Harvey <small>PLUMBING</small></span></div><div class="navlinks"><a href="#services">Services</a><a href="#about">About</a><a href="#work">How It Works</a><a href="#areas">Areas</a><a class="btn" href="/request-quote">Get a Quote</a></div></div></header>
<section class="hero"><div class="wrap"><div class="hero-copy"><div class="eyebrow">Nigel Harvey Plumbing · Guildford</div><h1>Local plumbing.<br>Done properly.</h1><p>Reliable plumbing repairs, bathrooms, showers and heating work across Guildford and Surrey. From first enquiry to finished job, you deal directly with me, Nigel.</p><div class="actions"><a class="btn" href="/request-quote">Get a Quote</a><a class="btn white" href="tel:__COMPANY_PHONE_TEL__">Call __COMPANY_PHONE__</a></div></div></div></section>
<div class="trust"><div class="wrap trustgrid"><div><strong>Local & independent</strong><span>Based in Guildford</span></div><div><strong>Clear communication</strong><span>Before, during & after</span></div><div><strong>Clear quotes</strong><span>Labour & materials explained</span></div><div><strong>Direct contact</strong><span>Deal directly with me</span></div></div></div>
<section id="services"><div class="wrap"><div class="intro"><h2>Plumbing services without the fuss</h2><p>From a leaking fitting to a bathroom project, get straightforward advice, clear pricing and tidy workmanship.</p></div><div class="cards">
<div class="card"><div class="icon">🔧</div><h3>Plumbing Repairs</h3><p>Leaks, taps, wastes, toilets, pipework and everyday plumbing problems.</p></div>
<div class="card"><div class="icon">🚿</div><h3>Bathrooms & Showers</h3><p>Bathroom plumbing, shower replacements, trays, screens and associated pipework.</p></div>
<div class="card"><div class="icon">♨️</div><h3>Radiators & Heating</h3><p>Radiators, valves, system improvements and heating pipework.</p></div>
<div class="card"><div class="icon">💧</div><h3>Installations</h3><p>Outside taps, appliances, sinks and practical plumbing upgrades around the home.</p></div>
</div></div></section>
<section id="about" style="background:#f3f7fa"><div class="wrap split"><div><h2>A local tradesman you can actually speak to</h2><p class="muted">When you contact Nigel Harvey Plumbing, you deal directly with Nigel — not a call centre or salesperson.</p><div class="ticks"><div class="tick">Straightforward communication before the job</div><div class="tick">Clear, itemised quotations</div><div class="tick">Care taken in your home</div><div class="tick">One point of contact from enquiry to completion</div></div><a class="btn" href="/request-quote">Ask Nigel about your job</a></div><div class="photo"></div></div></section>
<section class="dark" id="work"><div class="wrap"><div class="intro"><h2>Simple, straightforward service</h2><p>No confusing process. Tell Nigel what needs doing, receive a clear quote, and arrange a suitable time for the work.</p></div><div class="jobs"><div class="job"><small>01 · Enquire</small><h3>Tell me about the job</h3><p>Send the details online or call. Photos and a short description can help establish what is required.</p></div><div class="job"><small>02 · Quote</small><h3>Clear pricing</h3><p>Receive a straightforward quote with the work and relevant charges made clear before you proceed.</p></div><div class="job"><small>03 · Complete</small><h3>Get the job sorted</h3><p>Arrange a suitable date and deal directly with Nigel through to completion.</p></div></div></div></section>
<section class="review"><div class="wrap"><div class="reviewbox">__GOOGLE_REVIEWS_HTML__</div></div></section>
<section class="area" id="areas"><div class="wrap"><div class="area-intro"><h2>Local plumber serving Guildford and Surrey</h2><p class="muted">Nigel Harvey Plumbing is based in Guildford and carries out domestic plumbing work across Guildford and surrounding Surrey towns. Choose your area below for local service information.</p></div><div class="area-links"><a class="area-link" href="/plumber-guildford">Plumber in Guildford</a><a class="area-link" href="/plumber-godalming">Plumber in Godalming</a><a class="area-link" href="/plumber-woking">Plumber in Woking</a><a class="area-link" href="/plumber-farnham">Plumber in Farnham</a><a class="area-link" href="/plumber-camberley">Plumber in Camberley</a><a class="area-link" href="/plumber-aldershot">Plumber in Aldershot</a><a class="area-link" href="/plumber-leatherhead">Plumber in Leatherhead</a><a class="area-link" href="/plumber-epsom">Plumber in Epsom</a><a class="area-link" href="/plumber-fairlands">Plumber in Fairlands</a><a class="area-link" href="/plumber-worplesdon">Plumber in Worplesdon</a><a class="area-link" href="/plumber-merrow">Plumber in Merrow</a><a class="area-link" href="/plumber-burpham">Plumber in Burpham</a><a class="area-link" href="/plumber-shalford">Plumber in Shalford</a></div><div class="area-note"><div><h3>Not sure if I cover your area?</h3><p class="muted">Send your postcode and a short description of the work. For jobs further away, any travel charge can be made clear before you book.</p></div><a class="btn" href="/request-quote">Check your area</a></div></div></section>
<section class="cta"><div class="wrap"><div><h2>Need a plumber?</h2><p>Tell me what you need doing and I'll come back to you with the next step.</p></div><a class="btn white" href="/request-quote">Get a Quote</a></div></section>
<footer><div class="wrap foot"><div><strong>Nigel Harvey Plumbing</strong><br>Nigel Harvey Ltd · Guildford, Surrey</div><div>__COMPANY_PHONE__<br>__COMPANY_EMAIL__</div></div></footer>
<a class="mobile-call" href="tel:__COMPANY_PHONE_TEL__">Call Nigel · __COMPANY_PHONE__</a>
</body></html>
"""


@app.get("/new-home", response_class=HTMLResponse)
def new_homepage_preview(request: Request):
    html = NEW_HOMEPAGE_PREVIEW_HTML.replace("__PUBLIC_HOME_URL__", escape(absolute_url("/", request), quote=True))
    html = html.replace("__COMPANY_PHONE__", COMPANY_PHONE)
    html = html.replace("__COMPANY_PHONE_TEL__", COMPANY_PHONE_TEL)
    html = html.replace("__COMPANY_EMAIL__", COMPANY_EMAIL)
    html = html.replace("__GOOGLE_REVIEWS_URL__", GOOGLE_REVIEWS_URL)
    html = html.replace("__GOOGLE_REVIEWS_HTML__", _google_reviews_html())
    return HTMLResponse(content=html, media_type="text/html; charset=utf-8")


@app.get("/", response_class=HTMLResponse)
def landing_home(request: Request):
    html = NEW_HOMEPAGE_PREVIEW_HTML.replace("__PUBLIC_HOME_URL__", escape(absolute_url("/", request), quote=True))
    html = html.replace("__COMPANY_PHONE__", COMPANY_PHONE)
    html = html.replace("__COMPANY_PHONE_TEL__", COMPANY_PHONE_TEL)
    html = html.replace("__COMPANY_EMAIL__", COMPANY_EMAIL)
    html = html.replace("__GOOGLE_REVIEWS_URL__", GOOGLE_REVIEWS_URL)
    html = html.replace("__GOOGLE_REVIEWS_HTML__", _google_reviews_html())
    return HTMLResponse(content=html, media_type="text/html; charset=utf-8")


@app.get("/robots.txt")
def robots_txt(request: Request):
    sitemap_url = absolute_url("/sitemap.xml", request)
    content = f"User-agent: *\nAllow: /\nSitemap: {sitemap_url}\n"
    return Response(content=content, media_type="text/plain; charset=utf-8")


@app.get("/sitemap.xml")
def sitemap_xml(request: Request):
    urls = ["/", "/request-quote"]
    urls.extend(f"/plumber-{item['slug']}" for item in LOCATION_PAGES)
    urls.extend(f"/{item['slug']}" for item in SERVICE_PAGES)
    urls.extend(
        f"/{service['slug']}-{location['slug']}"
        for service in LOCAL_SERVICE_PAGES
        for location in LOCATION_PAGES
    )
    body = "".join(f"<url><loc>{absolute_url(url, request)}</loc></url>" for url in urls)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>'
    return Response(content=xml, media_type="application/xml; charset=utf-8")


@app.get("/plumber-{area_slug}", response_class=HTMLResponse)
def location_page(area_slug: str, request: Request):
    page = next((item for item in LOCATION_PAGES if item["slug"] == area_slug.lower()), None)
    if not page:
        raise HTTPException(status_code=404, detail="Area page not found")
    logo_html = get_company_logo_html(get_company_logo_value())
    return HTMLResponse(content=render_location_page(page["name"], logo_html), media_type="text/html; charset=utf-8")



@app.get("/{service_slug}-{area_slug}", response_class=HTMLResponse)
def local_service_location_page(service_slug: str, area_slug: str, request: Request):
    service = next((item for item in LOCAL_SERVICE_PAGES if item["slug"] == service_slug.lower()), None)
    location = next((item for item in LOCATION_PAGES if item["slug"] == area_slug.lower()), None)
    if not service or not location:
        raise HTTPException(status_code=404, detail="Local service page not found")
    logo_html = get_company_logo_html(get_company_logo_value())
    return HTMLResponse(
        content=render_local_service_location_page(service, location, logo_html, request),
        media_type="text/html; charset=utf-8"
    )

@app.get("/{service_slug}", response_class=HTMLResponse)
def service_page(service_slug: str):
    page = next((item for item in SERVICE_PAGES if item["slug"] == service_slug.lower()), None)
    if not page:
        raise HTTPException(status_code=404, detail="Service page not found")
    logo_html = get_company_logo_html(get_company_logo_value())
    return HTMLResponse(content=render_service_page(page, logo_html), media_type="text/html; charset=utf-8")




def get_material_search_library():
    items = []

    for item in MATERIAL_LIBRARY:
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


def _extract_toolstation_products(html: str, page_url: str):
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


def _extract_search_page_products(html: str, search_url: str, merchant_name: str, allowed_hosts):
    if merchant_name == "Toolstation":
        toolstation_items = _extract_toolstation_products(html, search_url)
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


def _read_product_page_details(product, merchant_name):
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


def search_live_merchant_products(query: str, suppliers=None, per_supplier: int = 5):
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
                        response.text, response.url, merchant_name, merchant["allowed_hosts"]
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
            detailed = _read_product_page_details(product, merchant_name)
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

    results.sort(key=lambda item: (
        1 if item.get("search_only") else 0,
        -safe_float(item.get("match_score", 0), 0),
        0 if safe_float(item.get("live_price", 0), 0) > 0 else 1,
        safe_float(item.get("live_price", 0), 0) or 999999,
    ))
    return results[:20]


@app.get("/api/live-product-search")
def api_live_product_search(q: str = "", suppliers: str = "", request: Request = None):
    if request is not None and not check_basic_auth(request):
        raise HTTPException(status_code=401, detail="Authentication required")
    selected = [value.strip() for value in (suppliers or "").split(",") if value.strip() in LIVE_MERCHANTS]
    return JSONResponse({
        "query": q,
        "suppliers": selected or list(LIVE_MERCHANTS.keys()),
        "results": search_live_merchant_products(q, selected or None, 3),
        "live_price_note": "Prices are checked from merchant product pages where accessible. Confirm price and availability before ordering.",
    })



@app.get("/api/live-product-refresh")
def api_live_product_refresh(url: str = "", name: str = "", supplier: str = "", request: Request = None):
    if request is not None and not check_basic_auth(request):
        raise HTTPException(status_code=401, detail="Authentication required")
    clean_url = normalize_material_url(url)
    if not clean_url.startswith("http"):
        raise HTTPException(status_code=400, detail="A valid product URL is required.")
    details = _read_product_page_details({"url": clean_url, "name": name, "price": 0}, supplier or "Merchant")
    if not details.get("url"):
        raise HTTPException(status_code=422, detail="The merchant product page could not be confirmed.")
    if details.get("live_price"):
        upsert_material_price_cache(
            details["url"], details.get("name", name), details.get("supplier", supplier),
            price=details["live_price"], manual_price=0, status="live",
        )
    return JSONResponse(details)


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


def _material_match_score(query: str, item: dict) -> int:
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


@app.get("/api/material-search")
def api_material_search(q: str = "", request: Request = None):
    if request is not None and not check_basic_auth(request):
        raise HTTPException(status_code=401, detail="Authentication required")

    query = (q or "").strip()
    items = get_material_search_library()

    if query:
        scored = []
        for item in items:
            score = _material_match_score(query, item)
            if score >= 45:
                enriched = dict(item)
                enriched["match_score"] = score
                scored.append(enriched)

        scored.sort(key=lambda item: (
            -int(item.get("match_score", 0)),
            0 if item.get("url") else 1,
            0 if safe_float(item.get("default_price", 0), 0) > 0 else 1,
            -(int(item.get("times_used", 0) or 0)),
        ))
        items = scored
    else:
        items = list(items)

    return JSONResponse(items[:30])




@app.get("/api/material-resolve")
def api_material_resolve(name: str = "", request: Request = None):
    if request is not None and not check_basic_auth(request):
        raise HTTPException(status_code=401, detail="Authentication required")

    requested = (name or "").strip()
    if not requested:
        raise HTTPException(status_code=400, detail="Material name is required.")

    candidates = get_material_search_library()
    scored = []
    for item in candidates:
        score = _material_match_score(requested, item)
        if score >= 60:
            result = dict(item)
            result["match_score"] = score
            scored.append(result)

    scored.sort(key=lambda item: (
        -int(item.get("match_score", 0)),
        0 if item.get("url") else 1,
        0 if safe_float(item.get("default_price", 0), 0) > 0 else 1,
        -(int(item.get("times_used", 0) or 0)),
    ))

    best = scored[0] if scored and int(scored[0].get("match_score", 0)) >= 72 else None
    return JSONResponse({
        "requested_name": requested,
        "matched": bool(best),
        "best": best,
        "alternatives": scored[:5],
    })


@app.get("/api/material-prices")
def api_material_prices(request: Request):
    if not check_basic_auth(request):
        raise HTTPException(status_code=401, detail="Authentication required")
    return JSONResponse(material_store.list_material_price_cache())


@app.post("/api/material-prices/refresh")
def api_refresh_material_prices(request: Request):
    if not check_basic_auth(request):
        raise HTTPException(status_code=401, detail="Authentication required")
    conn = get_db()
    rows = conn.execute("SELECT url, name, supplier, last_manual_price FROM material_price_cache ORDER BY updated_at DESC LIMIT 200").fetchall()
    conn.close()

    refreshed = []
    for row in rows:
        price, source = fetch_tracked_price(row["url"], row["name"] or "", row["supplier"] or "", row["last_manual_price"] or 0)
        refreshed.append({
            "url": row["url"],
            "name": row["name"],
            "supplier": row["supplier"],
            "price": price,
            "source": source,
        })

    return JSONResponse({"refreshed": refreshed})



class MaterialCacheUpdateRequest(BaseModel):
    name: str = ""
    supplier: str = ""
    url: str = ""
    manual_price: float = 0


@app.put("/api/material-prices/{material_id}")
def api_update_material_price(material_id: int, data: MaterialCacheUpdateRequest, request: Request):
    if not check_basic_auth(request):
        raise HTTPException(status_code=401, detail="Authentication required")
    if not material_store.update_material_price_cache(material_id, data, now_uk, safe_float):
        raise HTTPException(status_code=404, detail="Material not found")
    return {"ok": True}


@app.delete("/api/material-prices/{material_id}")
def api_delete_material_price(material_id: int, request: Request):
    if not check_basic_auth(request):
        raise HTTPException(status_code=401, detail="Authentication required")
    if not material_store.delete_material_price_cache(material_id):
        raise HTTPException(status_code=404, detail="Material not found")
    return {"ok": True}



@app.get("/api/intelligence")
def api_intelligence(request: Request):
    if not check_basic_auth(request):
        raise HTTPException(status_code=401, detail="Authentication required")
    conn = get_db()
    jobs = conn.execute("""
        SELECT quote_type,
               COUNT(*) AS count,
               ROUND(AVG(labour), 2) AS avg_labour,
               ROUND(AVG(materials), 2) AS avg_materials,
               ROUND(AVG(total_price), 2) AS avg_total,
               ROUND(AVG(gross_profit), 2) AS avg_profit,
               ROUND(AVG(margin_percent), 2) AS avg_margin
        FROM quote_intelligence
        GROUP BY quote_type
        ORDER BY count DESC
    """).fetchall()
    materials = conn.execute("""
        SELECT name, supplier, COUNT(*) AS checks,
               ROUND(AVG(price), 2) AS avg_price,
               ROUND(MIN(price), 2) AS min_price,
               ROUND(MAX(price), 2) AS max_price,
               MAX(checked_at) AS last_checked
        FROM material_price_history
        WHERE price IS NOT NULL AND price > 0
        GROUP BY name, supplier
        ORDER BY checks DESC, last_checked DESC
        LIMIT 50
    """).fetchall()
    conn.close()
    return JSONResponse({
        "jobs": [dict(row) for row in jobs],
        "materials": [dict(row) for row in materials],
    })



@app.get("/api/health")
def api_health():
    return {
        "ok": True,
        "version": APP_VERSION,
        "db_exists": DB_PATH.exists(),
        "db_path": str(DB_PATH),
        "db_size_bytes": DB_PATH.stat().st_size if DB_PATH.exists() else 0,
        "counts": database_counts(),
        "backup_count": len(list_db_backups()),
        "time": now_uk().isoformat(),
    }


@app.get("/api/backups")
def api_list_backups(request: Request):
    if not check_basic_auth(request):
        raise HTTPException(status_code=401, detail="Authentication required")
    return {
        "version": APP_VERSION,
        "backups": list_db_backups(),
        "counts": database_counts(),
    }


@app.post("/api/backups")
def api_create_backup(request: Request):
    if not check_basic_auth(request):
        raise HTTPException(status_code=401, detail="Authentication required")
    backup = create_db_backup("manual")
    if not backup:
        raise HTTPException(status_code=404, detail="Database not found")
    return backup


@app.get("/api/backups/{filename}")
def api_download_backup(filename: str, request: Request):
    if not check_basic_auth(request):
        raise HTTPException(status_code=401, detail="Authentication required")

    safe_name = Path(filename).name
    backup_path = DB_BACKUP_DIR / safe_name
    if not backup_path.exists() or not safe_name.startswith("quotes-backup-") or backup_path.suffix != ".db":
        raise HTTPException(status_code=404, detail="Backup not found")

    headers = {"Content-Disposition": f'attachment; filename="{safe_name}"'}
    return Response(content=backup_path.read_bytes(), media_type="application/octet-stream", headers=headers)


@app.get("/api/dashboard")
def api_dashboard():
    return get_dashboard()


@app.get("/api/dashboard/monthly-profit")
def api_dashboard_monthly_profit():
    return get_monthly_profit_series(6)


@app.get("/api/quotes")
def api_quotes():
    return load_quotes()


@app.get("/api/quotes/{quote_id}")
def api_quote(quote_id: int):
    quote = get_quote_by_id(quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    return quote


@app.delete("/api/quotes/{quote_id}")
def api_delete_quote(quote_id: int):
    if not delete_quote_by_id(quote_id):
        raise HTTPException(status_code=404, detail="Quote not found")
    return {"ok": True}






@app.get("/api/master-materials")
def api_master_materials(category: str = ""):
    if category:
        return JSONResponse(content=get_materials_by_category(category))
    return JSONResponse(content=MASTER_MATERIAL_LIBRARY)




@app.get("/api/material-quantity")
def api_material_quantity(q: str = "", job: str = "", quote_type: str = ""):
    learned = learned_material_quantity_from_quotes(q, job, quote_type)
    return JSONResponse(content={
        "name": q,
        "suggested_quantity": learned.get("rounded_quantity", 1),
        "average_quantity": learned.get("quantity", 1),
        "source": learned.get("source", "rule"),
        "used_count": learned.get("used_count", 0),
        "similar_count": learned.get("similar_count", 0),
        "used_percent": learned.get("used_percent", 0),
    })


@app.get("/api/material-charging")
def api_material_charging(q: str = ""):
    return JSONResponse(content=get_material_charging_rule(q))


@app.get("/api/material-alias")
def api_material_alias(q: str = ""):
    return JSONResponse(content=material_alias_info(q))


@app.get("/api/trade-jobs")
def api_trade_jobs():
    return JSONResponse(content=get_all_job_templates())


def labour_intelligence_for_job(job_text: str = "", quote_type: str = "", current_labour: float = 0):
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


def detect_forgotten_items(job_text: str, materials: list):
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



def supplier_preference_for_material(material_name: str):
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


def supplier_preferences_summary():
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





AI_ESTIMATOR_FALLBACK_LIBRARY = [
    {
        "category": "shower replacement",
        "keywords": ["replace shower", "replacement shower", "remove old shower", "fit new shower", "install shower", "change shower"],
        "scope_hint": "Remove the existing shower and fit a compatible replacement, reconnect services, seal as required and test operation.",
        "labour_range": [180, 350],
        "materials": [
            {"name": "Replacement shower unit", "quantity": 1, "required": False, "reason": "Include only if Nigel is supplying the shower; exact type and model must be confirmed."},
            {"name": "Sanitary silicone", "quantity": 1, "required": True, "reason": "For sealing around the replacement where required."},
            {"name": "Suitable wall fixings", "quantity": 1, "required": True, "reason": "Fixings depend on the wall construction and the replacement shower."},
            {"name": "PTFE tape", "quantity": 0.1, "required": False, "reason": "Small consumable allowance where threaded plumbing connections are used."},
            {"name": "15mm copper olives", "quantity": 2, "required": False, "reason": "May be needed if compression connections are disturbed or renewed."},
            {"name": "15mm compression nuts", "quantity": 2, "required": False, "reason": "May be needed if existing compression fittings cannot be reused."},
            {"name": "Shower connection adaptors", "quantity": 2, "required": False, "reason": "Only required if the replacement inlet centres or connection type differ."}
        ],
        "questions": [
            "Is the existing shower electric, exposed mixer, concealed mixer, digital or pumped?",
            "Who is supplying the replacement shower?",
            "Is the replacement the same model or compatible with the existing inlet positions?",
            "Are the water isolation valves accessible and working?",
            "Is any electrical work required?",
            "Is the wall or tiling damaged and is making good required?"
        ],
        "risks": [
            "Existing inlet centres, pipe positions and fixings may not match the replacement.",
            "Concealed pipework and wall condition cannot be confirmed from the description.",
            "Electrical shower work must be completed by a suitably qualified person where required."
        ]
    },
    {
        "category": "tap replacement",
        "keywords": ["replace tap", "replace taps", "fit new tap", "change tap", "mixer tap", "basin tap", "kitchen tap"],
        "scope_hint": "Isolate the water supply, remove the existing tap, fit the compatible replacement, reconnect supplies and test for leaks and operation.",
        "labour_range": [120, 220],
        "materials": [
            {"name": "Replacement tap", "quantity": 1, "required": False, "reason": "Include only if Nigel is supplying the tap."},
            {"name": "15mm isolating valve", "quantity": 2, "required": False, "reason": "Recommended if existing valves are missing, seized or unreliable."},
            {"name": "Flexible tap connector", "quantity": 2, "required": False, "reason": "Required where not supplied with the replacement tap or existing tails are unsuitable."},
            {"name": "PTFE tape", "quantity": 0.1, "required": False, "reason": "Small consumable allowance for suitable threaded connections."},
            {"name": "Sanitary silicone", "quantity": 0.1, "required": False, "reason": "May be required around the tap base depending on the fitting."}
        ],
        "questions": [
            "Who is supplying the tap?",
            "Are working isolation valves present?",
            "Is access beneath the basin or sink restricted?",
            "Are the existing supply sizes and connections compatible?"
        ],
        "risks": [
            "Old isolation valves or rigid pipework may require additional replacement work.",
            "Restricted access can increase labour time."
        ]
    },
    {
        "category": "toilet replacement",
        "keywords": ["replace toilet", "toilet replacement", "fit new toilet", "change toilet", "replace wc"],
        "scope_hint": "Isolate and disconnect the existing toilet, remove it, fit a compatible replacement, reconnect the inlet and soil connection, secure, seal and test.",
        "labour_range": [180, 320],
        "materials": [
            {"name": "Replacement toilet", "quantity": 1, "required": False, "reason": "Include only if Nigel is supplying the toilet."},
            {"name": "Pan connector", "quantity": 1, "required": True, "reason": "A compatible connector is normally needed for the soil connection."},
            {"name": "Toilet fixing kit", "quantity": 1, "required": True, "reason": "For securely fixing the pan or cistern as appropriate."},
            {"name": "15mm isolating valve", "quantity": 1, "required": False, "reason": "Recommended if the existing valve is absent or unreliable."},
            {"name": "Flexible tap connector", "quantity": 1, "required": False, "reason": "May be required for the cistern inlet connection."},
            {"name": "Sanitary silicone", "quantity": 0.25, "required": True, "reason": "For sealing around the installation where appropriate."}
        ],
        "questions": [
            "Who is supplying the toilet?",
            "Is it close-coupled, back-to-wall or wall-hung?",
            "Does the replacement match the existing soil outlet position?",
            "Is flooring or wall making-good likely?"
        ],
        "risks": [
            "The replacement footprint may expose damaged flooring or previous fixing holes.",
            "Soil outlet alignment may require a different pan connector or additional work."
        ]
    },
    {
        "category": "radiator or TRV work",
        "keywords": ["replace radiator", "fit radiator", "install radiator", "replace trv", "change trv", "radiator valve", "trv"],
        "scope_hint": "Isolate and drain the relevant heating section, complete the radiator or valve work, refill, vent, dose as required and test.",
        "labour_range": [150, 350],
        "materials": [
            {"name": "TRV valve", "quantity": 1, "required": False, "reason": "Required for a TRV replacement or where specified with a radiator."},
            {"name": "Lockshield valve", "quantity": 1, "required": False, "reason": "Often replaced as a matching pair where condition is poor."},
            {"name": "Radiator valve tail", "quantity": 2, "required": False, "reason": "May be required for replacement valves or a new radiator."},
            {"name": "Central heating inhibitor", "quantity": 1, "required": True, "reason": "System protection should be considered after draining and refilling."},
            {"name": "PTFE tape", "quantity": 0.1, "required": False, "reason": "Small consumable allowance for appropriate threaded joints."},
            {"name": "15mm copper olives", "quantity": 2, "required": False, "reason": "May be needed where compression joints are renewed."}
        ],
        "questions": [
            "Is the system sealed or open vented?",
            "Does the whole system need draining?",
            "Are the existing pipe centres compatible?",
            "Is the radiator being supplied by the customer?"
        ],
        "risks": [
            "Old valves or pipework may not reseal once disturbed.",
            "Airlocks, seized valves or poor system water condition can increase labour."
        ]
    },
    {
        "category": "outside tap",
        "keywords": ["outside tap", "garden tap", "external tap", "hose union bib tap"],
        "scope_hint": "Connect a new cold-water supply to an outside tap, including internal isolation and backflow protection where required, secure pipework and test.",
        "labour_range": [150, 280],
        "materials": [
            {"name": "Outside tap kit", "quantity": 1, "required": True, "reason": "Main outlet and wall plate components."},
            {"name": "15mm isolating valve", "quantity": 1, "required": True, "reason": "Allows internal isolation for maintenance and winter protection."},
            {"name": "Double check valve 15mm", "quantity": 1, "required": True, "reason": "Backflow protection where required."},
            {"name": "15mm copper pipe", "quantity": 3, "required": False, "reason": "Provisional pipe allowance until the route is measured."},
            {"name": "15mm pipe clips", "quantity": 6, "required": False, "reason": "Provisional allowance for supporting the pipe route."},
            {"name": "Drain off cock 15mm", "quantity": 1, "required": False, "reason": "Useful for draining exposed external pipework where freezing is possible."}
        ],
        "questions": [
            "How far is the proposed tap from a suitable cold-water supply?",
            "Can the pipe pass directly through the wall?",
            "Is exposed external pipework required?",
            "Is frost protection or lagging required?"
        ],
        "risks": [
            "The final pipe quantity depends on the route and access.",
            "External pipework must be protected against freezing."
        ]
    }
]


def normalise_ai_job_text(value: str):
    value = (value or "").lower().strip()
    corrections = {
        "rmove": "remove",
        "remve": "remove",
        "shower and fix": "shower and fit",
        "showe ": "shower ",
        "fitt ": "fit ",
        "replce": "replace",
        "toilte": "toilet",
        "raditor": "radiator",
        "outisde": "outside",
    }
    for old, new in corrections.items():
        value = value.replace(old, new)
    value = re.sub(r"\s+", " ", value)
    return value


def ai_fallback_matches(job_text: str):
    job = normalise_ai_job_text(job_text)
    matches = []
    for item in AI_ESTIMATOR_FALLBACK_LIBRARY:
        score = 0
        for phrase in item.get("keywords", []):
            if phrase in job:
                score += max(2, len(phrase.split()))
            else:
                phrase_tokens = set(phrase.split())
                job_tokens = set(job.split())
                score += len(phrase_tokens.intersection(job_tokens))
        if score > 0:
            matches.append((score, item))
    matches.sort(key=lambda x: x[0], reverse=True)
    return [item for score, item in matches[:3] if score >= 2]


def ai_master_material_candidates(job_text: str, fallback_matches: list):
    wanted = set()
    for match in fallback_matches or []:
        for item in match.get("materials", []):
            wanted.add(canonical_material_name(item.get("name", "")))

    candidates = []
    library = globals().get("MASTER_MATERIAL_LIBRARY", [])
    if isinstance(library, dict):
        iterable = []
        for category, values in library.items():
            if isinstance(values, list):
                iterable.extend(values)
    else:
        iterable = library if isinstance(library, list) else []

    for item in iterable:
        if isinstance(item, str):
            name = item
            data = {"name": item}
        elif isinstance(item, dict):
            data = item
            name = item.get("name", "")
        else:
            continue

        canonical = canonical_material_name(name)
        if canonical in wanted or any(w and (w in canonical or canonical in w) for w in wanted):
            candidates.append({
                "name": name,
                "canonical_name": canonical,
                "category": data.get("category", ""),
                "aliases": data.get("aliases", []),
            })

    return candidates[:30]


AI_QUOTE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "scope_of_work": {"type": "string"},
        "customer_summary": {"type": "string"},
        "labour_suggestion": {"type": "number"},
        "materials": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "quantity": {"type": "number"},
                    "supplier": {"type": "string"},
                    "reason": {"type": "string"},
                    "required": {"type": "boolean"},
                    "url": {"type": "string"},
                    "manual_price": {"type": "number"},
                    "data_source": {"type": "string"}
                },
                "required": ["name", "quantity", "supplier", "reason", "required", "url", "manual_price", "data_source"]
            }
        },
        "risk_notes": {
            "type": "array",
            "items": {"type": "string"}
        },
        "questions_to_confirm": {
            "type": "array",
            "items": {"type": "string"}
        },
        "warnings": {
            "type": "array",
            "items": {"type": "string"}
        },
        "job_breakdown": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "job_type": {"type": "string"},
                    "display_name": {"type": "string"},
                    "scope": {"type": "string"},
                    "labour_suggestion": {"type": "number"}
                },
                "required": ["job_type", "display_name", "scope", "labour_suggestion"]
            }
        },
        "confidence": {
            "type": "string",
            "enum": ["low", "medium", "high"]
        }
    },
    "required": [
        "scope_of_work",
        "customer_summary",
        "labour_suggestion",
        "materials",
        "risk_notes",
        "questions_to_confirm",
        "warnings",
        "job_breakdown",
        "confidence"
    ]
}


def extract_openai_output_text(response_json: dict):
    if not isinstance(response_json, dict):
        return ""

    direct = response_json.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    chunks = []
    for item in response_json.get("output", []) or []:
        for content in item.get("content", []) or []:
            if content.get("type") in ("output_text", "text"):
                value = content.get("text", "")
                if isinstance(value, str):
                    chunks.append(value)
                elif isinstance(value, dict):
                    chunks.append(value.get("value", ""))

    return "\n".join(x for x in chunks if x).strip()



def ai_text_tokens(value: str):
    value = normalise_ai_job_text(value)
    return {
        token for token in re.findall(r"[a-z0-9]+", value)
        if len(token) > 1 and token not in {
            "the", "and", "for", "with", "from", "into", "new", "old",
            "fit", "supply", "supplied", "replace", "replacement", "remove"
        }
    }


def ai_material_search_score(query: str, item: dict):
    query_normal = normalise_ai_job_text(query)
    name = item.get("name", "") or ""
    name_normal = normalise_ai_job_text(name)

    if not query_normal or not name_normal:
        return 0

    score = 0
    if query_normal == name_normal:
        score += 100
    elif query_normal in name_normal or name_normal in query_normal:
        score += 45

    query_can = canonical_material_name(query_normal)
    name_can = canonical_material_name(name_normal)
    if query_can and name_can:
        if query_can == name_can:
            score += 90
        elif query_can in name_can or name_can in query_can:
            score += 35

    query_tokens = ai_text_tokens(query_normal)
    name_tokens = ai_text_tokens(name_normal)
    if query_tokens and name_tokens:
        overlap = query_tokens.intersection(name_tokens)
        score += len(overlap) * 14
        score += round((len(overlap) / max(len(query_tokens), 1)) * 20)

    if item.get("source") == "saved":
        score += 8
    score += min(int(item.get("times_used") or 0), 10)

    return score


def get_ai_business_material_library():
    rows = []
    seen = set()

    try:
        source_items = get_material_search_library()
    except Exception:
        source_items = []

    for item in source_items or []:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if not name:
            continue

        supplier = (item.get("supplier") or "").strip()
        url = (item.get("url") or "").strip()
        key = (canonical_material_name(name), supplier.lower(), url)
        if key in seen:
            continue

        price = safe_float(
            item.get("default_price", item.get("last_price", item.get("last_manual_price", 0))),
            0
        )

        rows.append({
            "name": name,
            "canonical_name": canonical_material_name(name),
            "supplier": supplier,
            "url": url,
            "manual_price": round(price, 2) if price > 0 else 0,
            "price_status": item.get("last_status", ""),
            "times_used": int(item.get("times_used") or 0),
            "source": item.get("source", "built-in"),
        })
        seen.add(key)

    return rows


def find_ai_material_matches(query: str, limit: int = 5):
    scored = []
    for item in get_ai_business_material_library():
        score = ai_material_search_score(query, item)
        if score > 10:
            scored.append((score, item))

    scored.sort(
        key=lambda pair: (
            pair[0],
            pair[1].get("times_used", 0),
            1 if pair[1].get("manual_price", 0) > 0 else 0
        ),
        reverse=True
    )

    return [
        {**item, "match_score": score}
        for score, item in scored[:limit]
    ]


def get_relevant_ai_business_materials(job_text: str, trade_templates: list, fallback_matches: list, limit: int = 40):
    search_phrases = [job_text]

    for template in trade_templates or []:
        search_phrases.extend([
            template.get("name", ""),
            template.get("job", ""),
        ])
        for material in template.get("materials", []) or []:
            if isinstance(material, dict):
                search_phrases.append(material.get("name", ""))
            else:
                search_phrases.append(str(material))

    for fallback in fallback_matches or []:
        search_phrases.append(fallback.get("category", ""))
        for material in fallback.get("materials", []) or []:
            search_phrases.append(material.get("name", ""))

    combined = []
    best_by_key = {}
    for phrase in search_phrases:
        if not phrase:
            continue
        for match in find_ai_material_matches(phrase, limit=8):
            key = (
                match.get("canonical_name", ""),
                match.get("supplier", "").lower(),
                match.get("url", "")
            )
            old = best_by_key.get(key)
            if old is None or match.get("match_score", 0) > old.get("match_score", 0):
                best_by_key[key] = match

    combined = list(best_by_key.values())
    combined.sort(
        key=lambda item: (
            item.get("match_score", 0),
            item.get("times_used", 0),
            1 if item.get("manual_price", 0) > 0 else 0
        ),
        reverse=True
    )
    return combined[:limit]


def reconcile_ai_draft_with_business_data(draft: dict, context: dict):
    if not isinstance(draft, dict):
        return draft

    job = context.get("request", {}).get("normalised_job_description", "")
    quote_type = context.get("request", {}).get("quote_type", "")
    business_materials = context.get("business_material_matches", []) or []

    resolved_materials = []
    for material in draft.get("materials", []) or []:
        if not isinstance(material, dict):
            continue

        original_name = (material.get("name") or "").strip()
        if not original_name:
            continue

        candidates = []
        for item in business_materials:
            score = ai_material_search_score(original_name, item)
            if score > 10:
                candidates.append((score, item))

        if not candidates:
            for item in find_ai_material_matches(original_name, limit=5):
                candidates.append((item.get("match_score", 0), item))

        candidates.sort(
            key=lambda pair: (
                pair[0],
                pair[1].get("times_used", 0),
                1 if pair[1].get("manual_price", 0) > 0 else 0
            ),
            reverse=True
        )

        best = candidates[0][1] if candidates and candidates[0][0] >= 35 else None
        best_score = candidates[0][0] if candidates else 0

        quantity_info = learned_material_quantity_from_quotes(
            best.get("name") if best else original_name,
            job,
            quote_type
        )

        ai_quantity = safe_float(material.get("quantity", 1), 1)
        learned_quantity = safe_float(quantity_info.get("quantity", 0), 0)
        quantity = learned_quantity if quantity_info.get("source") == "learned" and learned_quantity > 0 else ai_quantity

        preferred = supplier_preference_for_material(
            best.get("name") if best else original_name
        ) if "supplier_preference_for_material" in globals() else {}

        supplier = ""
        url = ""
        manual_price = 0
        data_source = "ai_general"
        resolved_name = original_name

        if best:
            resolved_name = best.get("name") or original_name
            supplier = best.get("supplier") or ""
            url = best.get("url") or ""
            manual_price = safe_float(best.get("manual_price", 0), 0)
            data_source = "saved_material" if best.get("source") == "saved" else "material_library"

        if preferred.get("preferred_supplier"):
            preferred_supplier = preferred.get("preferred_supplier")
            # Prefer a matching saved row from the learned supplier.
            supplier_rows = [
                pair for pair in candidates
                if (pair[1].get("supplier") or "").lower() == preferred_supplier.lower()
            ]
            if supplier_rows and supplier_rows[0][0] >= 30:
                preferred_row = supplier_rows[0][1]
                resolved_name = preferred_row.get("name") or resolved_name
                supplier = preferred_row.get("supplier") or supplier
                url = preferred_row.get("url") or url
                manual_price = safe_float(preferred_row.get("manual_price", manual_price), manual_price)
                data_source = "preferred_supplier_history"
            elif not supplier:
                supplier = preferred_supplier

        if not supplier:
            supplier = material.get("supplier") or "City Plumbing"

        resolved_materials.append({
            **material,
            "name": resolved_name,
            "quantity": round(quantity, 2),
            "supplier": supplier,
            "url": url,
            "manual_price": round(manual_price, 2),
            "data_source": data_source,
            "original_ai_name": original_name,
            "match_score": round(best_score, 2),
            "quantity_source": quantity_info.get("source", "ai"),
            "learned_used_count": quantity_info.get("used_count", 0),
        })

    draft["materials"] = resolved_materials
    draft["business_brain"] = {
        "matched_materials": sum(
            1 for item in resolved_materials
            if item.get("data_source") != "ai_general"
        ),
        "priced_materials": sum(
            1 for item in resolved_materials
            if safe_float(item.get("manual_price", 0), 0) > 0
        ),
        "learned_quantities": sum(
            1 for item in resolved_materials
            if item.get("quantity_source") == "learned"
        ),
        "materials_total_before_handling": round(sum(
            safe_float(item.get("manual_price", 0), 0) *
            safe_float(item.get("quantity", 1), 1)
            for item in resolved_materials
        ), 2),
    }

    return draft



def ai_material_required_from_template(material: dict):
    if not isinstance(material, dict):
        return False
    if "required" in material:
        return bool(material.get("required"))
    name = normalise_ai_job_text(material.get("name", ""))
    optional_markers = [
        "replacement shower", "replacement tap", "replacement toilet",
        "replacement radiator", "customer supplied", "optional"
    ]
    return not any(marker in name for marker in optional_markers)


def merge_database_first_material(materials_by_key: dict, candidate: dict, source_priority: int):
    name = (candidate.get("name") or "").strip()
    if not name:
        return

    canonical = canonical_material_name(name)
    key = canonical or normalise_ai_job_text(name)
    if not key:
        return

    quantity = safe_float(candidate.get("quantity", 1), 1)
    if quantity <= 0:
        quantity = 1

    existing = materials_by_key.get(key)
    if existing is None:
        row = dict(candidate)
        row["_priority"] = source_priority
        row["quantity"] = quantity
        row.setdefault("required", False)
        row.setdefault("reason", "")
        row.setdefault("supplier", "")
        row.setdefault("url", "")
        row.setdefault("manual_price", 0)
        row.setdefault("data_source", "database_first")
        materials_by_key[key] = row
        return

    # Higher-priority sources control the core name/reason, while quantities
    # and required flags accumulate safely.
    if source_priority > existing.get("_priority", 0):
        old_quantity = existing.get("quantity", 1)
        old_required = existing.get("required", False)
        old_supplier = existing.get("supplier", "")
        old_url = existing.get("url", "")
        old_price = existing.get("manual_price", 0)

        replacement = dict(candidate)
        replacement["_priority"] = source_priority
        replacement["quantity"] = max(quantity, safe_float(old_quantity, 1))
        replacement["required"] = bool(candidate.get("required", False) or old_required)
        replacement["supplier"] = candidate.get("supplier") or old_supplier
        replacement["url"] = candidate.get("url") or old_url
        replacement["manual_price"] = safe_float(candidate.get("manual_price", old_price), old_price)
        replacement.setdefault("data_source", "database_first")
        materials_by_key[key] = replacement
    else:
        existing["quantity"] = max(safe_float(existing.get("quantity", 1), 1), quantity)
        existing["required"] = bool(existing.get("required", False) or candidate.get("required", False))
        if not existing.get("reason") and candidate.get("reason"):
            existing["reason"] = candidate.get("reason")
        if not existing.get("supplier") and candidate.get("supplier"):
            existing["supplier"] = candidate.get("supplier")
        if not existing.get("url") and candidate.get("url"):
            existing["url"] = candidate.get("url")
        if safe_float(existing.get("manual_price", 0), 0) <= 0:
            existing["manual_price"] = safe_float(candidate.get("manual_price", 0), 0)


def resolve_database_first_material(candidate: dict, job: str, quote_type: str):
    original_name = (candidate.get("name") or "").strip()
    matches = find_ai_material_matches(original_name, limit=8)

    best = matches[0] if matches and matches[0].get("match_score", 0) >= 35 else None
    resolved_name = best.get("name") if best else original_name

    quantity_info = learned_material_quantity_from_quotes(
        resolved_name,
        job,
        quote_type
    )
    requested_qty = safe_float(candidate.get("quantity", 1), 1)
    learned_qty = safe_float(quantity_info.get("quantity", 0), 0)
    quantity = learned_qty if quantity_info.get("source") == "learned" and learned_qty > 0 else requested_qty

    supplier_pref = supplier_preference_for_material(resolved_name)
    preferred_supplier = supplier_pref.get("preferred_supplier", "")

    chosen = best
    if preferred_supplier and matches:
        preferred_rows = [
            item for item in matches
            if (item.get("supplier") or "").lower() == preferred_supplier.lower()
            and item.get("match_score", 0) >= 30
        ]
        if preferred_rows:
            chosen = preferred_rows[0]
            resolved_name = chosen.get("name") or resolved_name

    supplier = (chosen.get("supplier") if chosen else "") or preferred_supplier or candidate.get("supplier") or "City Plumbing"
    url = (chosen.get("url") if chosen else "") or candidate.get("url") or ""
    manual_price = safe_float(
        (chosen.get("manual_price") if chosen else 0) or candidate.get("manual_price", 0),
        0
    )

    return {
        "name": resolved_name,
        "quantity": round(quantity, 2),
        "supplier": supplier,
        "url": url,
        "manual_price": round(manual_price, 2),
        "reason": candidate.get("reason", ""),
        "required": bool(candidate.get("required", False)),
        "data_source": (
            "database_first_saved_material"
            if chosen and chosen.get("source") == "saved"
            else "database_first_library"
            if chosen
            else candidate.get("data_source", "database_first_rule")
        ),
        "quantity_source": quantity_info.get("source", "rule"),
        "learned_used_count": quantity_info.get("used_count", 0),
        "original_rule_name": original_name,
        "match_score": chosen.get("match_score", 0) if chosen else 0,
    }


def build_database_first_kit(
    job: str,
    quote_type: str,
    history: dict,
    compact_templates: list,
    fallback_matches: list,
    forgotten: list
):
    materials_by_key = {}

    # 1. Historical common materials are the strongest business evidence.
    for item in (history.get("common_materials", []) or [])[:20]:
        used_percent = safe_float(item.get("used_percent", 0), 0)
        avg_qty = safe_float(item.get("average_quantity", 1), 1)
        merge_database_first_material(materials_by_key, {
            "name": item.get("name", ""),
            "quantity": avg_qty,
            "supplier": item.get("supplier", ""),
            "manual_price": safe_float(item.get("average_unit_price", 0), 0),
            "required": used_percent >= 75,
            "reason": f"Used in {round(used_percent)}% of similar saved quotes.",
            "data_source": "historical_quote_pattern",
        }, 100)

    # 2. Saved/trade templates provide the standard kit structure.
    for template in compact_templates[:5]:
        template_name = template.get("name") or template.get("job") or "matching trade template"
        for item in template.get("materials", []) or []:
            if isinstance(item, str):
                item = {"name": item, "quantity": 1}
            if not isinstance(item, dict):
                continue
            merge_database_first_material(materials_by_key, {
                "name": item.get("name", ""),
                "quantity": item.get("quantity", item.get("qty", 1)),
                "supplier": item.get("supplier", ""),
                "url": item.get("url", ""),
                "manual_price": item.get("manual_price", item.get("price", 0)),
                "required": ai_material_required_from_template(item),
                "reason": f"Included by trade template: {template_name}.",
                "data_source": "trade_template",
            }, 80)

    # 3. Controlled kits fill gaps where the database has limited history.
    for fallback in fallback_matches[:2]:
        for item in fallback.get("materials", []) or []:
            merge_database_first_material(materials_by_key, {
                **item,
                "data_source": "controlled_trade_kit",
            }, 60)

    # 4. Forgotten-item rules act as a final checklist.
    for warning in forgotten or []:
        for name in warning.get("missing", []) or []:
            merge_database_first_material(materials_by_key, {
                "name": name,
                "quantity": suggest_material_quantity(name, job),
                "required": False,
                "reason": warning.get("reason", "Common companion material to check."),
                "data_source": "forgotten_item_check",
            }, 40)

    resolved = [
        resolve_database_first_material(item, job, quote_type)
        for item in materials_by_key.values()
    ]

    resolved.sort(
        key=lambda item: (
            1 if item.get("required") else 0,
            1 if item.get("data_source") == "historical_quote_pattern" else 0,
            1 if safe_float(item.get("manual_price", 0), 0) > 0 else 0,
            item.get("name", "")
        ),
        reverse=True
    )

    return resolved[:30]


def enforce_database_first_kit(draft: dict, context: dict):
    if not isinstance(draft, dict):
        draft = {}

    kit = context.get("database_first_kit", []) or []
    ai_materials = draft.get("materials", []) or []

    ai_by_canonical = {}
    for item in ai_materials:
        if not isinstance(item, dict):
            continue
        key = canonical_material_name(item.get("name", ""))
        if key:
            ai_by_canonical[key] = item

    final_materials = []
    for database_item in kit:
        item = dict(database_item)
        key = canonical_material_name(item.get("name", ""))
        ai_item = ai_by_canonical.get(key)

        # AI may improve wording/reason or required status, but cannot overwrite
        # the database name, URL, supplier or saved price.
        if ai_item:
            if ai_item.get("reason"):
                item["reason"] = ai_item.get("reason")
            item["required"] = bool(item.get("required") or ai_item.get("required"))

        final_materials.append(item)

    # Allow genuinely new AI gap-fill items only when they are not duplicates.
    existing_keys = {
        canonical_material_name(item.get("name", ""))
        for item in final_materials
    }
    for ai_item in ai_materials:
        if not isinstance(ai_item, dict):
            continue
        key = canonical_material_name(ai_item.get("name", ""))
        if not key or key in existing_keys:
            continue
        gap_item = resolve_database_first_material({
            **ai_item,
            "data_source": "ai_gap_fill",
        }, context.get("request", {}).get("normalised_job_description", ""),
           context.get("request", {}).get("quote_type", ""))
        final_materials.append(gap_item)
        existing_keys.add(key)

    draft["materials"] = final_materials[:30]
    draft["database_first_summary"] = {
        "kit_items": len(kit),
        "historical_items": sum(1 for x in kit if x.get("data_source") == "historical_quote_pattern"),
        "template_items": sum(1 for x in kit if x.get("data_source") == "trade_template"),
        "saved_material_matches": sum(
            1 for x in final_materials
            if x.get("data_source") in {
                "database_first_saved_material",
                "preferred_supplier_history"
            }
        ),
        "priced_items": sum(1 for x in final_materials if safe_float(x.get("manual_price", 0), 0) > 0),
        "learned_quantities": sum(1 for x in final_materials if x.get("quantity_source") == "learned"),
        "materials_total_before_handling": round(sum(
            safe_float(x.get("manual_price", 0), 0) *
            safe_float(x.get("quantity", 1), 1)
            for x in final_materials
        ), 2),
    }

    return draft



SMART_JOB_MATERIAL_KITS = [
    {
        "job_type": "outside_tap",
        "display_name": "Outside tap installation/replacement",
        "keywords": [
            "outside tap", "garden tap", "external tap", "hose union bib tap",
            "replace outside tap", "fit outside tap"
        ],
        "exclude_keywords": ["toilet", "wc", "basin waste", "sink waste", "shower waste"],
        "labour_range": [150, 280],
        "materials": [
            {"name": "Outside tap kit", "quantity": 1, "required": True, "reason": "Main tap and wall-plate assembly."},
            {"name": "15mm isolating valve", "quantity": 1, "required": True, "reason": "Internal isolation for maintenance and winter shut-off."},
            {"name": "Double check valve 15mm", "quantity": 1, "required": True, "reason": "Backflow protection where required."},
            {"name": "15mm copper pipe", "quantity": 3, "required": False, "reason": "Provisional allowance until the route is measured."},
            {"name": "15mm wall plate elbow", "quantity": 1, "required": True, "reason": "Provides a secure wall termination for the tap."},
            {"name": "15mm pipe clips", "quantity": 6, "required": False, "reason": "Supports the internal or external pipe route."},
            {"name": "PTFE tape", "quantity": 0.1, "required": False, "reason": "Small consumable allowance for threaded connections."},
            {"name": "Sanitary silicone", "quantity": 0.1, "required": False, "reason": "Seal around the wall penetration or tap plate if needed."},
            {"name": "Drain off cock 15mm", "quantity": 1, "required": False, "reason": "Optional where exposed pipework needs winter draining."},
        ],
        "questions": [
            "How long is the approximate pipe run?",
            "Can the pipe pass directly through the wall?",
            "Will any pipework remain exposed externally?",
            "Is there a suitable internal cold-water supply and working isolation point?"
        ]
    },
    {
        "job_type": "tap_replacement",
        "display_name": "Tap replacement",
        "keywords": ["replace tap", "replace taps", "kitchen tap", "basin tap", "mixer tap", "fit new tap"],
        "exclude_keywords": ["outside tap", "garden tap"],
        "labour_range": [120, 220],
        "materials": [
            {"name": "Replacement tap", "quantity": 1, "required": False, "reason": "Include only if Nigel is supplying the tap."},
            {"name": "15mm isolating valve", "quantity": 2, "required": False, "reason": "Use where existing valves are absent, seized or unreliable."},
            {"name": "Flexible tap connector", "quantity": 2, "required": False, "reason": "Use if existing tails are unsuitable or not supplied."},
            {"name": "PTFE tape", "quantity": 0.1, "required": False, "reason": "Small consumable allowance."},
            {"name": "Sanitary silicone", "quantity": 0.1, "required": False, "reason": "May be needed around the tap base."},
        ],
        "questions": [
            "Who is supplying the replacement tap?",
            "Are working isolation valves present?",
            "Is access underneath restricted?"
        ]
    },
    {
        "job_type": "toilet_replacement",
        "display_name": "Toilet replacement",
        "keywords": ["replace toilet", "toilet replacement", "replace wc", "fit new toilet"],
        "exclude_keywords": [],
        "labour_range": [180, 320],
        "materials": [
            {"name": "Replacement toilet", "quantity": 1, "required": False, "reason": "Include only if Nigel is supplying it."},
            {"name": "Pan connector", "quantity": 1, "required": True, "reason": "Connects the pan to the soil outlet."},
            {"name": "Toilet fixing kit", "quantity": 1, "required": True, "reason": "Secures the toilet."},
            {"name": "15mm isolating valve", "quantity": 1, "required": False, "reason": "Use if existing isolation is missing or unreliable."},
            {"name": "Flexible tap connector", "quantity": 1, "required": False, "reason": "May be required for the cistern inlet."},
            {"name": "Sanitary silicone", "quantity": 0.25, "required": True, "reason": "Seal around the installation where appropriate."},
        ],
        "questions": [
            "Is the replacement close-coupled, back-to-wall or wall-hung?",
            "Does it match the existing soil outlet position?",
            "Who is supplying the toilet?"
        ]
    },
    {
        "job_type": "bath_to_shower_conversion",
        "display_name": "Bath removal and shower tray/enclosure installation",
        "keywords": [
            "replace bath with shower", "remove bath and fit shower", "remove bath fit shower",
            "bath to shower", "shower tray and screen", "shower tray and enclosure",
            "remove the bath", "replace the bath"
        ],
        "exclude_keywords": [],
        "labour_range": [900, 1800],
        "materials": [
            {"name": "Shower tray", "quantity": 1, "required": True, "reason": "Main shower base; confirm dimensions and handing before ordering."},
            {"name": "Shower screen / enclosure", "quantity": 1, "required": True, "reason": "Confirm opening, handing and tray compatibility before ordering."},
            {"name": "90mm shower waste", "quantity": 1, "required": True, "reason": "Waste fitting for the shower tray."},
            {"name": "40mm waste pipe", "quantity": 2, "required": False, "reason": "Provisional allowance for adapting the shower waste run."},
            {"name": "40mm waste bend", "quantity": 2, "required": False, "reason": "Provisional fittings for the waste route."},
            {"name": "15mm copper pipe", "quantity": 3, "required": False, "reason": "Provisional allowance for hot/cold pipe alterations."},
            {"name": "15mm copper elbow", "quantity": 4, "required": False, "reason": "Quick-adjust fitting allowance; set the quantity after checking the route."},
            {"name": "15mm copper tee", "quantity": 2, "required": False, "reason": "Quick-adjust fitting allowance where branches are required."},
            {"name": "15mm copper coupler", "quantity": 2, "required": False, "reason": "Quick-adjust fitting allowance for pipe alterations."},
            {"name": "15mm isolating valve", "quantity": 2, "required": False, "reason": "Use where suitable service isolation is required."},
            {"name": "Sanitary silicone", "quantity": 1, "required": True, "reason": "Seal tray/screen junctions and disturbed sanitary edges."},
            {"name": "18mm plywood", "quantity": 1, "required": False, "reason": "Include when a rigid tray base is required."},
            {"name": "3x2 treated timber", "quantity": 4, "required": False, "reason": "Include when building a raised/supporting tray base."},
            {"name": "Waterproof tile backer board", "quantity": 2, "required": False, "reason": "Use where the shower area needs rebuilding or waterproof backing."},
            {"name": "Waterproofing tape / tanking", "quantity": 1, "required": False, "reason": "Use where disturbed shower walls require waterproofing."}
        ],
        "questions": [
            "What are the exact shower tray dimensions and waste position?",
            "Is the enclosure a pivot, sliding, quadrant or fixed screen, and what handing is required?",
            "Is Nigel supplying the tray and enclosure?",
            "How much 15mm copper and 40mm waste pipe is actually required?",
            "Does the tray need a raised timber/ply base?"
        ]
    },
    {
        "job_type": "shower_replacement",
        "display_name": "Shower replacement",
        "keywords": ["replace shower", "remove old shower", "fit new shower", "replacement shower"],
        "exclude_keywords": ["shower tray", "shower waste"],
        "labour_range": [180, 350],
        "materials": [
            {"name": "Replacement shower unit", "quantity": 1, "required": False, "reason": "Include only if Nigel is supplying the shower."},
            {"name": "Sanitary silicone", "quantity": 1, "required": True, "reason": "Seal disturbed areas around the replacement."},
            {"name": "Suitable wall fixings", "quantity": 1, "required": True, "reason": "Fixings depend on wall construction."},
            {"name": "PTFE tape", "quantity": 0.1, "required": False, "reason": "Small consumable allowance."},
            {"name": "15mm copper olives", "quantity": 2, "required": False, "reason": "May be needed if compression joints are disturbed."},
            {"name": "Shower connection adaptors", "quantity": 2, "required": False, "reason": "Only if inlet centres or connections differ."},
        ],
        "questions": [
            "Is it electric, exposed mixer, concealed mixer, digital or pumped?",
            "Who is supplying the shower?",
            "Does the replacement match the existing inlet positions?"
        ]
    },
    {
        "job_type": "radiator_replacement",
        "display_name": "Radiator replacement",
        "keywords": ["replace radiator", "fit radiator", "new radiator", "radiator replacement"],
        "exclude_keywords": ["trv only", "replace trv"],
        "labour_range": [180, 350],
        "materials": [
            {"name": "Radiator", "quantity": 1, "required": False, "reason": "Include only if Nigel is supplying it."},
            {"name": "TRV valve", "quantity": 1, "required": False, "reason": "Use if new valves are required."},
            {"name": "Lockshield valve", "quantity": 1, "required": False, "reason": "Matching return valve."},
            {"name": "Radiator valve tail", "quantity": 2, "required": False, "reason": "Required with new valves or radiator connections."},
            {"name": "Central heating inhibitor", "quantity": 1, "required": True, "reason": "System protection after draining and refilling."},
            {"name": "PTFE tape", "quantity": 0.1, "required": False, "reason": "Small consumable allowance."},
        ],
        "questions": [
            "Are the new radiator dimensions the same?",
            "Does the whole system need draining?",
            "Who is supplying the radiator?"
        ]
    },
    {
        "job_type": "trv_replacement",
        "display_name": "TRV replacement",
        "keywords": ["replace trv", "change trv", "thermostatic radiator valve", "trv valve"],
        "exclude_keywords": [],
        "labour_range": [120, 250],
        "materials": [
            {"name": "TRV valve", "quantity": 1, "required": True, "reason": "Replacement thermostatic valve."},
            {"name": "Radiator valve tail", "quantity": 1, "required": False, "reason": "May be required if the existing tail is incompatible."},
            {"name": "15mm copper olives", "quantity": 1, "required": False, "reason": "May be required for a renewed compression joint."},
            {"name": "PTFE tape", "quantity": 0.1, "required": False, "reason": "Small consumable allowance."},
            {"name": "Central heating inhibitor", "quantity": 1, "required": False, "reason": "Use if the system is drained/refilled."},
        ],
        "questions": [
            "Does the system need fully draining?",
            "Is the valve angled or straight?",
            "Is the existing tail compatible?"
        ]
    },
    {
        "job_type": "basin_waste",
        "display_name": "Basin waste replacement",
        "keywords": ["basin waste", "replace basin waste", "bottle trap", "basin trap"],
        "exclude_keywords": ["kitchen sink", "bath waste"],
        "labour_range": [100, 180],
        "materials": [
            {"name": "Basin waste", "quantity": 1, "required": True, "reason": "Replacement waste fitting."},
            {"name": "Bottle trap", "quantity": 1, "required": False, "reason": "Use if replacing or if existing trap is unsuitable."},
            {"name": "32mm waste pipe", "quantity": 1, "required": False, "reason": "Only if pipework alteration is needed."},
            {"name": "32mm waste bend", "quantity": 1, "required": False, "reason": "Only if alignment requires it."},
            {"name": "Sanitary silicone", "quantity": 0.1, "required": False, "reason": "Seal where required."},
        ],
        "questions": [
            "Is the basin slotted or unslotted?",
            "Is the existing trap being retained?",
            "Is pipework alteration required?"
        ]
    },
    {
        "job_type": "kitchen_sink_waste",
        "display_name": "Kitchen sink waste",
        "keywords": ["kitchen sink waste", "sink waste", "replace sink waste"],
        "exclude_keywords": ["basin"],
        "labour_range": [120, 220],
        "materials": [
            {"name": "Kitchen sink waste kit", "quantity": 1, "required": True, "reason": "Main sink waste assembly."},
            {"name": "40mm waste pipe", "quantity": 1, "required": False, "reason": "Only if pipework alteration is required."},
            {"name": "40mm waste bend", "quantity": 1, "required": False, "reason": "Only if alignment requires it."},
            {"name": "Appliance waste spigot", "quantity": 1, "required": False, "reason": "Only where dishwasher or washing machine connects."},
        ],
        "questions": [
            "Is it a single or double bowl sink?",
            "Are appliances connected to the waste?",
            "Is existing pipework being retained?"
        ]
    },
]


def classify_smart_job(job_text: str):
    job = normalise_ai_job_text(job_text)
    best = None
    best_score = 0

    for kit in SMART_JOB_MATERIAL_KITS:
        if any(ex in job for ex in kit.get("exclude_keywords", [])):
            continue

        score = 0
        for phrase in kit.get("keywords", []):
            phrase = normalise_ai_job_text(phrase)
            if phrase in job:
                score += 20 + len(phrase.split()) * 3
            else:
                score += len(ai_text_tokens(phrase).intersection(ai_text_tokens(job))) * 3

        if score > best_score:
            best = kit
            best_score = score

    if best_score < 8:
        return None

    return {**best, "classification_score": best_score}


def smart_kit_allowed_names(kit: dict):
    return {
        canonical_material_name(item.get("name", ""))
        for item in (kit or {}).get("materials", [])
        if item.get("name")
    }


def build_smart_job_kit(job: str, quote_type: str, history: dict):
    classification = classify_smart_job(job)
    if not classification:
        return {
            "classification": None,
            "materials": [],
            "questions": [],
            "labour_range": [],
        }

    materials = []
    seen = set()

    # Start only with the approved checklist for this job.
    for rule_item in classification.get("materials", []):
        resolved = resolve_database_first_material(rule_item, job, quote_type)
        key = canonical_material_name(resolved.get("name", ""))
        if key and key not in seen:
            materials.append(resolved)
            seen.add(key)

    # Historical evidence may adjust matching checklist quantities/prices,
    # but may not introduce unrelated categories.
    allowed = smart_kit_allowed_names(classification)
    for historical in (history.get("common_materials", []) or []):
        hist_name = historical.get("name", "")
        hist_can = canonical_material_name(hist_name)

        matched_rule = None
        for rule_item in classification.get("materials", []):
            rule_can = canonical_material_name(rule_item.get("name", ""))
            if (
                hist_can == rule_can
                or hist_can in rule_can
                or rule_can in hist_can
            ):
                matched_rule = rule_item
                break

        if not matched_rule:
            continue

        for item in materials:
            item_can = canonical_material_name(item.get("name", ""))
            rule_can = canonical_material_name(matched_rule.get("name", ""))
            if item_can == hist_can or item_can == rule_can or hist_can in item_can or item_can in hist_can:
                avg_qty = safe_float(historical.get("average_quantity", 0), 0)
                if avg_qty > 0:
                    item["quantity"] = round(avg_qty, 2)
                    item["quantity_source"] = "historical_job_type"
                    item["learned_used_count"] = historical.get("used_count", 0)
                avg_price = safe_float(historical.get("average_unit_price", 0), 0)
                if avg_price > 0 and safe_float(item.get("manual_price", 0), 0) <= 0:
                    item["manual_price"] = round(avg_price, 2)
                if historical.get("supplier") and not item.get("supplier"):
                    item["supplier"] = historical.get("supplier")
                break

    responsibility = detect_supply_responsibility(
        job,
        classification.get("job_type")
    )
    materials, removed_customer_items = apply_supply_responsibility_to_materials(
        materials,
        classification.get("job_type"),
        responsibility
    )

    return {
        "classification": {
            "job_type": classification.get("job_type"),
            "display_name": classification.get("display_name"),
            "score": classification.get("classification_score"),
        },
        "materials": materials,
        "questions": classification.get("questions", []),
        "labour_range": classification.get("labour_range", []),
        "supply_responsibility": responsibility,
        "customer_supplied_items_removed": [
            item.get("name", "") for item in removed_customer_items
        ],
    }


def enforce_smart_job_kit(draft: dict, context: dict):
    if not isinstance(draft, dict):
        draft = {}

    smart = context.get("smart_job_kit", {}) or {}
    classification = smart.get("classification")
    kit = smart.get("materials", []) or []

    if not classification:
        return enforce_database_first_kit(draft, context)

    allowed_keys = {
        canonical_material_name(item.get("name", ""))
        for item in kit
    }

    # AI can improve wording and required/optional status only.
    ai_materials = draft.get("materials", []) or []
    ai_map = {
        canonical_material_name(item.get("name", "")): item
        for item in ai_materials
        if isinstance(item, dict) and item.get("name")
    }

    final = []
    for item in kit:
        row = dict(item)
        key = canonical_material_name(row.get("name", ""))
        ai_item = ai_map.get(key)
        if ai_item:
            if ai_item.get("reason"):
                row["reason"] = ai_item.get("reason")
            row["required"] = bool(row.get("required") or ai_item.get("required"))
        final.append(row)

    # Do not allow AI to append materials outside the approved kit.
    draft["materials"] = final
    draft["smart_job_summary"] = {
        "job_type": classification.get("job_type"),
        "display_name": classification.get("display_name"),
        "classification_score": classification.get("score"),
        "kit_items": len(final),
        "priced_items": sum(1 for item in final if safe_float(item.get("manual_price", 0), 0) > 0),
        "saved_material_matches": sum(
            1 for item in final
            if item.get("data_source") in {
                "database_first_saved_material",
                "database_first_library"
            }
        ),
        "learned_quantities": sum(
            1 for item in final
            if item.get("quantity_source") in {"learned", "historical_job_type"}
        ),
        "materials_total_before_handling": round(sum(
            safe_float(item.get("manual_price", 0), 0) *
            safe_float(item.get("quantity", 1), 1)
            for item in final
        ), 2),
        "supply_responsibility": smart.get("supply_responsibility", "unknown"),
        "customer_supplied_items_removed": smart.get("customer_supplied_items_removed", []),
    }

    if smart.get("questions"):
        existing_questions = draft.get("questions_to_confirm", []) or []
        merged_questions = []
        seen_q = set()
        for q in smart.get("questions", []) + existing_questions:
            key = normalise_ai_job_text(q)
            if key and key not in seen_q:
                seen_q.add(key)
                merged_questions.append(q)
        draft["questions_to_confirm"] = merged_questions[:12]

    return draft



MULTI_JOB_CONNECTORS = [
    " and also ", " plus ", " as well as ", " then ", " additionally ",
    " also fit ", " also replace ", " also install ", " also repair "
]



CONTEXT_NOTE_PATTERNS = {
    "customer_supply": [
        r"\bcustomer (?:is )?supplying\b",
        r"\bcustomer supplied\b",
        r"\bcustomer to supply\b",
        r"\bclient (?:is )?supplying\b",
        r"\bclient supplied\b",
        r"\bsupplied by customer\b",
        r"\bsupplied by client\b",
    ],
    "business_supply": [
        r"\bnigel (?:is )?supplying\b",
        r"\bnigel harvey ltd (?:is )?supplying\b",
        r"\bwe (?:are )?supplying\b",
        r"\bsupply and fit\b",
        r"\bcontractor supplying\b",
    ],
    "access": [
        r"\baccess\b",
        r"\bawkward\b",
        r"\brestricted\b",
        r"\btight space\b",
        r"\bunder (?:the )?(?:sink|basin|bath)\b",
        r"\bbehind (?:the )?(?:toilet|basin|unit)\b",
    ],
    "existing_condition": [
        r"\bexisting\b",
        r"\bleaking\b",
        r"\bseized\b",
        r"\bold\b",
        r"\bdamaged\b",
        r"\bcorroded\b",
        r"\bnot working\b",
        r"\bfailed\b",
    ],
    "additional_work": [
        r"\bmake good\b",
        r"\btil(?:e|ing)\b",
        r"\bplaster\b",
        r"\bdecorate\b",
        r"\bpaint\b",
        r"\bboxing\b",
        r"\brun new pipework\b",
        r"\bmove pipework\b",
        r"\balter pipework\b",
        r"\bremove and refit\b",
        r"\bdispose\b",
    ],
    "measurement": [
        r"\b\d+(?:\.\d+)?\s*(?:mm|cm|m|metre|metres)\b",
        r"\bpipe run\b",
        r"\bcentres?\b",
        r"\bheight\b",
        r"\bwidth\b",
        r"\bdepth\b",
    ],
}


def classify_context_note(sentence: str):
    text = normalise_ai_job_text(sentence)
    matched = []
    for note_type, patterns in CONTEXT_NOTE_PATTERNS.items():
        if any(re.search(pattern, text, flags=re.I) for pattern in patterns):
            matched.append(note_type)
    return matched


def sentence_starts_new_job(sentence: str):
    text = normalise_ai_job_text(sentence)
    classification = classify_smart_job(sentence)
    if not classification:
        return False

    # A supply-only or condition-only statement is contextual, not a new job.
    action_words = re.findall(
        r"\b(?:replace|fit|install|repair|change|remove|supply and fit|move|relocate|renew)\b",
        text,
        flags=re.I
    )
    supply_note = any(
        re.search(pattern, text, flags=re.I)
        for pattern in CUSTOMER_SUPPLY_PATTERNS + BUSINESS_SUPPLY_PATTERNS
    )
    if supply_note and not action_words:
        return False

    return bool(action_words)


def attach_context_to_job(job_record: dict, sentence: str):
    note_types = classify_context_note(sentence)
    job_record.setdefault("context_notes", []).append({
        "text": sentence.strip(),
        "types": note_types,
    })

    if "customer_supply" in note_types:
        job_record["supply_responsibility"] = "customer"
    elif "business_supply" in note_types:
        job_record["supply_responsibility"] = "business"

    return job_record


def parse_context_aware_jobs(job_text: str):
    original = (job_text or "").strip()
    if not original:
        return {
            "jobs": [],
            "unattached_notes": [],
        }

    # Preserve line order, then split obvious sentence boundaries.
    raw_lines = re.split(r"[\n\r]+", original)
    sentences = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        parts = re.split(r"(?<=[.;!?])\s+", line)
        for part in parts:
            part = part.strip(" .;,-")
            if part:
                sentences.append(part)

    jobs = []
    unattached = []
    current = None

    for sentence in sentences:
        if sentence_starts_new_job(sentence):
            classification = classify_smart_job(sentence)
            current = {
                "job_text": sentence,
                "job_type": classification.get("job_type"),
                "display_name": classification.get("display_name"),
                "classification_score": classification.get("classification_score"),
                "context_notes": [],
                "supply_responsibility": detect_supply_responsibility(
                    sentence,
                    classification.get("job_type")
                ),
            }
            jobs.append(current)
            continue

        # Context note belongs to the most recent job where possible.
        if current is not None:
            attach_context_to_job(current, sentence)
        else:
            unattached.append(sentence)

    # Merge accidental consecutive duplicates of the same physical job.
    merged = []
    for job in jobs:
        if (
            merged
            and merged[-1].get("job_type") == job.get("job_type")
            and normalise_ai_job_text(merged[-1].get("job_text", "")) == normalise_ai_job_text(job.get("job_text", ""))
        ):
            merged[-1]["context_notes"].extend(job.get("context_notes", []))
            if job.get("supply_responsibility") != "unknown":
                merged[-1]["supply_responsibility"] = job.get("supply_responsibility")
            continue
        merged.append(job)

    return {
        "jobs": merged[:10],
        "unattached_notes": unattached,
    }


def context_notes_as_text(job_record: dict):
    return " ".join(
        note.get("text", "")
        for note in job_record.get("context_notes", [])
        if note.get("text")
    ).strip()


def context_note_summary(job_record: dict):
    groups = {}
    for note in job_record.get("context_notes", []):
        for note_type in note.get("types", []):
            groups.setdefault(note_type, []).append(note.get("text", ""))
    return groups


def split_multi_job_description(job_text: str):
    parsed = parse_context_aware_jobs(job_text)
    return [
        job.get("job_text", "")
        for job in parsed.get("jobs", [])
        if job.get("job_text")
    ]


def smart_job_labour_suggestion(job_segment: str, classification: dict, quote_type: str):
    labour_range = classification.get("labour_range", []) if classification else []
    minimum = safe_float(labour_range[0], 0) if len(labour_range) >= 1 else 0
    maximum = safe_float(labour_range[1], 0) if len(labour_range) >= 2 else minimum

    intelligence = labour_intelligence_for_job(
        job_segment,
        quote_type,
        0
    ) if "labour_intelligence_for_job" in globals() else {}

    learned = safe_float(
        intelligence.get("average_labour", intelligence.get("average", 0)),
        0
    )

    if learned > 0:
        if minimum > 0 and maximum > 0:
            learned = min(max(learned, minimum), maximum)
        return round(learned, 2), "labour_history"

    if minimum > 0 and maximum > 0:
        return round((minimum + maximum) / 2, 2), "smart_job_range"
    if minimum > 0:
        return round(minimum, 2), "smart_job_range"

    return 0, "unpriced"


def merge_multi_job_materials(job_records: list):
    merged = {}

    fractional_consumables = {
        canonical_material_name("PTFE tape"),
        canonical_material_name("Sanitary silicone"),
        canonical_material_name("Central heating inhibitor"),
    }

    for job_record in job_records:
        job_number = job_record.get("job_number")
        job_name = job_record.get("display_name", "")
        for material in job_record.get("materials", []) or []:
            row = dict(material)
            key = canonical_material_name(row.get("name", ""))
            if not key:
                continue

            quantity = safe_float(row.get("quantity", 1), 1)
            if key not in merged:
                row["used_for_jobs"] = [job_number]
                row["used_for_job_names"] = [job_name]
                merged[key] = row
                continue

            existing = merged[key]
            existing_qty = safe_float(existing.get("quantity", 1), 1)

            # Consumable fractions accumulate; identical reusable fittings also
            # accumulate because each separate job may need its own item.
            existing["quantity"] = round(existing_qty + quantity, 2)
            existing["required"] = bool(existing.get("required") or row.get("required"))

            if job_number not in existing.get("used_for_jobs", []):
                existing.setdefault("used_for_jobs", []).append(job_number)
            if job_name and job_name not in existing.get("used_for_job_names", []):
                existing.setdefault("used_for_job_names", []).append(job_name)

            if not existing.get("url") and row.get("url"):
                existing["url"] = row.get("url")
            if not existing.get("supplier") and row.get("supplier"):
                existing["supplier"] = row.get("supplier")
            if safe_float(existing.get("manual_price", 0), 0) <= 0:
                existing["manual_price"] = safe_float(row.get("manual_price", 0), 0)

    rows = list(merged.values())
    rows.sort(
        key=lambda item: (
            1 if item.get("required") else 0,
            len(item.get("used_for_jobs", [])),
            item.get("name", "")
        ),
        reverse=True
    )
    return rows



CUSTOMER_SUPPLY_PATTERNS = [
    r"\bcustomer (?:is )?supplying\b",
    r"\bcustomer supplied\b",
    r"\bcustomer to supply\b",
    r"\bclient (?:is )?supplying\b",
    r"\bclient supplied\b",
    r"\bclient to supply\b",
    r"\bowner (?:is )?supplying\b",
    r"\bowner supplied\b",
    r"\bsupplied by customer\b",
    r"\bsupplied by client\b",
]

BUSINESS_SUPPLY_PATTERNS = [
    r"\bnigel (?:is )?supplying\b",
    r"\bnigel harvey ltd (?:is )?supplying\b",
    r"\bwe (?:are )?supplying\b",
    r"\bsupply and fit\b",
    r"\bcontractor supplying\b",
]

MAIN_ITEM_BY_JOB_TYPE = {
    "outside_tap": ["outside tap kit", "outside tap", "hose union bib tap"],
    "tap_replacement": ["replacement tap", "kitchen tap", "basin tap", "mixer tap"],
    "toilet_replacement": ["replacement toilet", "toilet", "wc"],
    "shower_replacement": ["replacement shower unit", "replacement shower", "shower"],
    "radiator_replacement": ["radiator"],
    "trv_replacement": ["trv valve", "thermostatic radiator valve"],
    "basin_waste": ["basin waste"],
    "kitchen_sink_waste": ["kitchen sink waste kit", "sink waste kit"],
}


def detect_supply_responsibility(job_text: str, job_type: str):
    text = normalise_ai_job_text(job_text)

    customer_supplied = any(re.search(pattern, text, flags=re.I) for pattern in CUSTOMER_SUPPLY_PATTERNS)
    business_supplied = any(re.search(pattern, text, flags=re.I) for pattern in BUSINESS_SUPPLY_PATTERNS)

    if customer_supplied and not business_supplied:
        return "customer"
    if business_supplied and not customer_supplied:
        return "business"
    if customer_supplied and business_supplied:
        return "mixed"
    return "unknown"


def is_main_supply_item(material_name: str, job_type: str):
    canonical = canonical_material_name(material_name)
    for candidate in MAIN_ITEM_BY_JOB_TYPE.get(job_type, []):
        candidate_can = canonical_material_name(candidate)
        if canonical == candidate_can or candidate_can in canonical or canonical in candidate_can:
            return True
    return False


def apply_supply_responsibility_to_materials(materials: list, job_type: str, responsibility: str):
    rows = []
    removed = []

    for material in materials or []:
        row = dict(material)
        main_item = is_main_supply_item(row.get("name", ""), job_type)

        if responsibility == "customer" and main_item:
            removed.append(row)
            continue

        if responsibility == "business" and main_item:
            row["required"] = True
            row["reason"] = (
                row.get("reason", "") +
                " Nigel Harvey Ltd is supplying this main item."
            ).strip()

        if responsibility == "unknown" and main_item:
            row["required"] = False

        rows.append(row)

    return rows, removed


def labour_confidence_for_job(record: dict):
    similar = int(record.get("similar_quotes", 0) or 0)
    source = record.get("labour_source", "")

    if source == "labour_history" and similar >= 3:
        return {
            "level": "high",
            "message": f"Based on {similar} similar saved quotes."
        }
    if source == "labour_history" and similar >= 1:
        return {
            "level": "medium",
            "message": f"Based on {similar} similar saved quote(s)."
        }
    if source == "smart_job_range":
        return {
            "level": "medium",
            "message": "Based on the approved labour range for this job type."
        }
    return {
        "level": "low",
        "message": "Requires manual labour review."
    }


def merge_multi_job_materials_with_summary(job_records: list):
    before_count = sum(len(record.get("materials", []) or []) for record in job_records)
    merged = merge_multi_job_materials(job_records)
    after_count = len(merged)

    return merged, {
        "materials_before_merge": before_count,
        "unique_materials_after_merge": after_count,
        "duplicates_merged": max(0, before_count - after_count),
    }


def build_multi_job_estimate(job_text: str, quote_type: str):
    parsed = parse_context_aware_jobs(job_text)
    parsed_jobs = parsed.get("jobs", [])
    records = []
    unclassified = list(parsed.get("unattached_notes", []))

    for parsed_job in parsed_jobs:
        segment = parsed_job.get("job_text", "")
        classification = classify_smart_job(segment)
        if not classification:
            unclassified.append(segment)
            continue

        history = analyse_similar_quotes(segment, quote_type)
        smart = build_smart_job_kit(segment, quote_type, history)
        labour, labour_source = smart_job_labour_suggestion(
            segment,
            classification,
            quote_type
        )

        responsibility = parsed_job.get("supply_responsibility", "unknown")
        filtered_materials, removed_customer_items = apply_supply_responsibility_to_materials(
            smart.get("materials", []),
            classification.get("job_type"),
            responsibility
        )

        context_text = context_notes_as_text(parsed_job)
        record = {
            "job_number": len(records) + 1,
            "original_text": segment,
            "full_context_text": " ".join(x for x in [segment, context_text] if x).strip(),
            "job_type": classification.get("job_type"),
            "display_name": classification.get("display_name"),
            "classification_score": classification.get("classification_score"),
            "labour_suggestion": labour,
            "labour_source": labour_source,
            "materials": filtered_materials,
            "questions": smart.get("questions", []),
            "similar_quotes": history.get("similar_count", 0),
            "supply_responsibility": responsibility,
            "customer_supplied_items_removed": [
                item.get("name", "") for item in removed_customer_items
            ],
            "context_notes": parsed_job.get("context_notes", []),
            "context_note_summary": context_note_summary(parsed_job),
        }
        record["labour_confidence"] = labour_confidence_for_job(record)
        records.append(record)

    is_multi_job = len(records) >= 2
    combined_materials, merge_summary = merge_multi_job_materials_with_summary(records) if records else ([], {
        "materials_before_merge": 0,
        "unique_materials_after_merge": 0,
        "duplicates_merged": 0,
    })

    total_labour = round(sum(
        safe_float(record.get("labour_suggestion", 0), 0)
        for record in records
    ), 2)

    return {
        "is_multi_job": is_multi_job,
        "segments_found": len(parsed_jobs),
        "classified_jobs": records,
        "unclassified_segments": unclassified,
        "combined_materials": combined_materials,
        "combined_labour_suggestion": total_labour,
        "merge_summary": merge_summary,
        "context_parser_version": "v7",
    }


def enforce_multi_job_estimate(draft: dict, context: dict):
    multi = context.get("multi_job_estimate", {}) or {}
    if not multi.get("is_multi_job"):
        return enforce_smart_job_kit(draft, context)

    if not isinstance(draft, dict):
        draft = {}

    jobs = multi.get("classified_jobs", []) or []
    combined_materials = multi.get("combined_materials", []) or []

    # Database-generated materials and labour remain authoritative.
    draft["materials"] = combined_materials
    draft["labour_suggestion"] = multi.get("combined_labour_suggestion", 0)

    ai_breakdown = {
        item.get("job_type"): item
        for item in draft.get("job_breakdown", []) or []
        if isinstance(item, dict)
    }

    final_breakdown = []
    for record in jobs:
        ai_job = ai_breakdown.get(record.get("job_type"), {})
        final_breakdown.append({
            "job_number": record.get("job_number"),
            "job_type": record.get("job_type"),
            "display_name": record.get("display_name"),
            "original_text": record.get("original_text"),
            "scope": ai_job.get("scope", ""),
            "labour_suggestion": record.get("labour_suggestion", 0),
            "labour_source": record.get("labour_source", ""),
            "material_count": len(record.get("materials", [])),
            "similar_quotes": record.get("similar_quotes", 0),
            "questions": record.get("questions", []),
            "supply_responsibility": record.get("supply_responsibility", "unknown"),
            "customer_supplied_items_removed": record.get("customer_supplied_items_removed", []),
            "labour_confidence": record.get("labour_confidence", {}),
            "context_notes": record.get("context_notes", []),
            "context_note_summary": record.get("context_note_summary", {}),
        })

    draft["job_breakdown"] = final_breakdown

    questions = []
    seen_questions = set()
    for record in jobs:
        for question in record.get("questions", []) or []:
            key = normalise_ai_job_text(question)
            if key and key not in seen_questions:
                seen_questions.add(key)
                questions.append(
                    f"{record.get('display_name')}: {question}"
                )
    for question in draft.get("questions_to_confirm", []) or []:
        key = normalise_ai_job_text(question)
        if key and key not in seen_questions:
            seen_questions.add(key)
            questions.append(question)
    draft["questions_to_confirm"] = questions[:25]

    draft["multi_job_summary"] = {
        "job_count": len(jobs),
        "job_names": [record.get("display_name") for record in jobs],
        "combined_material_count": len(combined_materials),
        "priced_items": sum(
            1 for item in combined_materials
            if safe_float(item.get("manual_price", 0), 0) > 0
        ),
        "combined_labour": multi.get("combined_labour_suggestion", 0),
        "materials_total_before_handling": round(sum(
            safe_float(item.get("manual_price", 0), 0) *
            safe_float(item.get("quantity", 1), 1)
            for item in combined_materials
        ), 2),
        "unclassified_segments": multi.get("unclassified_segments", []),
        "materials_before_merge": multi.get("merge_summary", {}).get("materials_before_merge", 0),
        "duplicates_merged": multi.get("merge_summary", {}).get("duplicates_merged", 0),
        "customer_supplied_items_removed": [
            item
            for record in jobs
            for item in record.get("customer_supplied_items_removed", [])
        ],
        "context_notes_attached": sum(
            len(record.get("context_notes", []))
            for record in jobs
        ),
        "context_parser_version": multi.get("context_parser_version", "v7"),
    }

    return draft



STANDARD_QUOTE_EXCLUSIONS = [
    "Substantial making good, plastering, tiling, flooring and decoration unless specifically included.",
    "Repairs to concealed or defective existing pipework discovered after work starts.",
    "Electrical or gas work unless specifically stated and completed by a suitably qualified person.",
]


def unique_short_items(items, limit=5):
    output, seen = [], set()
    for item in items or []:
        value = re.sub(r"\s+", " ", str(item or "")).strip(" •-\n\t")
        key = normalise_ai_job_text(value)
        if value and key not in seen:
            seen.add(key)
            output.append(value)
        if len(output) >= limit:
            break
    return output


def professional_assumptions_from_context(context: dict):
    assumptions = []
    jobs = (context.get("multi_job_estimate", {}) or {}).get("classified_jobs", []) or []
    for job in jobs:
        display = job.get("display_name", "Job")
        responsibility = job.get("supply_responsibility", "unknown")
        if responsibility == "customer":
            removed = job.get("customer_supplied_items_removed", []) or []
            assumptions.append(f"{display}: customer supplies {', '.join(removed) if removed else 'the main item'}.")
        elif responsibility == "business":
            assumptions.append(f"{display}: Nigel Harvey Ltd supplies the main item.")
        summary = job.get("context_note_summary", {}) or {}
        if summary.get("access"):
            assumptions.append(f"{display}: access remains reasonably workable as described.")
        if summary.get("measurement"):
            assumptions.append(f"{display}: measurements and pipe routes remain provisional until checked on site.")

    if not jobs:
        smart = context.get("smart_job_kit", {}) or {}
        responsibility = smart.get("supply_responsibility", "unknown")
        removed = smart.get("customer_supplied_items_removed", []) or []
        if responsibility == "customer":
            assumptions.append(f"Customer supplies {', '.join(removed) if removed else 'the main item'}.")
        elif responsibility == "business":
            assumptions.append("Nigel Harvey Ltd supplies the main item.")

    assumptions.extend([
        "Existing isolation points and reusable connections are serviceable unless stated otherwise.",
        "Final compatibility is subject to checking the existing installation and supplied products.",
    ])
    return unique_short_items(assumptions, 6)


def professional_exclusions_from_context(context: dict):
    exclusions = list(STANDARD_QUOTE_EXCLUSIONS)
    note_types = set()
    for job in (context.get("multi_job_estimate", {}) or {}).get("classified_jobs", []) or []:
        for note in job.get("context_notes", []) or []:
            note_types.update(note.get("types", []) or [])
    if "additional_work" in note_types:
        exclusions[0] = (
            "Only making-good or additional work expressly described in the scope is included; "
            "other plastering, tiling, flooring and decoration are excluded."
        )
    return unique_short_items(exclusions, 5)


def calculate_estimator_confidence(draft: dict, context: dict):
    score = 45
    positives, gaps = [], []
    multi = context.get("multi_job_estimate", {}) or {}
    jobs = multi.get("classified_jobs", []) or []
    smart = context.get("smart_job_kit", {}) or {}

    if multi.get("is_multi_job") and jobs:
        score += 12
        positives.append(f"{len(jobs)} physical jobs identified and separated.")
        if not multi.get("unclassified_segments"):
            score += 5
            positives.append("All description notes were attached or classified.")
        else:
            score -= 8
            gaps.append("Some description text could not be confidently attached.")
    elif smart.get("classification"):
        score += 14
        positives.append("A recognised smart job kit was selected.")
    else:
        score -= 12
        gaps.append("No exact smart job kit was identified.")

    materials = draft.get("materials", []) or []
    if materials:
        priced = sum(1 for x in materials if safe_float(x.get("manual_price", 0), 0) > 0)
        matched = sum(1 for x in materials if x.get("data_source") not in {"ai_general", "ai_gap_fill", ""})
        if matched == len(materials):
            score += 10
            positives.append("All materials came from approved or saved business data.")
        elif matched:
            score += 5
            positives.append(f"{matched} of {len(materials)} materials matched business data.")
        else:
            score -= 8
            gaps.append("Materials were not matched to saved business data.")
        if priced == len(materials):
            score += 8
            positives.append("All material prices are available.")
        elif priced:
            score += 3
            positives.append(f"{priced} of {len(materials)} material prices are available.")
        else:
            score -= 6
            gaps.append("Material prices are not yet available.")

    similar = sum(int(x.get("similar_quotes", 0) or 0) for x in jobs)
    if similar >= 3:
        score += 8
        positives.append(f"{similar} similar saved quote references were found.")
    elif similar:
        score += 4
        positives.append(f"{similar} similar saved quote reference(s) were found.")
    else:
        gaps.append("Little or no directly comparable quote history was found.")

    unknown_supply = sum(1 for x in jobs if x.get("supply_responsibility", "unknown") == "unknown")
    if jobs and unknown_supply == 0:
        score += 5
        positives.append("Supply responsibility was understood for each job.")
    elif unknown_supply:
        score -= min(unknown_supply * 3, 9)
        gaps.append("Supply responsibility still needs confirming for one or more jobs.")

    if len(draft.get("questions_to_confirm", []) or []) > 8:
        score -= 5
        gaps.append("Several details still need confirming.")

    score = max(20, min(98, int(round(score))))
    return {
        "score": score,
        "level": "high" if score >= 85 else "medium" if score >= 65 else "low",
        "positive_reasons": unique_short_items(positives, 5),
        "gaps": unique_short_items(gaps, 4),
    }


def build_professional_quote_mode(draft: dict, context: dict):
    if not isinstance(draft, dict):
        return draft

    full_risks = unique_short_items(draft.get("risk_notes", []), 20)
    full_questions = unique_short_items(draft.get("questions_to_confirm", []), 25)
    full_warnings = unique_short_items(draft.get("warnings", []), 20)

    evidence = []
    for item in (draft.get("materials", []) or [])[:25]:
        evidence.append({
            "name": item.get("name", ""),
            "source": (item.get("data_source") or "business data").replace("_", " "),
            "confidence": 92 if item.get("data_source") not in {"ai_general", "ai_gap_fill", ""} else 65,
            "used_count": int(item.get("learned_used_count", 0) or 0),
        })

    draft["professional_quote"] = {
        "confidence": calculate_estimator_confidence(draft, context),
        "assumptions": professional_assumptions_from_context(context),
        "exclusions": professional_exclusions_from_context(context),
        "questions": unique_short_items(full_questions, 5),
        "risk_notes": unique_short_items(full_risks, 4),
        "material_evidence": evidence,
    }
    draft["technical_detail"] = {
        "all_risk_notes": full_risks,
        "all_questions": full_questions,
        "all_warnings": full_warnings,
    }
    return draft



def calculate_quote_quality_breakdown(draft: dict, context: dict):
    professional = draft.get("professional_quote", {}) or {}
    base_confidence = int((professional.get("confidence", {}) or {}).get("score", 0) or 0)

    materials = draft.get("materials", []) or []
    jobs = draft.get("job_breakdown", []) or []

    if materials:
        priced = sum(1 for item in materials if safe_float(item.get("manual_price", 0), 0) > 0)
        matched = sum(
            1 for item in materials
            if item.get("data_source") not in {"", "ai_general", "ai_gap_fill"}
        )
        material_score = round(((priced / len(materials)) * 45) + ((matched / len(materials)) * 55))
    else:
        material_score = 50

    if jobs:
        labour_confidences = []
        for job in jobs:
            level = (job.get("labour_confidence", {}) or {}).get("level", "low")
            labour_confidences.append({"high": 95, "medium": 78, "low": 55}.get(level, 55))
        labour_score = round(sum(labour_confidences) / len(labour_confidences))
    else:
        labour_score = max(50, min(98, base_confidence))

    understanding_score = max(45, min(98, base_confidence + 3))
    questions = len((professional.get("questions", []) or []))
    site_confirmation = min(100, max(5, questions * 12 + (100 - base_confidence) // 3))

    overall = round(
        material_score * 0.32 +
        labour_score * 0.28 +
        understanding_score * 0.30 +
        (100 - site_confirmation) * 0.10
    )

    stars = max(1, min(5, round(overall / 20)))

    return {
        "overall": overall,
        "materials": material_score,
        "labour": labour_score,
        "understanding": understanding_score,
        "site_confirmation": site_confirmation,
        "stars": stars,
    }


def classify_material_status(item: dict):
    used_for = item.get("used_for_job_names", []) or []
    if item.get("customer_supplied"):
        return "customer_supplied"
    if item.get("required"):
        return "required"
    return "optional"


def build_customer_preview_payload(draft: dict):
    professional = draft.get("professional_quote", {}) or {}
    return {
        "scope_of_work": draft.get("scope_of_work", ""),
        "job_breakdown": [
            {
                "display_name": job.get("display_name", ""),
                "scope": job.get("scope", ""),
                "labour_suggestion": safe_float(job.get("labour_suggestion", 0), 0),
                "customer_supplied_items_removed": job.get("customer_supplied_items_removed", []),
            }
            for job in (draft.get("job_breakdown", []) or [])
        ],
        "materials": [
            {
                "name": item.get("name", ""),
                "quantity": safe_float(item.get("quantity", 1), 1),
                "supplier": item.get("supplier", ""),
                "manual_price": safe_float(item.get("manual_price", 0), 0),
                "status": classify_material_status(item),
            }
            for item in (draft.get("materials", []) or [])
        ],
        "assumptions": professional.get("assumptions", []),
        "exclusions": professional.get("exclusions", []),
        "labour_total": safe_float(draft.get("labour_suggestion", 0), 0),
    }


def enhance_v9_quote(draft: dict, context: dict):
    if not isinstance(draft, dict):
        return draft

    draft["quote_quality"] = calculate_quote_quality_breakdown(draft, context)
    draft["customer_preview"] = build_customer_preview_payload(draft)

    for material in draft.get("materials", []) or []:
        material["display_status"] = classify_material_status(material)

    return draft



QUOTE_HEALTH_JOB_RULES = {
    "outside_tap": {
        "recommended": [
            {
                "key": "outside_tap",
                "name": "Hose union bib tap with double check valve",
                "aliases": ["outside tap kit", "hose union bib", "bib tap", "double check"],
                "quantity": 1,
                "reason": "Main outside-tap fitting with backflow protection.",
            },
            {
                "key": "isolation_valve",
                "name": "15mm isolation valve",
                "aliases": ["15mm isolation valve", "15mm isolating valve"],
                "quantity": 1,
                "reason": "Internal isolation for servicing and winter shut-off.",
                "optional": True,
                "reuse_sensitive": True,
            },
            {
                "key": "wall_plate",
                "name": "15mm wall plate elbow",
                "aliases": ["wall plate elbow", "wallplate elbow"],
                "quantity": 1,
                "reason": "Secure wall termination where the tap is mounted through masonry.",
                "optional": True,
                "requires_any": ["through wall", "wall mounted", "outside wall", "external wall"],
            },
            {
                "key": "pipework",
                "name": "15mm copper pipe 3m",
                "aliases": ["15mm copper pipe", "15mm copper tube"],
                "quantity": 1,
                "reason": "Provisional pipe allowance where a new cold-water route is required.",
                "optional": True,
                "requires_any": ["new pipe", "pipe run", "run pipe", "extend", "route"],
            },
            {
                "key": "pipe_clips",
                "name": "15mm pipe clips",
                "aliases": ["15mm pipe clip", "pipe clips"],
                "quantity": 6,
                "reason": "Supports exposed or newly installed pipework.",
                "optional": True,
                "requires_any": ["new pipe", "pipe run", "exposed", "external"],
            },
            {
                "key": "drain_off",
                "name": "15mm drain off cock",
                "aliases": ["drain off cock", "drain cock"],
                "quantity": 1,
                "reason": "Useful where exposed external pipework may need winter draining.",
                "optional": True,
                "requires_any": ["external pipe", "exposed", "winter", "freezing"],
            },
            {
                "key": "sealant",
                "name": "Sanitary silicone",
                "aliases": ["sanitary silicone", "silicone", "sealant"],
                "quantity": 0.1,
                "reason": "Small sealant allowance around the wall penetration or wall plate.",
                "optional": True,
            },
        ],
        "quantity_limits": {
            "outside tap": {"max_per_job": 1},
            "hose union bib": {"max_per_job": 1},
            "isolation valve": {"max_per_job": 1},
            "isolating valve": {"max_per_job": 1},
            "wall plate elbow": {"max_per_job": 1},
            "drain off": {"max_per_job": 1},
            "copper pipe 3m": {"max_per_job": 3},
        },
    },
    "tap_replacement": {
        "recommended": [
            {
                "key": "replacement_tap",
                "name": "Replacement tap",
                "aliases": ["replacement tap", "kitchen tap", "basin tap", "mixer tap"],
                "quantity": 1,
                "reason": "Main product where Nigel Harvey Ltd is supplying the tap.",
                "optional": True,
                "supplier_sensitive": True,
            },
            {
                "key": "tap_connectors",
                "name": "Flexible tap connector",
                "aliases": ["flexible tap connector", "flexi tap connector", "tap connector", "flexi hose"],
                "quantity": 2,
                "reason": "Hot and cold connectors where suitable tails are not supplied or cannot be reused.",
                "optional": True,
                "reuse_sensitive": True,
            },
            {
                "key": "isolation_valves",
                "name": "15mm isolation valve",
                "aliases": ["isolation valve", "isolating valve"],
                "quantity": 2,
                "reason": "Hot and cold isolation where existing valves are missing, seized or unreliable.",
                "optional": True,
                "reuse_sensitive": True,
            },
            {
                "key": "tap_fixing",
                "name": "Tap fixing kit",
                "aliases": ["tap fixing kit", "tap brace", "tap fixing"],
                "quantity": 1,
                "reason": "Optional support where the sink or worktop is thin or flexible.",
                "optional": True,
                "requires_any": ["loose tap", "thin sink", "flexing", "brace"],
            },
            {
                "key": "ptfe",
                "name": "PTFE tape",
                "aliases": ["ptfe tape"],
                "quantity": 0.1,
                "reason": "Small threaded-joint consumable allowance.",
                "optional": True,
            },
        ],
        "quantity_limits": {
            "replacement tap": {"max_per_job": 1},
            "flexible tap connector": {"max_per_job": 2},
            "isolation valve": {"max_per_job": 2},
            "isolating valve": {"max_per_job": 2},
            "tap fixing": {"max_per_job": 1},
        },
    },
    "toilet_replacement": {
        "recommended": [
            {
                "key": "replacement_toilet",
                "name": "Replacement toilet",
                "aliases": ["replacement toilet", "toilet pan", "wc pan"],
                "quantity": 1,
                "reason": "Main product where Nigel Harvey Ltd is supplying the toilet.",
                "optional": True,
                "supplier_sensitive": True,
            },
            {
                "key": "pan_connector",
                "name": "Pan connector",
                "aliases": ["pan connector"],
                "quantity": 1,
                "reason": "A suitable pan connector is commonly required when reconnecting the replacement toilet.",
                "optional": True,
                "reuse_sensitive": True,
            },
            {
                "key": "fixing_kit",
                "name": "Toilet fixing kit",
                "aliases": ["toilet fixing kit", "wc fixing kit", "pan fixing"],
                "quantity": 1,
                "reason": "Secures the pan where suitable manufacturer fixings are not supplied.",
                "optional": True,
                "reuse_sensitive": True,
            },
            {
                "key": "inlet_flexi",
                "name": "15mm x 1/2 flexible connector",
                "aliases": ["15mm x 1/2 flexi", "toilet flexi", "flexible connector"],
                "quantity": 1,
                "reason": "Inlet connection where the existing connector is unsuitable.",
                "optional": True,
                "reuse_sensitive": True,
            },
            {
                "key": "isolation_valve",
                "name": "15mm isolation valve",
                "aliases": ["isolation valve", "isolating valve"],
                "quantity": 1,
                "reason": "Local isolation where the existing valve is missing or unreliable.",
                "optional": True,
                "reuse_sensitive": True,
            },
            {
                "key": "sanitary_sealant",
                "name": "Sanitary silicone",
                "aliases": ["silicone", "sanitary sealant"],
                "quantity": 0.2,
                "reason": "Small sanitary sealant allowance around the finished installation.",
            },
            {
                "key": "close_coupling",
                "name": "Close-coupling doughnut washer",
                "aliases": ["doughnut washer", "close coupling washer"],
                "quantity": 1,
                "reason": "Required only for a close-coupled toilet where the supplied seal is absent or unsuitable.",
                "optional": True,
                "requires_any": ["close coupled", "close-coupled"],
            },
        ],
        "quantity_limits": {
            "replacement toilet": {"max_per_job": 1},
            "pan connector": {"max_per_job": 1},
            "flexible connector": {"max_per_job": 1},
            "isolation valve": {"max_per_job": 1},
            "isolating valve": {"max_per_job": 1},
            "toilet fixing": {"max_per_job": 1},
            "doughnut washer": {"max_per_job": 1},
        },
    },
    "radiator_replacement": {
        "recommended": [
            {
                "key": "radiator",
                "name": "Radiator",
                "aliases": ["radiator", "panel radiator", "towel radiator"],
                "quantity": 1,
                "reason": "Main product where Nigel Harvey Ltd is supplying the radiator.",
                "optional": True,
                "supplier_sensitive": True,
            },
            {
                "key": "radiator_valves",
                "name": "Radiator valve pair",
                "aliases": ["radiator valve pair", "radiator valve set", "trv valve", "lockshield"],
                "quantity": 1,
                "reason": "A compatible TRV and lockshield pair where existing valves cannot be reused.",
                "optional": True,
                "reuse_sensitive": True,
            },
            {
                "key": "radiator_tails",
                "name": "Radiator valve tails",
                "aliases": ["radiator valve tail", "radiator tails"],
                "quantity": 2,
                "reason": "New tails where the valve set does not include them or the old tails are incompatible.",
                "optional": True,
                "reuse_sensitive": True,
            },
            {
                "key": "inhibitor",
                "name": "Central heating inhibitor",
                "aliases": ["inhibitor"],
                "quantity": 1,
                "reason": "Required where the heating circuit is drained and refilled.",
                "optional": True,
                "requires_any": ["drain down", "drain system", "drain the system", "refill", "new pipework"],
            },
            {
                "key": "pipework",
                "name": "15mm copper pipe 3m",
                "aliases": ["15mm copper pipe", "15mm copper tube"],
                "quantity": 1,
                "reason": "Provisional pipe allowance where the radiator position or pipe centres are changing.",
                "optional": True,
                "requires_any": ["new position", "move radiator", "new pipe", "extend pipe", "pipework"],
            },
            {
                "key": "fittings_allowance",
                "name": "15mm copper fittings allowance",
                "aliases": ["15mm copper fittings allowance", "15mm endfeed elbow", "15mm endfeed tee"],
                "quantity": 1,
                "reason": "Provisional fitting allowance where final elbow and tee quantities depend on the concealed route.",
                "optional": True,
                "requires_any": ["new position", "move radiator", "new pipe", "extend pipe", "pipework", "floorboard"],
            },
        ],
        "quantity_limits": {
            "radiator": {"max_per_job": 1},
            "radiator valve pair": {"max_per_job": 1},
            "radiator valve": {"max_per_job": 2},
            "trv valve": {"max_per_job": 1},
            "lockshield": {"max_per_job": 1},
            "radiator tail": {"max_per_job": 2},
            "copper pipe 3m": {"max_per_job": 4},
        },
    },
    "trv_replacement": {
        "recommended": [
            {
                "key": "trv",
                "name": "TRV valve",
                "aliases": ["trv valve", "thermostatic radiator valve"],
                "quantity": 1,
                "reason": "One thermostatic radiator valve for each replacement.",
            },
            {
                "key": "lockshield",
                "name": "Lockshield valve",
                "aliases": ["lockshield", "lockshield valve"],
                "quantity": 1,
                "reason": "Optional matching lockshield where the existing valve is unsuitable.",
                "optional": True,
                "reuse_sensitive": True,
            },
            {
                "key": "tail",
                "name": "Radiator valve tail",
                "aliases": ["radiator valve tail", "radiator tail"],
                "quantity": 1,
                "reason": "Optional replacement tail where the existing tail is incompatible.",
                "optional": True,
                "reuse_sensitive": True,
            },
            {
                "key": "inhibitor",
                "name": "Central heating inhibitor",
                "aliases": ["inhibitor"],
                "quantity": 1,
                "reason": "Consider where the circuit is drained and refilled.",
                "optional": True,
                "requires_any": ["drain", "refill"],
            },
        ],
        "quantity_limits": {
            "trv valve": {"max_per_job": 1},
            "thermostatic radiator valve": {"max_per_job": 1},
            "lockshield": {"max_per_job": 1},
            "radiator tail": {"max_per_job": 1},
        },
    },
    "basin_waste": {
        "recommended": [
            {
                "key": "basin_waste",
                "name": "Basin waste",
                "aliases": ["basin waste"],
                "quantity": 1,
                "reason": "Compatible slotted or unslotted basin waste.",
            },
            {
                "key": "basin_trap",
                "name": "32mm basin trap",
                "aliases": ["basin trap", "32mm trap", "bottle trap"],
                "quantity": 1,
                "reason": "Trap required where an existing suitable trap is not being reused.",
                "optional": True,
                "reuse_sensitive": True,
            },
            {
                "key": "waste_pipe",
                "name": "32mm waste pipe 3m",
                "aliases": ["32mm waste pipe", "32mm solvent waste pipe"],
                "quantity": 1,
                "reason": "Waste pipe where the existing route requires alteration.",
                "optional": True,
                "requires_any": ["alter waste", "new waste", "move basin", "extend waste", "pipework"],
            },
            {
                "key": "waste_bends",
                "name": "32mm solvent waste bend",
                "aliases": ["32mm waste bend", "32mm solvent weld bend"],
                "quantity": 2,
                "reason": "Provisional bends where the waste route is being altered.",
                "optional": True,
                "requires_any": ["alter waste", "new waste", "move basin", "extend waste", "pipework"],
            },
            {
                "key": "sealant",
                "name": "Sanitary silicone",
                "aliases": ["sanitary silicone", "silicone"],
                "quantity": 0.1,
                "reason": "Small sealant allowance around the waste fitting if required.",
                "optional": True,
            },
        ],
        "quantity_limits": {
            "basin waste": {"max_per_job": 1},
            "basin trap": {"max_per_job": 1},
            "32mm waste pipe": {"max_per_job": 1},
        },
    },
    "kitchen_sink_waste": {
        "recommended": [
            {
                "key": "sink_waste",
                "name": "Kitchen sink waste kit",
                "aliases": ["kitchen sink waste", "sink waste kit", "sink waste"],
                "quantity": 1,
                "reason": "Compatible waste and overflow arrangement for the selected sink.",
            },
            {
                "key": "sink_trap",
                "name": "40mm sink trap",
                "aliases": ["40mm sink trap", "sink trap", "p trap"],
                "quantity": 1,
                "reason": "Trap where a suitable trap is not supplied with the waste kit or reused.",
                "optional": True,
                "reuse_sensitive": True,
            },
            {
                "key": "appliance_spigot",
                "name": "Appliance waste spigot",
                "aliases": ["appliance waste spigot", "washing machine spigot", "dishwasher spigot"],
                "quantity": 1,
                "reason": "Required only where a washing machine or dishwasher connects to the sink waste.",
                "optional": True,
                "requires_any": ["washing machine", "dishwasher", "appliance"],
            },
            {
                "key": "waste_pipe",
                "name": "40mm waste pipe 3m",
                "aliases": ["40mm waste pipe", "40mm solvent waste pipe"],
                "quantity": 1,
                "reason": "Waste pipe where the existing route needs alteration or extension.",
                "optional": True,
                "requires_any": ["alter waste", "new waste", "move sink", "extend waste", "pipework", "elbow", "tee"],
            },
            {
                "key": "waste_bends",
                "name": "40mm solvent waste bend",
                "aliases": ["40mm waste bend", "40mm solvent weld bend", "40mm elbow"],
                "quantity": 2,
                "reason": "Provisional bends where the waste route is being altered.",
                "optional": True,
                "requires_any": ["alter waste", "new waste", "move sink", "extend waste", "pipework", "elbow"],
            },
            {
                "key": "waste_tee",
                "name": "40mm solvent waste tee",
                "aliases": ["40mm waste tee", "40mm solvent weld tee", "waste tee"],
                "quantity": 1,
                "reason": "Tee where the specified waste arrangement requires a branch.",
                "optional": True,
                "requires_any": ["tee", "branch", "appliance"],
            },
            {
                "key": "solvent_cement",
                "name": "Solvent cement",
                "aliases": ["solvent cement", "solvent weld cement"],
                "quantity": 0.1,
                "reason": "Small consumable allowance for solvent-weld pipework.",
                "optional": True,
                "requires_any": ["solvent", "waste pipe", "elbow", "tee"],
            },
        ],
        "quantity_limits": {
            "sink waste": {"max_per_job": 1},
            "kitchen sink waste": {"max_per_job": 1},
            "sink trap": {"max_per_job": 1},
            "40mm waste pipe": {"max_per_job": 1},
            "40mm waste bend": {"max_per_job": 6},
            "40mm waste tee": {"max_per_job": 2},
        },
    },
    "shower_replacement": {
        "recommended": [
            {
                "key": "shower",
                "name": "Replacement shower",
                "aliases": ["replacement shower", "shower valve", "shower mixer"],
                "quantity": 1,
                "reason": "Main product where Nigel Harvey Ltd is supplying the shower.",
                "optional": True,
                "supplier_sensitive": True,
            },
            {
                "key": "connectors",
                "name": "Shower connection fittings",
                "aliases": ["shower connector", "wall plate elbow", "shower connection fitting"],
                "quantity": 2,
                "reason": "Connection fittings where the existing first-fix outlets are unsuitable.",
                "optional": True,
                "reuse_sensitive": True,
            },
            {
                "key": "sealant",
                "name": "Sanitary silicone",
                "aliases": ["sanitary silicone", "silicone"],
                "quantity": 0.2,
                "reason": "Seal around covers and penetrations where required.",
                "optional": True,
            },
        ],
        "quantity_limits": {
            "replacement shower": {"max_per_job": 1},
            "shower connection": {"max_per_job": 2},
        },
    },
}



def material_name_matches(name: str, aliases: list):
    canonical = canonical_material_name(name)
    return any(
        canonical_material_name(alias) in canonical
        or canonical in canonical_material_name(alias)
        for alias in aliases
        if alias
    )


def count_jobs_by_type(context: dict):
    counts = {}
    jobs = (context.get("multi_job_estimate", {}) or {}).get("classified_jobs", []) or []
    if jobs:
        for job in jobs:
            job_type = job.get("job_type")
            if job_type:
                counts[job_type] = counts.get(job_type, 0) + 1
        return counts

    smart = context.get("smart_job_kit", {}) or {}
    job_type = (smart.get("classification", {}) or {}).get("job_type")
    if job_type:
        counts[job_type] = 1
    return counts


def material_confidence_score(item: dict):
    source = item.get("data_source", "")
    used_count = int(item.get("learned_used_count", 0) or 0)
    if source in {"database first saved material", "database_first_saved_material", "trade_library", "saved_material"}:
        base = 92
    elif source in {"quote_history", "template", "smart_job_kit"}:
        base = 84
    elif source == "quote_health_suggestion":
        base = 72
    else:
        base = 65
    return max(40, min(98, base + min(used_count * 2, 6)))



def bundle_context_text(context: dict):
    request = context.get("request", {}) or {}
    survey = request.get("site_survey", {}) or {}
    parts = [
        request.get("job_description", ""),
        survey.get("summary", ""),
        survey.get("transcript", ""),
        survey.get("site_notes", ""),
    ]
    for component in survey.get("components", []) or []:
        if isinstance(component, dict):
            parts.extend([
                component.get("name", ""),
                component.get("finding", ""),
                component.get("evidence", ""),
                component.get("quote_action", ""),
            ])
    return normalise_ai_job_text(" ".join(str(part or "") for part in parts))


def bundle_supply_responsibility(context: dict, job: dict):
    stated = str(job.get("supply_responsibility", "") or "").lower()
    if stated and stated != "unknown":
        return stated
    smart = context.get("smart_job_kit", {}) or {}
    return str(smart.get("supply_responsibility", "unknown") or "unknown").lower()


def bundle_survey_action(context: dict, aliases: list):
    survey = ((context.get("request", {}) or {}).get("site_survey", {}) or {})
    for action in survey.get("material_actions", []) or []:
        action_name = action.get("material_name", "")
        if material_name_matches(action_name, aliases):
            return {
                "action": action.get("action", "site_check"),
                "reason": action.get("reason", ""),
                "confidence": int(action.get("confidence", 0) or 0),
            }
    return None


def bundle_recommendation_decision(rec: dict, context: dict, job: dict):
    text = bundle_context_text(context)
    requires_any = [normalise_ai_job_text(x) for x in rec.get("requires_any", []) if x]
    excludes_any = [normalise_ai_job_text(x) for x in rec.get("excludes_any", []) if x]

    if requires_any and not any(phrase in text for phrase in requires_any):
        return {"include": False, "reason": "Not indicated by the current job description or site survey."}
    if excludes_any and any(phrase in text for phrase in excludes_any):
        return {"include": False, "reason": "Excluded by the current job description or site survey."}

    responsibility = bundle_supply_responsibility(context, job)
    if rec.get("supplier_sensitive"):
        # A main product should not be silently included when the customer supplies it.
        if responsibility in {"customer", "customer_supplied", "customer supplies", "customer-supplied"}:
            return {"include": False, "reason": "Customer-supplied main product."}

    optional = bool(rec.get("optional", False))
    confidence = 94 if not optional else 76
    reason = rec.get("reason", "")

    survey_action = bundle_survey_action(context, rec.get("aliases", []) or [rec.get("name", "")])
    if survey_action:
        action = survey_action.get("action", "site_check")
        confidence = max(confidence, survey_action.get("confidence", 0))
        if survey_action.get("reason"):
            reason = survey_action.get("reason")

        if action == "include_required":
            optional = False
        elif action in {"keep_optional", "site_check", "reuse_existing", "existing_reusable"}:
            optional = True
        elif action in {"exclude", "not_required", "customer_supplied"}:
            return {"include": False, "reason": reason or "Site survey says this item is not required."}

    # Existing/reusable wording should keep replacement parts optional rather than required.
    if rec.get("reuse_sensitive"):
        reuse_terms = [
            "existing working", "working fine", "can be reused", "reuse existing",
            "existing valve present", "existing connection present", "serviceable",
            "already fitted", "already there"
        ]
        if any(term in text for term in reuse_terms):
            optional = True
            confidence = max(confidence, 84)
            if not survey_action:
                reason = f"{reason} Existing components may be reusable; confirm before adding."

    return {
        "include": True,
        "optional": optional,
        "confidence": min(99, max(55, confidence)),
        "reason": reason,
        "survey_action": survey_action,
    }



def calculate_bundle_health(bundle: dict):
    items = bundle.get("items", []) or []
    suppressed = bundle.get("suppressed_items", []) or []

    issues = []
    checks = []
    score = 100

    essentials = [item for item in items if not item.get("optional")]
    optionals = [item for item in items if item.get("optional")]
    missing_essentials = [item for item in essentials if not item.get("already_in_quote")]
    included_items = [item for item in items if item.get("already_in_quote")]

    if missing_essentials:
        score -= min(50, len(missing_essentials) * 18)
        issues.append({
            "severity": "high",
            "code": "missing_essentials",
            "message": f"{len(missing_essentials)} essential material item(s) have not been added.",
            "items": [item.get("name", "") for item in missing_essentials],
        })
    else:
        checks.append("All essential bundle items are already included.")

    low_confidence = [
        item for item in items
        if int(item.get("confidence", 0) or 0) < 70
    ]
    if low_confidence:
        score -= min(18, len(low_confidence) * 6)
        issues.append({
            "severity": "medium",
            "code": "low_confidence",
            "message": "Some bundle recommendations have low confidence and need review.",
            "items": [item.get("name", "") for item in low_confidence],
        })
    else:
        checks.append("All bundle recommendations have usable confidence.")

    site_checks = [
        item for item in items
        if item.get("site_survey_action") in {"site_check", "keep_optional", "reuse_existing", "existing_reusable"}
    ]
    if site_checks:
        score -= min(15, len(site_checks) * 4)
        issues.append({
            "severity": "medium",
            "code": "site_checks",
            "message": "Existing parts or site conditions still need confirmation.",
            "items": [item.get("name", "") for item in site_checks],
        })
    else:
        checks.append("No bundle items are waiting on a site-survey decision.")

    unpriced_included = [
        item for item in included_items
        if safe_float(item.get("manual_price", 0), 0) <= 0
    ]
    if unpriced_included:
        score -= min(15, len(unpriced_included) * 5)
        issues.append({
            "severity": "medium",
            "code": "missing_prices",
            "message": "Included bundle items still have no confirmed price.",
            "items": [item.get("name", "") for item in unpriced_included],
        })
    elif included_items:
        checks.append("Included bundle items have prices.")

    missing_urls = [
        item for item in included_items
        if not str(item.get("url", "") or "").strip()
    ]
    if missing_urls:
        score -= min(10, len(missing_urls) * 3)
        issues.append({
            "severity": "low",
            "code": "missing_urls",
            "message": "Some included bundle items have no saved product URL.",
            "items": [item.get("name", "") for item in missing_urls],
        })
    elif included_items:
        checks.append("Included bundle items have saved product links.")

    if suppressed:
        checks.append(
            f"{len(suppressed)} unsuitable, customer-supplied or unconfirmed item(s) were suppressed."
        )

    if optionals and not any(item.get("already_in_quote") for item in optionals):
        issues.append({
            "severity": "info",
            "code": "optional_review",
            "message": f"{len(optionals)} optional item(s) are available for review.",
            "items": [item.get("name", "") for item in optionals],
        })

    score = max(0, min(100, int(round(score))))
    if score >= 90:
        status = "healthy"
        label = "Healthy"
    elif score >= 70:
        status = "review"
        label = "Review recommended"
    else:
        status = "incomplete"
        label = "Incomplete"

    return {
        "score": score,
        "status": status,
        "label": label,
        "issues": issues,
        "checks": checks[:6],
        "missing_essential_count": len(missing_essentials),
        "optional_review_count": len(optionals),
        "included_count": len(included_items),
        "total_count": len(items),
        "ready_to_apply": len(missing_essentials) == 0,
    }


def build_job_specific_bundles(draft: dict, context: dict):
    bundles = []
    jobs = (context.get("multi_job_estimate", {}) or {}).get("classified_jobs", []) or []
    if not jobs:
        smart = context.get("smart_job_kit", {}) or {}
        classification = smart.get("classification", {}) or {}
        if classification.get("job_type"):
            jobs = [{
                "job_type": classification.get("job_type"),
                "display_name": classification.get("display_name") or classification.get("job_type"),
                "supply_responsibility": smart.get("supply_responsibility", "unknown"),
            }]

    seen_job_types = set()
    current_materials = draft.get("materials", []) or []

    for job in jobs:
        job_type = job.get("job_type")
        if not job_type or job_type in seen_job_types:
            continue
        seen_job_types.add(job_type)

        rule = QUOTE_HEALTH_JOB_RULES.get(job_type, {})
        items = []
        suppressed = []

        for rec in rule.get("recommended", []):
            decision = bundle_recommendation_decision(rec, context, job)
            if not decision.get("include"):
                suppressed.append({
                    "name": rec.get("name", ""),
                    "reason": decision.get("reason", ""),
                })
                continue

            aliases = rec.get("aliases", []) or [rec.get("name", "")]
            matched_material = next(
                (
                    material for material in current_materials
                    if material_name_matches(material.get("name", ""), aliases)
                ),
                None,
            )

            quantity = safe_float(rec.get("quantity", 1), 1)
            if matched_material:
                quantity = max(quantity, safe_float(matched_material.get("quantity", 0), 0))

            survey_action = decision.get("survey_action") or {}
            items.append({
                "id": f"{job_type}:{rec.get('key')}",
                "name": rec.get("name", ""),
                "quantity": quantity,
                "reason": decision.get("reason", rec.get("reason", "")),
                "optional": bool(decision.get("optional", rec.get("optional", False))),
                "confidence": int(decision.get("confidence", 76)),
                "already_in_quote": bool(matched_material),
                "site_survey_action": survey_action.get("action", ""),
                "site_survey_reason": survey_action.get("reason", ""),
                "supply_responsibility": bundle_supply_responsibility(context, job),
                "manual_price": safe_float((matched_material or {}).get("manual_price", 0), 0),
                "url": (matched_material or {}).get("url", ""),
                "supplier": (matched_material or {}).get("supplier", ""),
            })

        if items:
            required_count = sum(1 for item in items if not item.get("optional"))
            optional_count = sum(1 for item in items if item.get("optional"))
            bundle = {
                "job_type": job_type,
                "display_name": job.get("display_name") or job_type.replace("_", " ").title(),
                "items": items,
                "required_count": required_count,
                "optional_count": optional_count,
                "suppressed_items": suppressed,
                "logic_version": "v15.5",
            }
            bundle["health"] = calculate_bundle_health(bundle)
            bundles.append(bundle)

    return bundles



def build_quote_health(draft: dict, context: dict):
    materials = draft.get("materials", []) or []
    job_counts = count_jobs_by_type(context)
    missing_items, quantity_warnings, labour_warnings, checks_passed = [], [], [], []
    seen_missing = set()

    # Missing items remain job-specific.
    for job_type, job_count in job_counts.items():
        rule = QUOTE_HEALTH_JOB_RULES.get(job_type, {})
        job_context = {
            "job_type": job_type,
            "supply_responsibility": (
                (context.get("smart_job_kit", {}) or {}).get("supply_responsibility", "unknown")
            ),
        }
        for recommended in rule.get("recommended", []):
            decision = bundle_recommendation_decision(recommended, context, job_context)
            if not decision.get("include"):
                continue

            found = any(
                material_name_matches(item.get("name", ""), recommended.get("aliases", []))
                for item in materials
            )
            if not found:
                key = f"{job_type}:{recommended.get('key')}"
                if key not in seen_missing:
                    seen_missing.add(key)
                    missing_items.append({
                        "id": key,
                        "job_type": job_type,
                        "name": recommended.get("name", ""),
                        "quantity": round(safe_float(recommended.get("quantity", 1), 1) * job_count, 2),
                        "reason": decision.get("reason", recommended.get("reason", "")),
                        "optional": bool(decision.get("optional", recommended.get("optional", False))),
                        "supplier": "",
                        "url": "",
                        "manual_price": 0,
                        "confidence": int(decision.get("confidence", 76)),
                    })

    # Aggregate quantity limits across all relevant jobs to avoid duplicate warnings.
    aggregate_limits = {}
    for job_type, job_count in job_counts.items():
        rule = QUOTE_HEALTH_JOB_RULES.get(job_type, {})
        for alias, limit in (rule.get("quantity_limits", {}) or {}).items():
            canonical_alias = canonical_material_name(alias)
            aggregate_limits.setdefault(canonical_alias, {
                "aliases": set(),
                "expected_max": 0.0,
                "job_types": set(),
            })
            aggregate_limits[canonical_alias]["aliases"].add(alias)
            aggregate_limits[canonical_alias]["expected_max"] += safe_float(limit.get("max_per_job", 0), 0) * job_count
            aggregate_limits[canonical_alias]["job_types"].add(job_type)

    grouped_materials = {}
    for item in materials:
        canonical = canonical_material_name(item.get("name", ""))
        grouped_materials.setdefault(canonical, {
            "name": item.get("name", ""),
            "quantity": 0.0,
        })
        grouped_materials[canonical]["quantity"] += safe_float(item.get("quantity", 0), 0)

    emitted = set()
    for canonical_alias, limit_data in aggregate_limits.items():
        matching_keys = [
            key for key in grouped_materials
            if canonical_alias in key or key in canonical_alias
        ]
        if not matching_keys:
            continue
        actual = sum(grouped_materials[key]["quantity"] for key in matching_keys)
        expected_max = round(limit_data["expected_max"], 2)
        display_name = grouped_materials[matching_keys[0]]["name"]
        warning_key = canonical_material_name(display_name)
        if actual > expected_max + 0.001 and warning_key not in emitted:
            emitted.add(warning_key)
            quantity_warnings.append({
                "id": f"quantity:{warning_key}",
                "material": display_name,
                "material_key": warning_key,
                "actual_quantity": round(actual, 2),
                "suggested_quantity": expected_max,
                "expected_max": expected_max,
                "job_types": sorted(limit_data["job_types"]),
                "message": f"{display_name}: current quantity {actual:g}; suggested maximum {expected_max:g} for the identified jobs.",
            })

    # General consumable checks, deduplicated.
    for item in materials:
        name = canonical_material_name(item.get("name", ""))
        quantity = safe_float(item.get("quantity", 0), 0)
        if "ptfe" in name and quantity > 0.5 and "ptfe" not in emitted:
            emitted.add("ptfe")
            quantity_warnings.append({
                "id": "quantity:ptfe",
                "material": item.get("name", "PTFE tape"),
                "material_key": name,
                "actual_quantity": quantity,
                "suggested_quantity": 0.1,
                "expected_max": 0.5,
                "job_types": ["general"],
                "message": "PTFE allowance looks high. A 0.1 consumable allowance is normally more suitable than charging a full roll.",
            })

    breakdown = draft.get("job_breakdown", []) or []
    total_labour = safe_float(draft.get("labour_suggestion", 0), 0)
    breakdown_total = round(sum(safe_float(job.get("labour_suggestion", 0), 0) for job in breakdown), 2)

    if breakdown and abs(total_labour - breakdown_total) > 0.01:
        labour_warnings.append({
            "id": "labour:total_mismatch",
            "message": f"Combined labour is £{total_labour:.2f}, but the job breakdown totals £{breakdown_total:.2f}.",
        })
    else:
        checks_passed.append("Labour total matches the individual job breakdown.")

    for job in breakdown:
        confidence = (job.get("labour_confidence", {}) or {}).get("level", "low")
        if confidence == "low":
            labour_warnings.append({
                "id": f"labour:low_confidence:{job.get('job_number', 0)}",
                "message": f"{job.get('display_name', 'Job')} labour has low historical confidence and should be reviewed.",
            })

    if materials and all(safe_float(item.get("manual_price", 0), 0) > 0 for item in materials):
        checks_passed.append("All current material prices are available.")
    elif materials:
        unpriced = sum(1 for item in materials if safe_float(item.get("manual_price", 0), 0) <= 0)
        quantity_warnings.append({
            "id": "materials:unpriced",
            "material": "Unpriced materials",
            "material_key": "unpriced materials",
            "actual_quantity": unpriced,
            "suggested_quantity": 0,
            "expected_max": 0,
            "job_types": ["general"],
            "message": f"{unpriced} material item(s) still need a price before sending.",
            "no_auto_fix": True,
        })

    if not missing_items:
        checks_passed.append("No common required materials appear to be missing.")
    if not quantity_warnings:
        checks_passed.append("Material quantities are within normal advisory ranges.")
    if not labour_warnings:
        checks_passed.append("No labour inconsistencies were found.")
    if job_counts:
        checks_passed.append("Physical jobs were identified clearly.")

    score = 100
    score -= sum(4 if item.get("optional") else 9 for item in missing_items)
    score -= min(25, len(quantity_warnings) * 6)
    score -= min(25, len(labour_warnings) * 10)
    open_questions = len(((draft.get("professional_quote", {}) or {}).get("questions", []) or []))
    score -= min(15, open_questions * 2)
    score = max(20, min(100, int(round(score))))

    if score >= 90 and not labour_warnings and not any(not item.get("optional") for item in missing_items):
        readiness, readiness_label = "ready_to_send", "Ready to send"
    elif score >= 65:
        readiness, readiness_label = "review_recommended", "Review recommended"
    else:
        readiness, readiness_label = "do_not_send", "Do not send yet"

    return {
        "score": score,
        "readiness": readiness,
        "readiness_label": readiness_label,
        "missing_items": missing_items,
        "quantity_warnings": quantity_warnings,
        "labour_warnings": labour_warnings,
        "checks_passed": unique_short_items(checks_passed, 8),
        "open_site_checks": open_questions,
        "advisory_only": True,
        "job_specific_bundles": build_job_specific_bundles(draft, context),
    }



def apply_site_survey_to_draft(draft: dict, context: dict):
    survey = ((context.get("request", {}) or {}).get("site_survey", {}) or {})
    actions = survey.get("material_actions", []) or []
    applied = []

    for action in actions:
        name = action.get("material_name", "")
        if not name:
            continue
        for item in draft.get("materials", []) or []:
            if not material_name_matches(item.get("name", ""), [name]):
                continue
            quote_action = action.get("action", "site_check")
            item["site_survey_action"] = quote_action
            item["site_survey_reason"] = action.get("reason", "")
            item["site_survey_confidence"] = int(action.get("confidence", 0) or 0)

            if quote_action == "include_required":
                item["required"] = True
                item["display_status"] = "required"
            else:
                item["required"] = False
                item["display_status"] = "optional"

            applied.append({
                "material_name": item.get("name", name),
                "action": quote_action,
                "reason": action.get("reason", ""),
                "confidence": int(action.get("confidence", 0) or 0)
            })

    draft["site_survey_summary"] = {
        "used": bool(survey),
        "summary": survey.get("summary", ""),
        "components_reviewed": len(survey.get("components", []) or []),
        "material_actions_applied": applied,
        "warnings": survey.get("warnings", []) or []
    }
    return draft


def enhance_v10_quote(draft: dict, context: dict):
    if not isinstance(draft, dict):
        return draft
    draft = apply_site_survey_to_draft(draft, context)
    for item in draft.get("materials", []) or []:
        item["material_confidence"] = material_confidence_score(item)
    draft["quote_health"] = build_quote_health(draft, context)
    return draft


def build_ai_quote_context(data: AIQuoteDraftRequest):
    original_job = (data.job_description or "").strip()
    job = normalise_ai_job_text(original_job)
    quote_type = data.quote_type or "small"

    history = analyse_similar_quotes(job, quote_type) if job else {
        "similar_count": 0,
        "common_materials": [],
        "averages": {},
        "similar_quotes": []
    }

    labour_info = labour_intelligence_for_job(
        job,
        quote_type,
        data.current_labour
    ) if "labour_intelligence_for_job" in globals() else {}

    existing_materials = []
    for item in data.current_materials or []:
        existing_materials.append({
            "name": item.name,
            "quantity": item.quantity,
            "supplier": item.supplier,
            "manual_price": item.manual_price,
        })

    forgotten = detect_forgotten_items(
        job,
        [m.model_dump() if hasattr(m, "model_dump") else m.dict() for m in data.current_materials]
    ) if "detect_forgotten_items" in globals() else []

    common_materials = []
    for m in (history.get("common_materials", []) or [])[:20]:
        common_materials.append({
            "name": m.get("name"),
            "average_quantity": m.get("average_quantity"),
            "used_percent": m.get("used_percent"),
            "average_unit_price": m.get("average_unit_price"),
            "supplier": m.get("supplier"),
        })

    # Match saved/trade templates more generously than V1.
    trade_matches = []
    job_tokens = set(learning_tokens(job))
    for template in get_all_job_templates():
        template_text = " ".join([
            template.get("name", ""),
            template.get("job", ""),
            template.get("description", ""),
            " ".join(template.get("search_terms", []) or []),
            " ".join(x.get("name", "") for x in template.get("materials", []) or []),
        ]).lower()
        template_tokens = set(learning_tokens(template_text))
        overlap = len(job_tokens.intersection(template_tokens))
        phrase_bonus = 0
        for phrase in [template.get("name", ""), template.get("job", "")]:
            phrase = normalise_ai_job_text(phrase)
            if phrase and (phrase in job or job in phrase):
                phrase_bonus += 5
        score = overlap + phrase_bonus
        if score > 0:
            trade_matches.append((score, template))

    trade_matches.sort(key=lambda x: x[0], reverse=True)
    compact_templates = []
    for score, template in trade_matches[:8]:
        compact_templates.append({
            "match_score": score,
            "name": template.get("name"),
            "job": template.get("job"),
            "labour": template.get("labour", template.get("typical_labour", 0)),
            "labour_range": template.get("labour_range", ""),
            "materials": template.get("materials", [])[:20],
            "risk_notes": template.get("risk_notes", [])[:10],
        })

    fallback_matches = ai_fallback_matches(job)
    fallback_context = []
    for match in fallback_matches:
        fallback_context.append({
            "category": match.get("category"),
            "scope_hint": match.get("scope_hint"),
            "labour_range": match.get("labour_range"),
            "materials": match.get("materials", []),
            "questions": match.get("questions", []),
            "risks": match.get("risks", []),
        })

    master_candidates = ai_master_material_candidates(job, fallback_matches)
    business_material_matches = get_relevant_ai_business_materials(
        job,
        compact_templates,
        fallback_matches,
        limit=40
    )
    database_first_kit = build_database_first_kit(
        job,
        quote_type,
        history,
        compact_templates,
        fallback_matches,
        forgotten
    )
    smart_job_kit = build_smart_job_kit(job, quote_type, history)
    multi_job_estimate = build_multi_job_estimate(original_job, quote_type)

    return {
        "estimator_version": "workflow-fixes-v16-3-1",
        "business": {
            "name": "Nigel Harvey Ltd",
            "location": "Guildford, Surrey, UK",
            "trade": "Domestic plumbing and heating",
            "currency": "GBP"
        },
        "request": {
            "original_job_description": original_job,
            "normalised_job_description": job,
            "quote_type": quote_type,
            "customer_name": data.customer_name,
            "customer_address": data.customer_address,
            "current_labour": data.current_labour,
            "current_materials": existing_materials,
            "site_survey": data.site_survey or {},
        },
        "historical_learning": {
            "similar_count": history.get("similar_count", 0),
            "averages": history.get("averages", {}),
            "common_materials": common_materials,
            "similar_quotes": (history.get("similar_quotes", []) or [])[:6],
        },
        "labour_intelligence": labour_info,
        "forgotten_item_checks": forgotten,
        "matching_trade_templates": compact_templates,
        "controlled_fallback_trade_knowledge": fallback_context,
        "master_material_candidates": master_candidates,
        "business_material_matches": business_material_matches,
        "database_first_kit": database_first_kit,
        "smart_job_kit": smart_job_kit,
        "multi_job_estimate": multi_job_estimate,
        "decision_rules": {
            "do_not_assume_customer_or_contractor_supply": True,
            "include_provisional_materials_when_category_is_clear": True,
            "mark_uncertain_materials_as_optional": True,
            "prefer_master_library_names": True,
            "do_not_invent_live_prices_or_product_urls": True,
        }
    }


def call_openai_quote_builder(context: dict):
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is not configured in Render."
        )

    model = (os.getenv("OPENAI_MODEL") or "gpt-5.6-luna").strip()

    instructions = """
You are an experienced UK domestic plumbing estimator assisting Nigel Harvey Ltd in Guildford, Surrey.

Create a practical but cautious quote draft from the supplied job description and internal business data.

Priority order:
1. Preserve deterministic jobs, material kits, supply responsibility and attached context notes.
2. Write concise professional scopes suitable for a customer quotation.
3. Avoid repeating the same caveat across scope, risks, questions and warnings.
4. Return no more than five genuinely important confirmation questions.
5. Deterministic labour and materials remain authoritative.


Rules:
- Return only the requested structured JSON.
- Customer-facing wording should be clear, calm and concise.
- Do not produce long legalistic paragraphs or repeat generic hidden-defect warnings.
- Keep each individual job scope to a few sentences.
- Detailed technical reasoning will be shown only in an expandable internal section.
- Never create a separate job from a sentence that only says who is supplying an item.
- Never create a separate job from a sentence that only describes access, condition, dimensions, disposal or making good.
- One physical installation must remain one job even when followed by several context notes.
- job_breakdown must match the deterministic classified_jobs count exactly.
- For multi-job requests, job_breakdown must contain one entry per classified job and preserve its job_type.
- The overall scope_of_work should combine the separate job scopes into one professional quotation.
- Never merge two different jobs into one vague scope.
- Do not double-count labour or materials beyond the values supplied by multi_job_estimate.
- Never add toilet, waste, sink, basin, shower, heating or unrelated materials to another classified job type.
- A classified job kit is intentionally narrow. Do not broaden it based on loose keyword overlap.
- AI may not add extra materials when smart_job_kit has a classification.
- Do not remove a database_first_kit item merely because the job description is brief; mark uncertain items optional instead.
- Do not rename, reprice or replace database_first_kit records with invented products.
- Use AI primarily to write the scope, assess risks, identify confirmation questions and add only genuine missing items.
- Do not invent product URLs, exact product models or live prices.
- The supplied business_material_matches are Nigel's real material records. Prefer these exact names, suppliers, URLs and prices whenever they genuinely match.
- A real saved material match is more authoritative than a generic material name.
- If an exact product/model is not known, use a generic optional main item rather than selecting a random product.
- Set url, manual_price and data_source from business_material_matches when using one of those records; otherwise return an empty URL, price 0 and data_source "ai_general".
- Do not change a saved material price or invent one.
- Do not assume whether the customer or Nigel supplies the main appliance/sanitaryware. Include it as optional and ask who supplies it.
- When the job category is identifiable, always produce a useful provisional material kit rather than returning no materials.
- Mark items as required only when they are normally essential for the described work; mark compatibility-dependent items as optional.
- Prefer material names found in the master library or controlled fallback library.
- Quantities may be provisional and should be realistic for one job.
- Consumables such as PTFE or silicone may use fractional quantities where the app charges only a proportion.
- Use UK plumbing terminology.
- Labour is a suggestion in GBP and should be informed by history, templates or the controlled range.
- Keep customer-facing scope clear, professional and concise.
- Put uncertainty in risk notes and confirmation questions rather than making the whole draft unusably vague.
- Highlight access, isolation, hidden pipework, compatibility, making good and compliance.
- Never claim hidden conditions are confirmed from a short description.
- Treat site_survey findings as evidence, not absolute proof.
- Evidence priority: Nigel's explicit tested statement, then clear visual evidence, then AI inference.
- A visible component does not prove that it operates, is internally sound, correctly sized or reusable after disturbance.
- If Nigel says a component was tested and working, normally make replacement optional rather than required.
- Use site_survey material actions to avoid unnecessary replacement items, while preserving cautious site checks.
- Do not include gas appliance installation or repair work.
- Electrical shower work must be flagged for a suitably qualified electrician where applicable.
- The draft requires human review before it is saved or sent.
""".strip()

    payload = {
        "model": model,
        "instructions": instructions,
        "input": json.dumps(context, ensure_ascii=False),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "plumbing_quote_draft",
                "strict": True,
                "schema": AI_QUOTE_SCHEMA
            }
        }
    }

    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"OpenAI connection failed: {exc}")

    if response.status_code >= 400:
        try:
            error_detail = response.json().get("error", {}).get("message", response.text)
        except Exception:
            error_detail = response.text
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI API error: {error_detail[:500]}"
        )

    response_json = response.json()
    output_text = extract_openai_output_text(response_json)
    if not output_text:
        raise HTTPException(status_code=502, detail="OpenAI returned no quote draft.")

    try:
        draft = json.loads(output_text)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="OpenAI returned an invalid structured quote draft.")

    draft = enforce_multi_job_estimate(draft, context)
    draft = build_professional_quote_mode(draft, context)
    draft = enhance_v9_quote(draft, context)
    draft = enhance_v10_quote(draft, context)

    return {
        "draft": draft,
        "model": model,
        "response_id": response_json.get("id", ""),
        "review_required": True,
    }






SITE_SURVEY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "proposed_job_description": {"type": "string"},
        "site_visit_addition": {"type": "string"},
        "transcript": {"type": "string"},
        "components": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "component": {"type": "string"},
                "status": {"type": "string", "enum": [
                    "confirmed_visible", "not_visible",
                    "present_condition_unconfirmed", "confirmed_by_nigel", "ai_inferred"
                ]},
                "condition": {"type": "string"},
                "evidence": {"type": "string"},
                "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                "quote_action": {"type": "string", "enum": [
                    "reuse_existing", "keep_optional", "include_required",
                    "site_check", "no_quote_change"
                ]},
                "material_name": {"type": "string"}
            },
            "required": ["component", "status", "condition", "evidence",
                         "confidence", "quote_action", "material_name"]
        }},
        "site_conditions": {"type": "array", "items": {"type": "string"}},
        "material_actions": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "material_name": {"type": "string"},
                "action": {"type": "string", "enum": [
                    "reuse_existing", "keep_optional", "include_required", "site_check"
                ]},
                "reason": {"type": "string"},
                "confidence": {"type": "integer", "minimum": 0, "maximum": 100}
            },
            "required": ["material_name", "action", "reason", "confidence"]
        }},
        "warnings": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["summary", "proposed_job_description", "site_visit_addition",
                 "transcript", "components", "site_conditions",
                 "material_actions", "warnings"]
}


def _survey_data_url(content: bytes, mime_type: str):
    return f"data:{mime_type};base64,{base64.b64encode(content).decode('ascii')}"


def _run_ffmpeg(arguments):
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", *arguments],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=90, check=False
        )
    except FileNotFoundError:
        return False, "Video processing needs ffmpeg installed on Render."
    except subprocess.TimeoutExpired:
        return False, "Video processing took too long."
    if result.returncode:
        return False, result.stderr.decode("utf-8", errors="ignore")[:300]
    return True, ""


async def _stream_upload_to_disk(upload: UploadFile, destination: Path, max_bytes: int):
    """Copy an upload to disk in small chunks without loading it into RAM."""
    total = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("wb") as output:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=400,
                        detail=f"{upload.filename or 'Upload'} is too large."
                    )
                output.write(chunk)
    finally:
        await upload.close()
    return total


def _normalise_survey_image(source: Path, destination: Path):
    """Create a compact 1024px JPEG suitable for vision analysis."""
    ok, message = _run_ffmpeg([
        "-y",
        "-i", str(source),
        "-frames:v", "1",
        "-vf", "scale='min(1024,iw)':-2",
        "-q:v", "6",
        str(destination),
    ])
    if not ok:
        return False, message
    return destination.exists() and destination.stat().st_size > 0, message


def _transcribe_site_audio(audio_path: Path):
    transcript = ""
    warnings = []
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return "", ["OPENAI_API_KEY is not configured for audio transcription."]

    try:
        with audio_path.open("rb") as audio_file:
            response = requests.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={
                    "file": (
                        audio_path.name,
                        audio_file,
                        mimetypes.guess_type(audio_path.name)[0] or "audio/webm",
                    )
                },
                data={
                    "model": (
                        os.getenv("OPENAI_TRANSCRIBE_MODEL")
                        or "gpt-4o-mini-transcribe"
                    ).strip()
                },
                timeout=120,
            )
        if response.status_code < 400:
            transcript = response.json().get("text", "")
        else:
            warnings.append("The job walkthrough audio could not be transcribed.")
    except requests.RequestException:
        warnings.append("The job walkthrough audio could not be transcribed.")
    return transcript, warnings


def _extract_video_evidence(video_path: Path, work_dir: Path):
    """Extract only a small number of resized frames and a compressed audio track."""
    transcript, warnings = "", []
    frames_dir = work_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    audio_path = work_dir / "survey-audio.mp3"

    # Maximum six already-resized JPEGs. ffmpeg reads the video from disk.
    ok, message = _run_ffmpeg([
        "-y",
        "-i", str(video_path),
        "-vf", "fps=1/10,scale='min(1024,iw)':-2",
        "-frames:v", "6",
        "-q:v", "6",
        str(frames_dir / "frame-%02d.jpg"),
    ])
    if not ok and message:
        warnings.append(message)

    frame_paths = [
        path for path in sorted(frames_dir.glob("frame-*.jpg"))
        if path.exists() and path.stat().st_size > 0
    ][:6]

    # Create a small mono audio file on disk and stream that file to transcription.
    ok, message = _run_ffmpeg([
        "-y",
        "-i", str(video_path),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-b:a", "48k",
        str(audio_path),
    ])
    if ok and audio_path.exists():
        try:
            with audio_path.open("rb") as audio:
                response = requests.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={
                        "Authorization": f"Bearer {(os.getenv('OPENAI_API_KEY') or '').strip()}"
                    },
                    files={"file": ("survey-audio.mp3", audio, "audio/mpeg")},
                    data={
                        "model": (
                            os.getenv("OPENAI_TRANSCRIBE_MODEL")
                            or "gpt-4o-mini-transcribe"
                        ).strip()
                    },
                    timeout=90,
                )
            if response.status_code < 400:
                transcript = response.json().get("text", "")
            else:
                warnings.append(
                    "Video frames were analysed, but speech transcription failed."
                )
        except requests.RequestException:
            warnings.append(
                "Video frames were analysed, but speech transcription failed."
            )
        finally:
            try:
                audio_path.unlink(missing_ok=True)
            except Exception:
                pass
    elif message:
        warnings.append(message)

    return frame_paths, transcript, [item for item in warnings if item]


def _analyse_site_survey(job_description, transcript, image_paths, warnings, site_notes=''):
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured.")

    model = (
        os.getenv("OPENAI_VISION_MODEL")
        or os.getenv("OPENAI_MODEL")
        or "gpt-5.6-luna"
    ).strip()

    content = [{
        "type": "input_text",
        "text": f"""Review this UK domestic plumbing site survey for Nigel Harvey Ltd.

Job description:
{job_description or 'Not supplied'}

Nigel's spoken transcript:
{transcript or 'No transcript available'}

Additional site notes:
{site_notes or 'No additional notes'}

Use only supported evidence. Nigel explicitly saying he tested an item and it works is stronger than visual evidence. Seeing an item does not prove it works or will reseal after disturbance. Hidden pipework cannot be confirmed. Do not call something absent merely because the angle does not show it. Use reuse_existing only when Nigel explicitly confirms it works; keep_optional when visible but condition is uncertain; include_required when clearly absent/damaged or Nigel says it needs replacement; otherwise site_check. Use concise UK plumbing terminology.

Also write:
- proposed_job_description: a concise complete works description suitable for Nigel's quote form.
- site_visit_addition: only the useful new facts learned from the site survey that may be appended to an existing website enquiry.
Do not repeat vague enquiry wording. Do not include prices. Do not describe AI analysis. Keep uncertainty phrased as checks or provisional conditions."""
    }]

    # Compact files are read one at a time. At most eight small JPEG data URLs
    # are retained in the outgoing request.
    for image_path in image_paths[:8]:
        try:
            image_bytes = image_path.read_bytes()
            if not image_bytes:
                continue
            content.append({
                "type": "input_image",
                "image_url": _survey_data_url(image_bytes, "image/jpeg"),
                "detail": "low",
            })
        finally:
            try:
                image_path.unlink(missing_ok=True)
            except Exception:
                pass

    payload = {
        "model": model,
        "input": [{"role": "user", "content": content}],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "plumbing_site_survey",
                "strict": True,
                "schema": SITE_SURVEY_SCHEMA,
            }
        },
    }

    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Site-survey connection failed: {exc}",
        )
    finally:
        gc.collect()

    if response.status_code >= 400:
        try:
            detail = response.json().get("error", {}).get("message", response.text)
        except Exception:
            detail = response.text
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI site-survey error: {detail[:500]}",
        )

    output = extract_openai_output_text(response.json())
    try:
        result = json.loads(output)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Invalid structured site-survey response.",
        )

    result["transcript"] = transcript or result.get("transcript", "")
    result["warnings"] = unique_short_items(
        (result.get("warnings", []) or []) + warnings,
        12,
    )
    result["model"] = model
    result["review_required"] = True
    result["low_memory_pipeline"] = True
    return result


@app.post("/api/site-survey")
async def api_site_survey(
    job_description: str = Form(""),
    site_notes: str = Form(""),
    photos: list[UploadFile] = File(default=[]),
    plans: list[UploadFile] = File(default=[]),
    video: UploadFile | None = File(default=None),
    audio: UploadFile | None = File(default=None),
):
    warnings = []
    transcript_parts = []
    compact_images = []
    photo_count = 0
    plan_count = 0
    video_used = bool(video and video.filename)
    audio_used = bool(audio and audio.filename)

    with tempfile.TemporaryDirectory(prefix="site-visit-") as temp_folder:
        work_dir = Path(temp_folder)

        all_images = list(photos[:6])
        for plan in plans[:4]:
            mime_type = (
                plan.content_type
                or mimetypes.guess_type(plan.filename or "")[0]
                or ""
            )
            if mime_type.startswith("image/"):
                all_images.append(plan)
                plan_count += 1
            else:
                warnings.append(
                    f"{plan.filename or 'A plan'} was attached but PDF plans are not visually analysed in this version."
                )
                await plan.close()

        for index, photo in enumerate(all_images[:8], start=1):
            mime_type = (
                photo.content_type
                or mimetypes.guess_type(photo.filename or "")[0]
                or ""
            )
            if not mime_type.startswith("image/"):
                await photo.close()
                continue

            source_suffix = Path(photo.filename or "").suffix.lower() or ".jpg"
            source_path = work_dir / f"image-source-{index}{source_suffix}"
            compact_path = work_dir / f"image-{index}.jpg"

            await _stream_upload_to_disk(
                photo,
                source_path,
                max_bytes=10 * 1024 * 1024,
            )
            ok, message = _normalise_survey_image(source_path, compact_path)
            source_path.unlink(missing_ok=True)

            if ok:
                compact_images.append(compact_path)
                photo_count += 1
            elif message:
                warnings.append(
                    f"{photo.filename or 'An image'} could not be prepared for analysis."
                )

        if audio_used:
            audio_suffix = Path(audio.filename or "").suffix.lower() or ".webm"
            audio_path = work_dir / f"job-walkthrough{audio_suffix}"
            await _stream_upload_to_disk(
                audio,
                audio_path,
                max_bytes=40 * 1024 * 1024,
            )
            audio_transcript, audio_warnings = _transcribe_site_audio(audio_path)
            if audio_transcript:
                transcript_parts.append(audio_transcript)
            warnings.extend(audio_warnings)
            audio_path.unlink(missing_ok=True)
        elif audio:
            await audio.close()

        if video_used:
            suffix = Path(video.filename or "").suffix.lower() or ".mp4"
            video_path = work_dir / f"survey-video{suffix}"
            await _stream_upload_to_disk(
                video,
                video_path,
                max_bytes=80 * 1024 * 1024,
            )
            frame_paths, video_transcript, video_warnings = _extract_video_evidence(
                video_path,
                work_dir,
            )
            compact_images.extend(frame_paths)
            if video_transcript:
                transcript_parts.append(video_transcript)
            warnings.extend(video_warnings)
            video_path.unlink(missing_ok=True)
        elif video:
            await video.close()

        compact_images = compact_images[:8]
        transcript = "\n\n".join(part.strip() for part in transcript_parts if part.strip())

        if not compact_images and not transcript and not site_notes.strip():
            raise HTTPException(
                status_code=400,
                detail="Record an audio walkthrough, add video/photos, or enter site notes.",
            )

        result = _analyse_site_survey(
            job_description,
            transcript,
            compact_images,
            warnings,
            site_notes=site_notes,
        )
        result.update({
            "evidence_count": len(compact_images),
            "photo_count": photo_count,
            "plan_count": plan_count,
            "video_used": video_used,
            "audio_used": audio_used,
            "site_notes": site_notes,
            "input_modes": [
                mode for mode, used in [
                    ("audio", audio_used),
                    ("video", video_used),
                    ("photos", photo_count > 0),
                    ("plans", plan_count > 0),
                    ("notes", bool(site_notes.strip())),
                ] if used
            ],
            "media_limits": {
                "photos_and_plan_images": 8,
                "audio_mb": 40,
                "video_mb": 80,
                "video_frames": 6,
                "image_width_px": 1024,
            },
        })

    gc.collect()
    return JSONResponse(content=result)


@app.get("/api/ai-quote-status")
def api_ai_quote_status():
    configured = bool((os.getenv("OPENAI_API_KEY") or "").strip())
    return JSONResponse(content={
        "configured": configured,
        "model": (os.getenv("OPENAI_MODEL") or "gpt-5.6-luna").strip(),
        "qr_code_support": QRCODE_AVAILABLE,
    })


@app.post("/api/ai-quote-draft")
def api_ai_quote_draft(data: AIQuoteDraftRequest):
    if not (data.job_description or "").strip():
        raise HTTPException(status_code=400, detail="Enter a job description first.")

    context = build_ai_quote_context(data)
    result = call_openai_quote_builder(context)
    result["context_summary"] = {
        "version": context.get("estimator_version", "manual-job-reference-v16-2"),
        "similar_quotes": context.get("historical_learning", {}).get("similar_count", 0),
        "trade_templates": len(context.get("matching_trade_templates", [])),
        "fallback_matches": len(context.get("controlled_fallback_trade_knowledge", [])),
        "master_material_candidates": len(context.get("master_material_candidates", [])),
        "business_material_matches": len(context.get("business_material_matches", [])),
        "matched_draft_materials": result.get("draft", {}).get("business_brain", {}).get("matched_materials", 0),
        "priced_draft_materials": result.get("draft", {}).get("database_first_summary", {}).get("priced_items", 0),
        "database_kit_items": len(context.get("database_first_kit", [])),
        "historical_kit_items": result.get("draft", {}).get("database_first_summary", {}).get("historical_items", 0),
        "template_kit_items": result.get("draft", {}).get("database_first_summary", {}).get("template_items", 0),
        "smart_job_type": result.get("draft", {}).get("smart_job_summary", {}).get("display_name", ""),
        "smart_kit_items": result.get("draft", {}).get("smart_job_summary", {}).get("kit_items", 0),
        "smart_priced_items": result.get("draft", {}).get("smart_job_summary", {}).get("priced_items", 0),
        "is_multi_job": context.get("multi_job_estimate", {}).get("is_multi_job", False),
        "multi_job_count": result.get("draft", {}).get("multi_job_summary", {}).get("job_count", 0),
        "multi_job_names": result.get("draft", {}).get("multi_job_summary", {}).get("job_names", []),
        "combined_material_count": result.get("draft", {}).get("multi_job_summary", {}).get("combined_material_count", 0),
    }
    return JSONResponse(content=result)


@app.get("/api/supplier-preference")
def api_supplier_preference(q: str = ""):
    return JSONResponse(content=supplier_preference_for_material(q))


@app.get("/api/supplier-preferences")
def api_supplier_preferences():
    return JSONResponse(content={"items": supplier_preferences_summary()})


@app.post("/api/forgotten-items")
def api_forgotten_items(data: QuoteRequest):
    return JSONResponse(content={
        "warnings": detect_forgotten_items(data.job_description, data.materials)
    })


@app.get("/api/labour-intelligence")
def api_labour_intelligence(job: str = "", quote_type: str = "", labour: float = 0):
    return JSONResponse(content=labour_intelligence_for_job(job, quote_type, labour))


@app.get("/api/quote-learning")
def api_quote_learning(q: str = "", quote_type: str = ""):
    return JSONResponse(content=analyse_similar_quotes(q, quote_type))


@app.post("/api/quote")
def api_create_quote(data: QuoteRequest):
    request_data = data.model_dump()
    result_data = calculate_quote(data)
    quote_id = save_quote(request_data, result_data)
    quote = get_quote_by_id(quote_id)
    return JSONResponse(content=quote)


@app.put("/api/quotes/{quote_id}")
def api_update_quote(quote_id: int, data: QuoteRequest):
    request_data = data.model_dump()
    result_data = calculate_quote(data)
    quote = update_quote_by_id(quote_id, request_data, result_data)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    return JSONResponse(content=quote)


@app.post("/api/quotes/{quote_id}/to-invoice")
def api_quote_to_invoice(quote_id: int):
    invoice = create_invoice_from_quote(quote_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Quote not found")
    return invoice


@app.get("/invoice/{invoice_id}", response_class=HTMLResponse)
def public_invoice(invoice_id: int):
    item = get_invoice_by_id(invoice_id)
    if not item:
        raise HTTPException(status_code=404, detail="Invoice not found")

    invoice = item["invoice"]
    quote_result = item["quote_result"]
    is_small_job = (quote_result.get("quote_type", "") or "").lower() == "small"
    terms = INVOICE_TERMS[:3] if is_small_job else INVOICE_TERMS
    logo_html = f'<img src="{escape(COMPANY_LOGO_URL)}" alt="Logo" class="logo">' if COMPANY_LOGO_URL else ""
    payment_html = f'<div class="pay-box"><strong>Payment link:</strong> <a href="{escape(item.get("payment_link") or "")}" target="_blank">Pay online</a></div>' if item.get("payment_link") else ""
    bank_html = f"""
      <div class="pay-box">
        <div style="display:grid;grid-template-columns:1fr auto;gap:14px;align-items:start;">
          <div>
            <strong>Bank transfer</strong><br>
            Bank: {escape(BANK_NAME)}<br>
            Account name: {escape(BANK_ACCOUNT_NAME)}<br>
            Sort code: <strong>{escape(BANK_SORT_CODE)}</strong><br>
            Account number: <strong>{escape(BANK_ACCOUNT_NUMBER)}</strong><br>
            Reference: <strong>{escape(bank_payment_reference(item))}</strong><br>
            Amount due: <strong>{pounds_text(item.get("balance_due", 0))}</strong>
          </div>
          {(
              f'<img src="/api/invoices/{item["id"]}/payment-qr" alt="Payment details QR" '
              f'style="width:120px;height:120px;background:white;border:1px solid #ddd;border-radius:8px;">'
              if QRCODE_AVAILABLE else
              '<div style="width:120px;padding:10px;border:1px solid #ddd;border-radius:8px;'
              'background:#fafafa;font-size:12px;">QR unavailable</div>'
          )}
        </div>
        <div style="font-size:12px;color:#666;margin-top:6px;">The QR contains the payment details. Automatic bank-app prefilling varies.</div>
      </div>
    """
    paid_watermark_html = '<div class="paid-watermark">PAID</div>' if str(item.get("status", "")).lower() == "paid" else ""
    photos = item.get("photos", []) or []
    photos_html = ""
    if photos:
        cards = []
        for photo in photos:
            cards.append(
                f'<div class="photo-card">'
                f'<img src="{escape(photo.get("url", ""))}" alt="Job photo">'
                f'<div class="photo-caption"><strong>{escape(photo.get("category_label", "Job photo"))}</strong>'
                f'<br>{escape(photo.get("caption", "") or "")}</div></div>'
            )
        photos_html = '<div class="section-title">Job photos</div><div class="photo-grid">' + "".join(cards) + '</div>' 

    html = f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Invoice {escape(item['invoice_number'])}</title>
      <style>
        body {{ font-family: Arial, sans-serif; background:#f3f4f6; color:#111; margin:0; padding:18px; }}
        .sheet {{ position:relative; max-width:900px; margin:0 auto; background:white; border-radius:18px; padding:28px; box-shadow:0 10px 30px rgba(0,0,0,0.08); }}
        .paid-watermark {{ position:absolute; inset:0; display:flex; align-items:center; justify-content:center; font-size:120px; font-weight:900; color:rgba(22,163,74,.12); transform:rotate(-24deg); pointer-events:none; }}
        .top {{ display:flex; justify-content:space-between; gap:20px; align-items:flex-start; border-bottom:2px solid #111; padding-bottom:18px; }}
        .logo {{ max-height:72px; max-width:180px; object-fit:contain; }}
        .company {{ font-size:30px; font-weight:800; margin-bottom:8px; }}
        .doc-title {{ font-size:14px; text-transform:uppercase; letter-spacing:1.5px; color:#666; }}
        .doc-number {{ font-size:24px; font-weight:800; margin-top:6px; }}
        .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:20px; }}
        .box {{ border:1px solid #e5e7eb; border-radius:14px; padding:16px; background:#fafafa; }}
        .label {{ color:#666; font-size:13px; text-transform:uppercase; letter-spacing:.5px; margin-bottom:8px; }}
        .row {{ display:flex; justify-content:space-between; gap:12px; margin:10px 0; }}
        .muted {{ color:#666; }}
        .section-title {{ font-size:18px; font-weight:800; margin:24px 0 10px; }}
        .total {{ font-size:30px; font-weight:900; }}
        .pay-box {{ margin-top:12px; padding:12px; background:#eef7ff; border:1px solid #cfe5f8; border-radius:12px; }}
        .actions {{ margin-top:20px; display:flex; gap:10px; flex-wrap:wrap; }}
        .photo-grid {{ display:grid; grid-template-columns:repeat(2,1fr); gap:14px; }}
        .photo-card {{ border:1px solid #e5e7eb; border-radius:12px; overflow:hidden; background:#fafafa; }}
        .photo-card img {{ width:100%; height:230px; object-fit:cover; display:block; }}
        .photo-caption {{ padding:10px; }}
        .btn {{ display:inline-block; padding:13px 16px; border-radius:12px; background:black; color:white; text-decoration:none; font-weight:700; }}
        .btn.light {{ background:#e5e7eb; color:#111; }}
        ul {{ margin:0; padding-left:18px; }}
        @media (max-width:700px) {{ .sheet {{ padding:18px; }} .top, .grid, .row {{ display:block; }} .row span:last-child {{ display:block; margin-top:4px; }} .actions a {{ width:100%; text-align:center; box-sizing:border-box; }} }}
        @media print {{ body {{ background:white; padding:0; }} .sheet {{ box-shadow:none; border-radius:0; max-width:100%; padding:0; }} .actions {{ display:none !important; }} }}
      </style>
    </head>
    <body>
      <div class="sheet">
        {paid_watermark_html}
        <div class="top">
          <div>
            <div class="company">{escape(COMPANY_NAME)}</div>
            <div>{escape(COMPANY_ADDRESS)}<br>{escape(COMPANY_PHONE)}<br>{escape(COMPANY_EMAIL)}</div>
          </div>
          <div style="text-align:right;">{logo_html}<div class="doc-title">Invoice</div><div class="doc-number">{escape(item['invoice_number'])}</div></div>
        </div>
        <div class="grid">
          <div class="box"><div class="label">Bill To</div>{escape(invoice.get('customer_name', '-') or '-')}<br>{escape(invoice.get('customer_address', '-') or '-')}<br>{escape(invoice.get('customer_phone', '-') or '-')}</div>
          <div class="box">
            <div class="row"><span class="muted">Date</span><span>{escape(item['created_at'])}</span></div>
            <div class="row"><span class="muted">Job Ref</span><span>{escape(item.get('job_reference') or '-')}</span></div>
            <div class="row"><span class="muted">Due date</span><span>{escape(item['due_date'])}</span></div>
            <div class="row"><span class="muted">Status</span><span>{escape(item['status'].title())}</span></div>
          </div>
        </div>
        <div class="section-title">Work</div>
        <div class="box">{escape(invoice.get('job', '-') or '-').replace(chr(10), '<br>')}</div>
        {photos_html}
        <div class="section-title">Payment details</div>
        {bank_html}
        {payment_html}
        <div class="section-title">Invoice totals</div>
        <div class="box">
          <div class="row"><span class="muted">Labour</span><span>{pounds_text(invoice.get('labour', 0))}</span></div>
          <div class="row"><span class="muted">Materials</span><span>{pounds_text(invoice.get('materials', 0))}</span></div>
          <div class="row"><span class="muted">Total</span><span>{pounds_text(item['total_price'])}</span></div>
          <div class="row"><span class="muted">Amount paid</span><span>{pounds_text(item['amount_paid'])}</span></div>
          <div class="row"><span class="muted">Balance due</span><span class="total">{pounds_text(item['balance_due'])}</span></div>
        </div>
        <div class="section-title">Payment terms</div>
        <div class="box"><ul>{''.join(f'<li>{escape(t)}</li>' for t in terms)}</ul>{payment_html}</div>
        <div class="actions">
          <a href="/api/invoices/{item['id']}/pdf" target="_blank" class="btn">Download PDF</a>
          <a href="javascript:window.print()" class="btn light">Print</a>
        </div>
      </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html, media_type="text/html; charset=utf-8")




@app.get("/api/quotes/{quote_id}/pdf")
def api_quote_pdf(quote_id: int, request: Request):
    quote = get_quote_by_id(quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    pdf_bytes = generate_quote_pdf_bytes(quote)
    disposition = "inline" if request.query_params.get("view") == "1" else "attachment"
    headers = {"Content-Disposition": f'{disposition}; filename="quote-{quote_id}.pdf"'}
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)



@app.post("/api/invoices/{invoice_id}/photos")
async def api_upload_invoice_photos(
    invoice_id: int,
    category: str = Form("after"),
    caption: str = Form(""),
    photos: list[UploadFile] = File(default=[]),
):
    if not get_invoice_by_id(invoice_id):
        raise HTTPException(status_code=404, detail="Invoice not found")
    if not photos:
        raise HTTPException(status_code=400, detail="Choose at least one photo.")
    if len(photos) > 12:
        raise HTTPException(status_code=400, detail="Upload no more than 12 photos at a time.")

    folder = invoice_photo_folder(invoice_id)
    added = 0
    errors = []

    for upload in photos:
        mime_type = upload.content_type or mimetypes.guess_type(upload.filename or "")[0] or ""
        if not mime_type.startswith("image/"):
            await upload.close()
            errors.append(f"{upload.filename or 'A file'} is not an image.")
            continue

        safe_stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", Path(upload.filename or "photo").stem).strip("-")[:40] or "photo"
        stamp = now_uk().strftime("%Y%m%d%H%M%S%f")
        temp_path = folder / f"{stamp}-{safe_stem}.upload"
        final_name = f"{stamp}-{safe_stem}.jpg"
        final_path = folder / final_name

        try:
            await _stream_upload_to_disk(upload, temp_path, max_bytes=15 * 1024 * 1024)
            prepare_invoice_photo(temp_path, final_path)
            save_invoice_photo_record(invoice_id, category, caption, final_name, upload.filename or "")
            added += 1
        except Exception:
            errors.append(f"{upload.filename or 'A photo'} could not be prepared.")
            final_path.unlink(missing_ok=True)
        finally:
            temp_path.unlink(missing_ok=True)
            try:
                await upload.close()
            except Exception:
                pass

    if not added:
        raise HTTPException(status_code=400, detail="No usable photos were uploaded.")

    return {"ok": True, "added": added, "errors": errors, "photos": load_invoice_photos(invoice_id)}


@app.get("/api/invoices/{invoice_id}/photos/{photo_id}")
def api_invoice_photo(invoice_id: int, photo_id: int):
    path = invoice_photo_path(invoice_id, photo_id)
    if not path:
        raise HTTPException(status_code=404, detail="Photo not found")
    return Response(
        content=path.read_bytes(),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@app.delete("/api/invoices/{invoice_id}/photos/{photo_id}")
def api_delete_invoice_photo(invoice_id: int, photo_id: int):
    if not delete_invoice_photo_record(invoice_id, photo_id):
        raise HTTPException(status_code=404, detail="Photo not found")
    return {"ok": True, "photos": load_invoice_photos(invoice_id)}



@app.get("/api/invoices/{invoice_id}/payment-qr")
def api_invoice_payment_qr(invoice_id: int):
    item = get_invoice_by_id(invoice_id)
    if not item:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if not QRCODE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="QR support is unavailable until qrcode[pil] is installed."
        )
    return Response(
        content=bank_payment_qr_png(item),
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=300"},
    )


@app.post("/api/invoices/{invoice_id}/send-overdue-reminder")
def api_send_overdue_reminder(invoice_id: int):
    item = get_invoice_by_id(invoice_id)
    if not item:
        raise HTTPException(status_code=404, detail="Invoice not found")
    try:
        return send_overdue_reminder_now(item)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/invoices/run-overdue-reminders")
def api_run_overdue_reminders():
    return process_overdue_invoice_reminders()


@app.get("/api/invoices/{invoice_id}/pdf")
def api_invoice_pdf(invoice_id: int, request: Request):
    invoice = get_invoice_by_id(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    pdf_bytes = generate_invoice_pdf_bytes(invoice)
    disposition = "inline" if request.query_params.get("view") == "1" else "attachment"
    headers = {"Content-Disposition": f'{disposition}; filename="{invoice["invoice_number"]}.pdf"'}
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


@app.post("/api/invoices/{invoice_id}/send-email")
def api_invoice_send_email(invoice_id: int, data: SendInvoiceEmailRequest):
    invoice = get_invoice_by_id(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    try:
        send_invoice_email_now(invoice, data.to_email, data.message)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email send failed: {e}")
    return {"ok": True}

@app.get("/api/invoices")
def api_invoices():
    return load_invoices()


@app.get("/api/invoices/{invoice_id}")
def api_invoice(invoice_id: int):
    invoice = get_invoice_by_id(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@app.put("/api/invoices/{invoice_id}")
def api_update_invoice(invoice_id: int, data: InvoiceEditRequest):
    invoice = update_invoice_by_id(invoice_id, data)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@app.post("/api/invoices/{invoice_id}/status")
def api_invoice_status(invoice_id: int, data: InvoiceStatusRequest):
    invoice = update_invoice_status(invoice_id, data.status, data.amount_paid)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@app.post("/api/invoices/{invoice_id}/payment-link")
def api_invoice_payment_link(invoice_id: int, data: PaymentLinkUpdateRequest):
    invoice = get_invoice_by_id(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    invoice_payload = invoice["invoice"]
    invoice_payload["payment_link"] = (data.payment_link or "").strip()

    conn = get_db()
    conn.execute("""
        UPDATE invoices
        SET payment_link = ?, invoice_json = ?
        WHERE id = ?
    """, (
        (data.payment_link or "").strip(),
        json.dumps(invoice_payload),
        invoice_id,
    ))
    conn.commit()
    conn.close()
    return get_invoice_by_id(invoice_id)


@app.delete("/api/invoices/{invoice_id}")
def api_delete_invoice(invoice_id: int):
    if not delete_invoice_by_id(invoice_id):
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {"ok": True}


@app.get("/api/customers")
def api_customers():
    return get_customers()


@app.delete("/api/customers/{customer_id}")
def api_delete_customer(customer_id: int):
    result = customer_store.delete_customer_by_id(customer_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return result


@app.get("/api/customers/{customer_id}/history")
def api_customer_history(customer_id: int):
    history = get_customer_history(customer_id)
    if not history:
        raise HTTPException(status_code=404, detail="Customer not found")
    return history

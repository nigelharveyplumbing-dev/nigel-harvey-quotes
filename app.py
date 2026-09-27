# -*- coding: utf-8 -*-
from fastapi import FastAPI, HTTPException, Response, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from starlette.routing import Match
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import requests
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
from urllib.parse import urlparse, urlsplit
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
    ("GET", "/site-images/{filename}"),
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


def is_staging_environment():
    return (os.getenv("APP_ENVIRONMENT") or "").strip().lower() == "staging"


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
    if not is_staging_environment() and is_public_route(request):
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
    return google_reviews.google_reviews_html(
        GOOGLE_PLACES_API_KEY=GOOGLE_PLACES_API_KEY, GOOGLE_REVIEWS_URL=GOOGLE_REVIEWS_URL,
        _google_place_id=_google_place_id)


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
from business import quote_history
from business import public_invoice_render
from business import notifications
from business import ai_presentation
from business import job_context
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
    return merchant_search.scrape_live_price(url, safe_float=safe_float)



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
    return notifications.send_overdue_reminder_now(
        item, invoice_is_overdue=invoice_is_overdue, pounds_text=pounds_text, send_invoice_email_now=send_invoice_email_now, update_invoice_reminder_timestamp=update_invoice_reminder_timestamp, get_invoice_by_id=get_invoice_by_id)


def process_overdue_invoice_reminders():
    return notifications.process_overdue_invoice_reminders(
        load_invoices=load_invoices, invoice_is_overdue=invoice_is_overdue, send_overdue_reminder_now=send_overdue_reminder_now, now_uk=now_uk, UK_TZ=UK_TZ, OVERDUE_REMINDER_INTERVAL_HOURS=OVERDUE_REMINDER_INTERVAL_HOURS)


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


STOP_WORDS = quote_history.STOP_WORDS


def learning_tokens(text: str):
    return quote_history.learning_tokens(text)


def quote_similarity_score(query_tokens, quote: dict):
    return quote_history.quote_similarity_score(query_tokens, quote)


def analyse_similar_quotes(query: str, quote_type: str = ""):
    return quote_history.analyse_similar_quotes(query, quote_type, load_quotes=load_quotes,
                                                safe_float=safe_float, material_alias_info=material_alias_info)


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

from business import dashboard_reporting, public_pages, merchant_search, google_reviews, material_search, website_contact

def get_dashboard():
    return dashboard_reporting.get_dashboard(get_db, now_uk)


def get_monthly_profit_series(month_count: int = 6):
    return dashboard_reporting.get_monthly_profit_series(month_count, get_db, month_labels)


def get_customers():
    return customer_store.get_customers()


def get_customer_history(customer_id: int):
    return customer_store.get_customer_history(customer_id, row_to_quote, row_to_invoice)




def pounds_text(value):
    return f"£{safe_float(value, 0):.2f}"


def get_public_base_url(request: Request | None = None) -> str:
    production_origin = "https://www.nigelharveyplumbing.co.uk"
    configured = (os.getenv("PUBLIC_BASE_URL") or "").strip()
    staging = is_staging_environment()
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
    return notifications.send_lead_notification_email(
        lead, EMAIL_ENABLED=EMAIL_ENABLED, EMAIL_USER=EMAIL_USER, EMAIL_PASS=EMAIL_PASS, EMAIL_FROM_NAME=EMAIL_FROM_NAME, EMAIL_HOST=EMAIL_HOST, EMAIL_PORT=EMAIL_PORT, get_public_base_url=get_public_base_url)



def build_homepage_faq_schema() -> str:
    return public_pages.build_homepage_faq_schema()



def build_homepage_business_schema(canonical_home: str) -> str:
    return public_pages.build_homepage_business_schema(canonical_home)



def build_reviews_badge_html() -> str:
    return public_pages.build_reviews_badge_html()



def build_reviews_section_html() -> str:
    return public_pages.build_reviews_section_html()




LANDING_PAGE_HTML = (Path(__file__).resolve().parent / "templates/legacy_landing.html").read_text(encoding="utf-8")

SEO_CSS = public_pages.SEO_CSS


LOCATION_PAGES = public_pages.LOCATION_PAGES


SERVICE_PAGES = public_pages.SERVICE_PAGES


def get_company_logo_html(logo_value: str) -> str:
    return public_pages.get_company_logo_html(logo_value)


def render_location_page(location_name: str, logo_html: str, request: Request | None = None) -> str:
    return public_pages.render_location_page(
        location_name, logo_html, request, absolute_url=absolute_url,
        _google_reviews_html=_google_reviews_html)


def render_service_page(service: dict, logo_html: str, request: Request | None = None) -> str:
    return public_pages.render_service_page(
        service, logo_html, request, absolute_url=absolute_url)





# Full-scale local service pages for SEO.
# These create pages like:
# /emergency-plumber-guildford
# /toilet-repair-guildford
# /leak-repair-guildford
# /bathroom-plumbing-guildford
# /blocked-drains-guildford
LOCAL_SERVICE_PAGES = public_pages.LOCAL_SERVICE_PAGES


def render_local_service_location_page(service: dict, location: dict, logo_html: str, request: Request | None = None) -> str:
    return public_pages.render_local_service_location_page(
        service, location, logo_html, request, absolute_url=absolute_url)



LEAD_FORM_HTML = (Path(__file__).resolve().parent / "templates/request_quote.html").read_text(encoding="utf-8")


# Keep the original inline response: there are no additional browser requests or routes.
APP_UI_ROOT = Path(__file__).resolve().parent
HTML = (APP_UI_ROOT / "templates" / "app.html").read_text(encoding="utf-8")
HTML = HTML.replace("__APP_CSS__", (APP_UI_ROOT / "static" / "app.css").read_text(encoding="utf-8"))
payment_config = json.dumps({
    "bank": BANK_NAME,
    "accountName": BANK_ACCOUNT_NAME,
    "sortCode": BANK_SORT_CODE,
    "accountNumber": BANK_ACCOUNT_NUMBER,
}).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
HTML = HTML.replace("__APP_PAYMENT_CONFIG__", payment_config)
HTML = HTML.replace("__APP_JS__", (APP_UI_ROOT / "static" / "app.js").read_text(encoding="utf-8"))


@app.get("/request-quote", response_class=HTMLResponse)
def request_quote_page(request: Request):
    logo_value = get_company_logo_value()
    logo_html = f'<img src="{logo_value}" alt="Nigel Harvey Ltd logo" class="logo" width="240" height="90">' if logo_value else ""
    html = LEAD_FORM_HTML.replace("__COMPANY_LOGO_HTML__", logo_html)
    html = html.replace("__COMPANY_PHONE__", COMPANY_PHONE)
    html = html.replace("__COMPANY_PHONE_TEL__", website_contact.telephone_uri_number(COMPANY_PHONE))
    html = html.replace("__COMPANY_EMAIL__", COMPANY_EMAIL)
    html = html.replace("__CANONICAL_QUOTE__", escape(absolute_url("/request-quote", request), quote=True))
    html = html.replace("__WHATSAPP_URL__", escape(website_contact.whatsapp_url(COMPANY_PHONE, "Hi Nigel, I've got a plumbing job I'd like some help with."), quote=True))
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



NEW_HOMEPAGE_PREVIEW_HTML = (Path(__file__).resolve().parent / "templates/homepage.html").read_text(encoding="utf-8")


@app.get("/site-images/{filename}")
def public_site_image(filename: str):
    # Only the reviewed, bundled stock illustrations may be served publicly.
    if filename not in {"bathroom-illustrative.webp", "shower-illustrative.webp", "radiator-illustrative.webp"}:
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(Path(__file__).resolve().parent / "static" / "site-images" / filename,
                        media_type="image/webp", headers={"Cache-Control": "public, max-age=604800"})


def render_public_homepage(request: Request):
    reviews = _google_reviews_html()
    html = NEW_HOMEPAGE_PREVIEW_HTML.replace("__PUBLIC_HOME_URL__", escape(absolute_url("/", request), quote=True))
    html = html.replace("__COMPANY_PHONE__", COMPANY_PHONE)
    html = html.replace("__COMPANY_PHONE_TEL__", website_contact.telephone_uri_number(COMPANY_PHONE))
    html = html.replace("__COMPANY_EMAIL__", COMPANY_EMAIL)
    html = html.replace("__GOOGLE_REVIEW_SUMMARY__", website_contact.review_summary_html(reviews, GOOGLE_REVIEWS_URL))
    html = html.replace("__GOOGLE_REVIEWS_HTML__", reviews)
    html = html.replace("__WHATSAPP_URL__", escape(website_contact.whatsapp_url(COMPANY_PHONE, "Hi Nigel, I've got a plumbing job I'd like some help with."), quote=True))
    html = html.replace("__BUSINESS_SCHEMA__", build_homepage_business_schema(absolute_url("/", request)).replace("<", "\\u003c"))
    return HTMLResponse(content=html, media_type="text/html; charset=utf-8")


@app.get("/new-home", response_class=HTMLResponse)
def new_homepage_preview(request: Request):
    return render_public_homepage(request)


@app.get("/", response_class=HTMLResponse)
def landing_home(request: Request):
    return render_public_homepage(request)


@app.get("/robots.txt")
def robots_txt(request: Request):
    if is_staging_environment():
        return Response(content="User-agent: *\nDisallow: /\n",
                        media_type="text/plain; charset=utf-8")
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
        for location in LOCATION_PAGES if location["slug"] != "farnborough"
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
    # The established Surrey service slugs contain a hyphen and otherwise match
    # this two-part route before FastAPI reaches /{service_slug}.
    full_slug = f"{service_slug}-{area_slug}".lower()
    established_service = next((item for item in SERVICE_PAGES if item["slug"] == full_slug), None)
    if established_service:
        logo_html = get_company_logo_html(get_company_logo_value())
        return HTMLResponse(content=render_service_page(established_service, logo_html, request),
                            media_type="text/html; charset=utf-8")
    service = next((item for item in LOCAL_SERVICE_PAGES if item["slug"] == service_slug.lower()), None)
    # No automatic service × Farnborough doorway pages in this growth batch.
    location = next((item for item in LOCATION_PAGES if item["slug"] == area_slug.lower()
                     and item["slug"] != "farnborough"), None)
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
    return material_search.get_material_search_library(
        material_library=MATERIAL_LIBRARY, get_db=get_db, safe_float=safe_float)




LIVE_MERCHANTS = merchant_search.LIVE_MERCHANTS



def _clean_product_title(value: str):
    return merchant_search._clean_product_title(value)



def _merchant_host_allowed(url: str, allowed_hosts):
    return merchant_search._merchant_host_allowed(url, allowed_hosts)



def _looks_like_product_url(url: str):
    return merchant_search._looks_like_product_url(url)




def _toolstation_radiator_category_url(query: str):
    return merchant_search._toolstation_radiator_category_url(query)



def _extract_toolstation_products(html: str, page_url: str):
    return merchant_search._extract_toolstation_products(
        html, page_url, safe_float=safe_float,
        normalize_material_url=normalize_material_url)



def _extract_search_page_products(html: str, search_url: str, merchant_name: str, allowed_hosts):
    return merchant_search._extract_search_page_products(
        html, search_url, merchant_name, allowed_hosts,
        safe_float=safe_float, normalize_material_url=normalize_material_url)



def _read_product_page_details(product, merchant_name):
    return merchant_search._read_product_page_details(
        product, merchant_name, safe_float=safe_float,
        normalize_material_url=normalize_material_url,
        scrape_live_price=scrape_live_price)



def _product_search_intent(query: str):
    return merchant_search._product_search_intent(query)



def _strict_product_match(name: str, query: str):
    return merchant_search._strict_product_match(name, query)



def search_live_merchant_products(query: str, suppliers=None, per_supplier: int = 5):
    return merchant_search.search_live_merchant_products(
        query, suppliers, per_supplier, safe_float=safe_float,
        normalize_material_url=normalize_material_url,
        scrape_live_price=scrape_live_price,
        upsert_material_price_cache=upsert_material_price_cache)



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
    return material_search._material_match_normalise(value)



def _material_match_family(value: str) -> str:
    return material_search._material_match_family(value)



def _material_match_sizes(value: str) -> list[int]:
    return material_search._material_match_sizes(value)



def _material_match_score(query: str, item: dict) -> int:
    return material_search._material_match_score(query, item, safe_float=safe_float)



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
    return quote_history.labour_intelligence_for_job(
        job_text, quote_type, current_labour, analyse_similar_quotes=analyse_similar_quotes, safe_float=safe_float)



FORGOTTEN_ITEM_RULES = quote_history.FORGOTTEN_ITEM_RULES


def detect_forgotten_items(job_text: str, materials: list):
    return quote_history.detect_forgotten_items(job_text, materials, canonical_material_name=canonical_material_name)



def supplier_preference_for_material(material_name: str):
    return quote_history.supplier_preference_for_material(
        material_name, load_quotes=load_quotes, canonical_material_name=canonical_material_name, safe_float=safe_float)


def supplier_preferences_summary():
    return quote_history.supplier_preferences_summary(
        load_quotes=load_quotes, canonical_material_name=canonical_material_name, safe_float=safe_float)





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
    return ai_presentation.normalise_ai_job_text(value)


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



CONTEXT_NOTE_PATTERNS = job_context.CONTEXT_NOTE_PATTERNS


def classify_context_note(sentence: str):
    return job_context.classify_context_note(sentence, normalise_ai_job_text=normalise_ai_job_text)


def sentence_starts_new_job(sentence: str):
    return job_context.sentence_starts_new_job(sentence, normalise_ai_job_text=normalise_ai_job_text, classify_smart_job=classify_smart_job)


def attach_context_to_job(job_record: dict, sentence: str):
    return job_context.attach_context_to_job(job_record, sentence, classify_context_note=classify_context_note)


def parse_context_aware_jobs(job_text: str):
    return job_context.parse_context_aware_jobs(job_text, sentence_starts_new_job=sentence_starts_new_job, classify_smart_job=classify_smart_job, detect_supply_responsibility=detect_supply_responsibility, attach_context_to_job=attach_context_to_job, normalise_ai_job_text=normalise_ai_job_text)


def context_notes_as_text(job_record: dict):
    return job_context.context_notes_as_text(job_record)


def context_note_summary(job_record: dict):
    return job_context.context_note_summary(job_record)


def split_multi_job_description(job_text: str):
    return job_context.split_multi_job_description(job_text, parse_context_aware_jobs=parse_context_aware_jobs)


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
    return job_context.merge_multi_job_materials(job_records, canonical_material_name=canonical_material_name, safe_float=safe_float)



CUSTOMER_SUPPLY_PATTERNS = job_context.CUSTOMER_SUPPLY_PATTERNS

BUSINESS_SUPPLY_PATTERNS = job_context.BUSINESS_SUPPLY_PATTERNS

MAIN_ITEM_BY_JOB_TYPE = job_context.MAIN_ITEM_BY_JOB_TYPE


def detect_supply_responsibility(job_text: str, job_type: str):
    return job_context.detect_supply_responsibility(job_text, job_type, normalise_ai_job_text=normalise_ai_job_text)


def is_main_supply_item(material_name: str, job_type: str):
    return job_context.is_main_supply_item(material_name, job_type, canonical_material_name=canonical_material_name)


def apply_supply_responsibility_to_materials(materials: list, job_type: str, responsibility: str):
    return job_context.apply_supply_responsibility_to_materials(materials, job_type, responsibility, is_main_supply_item=is_main_supply_item)


def labour_confidence_for_job(record: dict):
    return job_context.labour_confidence_for_job(record)


def merge_multi_job_materials_with_summary(job_records: list):
    return job_context.merge_multi_job_materials_with_summary(job_records, merge_multi_job_materials=merge_multi_job_materials)


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



STANDARD_QUOTE_EXCLUSIONS = ai_presentation.STANDARD_QUOTE_EXCLUSIONS


def unique_short_items(items, limit=5):
    return ai_presentation.unique_short_items(items, limit)


def professional_assumptions_from_context(context: dict):
    return ai_presentation.professional_assumptions_from_context(context)


def professional_exclusions_from_context(context: dict):
    return ai_presentation.professional_exclusions_from_context(context)


def calculate_estimator_confidence(draft: dict, context: dict):
    return ai_presentation.calculate_estimator_confidence(draft, context, safe_float=safe_float)


def build_professional_quote_mode(draft: dict, context: dict):
    return ai_presentation.build_professional_quote_mode(
        draft, context, calculate_estimator_confidence=calculate_estimator_confidence,
        professional_assumptions_from_context=professional_assumptions_from_context,
        professional_exclusions_from_context=professional_exclusions_from_context)



def calculate_quote_quality_breakdown(draft: dict, context: dict):
    return ai_presentation.calculate_quote_quality_breakdown(draft, context, safe_float=safe_float)


def classify_material_status(item: dict):
    return ai_presentation.classify_material_status(item)


def build_customer_preview_payload(draft: dict):
    return ai_presentation.build_customer_preview_payload(draft, safe_float=safe_float)


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
    html = public_invoice_render.render_public_invoice_html(
        item,
        COMPANY_NAME=COMPANY_NAME,
        COMPANY_ADDRESS=COMPANY_ADDRESS,
        COMPANY_PHONE=COMPANY_PHONE,
        COMPANY_EMAIL=COMPANY_EMAIL,
        COMPANY_LOGO_URL=COMPANY_LOGO_URL,
        INVOICE_TERMS=INVOICE_TERMS,
        BANK_NAME=BANK_NAME,
        BANK_ACCOUNT_NAME=BANK_ACCOUNT_NAME,
        BANK_SORT_CODE=BANK_SORT_CODE,
        BANK_ACCOUNT_NUMBER=BANK_ACCOUNT_NUMBER,
        QRCODE_AVAILABLE=QRCODE_AVAILABLE,
        pounds_text=pounds_text,
        bank_payment_reference=bank_payment_reference,
    )
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

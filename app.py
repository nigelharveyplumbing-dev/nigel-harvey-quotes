# -*- coding: utf-8 -*-
from fastapi import FastAPI, HTTPException, Response, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
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
from urllib.parse import quote_plus, urljoin, urlparse, urlencode
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email import encoders
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from PIL import Image, ImageOps

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

APP_USERNAME = "nigel"
APP_PASSWORD = "Hmhair0310"

def check_basic_auth(request: Request):
    auth = request.headers.get("authorization")
    if not auth or not auth.startswith("Basic "):
        return False
    try:
        encoded = auth.split(" ")[1]
        decoded = base64.b64decode(encoded).decode("utf-8")
        user, pwd = decoded.split(":")
        return user == APP_USERNAME and pwd == APP_PASSWORD
    except:
        return False

@app.middleware("http")
async def protect_app_routes(request: Request, call_next):
    if request.url.path.startswith("/app"):
        if not check_basic_auth(request):
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": "Basic"},
                content="Authentication required"
            )
    return await call_next(request)


from business.config import (
    APP_VERSION,
    DB_PATH,
    DB_BACKUP_DIR,
    INVOICE_PHOTO_DIR,
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

JOB_TEMPLATES = [
    {"name": "Replace tap", "quote_type": "small", "job": "Remove existing tap and fit new tap including testing for leaks.", "labour": 120, "materials": [
        {"name": "Flexible Tap Connector", "quantity": 2},
        {"name": "15mm Isolating Valve", "quantity": 2},
    ]},
    {"name": "Replace toilet", "quote_type": "small", "job": "Remove existing toilet and fit new close-coupled toilet including waste connection and testing.", "labour": 180, "materials": [
        {"name": "Pan Connector", "quantity": 1},
        {"name": "Service Valve", "quantity": 1},
    ]},
    {"name": "Basin waste", "quote_type": "small", "job": "Remove faulty basin waste and fit new basin waste including testing for leaks.", "labour": 90, "materials": [
        {"name": "Basin Waste", "quantity": 1},
        {"name": "Bottle Trap Chrome", "quantity": 1},
    ]},
    {"name": "Outside tap", "quote_type": "small", "job": "Supply and fit outside tap kit with isolation and testing.", "labour": 150, "materials": [
        {"name": "Outside Tap Kit", "quantity": 1},
        {"name": "15mm Copper Pipe 3m", "quantity": 1},
        {"name": "15mm Isolating Valve", "quantity": 1},
    ]},
    {"name": "Kitchen sink waste", "quote_type": "small", "job": "Remove existing sink waste and fit new waste/trap arrangement including testing.", "labour": 120, "materials": [
        {"name": "Sink Waste Kit", "quantity": 1},
        {"name": "P Trap 1.5in", "quantity": 1},
    ]},
    {"name": "Bathroom install", "quote_type": "bathroom", "job": "Bathroom plumbing installation including first fix, second fix and sanitaryware connections.", "labour": 1800, "materials": [
        {"name": "15mm Copper Pipe 3m", "quantity": 4},
        {"name": "15mm Copper Elbow", "quantity": 10},
        {"name": "15mm Isolating Valve", "quantity": 4},
        {"name": "Basin Waste", "quantity": 1},
        {"name": "Bath Waste", "quantity": 1},
    ]},
    {"name": "Bathroom refurb", "quote_type": "bathroom", "job": "Bathroom refurbishment plumbing works including sanitaryware, wastes and connections.", "labour": 2200, "materials": [
        {"name": "15mm Copper Pipe 3m", "quantity": 4},
        {"name": "15mm Copper Elbow", "quantity": 10},
        {"name": "15mm Isolating Valve", "quantity": 4},
        {"name": "Basin Waste", "quantity": 1},
    ]},
    {"name": "Heating repair", "quote_type": "heating", "job": "Heating repair works including diagnosis, replacement parts and testing.", "labour": 150, "materials": [
        {"name": "Inhibitor 1L", "quantity": 1},
    ]},
    {"name": "Radiator install", "quote_type": "heating", "job": "Supply and fit radiator including valves and testing.", "labour": 180, "materials": [
        {"name": "Radiator Valve Pair", "quantity": 1},
        {"name": "Inhibitor 1L", "quantity": 1},
    ]},
    {"name": "Full heating system", "quote_type": "heating", "job": "Full heating system installation including pipework, controls, radiators and commissioning.", "labour": 3500, "materials": [
        {"name": "22mm Copper Pipe 3m", "quantity": 6},
        {"name": "15mm Copper Pipe 3m", "quantity": 8},
        {"name": "Magnetic Filter", "quantity": 1},
        {"name": "Inhibitor 1L", "quantity": 2},
    ]},
    {"name": "Outside tap - pipework run", "quote_type": "small", "job": "Supply hot and cold plus waste pipe for outside sink. Supply cold feed for new outside tap. Redo pipework as required, test all pipework and leave ready for customer-supplied sink.", "labour": 200, "materials": [
        {"name": "Plumbright Compression Coupling Male 15mm x 1/4", "quantity": 1},
        {"name": "Plumbright Hose Union Bib Tap Dbl Check 1/2", "quantity": 1},
        {"name": "3m Copper pipe 15mm", "quantity": 4},
        {"name": "Plumbright Isolating Valve 15mm Chrome Plated", "quantity": 4},
        {"name": "Plumbright Drain Off Cock 15mm", "quantity": 2},
        {"name": "Plumbright Endfeed Elbow 90 Degree 15mm", "quantity": 10},
        {"name": "Plumbright Endfeed Equal Tee 15mm", "quantity": 6},
        {"name": "Plumbright Solvent Waste Pipe Clips 32mm", "quantity": 2},
    ]},
    {"name": "Fridge cold water feed", "quote_type": "small", "job": "Supply and connect cold water feed for fridge, including isolation valve, pipework, fittings and testing for leaks.", "labour": 120, "materials": [
        {"name": "15mm Isolating Valve", "quantity": 1},
        {"name": "15mm Copper Pipe 3m", "quantity": 1},
        {"name": "Compression Coupler 15mm", "quantity": 2},
    ]},
    {"name": "Leak repair - bathroom", "quote_type": "small", "job": "Attend bathroom leak, identify source of leak, repair faulty pipework/fitting and test on completion.", "labour": 150, "materials": [
        {"name": "15mm Copper Pipe 3m", "quantity": 1},
        {"name": "15mm Copper Elbow", "quantity": 4},
        {"name": "15mm Straight Coupler", "quantity": 2},
    ]},
    {"name": "Replace bath taps", "quote_type": "small", "job": "Remove existing bath taps and fit replacement bath taps, including testing for leaks and checking connections.", "labour": 180, "materials": [
        {"name": "Flexible Tap Connector", "quantity": 2},
        {"name": "15mm Isolating Valve", "quantity": 2},
    ]}
]



MATERIAL_ALIAS_RULES = [
    {
        "canonical": "15mm copper pipe",
        "keywords": ["15mm copper", "copper pipe 15", "copper tube 15", "3m copper pipe 15", "plumbright copper pipe 15"],
        "category": "pipework",
    },
    {
        "canonical": "22mm copper pipe",
        "keywords": ["22mm copper", "copper pipe 22", "copper tube 22", "3m copper pipe 22"],
        "category": "pipework",
    },
    {
        "canonical": "15mm isolating valve",
        "keywords": ["15mm isolating", "isolation valve 15", "isolating valve", "service valve 15", "iso valve"],
        "category": "valves",
    },
    {
        "canonical": "double check valve 15mm",
        "keywords": ["double check", "dbl check", "check valve 15", "dcv"],
        "category": "valves",
    },
    {
        "canonical": "drain off cock 15mm",
        "keywords": ["drain off", "drain cock", "doc 15", "drain valve"],
        "category": "valves",
    },
    {
        "canonical": "wall plate elbow 15mm x 1/2",
        "keywords": ["wall plate elbow", "wallplate elbow", "back plate elbow", "15mm x 1/2 wall plate", "compression wall plate elbow"],
        "category": "fittings",
    },
    {
        "canonical": "hose union bib tap",
        "keywords": ["hose union bib", "bib tap", "outside tap", "garden tap"],
        "category": "taps",
    },
    {
        "canonical": "15mm compression coupler",
        "keywords": ["compression coupler 15", "compression coupling 15", "15mm coupler", "15mm coupling"],
        "category": "fittings",
    },
    {
        "canonical": "15mm endfeed elbow",
        "keywords": [
            "endfeed elbow 15",
            "endfeed elbow 90",
            "endfeed elbow 90 degree",
            "endfeed elbow 90 degree 15mm",
            "elbow 90 15",
            "elbow 90 degree 15",
            "90 degree elbow 15",
            "90 degree elbow 15mm",
            "15mm endfeed elbow",
            "15mm elbow",
            "end feed elbow",
            "plumbright endfeed elbow 90 degree 15mm"
        ],
        "category": "fittings",
    },
    {
        "canonical": "15mm endfeed tee",
        "keywords": ["endfeed equal tee 15", "endfeed tee 15", "15mm tee", "equal tee 15"],
        "category": "fittings",
    },
    {
        "canonical": "32mm waste pipe",
        "keywords": ["32mm waste pipe", "waste pipe 32", "solvent waste pipe 32"],
        "category": "waste",
    },
    {
        "canonical": "40mm waste pipe",
        "keywords": ["40mm waste pipe", "waste pipe 40", "solvent waste pipe 40"],
        "category": "waste",
    },
    {
        "canonical": "32mm waste pipe clips",
        "keywords": ["32mm waste clips", "waste pipe clips 32", "solvent waste pipe clips 32"],
        "category": "waste",
    },
    {
        "canonical": "40mm waste pipe clips",
        "keywords": ["40mm waste clips", "waste pipe clips 40"],
        "category": "waste",
    },
    {
        "canonical": "basin waste",
        "keywords": ["basin waste", "sink basin waste", "slotted basin waste", "unslotted basin waste"],
        "category": "waste",
    },
    {
        "canonical": "bottle trap 32mm",
        "keywords": ["bottle trap", "chrome bottle trap", "32mm bottle trap"],
        "category": "waste",
    },
    {
        "canonical": "kitchen sink waste kit",
        "keywords": ["sink waste kit", "kitchen waste kit", "basket strainer waste", "sink strainer waste"],
        "category": "waste",
    },
    {
        "canonical": "p trap 40mm",
        "keywords": ["p trap 40", "40mm trap", "sink trap", "kitchen trap"],
        "category": "waste",
    },
    {
        "canonical": "pan connector",
        "keywords": ["pan connector", "toilet connector", "wc connector", "offset pan connector", "straight pan connector"],
        "category": "toilet",
    },
    {
        "canonical": "toilet fill valve",
        "keywords": ["fill valve", "inlet valve", "toilet inlet", "cistern inlet"],
        "category": "toilet",
    },
    {
        "canonical": "toilet flush valve",
        "keywords": ["flush valve", "dual flush", "toilet siphon", "syphon"],
        "category": "toilet",
    },
    {
        "canonical": "flexible tap connector",
        "keywords": ["flexi tap", "flexible tap", "flexi connector", "tap flexi", "tap tails"],
        "category": "taps",
    },
    {
        "canonical": "bath tap connectors",
        "keywords": ["bath tap connector", "bath tap connectors", "bath flexi", "bath tap tails"],
        "category": "taps",
    },
    {
        "canonical": "ptfe tape",
        "keywords": ["ptfe", "thread tape"],
        "category": "consumables",
    },
    {
        "canonical": "silicone",
        "keywords": ["silicone", "sanitary silicone", "sealant"],
        "category": "consumables",
    },
    {
        "canonical": "pipe clips 15mm",
        "keywords": ["15mm pipe clips", "pipe clip 15", "copper clips 15"],
        "category": "clips",
    },
    {
        "canonical": "trv valve",
        "keywords": ["trv", "thermostatic radiator valve", "radiator trv"],
        "category": "heating",
    },
    {
        "canonical": "lockshield valve",
        "keywords": ["lockshield", "radiator lockshield"],
        "category": "heating",
    },
    {
        "canonical": "inhibitor 1l",
        "keywords": ["inhibitor", "central heating inhibitor", "sentinel x100", "fernox inhibitor"],
        "category": "heating",
    },
{
        "canonical": "32mm bottle trap",
        "keywords": ["32mm bottle trap", "bottle trap 32", "basin bottle trap", "chrome bottle trap", "plastic bottle trap"],
        "category": "waste",
    },
    {
        "canonical": "40mm bottle trap",
        "keywords": ["40mm bottle trap", "bottle trap 40", "sink bottle trap"],
        "category": "waste",
    },
    {
        "canonical": "32mm p trap",
        "keywords": ["32mm p trap", "p trap 32", "basin p trap"],
        "category": "waste",
    },
    {
        "canonical": "40mm p trap",
        "keywords": ["40mm p trap", "p trap 40", "sink p trap", "kitchen p trap"],
        "category": "waste",
    },
    {
        "canonical": "32mm s trap",
        "keywords": ["32mm s trap", "s trap 32", "basin s trap"],
        "category": "waste",
    },
    {
        "canonical": "40mm s trap",
        "keywords": ["40mm s trap", "s trap 40", "sink s trap"],
        "category": "waste",
    },
    {
        "canonical": "32mm shallow trap",
        "keywords": ["32mm shallow trap", "shallow basin trap", "low profile basin trap"],
        "category": "waste",
    },
    {
        "canonical": "40mm shallow trap",
        "keywords": ["40mm shallow trap", "shallow sink trap", "low profile sink trap"],
        "category": "waste",
    },
    {
        "canonical": "anti-syphon trap",
        "keywords": ["anti syphon trap", "anti-syphon trap", "resealing trap", "anti vacuum trap"],
        "category": "waste",
    },
    {
        "canonical": "32mm compression waste bend",
        "keywords": ["32mm compression bend", "32mm waste bend", "waste bend 32", "32mm knuckle bend"],
        "category": "waste",
    },
    {
        "canonical": "40mm compression waste bend",
        "keywords": ["40mm compression bend", "40mm waste bend", "waste bend 40", "40mm knuckle bend"],
        "category": "waste",
    },
    {
        "canonical": "32mm compression waste coupler",
        "keywords": ["32mm compression coupler", "32mm waste coupler", "32mm waste coupling", "waste coupling 32"],
        "category": "waste",
    },
    {
        "canonical": "40mm compression waste coupler",
        "keywords": ["40mm compression coupler", "40mm waste coupler", "40mm waste coupling", "waste coupling 40"],
        "category": "waste",
    },
    {
        "canonical": "32mm solvent weld bend",
        "keywords": ["32mm solvent bend", "32mm solvent weld bend", "solvent bend 32", "32mm swept bend"],
        "category": "waste",
    },
    {
        "canonical": "40mm solvent weld bend",
        "keywords": ["40mm solvent bend", "40mm solvent weld bend", "solvent bend 40", "40mm swept bend"],
        "category": "waste",
    },
    {
        "canonical": "32mm solvent weld coupler",
        "keywords": ["32mm solvent coupler", "32mm solvent weld coupling", "solvent coupling 32"],
        "category": "waste",
    },
    {
        "canonical": "40mm solvent weld coupler",
        "keywords": ["40mm solvent coupler", "40mm solvent weld coupling", "solvent coupling 40"],
        "category": "waste",
    },
    {
        "canonical": "32mm waste tee",
        "keywords": ["32mm waste tee", "waste tee 32", "32mm swept tee"],
        "category": "waste",
    },
    {
        "canonical": "40mm waste tee",
        "keywords": ["40mm waste tee", "waste tee 40", "40mm swept tee"],
        "category": "waste",
    },
    {
        "canonical": "slotted basin waste",
        "keywords": ["slotted basin waste", "basin waste slotted", "click clack slotted", "pop up slotted"],
        "category": "waste",
    },
    {
        "canonical": "unslotted basin waste",
        "keywords": ["unslotted basin waste", "basin waste unslotted", "click clack unslotted", "pop up unslotted"],
        "category": "waste",
    },
    {
        "canonical": "click clack basin waste",
        "keywords": ["click clack basin waste", "clicker waste", "basin clicker waste"],
        "category": "waste",
    },
    {
        "canonical": "bath waste and overflow",
        "keywords": ["bath waste", "bath waste overflow", "bath waste and overflow", "pop up bath waste"],
        "category": "waste",
    },
    {
        "canonical": "bath trap 40mm",
        "keywords": ["bath trap", "40mm bath trap", "shallow bath trap", "low level bath trap"],
        "category": "waste",
    },
    {
        "canonical": "shower trap 40mm",
        "keywords": ["shower trap", "40mm shower trap", "fast flow shower trap", "low profile shower trap"],
        "category": "waste",
    },
    {
        "canonical": "90mm shower waste",
        "keywords": ["90mm shower waste", "90mm shower trap", "shower waste 90mm"],
        "category": "waste",
    },
    {
        "canonical": "kitchen basket strainer waste",
        "keywords": ["basket strainer", "basket strainer waste", "kitchen basket waste", "sink basket waste"],
        "category": "waste",
    },
    {
        "canonical": "single bowl sink waste kit",
        "keywords": ["single bowl waste kit", "single sink waste kit", "single bowl sink waste"],
        "category": "waste",
    },
    {
        "canonical": "1.5 bowl sink waste kit",
        "keywords": ["1.5 bowl waste kit", "one and half bowl waste", "1 1/2 bowl sink waste", "1.5 sink waste"],
        "category": "waste",
    },
    {
        "canonical": "double bowl sink waste kit",
        "keywords": ["double bowl waste kit", "double sink waste kit", "two bowl sink waste"],
        "category": "waste",
    },
    {
        "canonical": "appliance waste spigot",
        "keywords": ["appliance waste spigot", "washing machine spigot", "dishwasher spigot", "appliance connector"],
        "category": "waste",
    },
    {
        "canonical": "washing machine trap",
        "keywords": ["washing machine trap", "standpipe trap", "appliance trap", "washing machine waste trap"],
        "category": "waste",
    },
    {
        "canonical": "tundish",
        "keywords": ["tundish", "unvented tundish", "condensate tundish"],
        "category": "waste",
    },
    {
        "canonical": "solvent weld cement",
        "keywords": ["solvent weld cement", "solvent cement", "waste pipe cement"],
        "category": "consumables",
    },
{
        "canonical": "full bore isolating valve 15mm",
        "keywords": ["full bore isolating valve", "full bore valve 15"],
        "category": "valves"
    },
    {
        "canonical": "washing machine valve",
        "keywords": ["washing machine valve", "appliance valve"],
        "category": "valves"
    },
    {
        "canonical": "flexi hose 300mm",
        "keywords": ["300mm flexi", "300mm flexible hose"],
        "category": "taps"
    },
    {
        "canonical": "15mm copper olive",
        "keywords": ["15mm olive", "compression olive"],
        "category": "fittings"
    },
{
        "canonical": "fluidmaster bottom entry fill valve",
        "keywords": ["fluidmaster bottom entry", "bottom entry fill valve"],
        "category": "toilet"
    },
    {
        "canonical": "dual flush valve",
        "keywords": ["dual flush valve", "flush valve"],
        "category": "toilet"
    },
    {
        "canonical": "straight pan connector",
        "keywords": ["straight pan connector"],
        "category": "toilet"
    },
    {
        "canonical": "doughnut washer",
        "keywords": ["doughnut washer", "close coupling washer"],
        "category": "toilet"
    },
{
    "canonical": "thermostatic radiator valve",
    "keywords": ["trv", "radiator valve", "thermostatic radiator valve"],
    "category": "heating"
},
{
    "canonical": "lockshield valve",
    "keywords": ["lockshield", "lockshield valve"],
    "category": "heating"
},
{
    "canonical": "radiator bleed valve",
    "keywords": ["bleed valve", "bleed vent"],
    "category": "heating"
},
{
    "canonical": "radiator tail extension",
    "keywords": ["radiator tail", "tail extension"],
    "category": "heating"
},
{
    "canonical": "central heating inhibitor",
    "keywords": ["inhibitor", "fernox inhibitor"],
    "category": "heating"
},
{
    "canonical": "filling loop",
    "keywords": ["boiler filling loop", "filling loop"],
    "category": "heating"
},
{
    "canonical": "automatic air vent",
    "keywords": ["automatic air vent", "aav"],
    "category": "heating"
},
{
    "canonical": "braided filling loop",
    "keywords": ["braided filling loop", "filling loop braided", "boiler filling loop"],
    "category": "heating"
},
{
    "canonical": "angled trv",
    "keywords": ["angled trv", "angled thermostatic radiator valve", "angle trv"],
    "category": "heating"
},
{
    "canonical": "angled lockshield valve",
    "keywords": ["angled lockshield", "angle lockshield", "radiator lockshield angled"],
    "category": "heating"
},
{
    "canonical": "radiator valve tail",
    "keywords": ["radiator tail", "radiator valve tail", "rad tail"],
    "category": "heating"
},
{
    "canonical": "pressure relief valve",
    "keywords": ["prv", "pressure relief valve", "safety valve", "3 bar prv"],
    "category": "heating"
},
{
    "canonical": "expansion vessel",
    "keywords": ["expansion vessel", "ev", "vessel", "boiler vessel"],
    "category": "heating"
},
{
    "canonical": "radiator bleed valve",
    "keywords": ["bleed valve", "radiator bleed valve", "bleed vent", "air bleed"],
    "category": "heating"
},
{
    "canonical": "radiator air lock",
    "keywords": ["air lock", "cold radiator", "radiator not heating", "no heat radiator"],
    "category": "heating"
}

]


def clean_material_name_for_matching(name: str):
    cleaned = (name or "").lower()
    cleaned = re.sub(r"https?://\S+", " ", cleaned)
    cleaned = re.sub(r"[^a-z0-9/.\- ]+", " ", cleaned)
    cleaned = re.sub(r"\b(plumbright|plumbright|city plumbing|screwfix|toolstation|topps tiles|white|chrome|each|pack|pack of)\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def material_alias_info(name: str):
    cleaned = clean_material_name_for_matching(name)
    for rule in MATERIAL_ALIAS_RULES:
        if any(keyword in cleaned for keyword in rule["keywords"]):
            return {
                "canonical": rule["canonical"],
                "category": rule.get("category", "other"),
                "matched": True,
            }
    return {
        "canonical": cleaned or (name or "").strip().lower(),
        "category": "other",
        "matched": False,
    }


def canonical_material_name(name: str):
    return material_alias_info(name)["canonical"]



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


MATERIAL_CHARGING_RULES = {
    "ptfe tape": {
        "material_type": "consumable",
        "charge_method": "partial",
        "default_charge": 0.50,
        "customer_label": "Small consumable allowance",
        "note": "Partial use only. Do not charge whole roll unless specifically supplied."
    },
    "silicone": {
        "material_type": "consumable",
        "charge_method": "partial",
        "default_charge": 3.00,
        "customer_label": "Sealant allowance",
        "note": "Partial tube use unless full tube supplied."
    },
    "solvent weld cement": {
        "material_type": "consumable",
        "charge_method": "partial",
        "default_charge": 2.00,
        "customer_label": "Solvent cement allowance",
        "note": "Partial use only."
    },
    "central heating inhibitor": {
        "material_type": "chargeable",
        "charge_method": "full",
        "default_charge": None,
        "customer_label": "Central heating inhibitor",
        "note": "Normally charged as full bottle when used."
    },
    "15mm copper olive": {
        "material_type": "small_part",
        "charge_method": "small_part",
        "default_charge": 0.30,
        "customer_label": "Compression olives",
        "note": "Small fittings normally charged individually or absorbed into sundries."
    },
}


def get_material_charging_rule(name: str):
    canonical = canonical_material_name(name)
    return MATERIAL_CHARGING_RULES.get(canonical, {
        "material_type": "chargeable",
        "charge_method": "full",
        "default_charge": None,
        "customer_label": canonical,
        "note": "Full chargeable material."
    })


def material_quote_unit_price(name: str, full_price: float, override_price=None):
    if override_price is not None:
        override = safe_float(override_price, None)
        if override is not None:
            return override
    rule = get_material_charging_rule(name)
    if rule.get("charge_method") in ("partial", "small_part") and rule.get("default_charge") is not None:
        return safe_float(rule.get("default_charge"), full_price)
    return full_price



SMART_QUANTITY_RULES = [
    {"match": ["pipe clips 15mm", "15mm pipe clips"], "default_quantity": 6, "job_keywords": ["outside tap", "fridge", "pipe run"]},
    {"match": ["32mm waste pipe clips", "waste pipe clips 32"], "default_quantity": 4, "job_keywords": ["basin", "waste"]},
    {"match": ["40mm waste pipe clips", "waste pipe clips 40"], "default_quantity": 4, "job_keywords": ["sink", "shower", "waste"]},
    {"match": ["15mm copper pipe"], "default_quantity": 1, "job_keywords": ["small", "tap", "fridge", "outside tap"]},
    {"match": ["15mm endfeed elbow", "endfeed elbow"], "default_quantity": 4, "job_keywords": ["outside tap", "pipe run", "leak"]},
    {"match": ["15mm endfeed tee", "endfeed tee"], "default_quantity": 1, "job_keywords": ["outside tap", "branch"]},
    {"match": ["15mm compression coupler", "compression coupler"], "default_quantity": 2, "job_keywords": ["repair", "leak", "extension"]},
    {"match": ["15mm isolating valve", "isolating valve"], "default_quantity": 1, "job_keywords": ["fridge", "appliance"]},
    {"match": ["15mm isolating valve", "isolating valve"], "default_quantity": 2, "job_keywords": ["tap", "basin tap", "kitchen tap"]},
    {"match": ["flexi hose 300mm", "flexi hose 500mm", "flexible tap connector"], "default_quantity": 2, "job_keywords": ["tap", "basin", "kitchen"]},
    {"match": ["15mm copper olive", "olive"], "default_quantity": 2, "job_keywords": ["trv", "valve", "compression"]},
    {"match": ["radiator valve tail", "radiator tail"], "default_quantity": 2, "job_keywords": ["radiator", "trv"]},
    {"match": ["angled trv", "thermostatic radiator valve"], "default_quantity": 1, "job_keywords": ["trv", "radiator"]},
    {"match": ["angled lockshield valve", "lockshield"], "default_quantity": 1, "job_keywords": ["trv", "radiator"]},
    {"match": ["ptfe tape"], "default_quantity": 1, "job_keywords": ["any"]},
    {"match": ["silicone"], "default_quantity": 1, "job_keywords": ["bath", "basin", "toilet", "sink"]},
]


def suggest_material_quantity(name: str, job_text: str = ""):
    canonical = canonical_material_name(name)
    hay = f"{canonical} {name}".lower()
    job = (job_text or "").lower()

    best = None
    best_score = -1
    for rule in SMART_QUANTITY_RULES:
        if not any(term in hay for term in rule.get("match", [])):
            continue

        score = 1
        kws = rule.get("job_keywords", [])
        if "any" in kws:
            score += 1
        score += sum(3 for kw in kws if kw and kw != "any" and kw in job)

        if score > best_score:
            best = rule
            best_score = score

    return best.get("default_quantity", 1) if best else 1


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


TRADE_JOB_LIBRARY = [
    {
        "name": "Outside tap",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Supply and fit outside tap with isolation, double check protection, pipework, clips and testing.",
        "typical_labour": 150,
        "labour_range": "£140 - £220",
        "risk_notes": [
            "Check pipe route and wall thickness.",
            "Add drain off where pipework may freeze.",
            "Lag external pipework where exposed.",
            "Confirm double check valve/backflow protection.",
        ],
        "essential": [
            {"name": "Hose Union Bib Tap 1/2", "quantity": 1},
            {"name": "15mm Isolating Valve", "quantity": 1},
            {"name": "Double Check Valve 15mm", "quantity": 1},
            {"name": "Wall Plate Elbow 15mm x 1/2", "quantity": 1},
            {"name": "15mm Copper Pipe 3m", "quantity": 1},
            {"name": "Pipe Clips 15mm", "quantity": 6},
        ],
        "common": [
            {"name": "Drain Off Cock 15mm", "quantity": 1},
            {"name": "PTFE Tape", "quantity": 1},
            {"name": "Pipe Lagging 15mm", "quantity": 1},
        ],
        "optional": [
            {"name": "Outside Tap Cover", "quantity": 1},
            {"name": "Non Return Valve", "quantity": 1},
        ],
    },
    {
        "name": "Fridge cold water feed",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Supply and connect cold water feed for fridge with isolation valve, pipework, fittings and testing.",
        "typical_labour": 120,
        "labour_range": "£100 - £180",
        "risk_notes": [
            "Confirm fridge connection size before attending.",
            "Check route from nearest cold supply.",
            "Isolation valve should be accessible.",
        ],
        "essential": [
            {"name": "15mm Isolating Valve", "quantity": 1},
            {"name": "15mm Copper Pipe 3m", "quantity": 1},
            {"name": "Compression Coupler 15mm", "quantity": 2},
        ],
        "common": [
            {"name": "Appliance Valve", "quantity": 1},
            {"name": "PTFE Tape", "quantity": 1},
            {"name": "Pipe Clips 15mm", "quantity": 4},
        ],
        "optional": [
            {"name": "Water Filter Inline", "quantity": 1},
        ],
    },
    {
        "name": "Washing machine feed",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Install washing machine cold feed and waste connection, including isolation valve and testing.",
        "typical_labour": 120,
        "labour_range": "£100 - £180",
        "risk_notes": [
            "Check waste height and trap connection.",
            "Make sure appliance valve remains accessible.",
        ],
        "essential": [
            {"name": "Washing Machine Valve 15mm x 3/4", "quantity": 1},
            {"name": "15mm Copper Pipe 3m", "quantity": 1},
            {"name": "Compression Coupler 15mm", "quantity": 2},
            {"name": "Appliance Waste Trap", "quantity": 1},
        ],
        "common": [
            {"name": "Pipe Clips 15mm", "quantity": 4},
            {"name": "PTFE Tape", "quantity": 1},
            {"name": "Waste Pipe 40mm", "quantity": 1},
        ],
        "optional": [
            {"name": "Non Return Valve", "quantity": 1},
        ],
    },
    {
        "name": "Dishwasher feed",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Install dishwasher cold feed and waste connection, including isolation valve and testing.",
        "typical_labour": 120,
        "labour_range": "£100 - £180",
        "risk_notes": [
            "Check sink waste has appliance spigot.",
            "Check hose route and kinks.",
        ],
        "essential": [
            {"name": "Washing Machine Valve 15mm x 3/4", "quantity": 1},
            {"name": "Appliance Waste Trap", "quantity": 1},
            {"name": "15mm Copper Pipe 3m", "quantity": 1},
        ],
        "common": [
            {"name": "Compression Coupler 15mm", "quantity": 2},
            {"name": "Pipe Clips 15mm", "quantity": 4},
            {"name": "PTFE Tape", "quantity": 1},
        ],
        "optional": [
            {"name": "Y Piece Appliance Connector", "quantity": 1},
        ],
    },
    {
        "name": "Kitchen sink waste",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Remove existing kitchen sink waste and fit new waste/trap arrangement including testing for leaks.",
        "typical_labour": 120,
        "labour_range": "£90 - £180",
        "risk_notes": [
            "Check single or double bowl sink.",
            "Check whether appliance connections are needed.",
            "Allow for solvent weld or compression depending on existing waste.",
        ],
        "essential": [
            {"name": "Kitchen Sink Waste Kit", "quantity": 1},
            {"name": "P Trap 40mm", "quantity": 1},
            {"name": "Waste Pipe 40mm", "quantity": 1},
        ],
        "common": [
            {"name": "Waste Pipe Clips 40mm", "quantity": 4},
            {"name": "Solvent Weld Cement", "quantity": 1},
            {"name": "Silicone", "quantity": 1},
        ],
        "optional": [
            {"name": "Appliance Waste Connector", "quantity": 1},
            {"name": "Basket Strainer Waste", "quantity": 1},
        ],
    },
    {
        "name": "Basin waste",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Remove faulty basin waste and fit new basin waste and trap, including testing for leaks.",
        "typical_labour": 90,
        "labour_range": "£80 - £140",
        "risk_notes": [
            "Check slotted or unslotted waste.",
            "Check bottle trap condition.",
            "Old wastes can be seized.",
        ],
        "essential": [
            {"name": "Basin Waste", "quantity": 1},
            {"name": "Bottle Trap 32mm", "quantity": 1},
        ],
        "common": [
            {"name": "Waste Pipe 32mm", "quantity": 1},
            {"name": "Waste Pipe Clips 32mm", "quantity": 2},
            {"name": "Silicone", "quantity": 1},
        ],
        "optional": [
            {"name": "Chrome Bottle Trap", "quantity": 1},
        ],
    },
    {
        "name": "Replace bath taps",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Remove existing bath taps and fit replacement bath taps, including connection checks and testing for leaks.",
        "typical_labour": 180,
        "labour_range": "£150 - £260",
        "risk_notes": [
            "Access behind bath may be poor.",
            "Old tap nuts may be seized.",
            "Check if isolation valves are present.",
        ],
        "essential": [
            {"name": "Bath Tap Connectors", "quantity": 2},
            {"name": "Flexible Tap Connector", "quantity": 2},
            {"name": "PTFE Tape", "quantity": 1},
        ],
        "common": [
            {"name": "15mm Isolating Valve", "quantity": 2},
            {"name": "Tap Back Nut Spanner", "quantity": 1},
        ],
        "optional": [
            {"name": "Bath Taps", "quantity": 1},
        ],
    },
    {
        "name": "Toilet repair",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Repair toilet fault including inlet/fill valve, flush valve or siphon as required, then test operation.",
        "typical_labour": 120,
        "labour_range": "£100 - £180",
        "risk_notes": [
            "Identify whether it is fill valve, flush valve, siphon, button or overflow issue.",
            "Old cistern fittings can be brittle.",
        ],
        "essential": [
            {"name": "Toilet Fill Valve", "quantity": 1},
            {"name": "Toilet Flush Valve", "quantity": 1},
        ],
        "common": [
            {"name": "Close Coupling Kit", "quantity": 1},
            {"name": "15mm Isolating Valve", "quantity": 1},
        ],
        "optional": [
            {"name": "Toilet Button", "quantity": 1},
            {"name": "Toilet Siphon", "quantity": 1},
        ],
    },
    {
        "name": "Toilet replacement",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Remove existing toilet and fit replacement toilet including pan connector, inlet connection and testing.",
        "typical_labour": 180,
        "labour_range": "£160 - £260",
        "risk_notes": [
            "Check soil outlet direction and distance.",
            "Check floor fixing condition.",
            "Allow for new isolation valve if old one fails.",
        ],
        "essential": [
            {"name": "Pan Connector", "quantity": 1},
            {"name": "15mm Isolating Valve", "quantity": 1},
            {"name": "Flexible Tap Connector", "quantity": 1},
            {"name": "Sanitary Silicone", "quantity": 1},
        ],
        "common": [
            {"name": "Toilet Fixing Kit", "quantity": 1},
            {"name": "Close Coupling Kit", "quantity": 1},
        ],
        "optional": [
            {"name": "Offset Pan Connector", "quantity": 1},
        ],
    },
    {
        "name": "Leak repair",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Attend leak, identify source, repair faulty pipework or fitting and test on completion.",
        "typical_labour": 150,
        "labour_range": "£120 - £250",
        "risk_notes": [
            "Leak source may not be visible immediately.",
            "Access damage may be required.",
            "Allow for isolation and drain down time.",
        ],
        "essential": [
            {"name": "15mm Copper Pipe 3m", "quantity": 1},
            {"name": "15mm Straight Coupler", "quantity": 2},
            {"name": "15mm Copper Elbow", "quantity": 4},
        ],
        "common": [
            {"name": "PTFE Tape", "quantity": 1},
            {"name": "Pipe Clips 15mm", "quantity": 4},
            {"name": "15mm Isolating Valve", "quantity": 1},
        ],
        "optional": [
            {"name": "22mm Copper Pipe 3m", "quantity": 1},
            {"name": "22mm Coupler", "quantity": 2},
        ],
    },
    {
        "name": "Stopcock replacement",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Replace faulty stopcock including isolation, pipework adjustment and testing.",
        "typical_labour": 180,
        "labour_range": "£150 - £280",
        "risk_notes": [
            "External stopcock may be needed to isolate supply.",
            "Old pipework may be seized or brittle.",
            "Check pipe size before attending.",
        ],
        "essential": [
            {"name": "Stopcock 15mm", "quantity": 1},
            {"name": "15mm Copper Pipe 3m", "quantity": 1},
            {"name": "Compression Coupler 15mm", "quantity": 2},
        ],
        "common": [
            {"name": "PTFE Tape", "quantity": 1},
            {"name": "Pipe Clips 15mm", "quantity": 2},
        ],
        "optional": [
            {"name": "Stopcock 22mm", "quantity": 1},
        ],
    },
    {
        "name": "Radiator valve replacement",
        "category": "Heating",
        "quote_type": "heating",
        "job": "Replace radiator valves/TRV, refill, test and bleed radiator.",
        "typical_labour": 150,
        "labour_range": "£120 - £220",
        "risk_notes": [
            "System may need partial or full drain down.",
            "Old valve tails can be seized.",
            "Check lockshield and TRV sizes.",
        ],
        "essential": [
            {"name": "TRV Valve", "quantity": 1},
            {"name": "Lockshield Valve", "quantity": 1},
            {"name": "PTFE Tape", "quantity": 1},
        ],
        "common": [
            {"name": "Inhibitor 1L", "quantity": 1},
            {"name": "15mm Copper Olive", "quantity": 2},
        ],
        "optional": [
            {"name": "Radiator Tail Extension", "quantity": 1},
        ],
    },
{
        "name": "Replace basin bottle trap",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Remove existing basin trap and fit new 32mm bottle trap, including waste alignment and leak testing.",
        "typical_labour": 90,
        "labour_range": "£80 - £140",
        "risk_notes": ["Check slotted/unslotted waste.", "Old chrome traps can be seized.", "Check waste pipe alignment."],
        "essential": [
            {"name": "32mm bottle trap", "quantity": 1},
            {"name": "32mm waste pipe", "quantity": 1}
        ],
        "common": [
            {"name": "32mm compression waste coupler", "quantity": 1},
            {"name": "32mm waste pipe clips", "quantity": 2}
        ],
        "optional": [
            {"name": "slotted basin waste", "quantity": 1},
            {"name": "unslotted basin waste", "quantity": 1}
        ],
    },
    {
        "name": "Replace kitchen sink trap",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Remove faulty kitchen sink trap/waste and fit new 40mm trap arrangement, including appliance connections where required and leak testing.",
        "typical_labour": 120,
        "labour_range": "£100 - £180",
        "risk_notes": ["Check single, 1.5 bowl or double bowl sink.", "Confirm dishwasher/washing machine spigots.", "Check existing waste is compression or solvent weld."],
        "essential": [
            {"name": "40mm p trap", "quantity": 1},
            {"name": "40mm waste pipe", "quantity": 1}
        ],
        "common": [
            {"name": "40mm compression waste bend", "quantity": 2},
            {"name": "40mm compression waste coupler", "quantity": 1},
            {"name": "appliance waste spigot", "quantity": 1}
        ],
        "optional": [
            {"name": "single bowl sink waste kit", "quantity": 1},
            {"name": "1.5 bowl sink waste kit", "quantity": 1},
            {"name": "double bowl sink waste kit", "quantity": 1}
        ],
    },
    {
        "name": "Replace bath waste",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Remove existing bath waste/overflow and fit replacement bath waste and trap, including testing for leaks.",
        "typical_labour": 150,
        "labour_range": "£120 - £220",
        "risk_notes": ["Bath access panel may be poor.", "Old bath waste can be seized.", "Check trap depth and floor void."],
        "essential": [
            {"name": "bath waste and overflow", "quantity": 1},
            {"name": "bath trap 40mm", "quantity": 1}
        ],
        "common": [
            {"name": "40mm compression waste coupler", "quantity": 1},
            {"name": "40mm waste pipe", "quantity": 1}
        ],
        "optional": [
            {"name": "40mm shallow trap", "quantity": 1}
        ],
    },
    {
        "name": "Replace shower trap",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Remove and replace shower trap/waste where accessible, including sealing and leak testing.",
        "typical_labour": 150,
        "labour_range": "£120 - £250",
        "risk_notes": ["Access below tray is critical.", "Some trays require removal to replace trap.", "Check 90mm or low profile trap size."],
        "essential": [
            {"name": "shower trap 40mm", "quantity": 1}
        ],
        "common": [
            {"name": "90mm shower waste", "quantity": 1},
            {"name": "40mm compression waste coupler", "quantity": 1}
        ],
        "optional": [
            {"name": "40mm shallow trap", "quantity": 1}
        ],
    },
{
        "name": "Replace kitchen tap",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Remove existing kitchen tap and fit replacement tap.",
        "typical_labour": 140,
        "labour_range": "£120 - £220",
        "risk_notes": ["Check access under sink."],
        "essential": [
            {"name": "flexi hose 300mm", "quantity": 2},
            {"name": "15mm isolating valve", "quantity": 2}
        ],
        "common": [
            {"name": "15mm copper olive", "quantity": 2}
        ],
        "optional": []
    },
    {
        "name": "Install washing machine",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Install washing machine feed and waste.",
        "typical_labour": 120,
        "labour_range": "£100 - £180",
        "risk_notes": ["Check waste spigot."],
        "essential": [
            {"name": "washing machine valve", "quantity": 1}
        ],
        "common": [
            {"name": "appliance waste spigot", "quantity": 1}
        ],
        "optional": []
    },
{
        "name": "Toilet not filling",
        "category": "Toilet repair",
        "quote_type": "small",
        "job": "Repair toilet not filling including fill valve replacement.",
        "typical_labour": 110,
        "labour_range": "£90 - £160",
        "risk_notes": ["Check side or bottom entry."],
        "essential": [
            {"name": "fluidmaster bottom entry fill valve", "quantity": 1},
            {"name": "15mm isolating valve", "quantity": 1}
        ],
        "common": [
            {"name": "15mm x 1/2 flexi hose", "quantity": 1}
        ],
        "optional": []
    },
    {
        "name": "Toilet constantly running",
        "category": "Toilet repair",
        "quote_type": "small",
        "job": "Repair toilet constantly running including flush valve replacement.",
        "typical_labour": 110,
        "labour_range": "£90 - £160",
        "risk_notes": ["Check flush valve compatibility."],
        "essential": [
            {"name": "dual flush valve", "quantity": 1},
            {"name": "doughnut washer", "quantity": 1}
        ],
        "common": [],
        "optional": []
    },
    {
        "name": "Replace toilet",
        "category": "Toilet repair",
        "quote_type": "small",
        "job": "Replace toilet including pan connector and testing.",
        "typical_labour": 220,
        "labour_range": "£180 - £320",
        "risk_notes": ["Check pan alignment."],
        "essential": [
            {"name": "straight pan connector", "quantity": 1},
            {"name": "toilet fixing kit", "quantity": 1}
        ],
        "common": [
            {"name": "doughnut washer", "quantity": 1}
        ],
        "optional": []
    },
{
    "name": "Replace TRV",
    "category": "Heating repair",
    "quote_type": "small",
    "search_terms": ["trv", "thermostatic radiator valve", "radiator valve", "stuck valve", "valve leaking"],
    "job": "Replace faulty thermostatic radiator valve and rebalance radiator.",
    "typical_labour": 120,
    "labour_range": "£100 - £180",
    "risk_notes": ["Check valve compatibility.", "May require draining."],
    "essential": [
        {"name": "angled trv", "quantity": 1},
        {"name": "angled lockshield valve", "quantity": 1},
        {"name": "radiator valve tail", "quantity": 2}
    ],
    "common": [
        {"name": "ptfe tape", "quantity": 1},
        {"name": "15mm copper olive", "quantity": 2},
        {"name": "central heating inhibitor", "quantity": 1}
    ],
    "optional": [],
    "source": "trade_knowledge"
},
{
    "name": "Radiator replacement",
    "category": "Heating repair",
    "quote_type": "heating",
    "search_terms": ["replace radiator", "new radiator", "radiator install", "radiator swap", "rad replacement"],
    "job": "Remove existing radiator and install replacement radiator including valves and inhibitor.",
    "typical_labour": 240,
    "labour_range": "£180 - £350",
    "risk_notes": ["Check wall condition.", "Pipework alterations may be required."],
    "essential": [
        {"name": "angled trv", "quantity": 1},
        {"name": "angled lockshield valve", "quantity": 1},
        {"name": "radiator tail extension", "quantity": 2}
    ],
    "common": [
        {"name": "central heating inhibitor", "quantity": 1},
        {"name": "radiator bleed valve", "quantity": 1}
    ],
    "optional": [],
    "source": "trade_knowledge"
},
{
    "name": "Heating leak repair",
    "category": "Heating repair",
    "quote_type": "small",
    "search_terms": ["aav", "automatic air vent", "heating leak", "radiator leak", "pressure loss", "leaking pipe", "leaking valve"],
    "job": "Investigate and repair heating leak including refill and inhibitor dosing.",
    "typical_labour": 140,
    "labour_range": "£120 - £240",
    "risk_notes": ["Leak location may increase labour.", "System may require partial drain."],
    "essential": [
        {"name": "automatic air vent", "quantity": 1},
        {"name": "central heating inhibitor", "quantity": 1}
    ],
    "common": [
        {"name": "15mm compression elbow", "quantity": 2}
    ],
    "optional": [],
    "source": "trade_knowledge"
},
{
    "name": "System repressurisation",
    "category": "Heating repair",
    "quote_type": "small",
    "search_terms": ["filling loop", "pressure dropping", "low pressure", "boiler pressure", "repressurise", "top up pressure"],
    "job": "Diagnose pressure loss and repressurise heating system.",
    "typical_labour": 90,
    "labour_range": "£80 - £140",
    "risk_notes": ["Pressure loss may indicate hidden leak."],
    "essential": [
        {"name": "braided filling loop", "quantity": 1}
    ],
    "common": [
        {"name": "15mm isolating valve", "quantity": 2},
        {"name": "double check valve 15mm", "quantity": 1},
        {"name": "central heating inhibitor", "quantity": 1}
    ],
    "optional": [],
    "source": "trade_knowledge"
},
{
    "name": "Automatic air vent replacement",
    "category": "Heating repair",
    "quote_type": "small",
    "search_terms": ["aav", "automatic air vent", "air vent", "leaking aav", "heating air vent"],
    "job": "Replace leaking or faulty automatic air vent, refill/vent system and test.",
    "typical_labour": 130,
    "labour_range": "£110 - £200",
    "risk_notes": ["Check access to AAV.", "System may need partial drain down.", "Check pressure after repair."],
    "essential": [
        {"name": "automatic air vent", "quantity": 1},
        {"name": "central heating inhibitor", "quantity": 1}
    ],
    "common": [
        {"name": "ptfe tape", "quantity": 1},
        {"name": "15mm isolating valve", "quantity": 1}
    ],
    "optional": [],
    "source": "trade_knowledge"
},
{
    "name": "Pressure relief valve check",
    "category": "Heating repair",
    "quote_type": "small",
    "search_terms": ["prv", "pressure relief valve", "prv discharge", "overflow pipe dripping", "pressure dropping"],
    "job": "Check pressure relief valve discharge and diagnose heating pressure loss.",
    "typical_labour": 130,
    "labour_range": "£110 - £220",
    "risk_notes": ["Check expansion vessel charge.", "Do not replace PRV without finding cause.", "Check discharge pipe outside."],
    "essential": [
        {"name": "pressure relief valve", "quantity": 1}
    ],
    "common": [
        {"name": "central heating inhibitor", "quantity": 1}
    ],
    "optional": [
        {"name": "expansion vessel", "quantity": 1}
    ],
    "source": "trade_knowledge"
},
{
    "name": "Cold radiator diagnosis",
    "category": "Heating repair",
    "quote_type": "small",
    "search_terms": ["cold radiator", "radiator not heating", "no heating radiator", "air lock", "bleed radiator", "stuck trv"],
    "job": "Diagnose radiator not heating, bleed/test radiator and check TRV/lockshield operation.",
    "typical_labour": 100,
    "labour_range": "£90 - £160",
    "risk_notes": ["Could be air, stuck TRV, balancing issue or sludge.", "Do not promise fix without diagnosis."],
    "essential": [
        {"name": "radiator bleed valve", "quantity": 1}
    ],
    "common": [
        {"name": "angled trv", "quantity": 1},
        {"name": "central heating inhibitor", "quantity": 1}
    ],
    "optional": [],
    "source": "trade_knowledge"
}

]


def get_all_job_templates():
    trade_templates = []
    for job in TRADE_JOB_LIBRARY:
        materials = []
        for group in ("essential", "common"):
            for item in job.get(group, []):
                copied = dict(item)
                copied["bundle_group"] = group
                materials.append(copied)

        trade_templates.append({
            "name": job["name"],
            "category": job.get("category", ""),
            "quote_type": job.get("quote_type", "small"),
            "job": job.get("job", ""),
            "labour": job.get("typical_labour", 0),
            "labour_range": job.get("labour_range", ""),
            "risk_notes": job.get("risk_notes", []),
            "materials": materials,
            "essential": job.get("essential", []),
            "common": job.get("common", []),
            "optional": job.get("optional", []),
            "source": "trade_knowledge",
        })

    existing_names = {t.get("name", "").lower() for t in JOB_TEMPLATES}
    combined = list(JOB_TEMPLATES)
    for template in trade_templates:
        if template["name"].lower() not in existing_names:
            combined.append(template)
    return combined


LABOUR_HINTS = {
    "small": [
        {"keywords": ["tap"], "suggestion": 120, "range": "£100 - £140"},
        {"keywords": ["toilet", "wc"], "suggestion": 180, "range": "£160 - £220"},
        {"keywords": ["waste", "trap"], "suggestion": 120, "range": "£90 - £140"},
        {"keywords": ["outside tap"], "suggestion": 150, "range": "£140 - £180"},
    ],
    "bathroom": [
        {"keywords": ["install"], "suggestion": 1800, "range": "£1,600 - £2,200"},
        {"keywords": ["refurb"], "suggestion": 2200, "range": "£2,000 - £2,800"},
        {"keywords": ["bathroom"], "suggestion": 2000, "range": "£1,600 - £2,800"},
    ],
    "heating": [
        {"keywords": ["radiator"], "suggestion": 180, "range": "£160 - £220"},
        {"keywords": ["repair"], "suggestion": 150, "range": "£120 - £220"},
        {"keywords": ["system"], "suggestion": 3500, "range": "£3,000 - £4,500"},
    ],
}


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
from business import quote_store, invoice_store
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


def normalize_material_url(url: str):
    return (url or "").strip()


def upsert_material_price_cache(url: str, name: str = "", supplier: str = "", price=None, manual_price=None, status: str = "live"):
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
    text = (job_description or "").lower()
    rules = LABOUR_HINTS.get(quote_type, [])
    for rule in rules:
        if any(keyword in text for keyword in rule["keywords"]):
            return rule

    if quote_type == "bathroom":
        return {"suggestion": 2000, "range": "£1,600 - £2,800"}
    if quote_type == "heating":
        return {"suggestion": 180, "range": "£150 - £300"}
    return {"suggestion": 120, "range": "£90 - £180"}


def calculate_quote(data: QuoteRequest):
    raw_materials = 0.0
    material_lines = []

    for item in data.materials:
        url = item.url.strip() if item.url else ""
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

def upsert_customer(name: str, address: str, phone: str):
    name = (name or "").strip()
    address = (address or "").strip()
    phone = (phone or "").strip()

    conn = get_db()
    now = now_uk().isoformat()

    if phone:
        row = conn.execute("SELECT * FROM customers WHERE phone = ? LIMIT 1", (phone,)).fetchone()
        if row:
            conn.execute(
                "UPDATE customers SET name = ?, address = ?, updated_at = ? WHERE id = ?",
                (name or row["name"], address or row["address"], now, row["id"])
            )
            conn.commit()
            conn.close()
            return row["id"]

    if name and address:
        row = conn.execute(
            "SELECT * FROM customers WHERE name = ? AND address = ? LIMIT 1",
            (name, address)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE customers SET phone = ?, updated_at = ? WHERE id = ?",
                (phone or row["phone"], now, row["id"])
            )
            conn.commit()
            conn.close()
            return row["id"]

    conn.execute(
        "INSERT INTO customers (name, address, phone, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (name, address, phone, now, now)
    )
    customer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return customer_id



PHOTO_CATEGORIES = {
    "before": "Before",
    "during": "During",
    "after": "Completed",
    "hidden_pipework": "Hidden pipework",
    "damage": "Damage found",
    "parts_replaced": "Parts replaced",
    "compliance": "Compliance",
    "customer_supplied": "Customer supplied",
    "other": "Other",
}


def normalise_photo_category(value: str) -> str:
    value = (value or "after").strip().lower().replace(" ", "_")
    return value if value in PHOTO_CATEGORIES else "other"


def invoice_photo_folder(invoice_id: int) -> Path:
    folder = INVOICE_PHOTO_DIR / str(int(invoice_id))
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def load_invoice_photos(invoice_id: int):
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM invoice_photos
        WHERE invoice_id = ?
        ORDER BY
          CASE category
            WHEN 'before' THEN 1
            WHEN 'during' THEN 2
            WHEN 'hidden_pipework' THEN 3
            WHEN 'damage' THEN 4
            WHEN 'parts_replaced' THEN 5
            WHEN 'compliance' THEN 6
            WHEN 'customer_supplied' THEN 7
            WHEN 'after' THEN 8
            ELSE 9
          END,
          sort_order ASC,
          id ASC
    """, (invoice_id,)).fetchall()
    conn.close()
    return [{
        "id": row["id"],
        "invoice_id": row["invoice_id"],
        "category": row["category"],
        "category_label": PHOTO_CATEGORIES.get(row["category"], "Other"),
        "caption": row["caption"] or "",
        "filename": row["filename"],
        "original_filename": row["original_filename"] or "",
        "sort_order": row["sort_order"] or 0,
        "created_at": row["created_at"],
        "url": f"/api/invoices/{invoice_id}/photos/{row['id']}",
    } for row in rows]


def save_invoice_photo_record(invoice_id: int, category: str, caption: str,
                              filename: str, original_filename: str):
    conn = get_db()
    next_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM invoice_photos WHERE invoice_id = ?",
        (invoice_id,),
    ).fetchone()[0]
    conn.execute("""
        INSERT INTO invoice_photos (
            invoice_id, category, caption, filename, original_filename,
            sort_order, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        invoice_id,
        normalise_photo_category(category),
        (caption or "").strip(),
        filename,
        original_filename or "",
        int(next_order or 1),
        now_uk().isoformat(),
    ))
    photo_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return photo_id


def prepare_invoice_photo(source_path: Path, output_path: Path):
    with Image.open(source_path) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode not in ("RGB", "L"):
            background = Image.new("RGB", image.size, "white")
            if "A" in image.getbands():
                background.paste(image, mask=image.getchannel("A"))
            else:
                background.paste(image)
            image = background
        elif image.mode == "L":
            image = image.convert("RGB")
        image.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
        image.save(output_path, format="JPEG", quality=82, optimize=True)


def delete_invoice_photo_record(invoice_id: int, photo_id: int):
    conn = get_db()
    row = conn.execute(
        "SELECT filename FROM invoice_photos WHERE id = ? AND invoice_id = ?",
        (photo_id, invoice_id),
    ).fetchone()
    if not row:
        conn.close()
        return False
    conn.execute(
        "DELETE FROM invoice_photos WHERE id = ? AND invoice_id = ?",
        (photo_id, invoice_id),
    )
    conn.commit()
    conn.close()
    try:
        (invoice_photo_folder(invoice_id) / row["filename"]).unlink(missing_ok=True)
    except Exception:
        pass
    return True


def invoice_photo_path(invoice_id: int, photo_id: int):
    conn = get_db()
    row = conn.execute(
        "SELECT filename FROM invoice_photos WHERE id = ? AND invoice_id = ?",
        (photo_id, invoice_id),
    ).fetchone()
    conn.close()
    if not row:
        return None
    path = invoice_photo_folder(invoice_id) / row["filename"]
    return path if path.exists() else None



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
    conn = get_db()
    rows = conn.execute("""
        SELECT *
        FROM customers
        ORDER BY updated_at DESC, id DESC
        LIMIT 200
    """).fetchall()
    conn.close()

    out = []
    for row in rows:
        out.append({
            "id": row["id"],
            "name": row["name"] or "",
            "address": row["address"] or "",
            "phone": row["phone"] or "",
            "updated_at": row["updated_at"],
        })
    return out


def get_customer_history(customer_id: int):
    conn = get_db()
    customer = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if not customer:
        conn.close()
        return None

    quotes = conn.execute("""
        SELECT * FROM quotes
        WHERE customer_id = ?
        ORDER BY created_at_sort DESC, id DESC
        LIMIT 50
    """, (customer_id,)).fetchall()

    invoices = conn.execute("""
        SELECT * FROM invoices
        WHERE customer_id = ?
        ORDER BY created_at_sort DESC, id DESC
        LIMIT 50
    """, (customer_id,)).fetchall()
    conn.close()

    return {
        "customer": {
            "id": customer["id"],
            "name": customer["name"] or "",
            "address": customer["address"] or "",
            "phone": customer["phone"] or "",
        },
        "quotes": [row_to_quote(r) for r in quotes],
        "invoices": [row_to_invoice(r) for r in invoices],
    }




def pounds_text(value):
    return f"£{safe_float(value, 0):.2f}"


def get_public_base_url(request: Request | None = None) -> str:
    return "https://www.nigelharveyplumbing.co.uk"


def absolute_url(path: str, request: Request | None = None) -> str:
    clean_path = path if path.startswith("/") else f"/{path}"
    base = get_public_base_url(request)
    return f"{base}{clean_path}" if base else clean_path


def build_invoice_public_url(invoice_id: int, request: Request | None = None):
    return absolute_url(f"/invoice/{invoice_id}", request)


def _pdf_header(c, title: str, ref_number: str):
    width, height = A4
    y = height - 48
    logo_reader = _pdf_logo_reader()

    text_left = 40
    if logo_reader:
        try:
            c.drawImage(logo_reader, 40, y - 52, width=150, height=48, preserveAspectRatio=True, mask='auto')
            text_left = 205
        except Exception:
            text_left = 40

    c.setFont("Helvetica-Bold", 24)
    c.drawString(text_left, y, COMPANY_NAME)
    c.setFont("Helvetica", 11)
    c.drawString(text_left, y - 18, COMPANY_ADDRESS)
    c.drawString(text_left, y - 34, COMPANY_PHONE)
    c.drawString(text_left, y - 50, COMPANY_EMAIL)
    c.setFont("Helvetica-Bold", 18)
    c.drawRightString(width - 40, y, title)
    c.setFont("Helvetica", 11)
    c.drawRightString(width - 40, y - 18, ref_number)
    c.line(40, y - 62, width - 40, y - 62)
    return y - 84


def _pdf_row(c, y, left, right, bold=False):
    c.setFont("Helvetica-Bold" if bold else "Helvetica", 11)
    c.drawString(50, y, str(left))
    c.drawRightString(A4[0] - 50, y, str(right))
    return y - 18

def _pdf_new_page_if_needed(c, y, min_y=70):
    if y < min_y:
        c.showPage()
        return A4[1] - 50
    return y


def _pdf_draw_wrapped_text(c, text, x, y, max_chars=95, font="Helvetica", size=10, leading=12):
    c.setFont(font, size)
    for raw_line in str(text or "").splitlines() or [""]:
        line = raw_line.strip()
        if not line:
            y -= leading
            continue
        while len(line) > max_chars:
            cut = line.rfind(" ", 0, max_chars)
            if cut <= 0:
                cut = max_chars
            c.drawString(x, y, line[:cut])
            y -= leading
            line = line[cut:].strip()
            y = _pdf_new_page_if_needed(c, y)
            c.setFont(font, size)
        c.drawString(x, y, line)
        y -= leading
        y = _pdf_new_page_if_needed(c, y)
        c.setFont(font, size)
    return y


def _pdf_draw_materials_section(c, y, result):
    material_lines = result.get("material_lines") or []
    if not material_lines:
        return y

    y = _pdf_new_page_if_needed(c, y, 150)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Materials Used")
    y -= 18

    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y, "Item")
    c.drawRightString(390, y, "Qty")
    c.drawRightString(470, y, "Unit")
    c.drawRightString(555, y, "Line total")
    y -= 10
    c.line(40, y, A4[0] - 40, y)
    y -= 14

    c.setFont("Helvetica", 9)
    for item in material_lines:
        y = _pdf_new_page_if_needed(c, y, 90)
        name = str(item.get("name", "Material"))
        qty = item.get("quantity", 1)
        unit_price = item.get("unit_price_used", 0)
        line_total = item.get("line_total", 0)
        source = item.get("price_source") or ("live" if item.get("live_price_used") else "manual")
        source_label = "cached live" if source == "cached" else source

        left_text = f"{name} ({source_label})"
        c.setFont("Helvetica", 9)
        if len(left_text) <= 62:
            c.drawString(40, y, left_text)
            used_lines = 1
        else:
            first = left_text[:62]
            cut = first.rfind(" ")
            if cut > 20:
                first = left_text[:cut]
                rest = left_text[cut:].strip()
            else:
                rest = left_text[62:].strip()
            c.drawString(40, y, first)
            used_lines = 1
            while rest:
                y -= 11
                part = rest[:62]
                cut = part.rfind(" ")
                if cut > 20 and len(rest) > 62:
                    part = rest[:cut]
                    rest = rest[cut:].strip()
                else:
                    rest = rest[len(part):].strip()
                c.drawString(40, y, part)
                used_lines += 1

        top_y = y + (used_lines - 1) * 11
        c.drawRightString(390, top_y, str(qty))
        c.drawRightString(470, top_y, pounds_text(unit_price))
        c.drawRightString(555, top_y, pounds_text(line_total))
        y -= 15

    y -= 6
    c.line(40, y, A4[0] - 40, y)
    y -= 18
    return y



def _pdf_photo_page_header(c, continued=False):
    c.showPage()
    y = _pdf_header(c, "INVOICE JOB PHOTOS", "")
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, "Job Photos" + (" (continued)" if continued else ""))
    return y - 24


def _pdf_draw_invoice_photos(c, item: dict):
    photos = item.get("photos", []) or []
    if not photos:
        return

    y = _pdf_photo_page_header(c, False)
    usable_width = A4[0] - 80
    image_width = (usable_width - 14) / 2
    image_height = 165

    for index, photo in enumerate(photos):
        col = index % 2
        if col == 0 and y < image_height + 80:
            y = _pdf_photo_page_header(c, True)

        x = 40 + col * (image_width + 14)
        image_path = invoice_photo_path(item["id"], photo["id"])

        if image_path:
            try:
                with Image.open(image_path) as im:
                    width, height = im.size
                ratio = min(image_width / max(width, 1), image_height / max(height, 1))
                draw_width, draw_height = width * ratio, height * ratio
                draw_x = x + (image_width - draw_width) / 2
                draw_y = y - draw_height
                c.drawImage(
                    ImageReader(str(image_path)),
                    draw_x, draw_y,
                    width=draw_width, height=draw_height,
                    preserveAspectRatio=True,
                    mask="auto",
                )
            except Exception:
                c.rect(x, y - image_height, image_width, image_height)
                c.drawString(x + 8, y - 20, "Photo unavailable")

        caption_y = y - image_height - 12
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x, caption_y, str(photo.get("category_label", "Job photo"))[:45])
        caption = str(photo.get("caption", "") or "").strip()
        if caption:
            c.setFont("Helvetica", 8)
            for line_number, line in enumerate(textwrap.wrap(caption, width=48)[:3]):
                c.drawString(x, caption_y - 11 - (line_number * 10), line)

        if col == 1 or index == len(photos) - 1:
            y -= image_height + 58


def generate_invoice_pdf_bytes(item: dict):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    invoice = item["invoice"]
    quote_result = item["quote_result"]
    page_width, page_height = A4

    y = _pdf_header(c, "INVOICE", item["invoice_number"])

    # Match the online invoice with two separate information boxes.
    left_x = 40
    gap = 16
    box_width = (page_width - 80 - gap) / 2
    right_x = left_x + box_width + gap

    customer_lines = []
    for value in [
        invoice.get("customer_name", ""),
        invoice.get("customer_address", ""),
        invoice.get("customer_phone", ""),
    ]:
        for raw_line in str(value or "").replace("\r", "").splitlines():
            raw_line = raw_line.strip()
            if raw_line:
                customer_lines.extend(textwrap.wrap(raw_line, width=43) or [raw_line])

    if not customer_lines:
        customer_lines = ["-"]

    detail_lines = [
        ("Date", item.get("created_at", "-")),
        ("Job Ref", item.get("job_reference") or "-"),
        ("Due date", item.get("due_date", "-")),
        ("Status", str(item.get("status", "-")).title()),
    ]

    left_height = 38 + len(customer_lines) * 13
    right_height = 38 + len(detail_lines) * 18
    box_height = max(105, left_height, right_height)
    box_bottom = y - box_height

    c.setFillColorRGB(0.98, 0.98, 0.98)
    c.setStrokeColorRGB(0.88, 0.89, 0.91)
    c.roundRect(left_x, box_bottom, box_width, box_height, 10, fill=1, stroke=1)
    c.roundRect(right_x, box_bottom, box_width, box_height, 10, fill=1, stroke=1)

    c.setFillColorRGB(0.35, 0.35, 0.35)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(left_x + 12, y - 18, "BILL TO")
    c.drawString(right_x + 12, y - 18, "INVOICE DETAILS")

    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica", 10)
    line_y = y - 36
    for line in customer_lines:
        c.drawString(left_x + 12, line_y, line)
        line_y -= 13

    detail_y = y - 38
    for label, value in detail_lines:
        c.setFont("Helvetica", 10)
        c.setFillColorRGB(0.35, 0.35, 0.35)
        c.drawString(right_x + 12, detail_y, str(label))
        c.setFillColorRGB(0, 0, 0)
        c.drawRightString(right_x + box_width - 12, detail_y, str(value)[:38])
        detail_y -= 18

    y = box_bottom - 24

    # Work description, fully wrapped rather than clipped.
    y = _pdf_new_page_if_needed(c, y, 150)
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(40, y, "Work")
    y -= 18

    work_lines = []
    for raw_line in str(invoice.get("job", "-") or "-").replace("\r", "").splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            work_lines.append("")
        else:
            work_lines.extend(textwrap.wrap(raw_line, width=94) or [raw_line])

    work_height = max(54, 24 + len(work_lines) * 13)
    if y - work_height < 70:
        c.showPage()
        y = page_height - 50
        c.setFont("Helvetica-Bold", 13)
        c.drawString(40, y, "Work")
        y -= 18

    work_bottom = y - work_height
    c.setFillColorRGB(0.98, 0.98, 0.98)
    c.setStrokeColorRGB(0.88, 0.89, 0.91)
    c.roundRect(40, work_bottom, page_width - 80, work_height, 10, fill=1, stroke=1)
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica", 10)
    work_y = y - 18
    for line in work_lines:
        c.drawString(52, work_y, line)
        work_y -= 13

    y = work_bottom - 24

    # Materials remain itemised in the downloaded PDF.
    y = _pdf_draw_materials_section(c, y, quote_result)

    y = _pdf_new_page_if_needed(c, y, 255)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(40, y, "Invoice totals")
    y -= 18

    materials_base = quote_result.get("materials_base", invoice.get("materials", 0))
    procurement_amount = quote_result.get("materials_procurement_amount", 0)
    procurement_percent = quote_result.get("materials_procurement_percent", 0)

    total_rows = [
        ("Labour", pounds_text(invoice.get("labour", 0)), False),
    ]
    invoice_callout = safe_float(invoice.get("callout_charge", quote_result.get("callout_charge", 0)), 0)
    if invoice_callout > 0:
        total_rows.append(("Call-out charge", pounds_text(invoice_callout), False))
    invoice_travel = safe_float(invoice.get("travel_charge", quote_result.get("travel_charge", 0)), 0)
    if invoice_travel > 0:
        total_rows.append(("Travel charge", pounds_text(invoice_travel), False))
    total_rows.append(("Materials", pounds_text(materials_base), False))
    if safe_float(procurement_amount, 0) > 0:
        total_rows.append((
            f"Materials procurement & handling ({safe_float(procurement_percent, 0):.0f}%)",
            pounds_text(procurement_amount),
            False,
        ))
    total_rows.extend([
        ("Total", pounds_text(item.get("total_price", 0)), False),
        ("Amount paid", pounds_text(item.get("amount_paid", 0)), False),
        ("Balance due", pounds_text(item.get("balance_due", 0)), True),
    ])

    totals_height = 24 + len(total_rows) * 20
    totals_bottom = y - totals_height
    c.setFillColorRGB(0.98, 0.98, 0.98)
    c.setStrokeColorRGB(0.88, 0.89, 0.91)
    c.roundRect(40, totals_bottom, page_width - 80, totals_height, 10, fill=1, stroke=1)

    row_y = y - 18
    for label, value, important in total_rows:
        c.setFillColorRGB(0.35, 0.35, 0.35)
        c.setFont("Helvetica-Bold" if important else "Helvetica", 11 if not important else 12)
        c.drawString(52, row_y, label)
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold" if important else "Helvetica", 11 if not important else 16)
        c.drawRightString(page_width - 52, row_y, value)
        row_y -= 20

    y = totals_bottom - 24

    # Payment panel matching the online invoice.
    y = _pdf_new_page_if_needed(c, y, 210)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(40, y, "Payment details")
    y -= 18

    payment_height = 138
    payment_bottom = y - payment_height
    c.setFillColorRGB(0.93, 0.97, 1.0)
    c.setStrokeColorRGB(0.75, 0.87, 0.97)
    c.roundRect(40, payment_bottom, page_width - 80, payment_height, 10, fill=1, stroke=1)

    payment_lines = [
        ("Bank", BANK_NAME),
        ("Account name", BANK_ACCOUNT_NAME),
        ("Sort code", BANK_SORT_CODE),
        ("Account number", BANK_ACCOUNT_NUMBER),
        ("Reference", bank_payment_reference(item)),
        ("Amount due", pounds_text(item.get("balance_due", 0))),
    ]
    payment_y = y - 20
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(52, payment_y, "Bank transfer")
    payment_y -= 16

    for label, value in payment_lines:
        c.setFont("Helvetica", 10)
        c.drawString(52, payment_y, f"{label}:")
        c.setFont("Helvetica-Bold" if label in {"Sort code", "Account number", "Reference", "Amount due"} else "Helvetica", 10)
        c.drawString(130, payment_y, str(value))
        payment_y -= 15

    try:
        if QRCODE_AVAILABLE:
            qr_bytes = bank_payment_qr_png(item)
            c.drawImage(
                ImageReader(io.BytesIO(qr_bytes)),
                page_width - 152,
                payment_bottom + 17,
                width=102,
                height=102,
                preserveAspectRatio=True,
                mask="auto",
            )
    except Exception:
        pass

    y = payment_bottom - 22

    # Full payment terms, wrapped properly.
    y = _pdf_new_page_if_needed(c, y, 130)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Payment Terms")
    y -= 17
    c.setFont("Helvetica", 9)

    terms = INVOICE_TERMS[:]
    if (quote_result.get("quote_type", "") or "").lower() == "small":
        terms = terms[:3]

    for term in terms:
        for line_index, line in enumerate(textwrap.wrap(str(term), width=105) or [str(term)]):
            prefix = "• " if line_index == 0 else "  "
            c.drawString(40, y, prefix + line)
            y -= 12
            y = _pdf_new_page_if_needed(c, y, 55)
            c.setFont("Helvetica", 9)

    if item.get("payment_link"):
        y -= 4
        c.drawString(40, y, f"Payment link: {item['payment_link']}")
        y -= 12

    if str(item.get("status", "")).lower() == "paid":
        invoice_paid_watermark(c)

    _pdf_draw_invoice_photos(c, item)

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def generate_quote_pdf_bytes(item: dict):
    result = item["result"]
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    y = _pdf_header(c, "QUOTE", f"Quote #{item['id']}")

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Customer")
    y -= 18
    c.setFont("Helvetica", 11)
    for line in [result.get("customer_name", "-"), result.get("customer_address", "-"), result.get("customer_phone", "-")]:
        if line:
            c.drawString(40, y, str(line)[:75])
            y -= 15

    y -= 8
    c.line(40, y, A4[0] - 40, y)
    y -= 22

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Works")
    y -= 18
    y = _pdf_draw_wrapped_text(c, result.get("job", "-"), 40, y, max_chars=95, font="Helvetica", size=10, leading=14)
    y -= 8
    c.line(40, y, A4[0] - 40, y)
    y -= 24

    # Itemised materials list for customer PDF
    y = _pdf_draw_materials_section(c, y, result)

    y = _pdf_new_page_if_needed(c, y, 170)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Price")
    y -= 20

    materials_base = result.get("materials_base", result.get("materials", 0))
    procurement_amount = result.get("materials_procurement_amount", 0)
    procurement_percent = result.get("materials_procurement_percent", 0)

    y = _pdf_row(c, y, "Labour", pounds_text(result.get("labour", 0)))
    if safe_float(result.get("callout_charge", 0), 0) > 0:
        y = _pdf_row(c, y, "Call-out charge", pounds_text(result.get("callout_charge", 0)))
    if safe_float(result.get("travel_charge", 0), 0) > 0:
        y = _pdf_row(c, y, "Travel charge", pounds_text(result.get("travel_charge", 0)))
    y = _pdf_row(c, y, "Materials supplied", pounds_text(materials_base))

    if safe_float(procurement_amount, 0) > 0:
        y = _pdf_row(
            c,
            y,
            f"Materials procurement & handling ({safe_float(procurement_percent, 0):.0f}%)",
            pounds_text(procurement_amount)
        )

    y = _pdf_row(c, y, "Materials total", pounds_text(result.get("materials", 0)))
    y = _pdf_row(c, y, "Deposit", pounds_text(result.get("deposit_amount", 0)))
    y = _pdf_row(c, y, "Total Price", pounds_text(result.get("total_price", 0)), bold=True)

    y -= 12
    y = _pdf_new_page_if_needed(c, y, 130)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Terms")
    y -= 18
    c.setFont("Helvetica", 9)
    text_obj = c.beginText(40, y)
    for line in QUOTE_TERMS:
        text_obj.textLine(f"• {line}")
    c.drawText(text_obj)

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def send_invoice_email_now(item: dict, to_email: str, extra_message: str = ""):
    if not EMAIL_ENABLED or not EMAIL_USER or not EMAIL_PASS:
        raise RuntimeError("Email sending is not configured yet. Set EMAIL_ENABLED=1, EMAIL_USER and EMAIL_PASS.")

    invoice = item["invoice"]
    public_url = build_invoice_public_url(item["id"])
    subject = (
        f"Invoice {item['invoice_number']}"
        + (f" - Job Ref {item['job_reference']}" if item.get("job_reference") else "")
        + f" - {COMPANY_NAME}"
    )

    greeting = f"Hello {invoice.get('customer_name') or ''},".strip()
    plain_lines = [
        greeting,
        "",
        extra_message.strip() if extra_message else "Please find your invoice attached as a PDF.",
        "",
        f"Invoice number: {item['invoice_number']}",
        f"Job Ref: {item.get('job_reference') or '-'}",
        f"Balance due: {pounds_text(item.get('balance_due', 0))}",
        f"Invoice link: {public_url}",
        "",
        COMPANY_NAME,
        COMPANY_PHONE,
        COMPANY_EMAIL,
    ]
    plain_body = "\n".join([line for line in plain_lines if line is not None])

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = f"{EMAIL_FROM_NAME} <{EMAIL_USER}>"
    msg["To"] = to_email.strip()

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(plain_body, "plain", "utf-8"))

    logo_value = get_company_logo_value()
    html_logo = ""
    logo_bytes = None
    if logo_value:
        try:
            if logo_value.startswith("data:image"):
                _, encoded = logo_value.split(",", 1)
                logo_bytes = base64.b64decode(encoded)
                html_logo = '<img src="cid:companylogo" alt="Nigel Harvey Ltd logo" style="max-height:72px; max-width:220px; display:block; margin:0 0 14px auto;">'
            else:
                html_logo = f'<img src="{escape(logo_value)}" alt="Nigel Harvey Ltd logo" style="max-height:72px; max-width:220px; display:block; margin:0 0 14px auto;">'
        except Exception:
            html_logo = ""

    message_text = escape(extra_message.strip()) if extra_message else "Please find your invoice attached as a PDF."
    customer_name = escape(invoice.get("customer_name") or "")
    html_body = f"""
    <html>
      <body style="margin:0; padding:0; background:#f4f4f4; font-family:Arial, sans-serif; color:#111;">
        <div style="max-width:680px; margin:0 auto; padding:24px 14px;">
          <div style="background:#ffffff; border-radius:16px; padding:28px; box-shadow:0 2px 12px rgba(0,0,0,0.06);">
            <div style="text-align:right;">{html_logo}</div>
            <div style="font-size:18px; font-weight:700; margin-bottom:14px;">{greeting}</div>
            <div style="font-size:16px; line-height:1.6; margin-bottom:18px;">{message_text}</div>
            <div style="border:1px solid #e5e7eb; border-radius:14px; padding:18px; background:#fafafa; margin-bottom:18px;">
              <div style="font-size:13px; letter-spacing:.5px; color:#666; text-transform:uppercase; margin-bottom:10px;">Invoice summary</div>
              <div style="display:flex; justify-content:space-between; gap:12px; margin:8px 0;"><span>Invoice number</span><strong>{escape(item['invoice_number'])}</strong></div>
              <div style="display:flex; justify-content:space-between; gap:12px; margin:8px 0;"><span>Status</span><strong>{escape(item['status'].title())}</strong></div>
              <div style="display:flex; justify-content:space-between; gap:12px; margin:8px 0;"><span>Balance due</span><strong>{escape(pounds_text(item.get('balance_due', 0)))}</strong></div>
            </div>
            <div style="margin-bottom:18px;">
              <a href="{escape(public_url)}" style="display:inline-block; background:#111; color:#fff; text-decoration:none; padding:12px 18px; border-radius:12px; font-weight:700;">Open invoice online</a>
            </div>
            <div style="font-size:14px; line-height:1.6; color:#444;">
              {escape(COMPANY_NAME)}<br>
              {escape(COMPANY_PHONE)}<br>
              {escape(COMPANY_EMAIL)}
            </div>
          </div>
        </div>
      </body>
    </html>
    """

    related = MIMEMultipart("related")
    related.attach(MIMEText(html_body, "html", "utf-8"))

    if logo_bytes:
        image_part = MIMEImage(logo_bytes, _subtype="png")
        image_part.add_header("Content-ID", "<companylogo>")
        image_part.add_header("Content-Disposition", "inline", filename="logo.png")
        related.attach(image_part)

    alt.attach(related)
    msg.attach(alt)

    pdf_part = MIMEBase("application", "pdf")
    pdf_part.set_payload(generate_invoice_pdf_bytes(item))
    encoders.encode_base64(pdf_part)
    pdf_part.add_header("Content-Disposition", "attachment", filename=f"{item['invoice_number']}.pdf")
    msg.attach(pdf_part)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(EMAIL_HOST, EMAIL_PORT, context=context) as server:
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, [to_email.strip()], msg.as_string())

def row_to_lead(row):
    return {
        "id": row["id"],
        "name": row["name"] or "",
        "phone": row["phone"] or "",
        "email": row["email"] or "",
        "address": row["address"] or "",
        "job_type": row["job_type"] or "small",
        "description": row["description"] or "",
        "status": row["status"] or "new",
        "source": row["source"] or "website",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def save_lead(data: LeadRequest):
    now = now_uk()
    conn = get_db()
    conn.execute(
        """
        INSERT INTO leads (name, phone, email, address, job_type, description, status, source, created_at, created_at_sort, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (data.name or "").strip(),
            (data.phone or "").strip(),
            (data.email or "").strip(),
            (data.address or "").strip(),
            (data.job_type or "small").strip() or "small",
            (data.description or "").strip(),
            "new",
            (data.source or "website").strip() or "website",
            format_dt(now),
            now.isoformat(),
            now.isoformat(),
        ),
    )
    lead_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return get_lead_by_id(lead_id)


def get_lead_by_id(lead_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    conn.close()
    return row_to_lead(row) if row else None


def load_leads():
    conn = get_db()
    rows = conn.execute(
        """
        SELECT * FROM leads
        ORDER BY created_at_sort DESC, id DESC
        LIMIT 300
        """
    ).fetchall()
    conn.close()
    return [row_to_lead(r) for r in rows]


def update_lead_status(lead_id: int, status: str):
    status = (status or "new").strip().lower()
    if status not in {"new", "contacted", "quoted", "won", "lost"}:
        status = "new"
    conn = get_db()
    cur = conn.execute(
        "UPDATE leads SET status = ?, updated_at = ? WHERE id = ?",
        (status, now_uk().isoformat(), lead_id),
    )
    conn.commit()
    conn.close()
    if cur.rowcount <= 0:
        return None
    return get_lead_by_id(lead_id)


def delete_lead_by_id(lead_id: int):
    conn = get_db()
    cur = conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def send_lead_notification_email(lead: dict):
    if not EMAIL_ENABLED or not EMAIL_USER or not EMAIL_PASS:
        return
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"New quote request - {lead.get('name') or 'Website lead'}"
        msg["From"] = f"{EMAIL_FROM_NAME} <{EMAIL_USER}>"
        msg["To"] = EMAIL_USER
        public_url = os.getenv("PUBLIC_BASE_URL", "").strip()
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


HTML = r'''
<!doctype html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nigel Harvey Ltd Business App</title>
<style>
body { font-family: Arial, sans-serif; background:#f5f5f5; margin:0; padding:12px; color:#111; }
.wrap { max-width:1100px; margin:0 auto; }
.card { background:white; padding:18px; border-radius:18px; margin-bottom:14px; box-shadow:0 2px 14px rgba(0,0,0,0.06); }
h1 { margin:0 0 6px 0; font-size:30px; }
h2 { margin:0 0 12px 0; font-size:22px; }
h3 { margin:18px 0 8px 0; }
.sub { color:#666; margin-bottom:16px; }
label { display:block; font-weight:700; margin:12px 0 6px; }
input, textarea, select { width:100%; box-sizing:border-box; padding:12px; border:1px solid #ccc; border-radius:10px; font-size:16px; background:white; }
textarea { min-height:100px; resize:vertical; }
button, .btn-link { width:100%; padding:14px; border:none; border-radius:12px; background:black; color:white; font-size:17px; font-weight:700; text-align:center; text-decoration:none; display:inline-block; box-sizing:border-box; cursor:pointer; min-height:52px; }
.btn-secondary { background:#1f7a1f; }
.btn-light { background:#ececec; color:#111; }
.btn-red { background:#b62323; color:white; }
.btn-blue { background:#1e5fbf; color:white; }
.btn-template { background:#333; font-size:15px; padding:10px; }
.templates, .favourites { display:grid; grid-template-columns:repeat(2, 1fr); gap:8px; }
.favourites .btn-template { background:#5a4a00; }
.material-row { border:1px solid #ddd; padding:12px; border-radius:10px; margin-bottom:10px; background:#fafafa; }
.row { display:flex; justify-content:space-between; gap:10px; margin:8px 0; }
.muted { color:#666; }
.result { display:none; background:#f3faf3; border:1px solid #b7d7b7; }
.error { display:none; background:#fff3f3; border:1px solid #e0b7b7; color:#a33; padding:12px; border-radius:10px; margin-top:12px; }
.actions { display:grid; gap:10px; margin-top:14px; }
.notice { display:none; background:#eef7ff; border:1px solid #c7def5; color:#124a7a; padding:12px; border-radius:12px; margin-top:12px; font-weight:700; }
.print-head { display:flex; align-items:center; justify-content:space-between; gap:16px; }
.logo-box img { max-height:70px; max-width:170px; object-fit:contain; }
.history-item { border:1px solid #ddd; border-radius:10px; padding:12px; margin-bottom:10px; background:#fafafa; }
.history-actions { display:grid; grid-template-columns:repeat(2, 1fr); gap:8px; margin-top:10px; }
.history-actions button, .history-actions a { font-size:15px; padding:10px; }
.small { font-size:14px; color:#666; }
.hidden { display:none; }
.check-row { display:flex; align-items:center; gap:10px; margin:12px 0 6px; font-weight:700; }
.check-row input[type="checkbox"] { width:auto; transform:scale(1.2); }
.quote-sheet, .invoice-sheet { background:white; }
.quote-header { border-bottom:2px solid #111; padding-bottom:12px; margin-bottom:14px; }
.quote-company { font-size:28px; font-weight:800; }
.quote-meta { color:#444; margin-top:6px; line-height:1.5; }
.quote-section-title { font-size:18px; font-weight:800; margin-top:18px; margin-bottom:8px; }
.quote-box { border:1px solid #ddd; border-radius:10px; padding:12px; background:#fafafa; }
.quote-total { font-size:32px; font-weight:900; }
.doc-grid-two { display:grid; grid-template-columns:1.15fr 0.85fr; gap:14px; margin-top:14px; }
.doc-grid-bottom { display:grid; grid-template-columns:1fr 0.95fr; gap:14px; margin-top:14px; align-items:start; }
.doc-panel { border:1px solid #ddd; border-radius:12px; background:#fafafa; padding:14px; }
.doc-panel-title { font-size:17px; font-weight:800; margin-bottom:10px; }
.doc-summary .row { margin:10px 0; }
.doc-total-box { border-top:1px solid #ddd; margin-top:12px; padding-top:12px; }
.doc-total-box .quote-total { font-size:40px; line-height:1.05; }
.doc-notes { margin-top:14px; }
.doc-notes-content { line-height:1.6; }
.doc-work-text { line-height:1.6; white-space:pre-wrap; }
.internal-box { margin-top:16px; border:1px dashed #999; background:#fffdf3; }
.search-results { border:1px solid #ddd; border-radius:10px; max-height:220px; overflow:auto; background:#fff; margin-top:8px; }
.search-item { padding:10px; border-bottom:1px solid #eee; cursor:pointer; }
.search-item:last-child { border-bottom:none; }
.search-item:hover { background:#f2f2f2; }
.no-print { display:block; }
.status-bar { font-size:14px; color:#1f7a1f; margin-top:8px; font-weight:700; }
.dashboard-grid { display:grid; grid-template-columns:repeat(2, 1fr); gap:10px; }
.dashboard-item { border:1px solid #ddd; border-radius:10px; padding:12px; background:#fafafa; }
.dashboard-item .num { font-size:26px; font-weight:800; margin-top:4px; }
.tabs { display:grid; grid-template-columns:repeat(7, 1fr); gap:8px; margin-bottom:14px; }
.tabs button { padding:12px; }
.tab-panel { display:none; }
.tab-panel.active { display:block; }
.material-lines { margin-top:10px; }
.material-lines div { font-size:14px; margin-bottom:6px; }
.badge { display:inline-block; padding:4px 8px; border-radius:999px; font-size:12px; font-weight:700; background:#ececec; color:#111; }
.badge.green { background:#dff5df; color:#0c5d0c; }
.badge.red { background:#ffe3e3; color:#8e1414; }
.badge.orange { background:#fff0d9; color:#8a5500; }
.invoice-note { margin-top:10px; font-size:14px; }
.notice { display:none; padding:12px; border-radius:10px; margin-top:12px; font-weight:700; }
.notice.success { background:#eef8ee; border:1px solid #b7d7b7; color:#1f7a1f; }
.notice.error { background:#fff3f3; border:1px solid #e0b7b7; color:#a33; }
.dashboard-summary { display:grid; grid-template-columns:repeat(2, 1fr); gap:10px; margin-top:10px; }
@media print {
  .no-print { display:none !important; }
  body { background:white; padding:0; }
  .card { box-shadow:none; border:none; padding:0; margin:0 0 12px 0; }
  .wrap { max-width:100%; }
  .quote-sheet, .invoice-sheet { page-break-inside: avoid; }
}
@media (max-width: 768px) {
  body { padding:10px; }
  h1 { font-size:26px; }
  h2 { font-size:21px; }
  .tabs { grid-template-columns:repeat(2, 1fr); }
  .templates, .favourites, .dashboard-grid, .history-actions, .doc-grid-two, .doc-grid-bottom, .dashboard-summary { grid-template-columns:1fr; }
  .row { flex-direction:column; gap:4px; }
  .actions { position:sticky; bottom:8px; z-index:5; }
  .doc-total-box .quote-total { font-size:34px; }
}
</style>
</head>
<body>
<div class="wrap">

  <div id="appNotice" class="notice" style="display:none;"></div>

  <div class="card">
    <h1>Nigel Harvey Ltd</h1>
    <div class="sub">Quotes, invoices, customers, profit tracking</div>
    <div id="appNotice" class="notice success"></div>

    <div class="tabs no-print">
      <button class="btn-light" onclick="showTab('dashboardTab')">Dashboard</button>
      <button class="btn-light" onclick="showTab('quotesTab')">Quotes</button>
      <button class="btn-light" onclick="showTab('invoicesTab')">Invoices</button>
      <button class="btn-light" onclick="showTab('customersTab')">Customers</button>
      <button class="btn-light" onclick="showTab('leadsTab')">Leads</button>
      <button class="btn-light" onclick="showTab('safetyTab')">Safety</button>
      <button class="btn-light" onclick="showTab('materialsDbTab')">Material Database</button>
      <button class="btn-light" onclick="showTab('intelligenceTab')">Intelligence</button>
    </div>

    <div id="dashboardTab" class="tab-panel active">
      <h2>Dashboard</h2>
      <div class="small" id="dashboardMonth"></div>
      <div id="dashboardGrid" class="dashboard-grid"></div>
      <h3>Monthly profit</h3>
      <div id="profitChart" class="quote-box small">Loading chart...</div>
      <div id="dashboardSummary" class="dashboard-summary"></div>
    </div>

    <div id="quotesTab" class="tab-panel">
      <h2>AI Quote Builder</h2>
      <p class="small">Enter the customer and describe the work. AI will build the scope, labour and materials for you. Review and adjust before generating the final quote.</p>
      <div id="editingStatus" class="status-bar hidden"></div>
      <button type="button" class="btn-light no-print" style="margin-bottom:12px;" onclick="startNewQuote()">Start Fresh Quote</button>

      <div class="quote-box small no-print" style="margin-bottom:12px;background:#f8fafc;">
        <strong>Simple workflow</strong><br>
        <span class="small">1. Add customer details &nbsp; 2. Describe the work &nbsp; 3. Build with AI &nbsp; 4. Review materials and labour &nbsp; 5. Generate quote</span>
      </div>

      <label for="quote_type">Quote type</label>
      <select id="quote_type" onchange="document.addEventListener("click", function(event) {
  const panel = document.getElementById("invoiceEditPanel");
  if (panel && event.target === panel) cancelInvoiceEdit();
});

document.addEventListener("keydown", function(event) {
  if (event.key === "Escape") {
    const panel = document.getElementById("invoiceEditPanel");
    if (panel && !panel.classList.contains("hidden")) cancelInvoiceEdit();
  }
});

toggleBathroomFields(); updateLabourSuggestion(); scheduleQuoteLearning(); scheduleLabourIntelligence();">
        <option value="small">Small Job</option>
        <option value="bathroom">Bathroom</option>
        <option value="heating">Heating</option>
      </select>

      <label for="customer_name">Customer name</label>
      <input id="customer_name" placeholder="John Smith">

      <label for="customer_address">Customer address</label>
      <textarea id="customer_address" placeholder="125 Bushy Hill Drive, Guildford, GU1 2UG"></textarea>

      <label for="customer_phone">Customer phone</label>
      <input id="customer_phone" placeholder="07123 456789">

      <label for="job">Job description</label>
      <textarea id="job" placeholder="Example: Replace kitchen tap" oninput="updateLabourSuggestion(); scheduleQuoteLearning(); scheduleLabourIntelligence(); updateForgottenItemWarnings()"></textarea>

      <div class="quote-box small no-print" style="margin-top:10px;border-color:#2563eb;background:#eff6ff;">
        <strong>Workflow Fixes + Travel V16.3.2</strong><br>
        <span class="small">Describe the job by voice, or add video, photos, plans and notes. Audio-only is recommended for most site visits.</span>

        <div class="history-actions" style="grid-template-columns:1fr;margin-top:10px;">
          <button type="button" class="btn-green" onclick="toggleSiteInformationPanel()">➕ Add Site Information</button>
        </div>

        <div id="siteInformationPanel" class="hidden" style="margin-top:10px;padding:10px;border:1px solid #93c5fd;border-radius:10px;background:white;">
          <div class="history-actions" style="grid-template-columns:1fr 1fr;gap:8px;">
            <button type="button" id="recordSiteAudioButton" class="btn-green" onclick="startSiteAudioRecording()">🎙️ Record Job Walkthrough</button>
            <button type="button" id="recordSiteVideoButton" class="btn-light" onclick="startSiteVideoRecording()">📹 Record Video Walkthrough</button>
            <button type="button" class="btn-light" onclick="takeSitePhoto()">📷 Add Photos</button>
            <button type="button" class="btn-light" onclick="document.getElementById('sitePlans')?.click()">📄 Add Plans / Drawings</button>
          </div>

          <div id="siteAudioRecorder" class="hidden" style="margin-top:10px;padding:10px;border:1px solid #86efac;border-radius:10px;background:#f0fdf4;">
            <strong>Recording job walkthrough</strong><br>
            <span class="small">Say what is being fitted, measurements, pipe/fitting quantities, what can stay, who supplies the main product, access and making-good.</span>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px;">
              <strong id="siteAudioTimer">00:00</strong>
              <span id="siteAudioSize" class="small">Recording…</span>
            </div>
            <div class="history-actions" style="grid-template-columns:1fr 1fr;gap:8px;margin-top:8px;">
              <button type="button" class="btn-red" onclick="stopSiteAudioRecording()">Stop & use audio</button>
              <button type="button" class="btn-light" onclick="cancelSiteAudioRecording()">Cancel</button>
            </div>
          </div>

          <div id="siteVideoRecorder" class="hidden" style="margin-top:10px;padding:10px;border:1px solid #93c5fd;border-radius:10px;background:white;">
            <video id="siteVideoPreview" autoplay muted playsinline style="width:100%;max-height:360px;border-radius:8px;background:#111;"></video>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px;">
              <strong id="siteVideoTimer">00:00</strong>
              <span id="siteVideoSize" class="small">Preparing camera…</span>
            </div>
            <div class="history-actions" style="grid-template-columns:1fr 1fr;gap:8px;margin-top:8px;">
              <button type="button" class="btn-red" onclick="stopSiteVideoRecording()">Stop & use video</button>
              <button type="button" class="btn-light" onclick="cancelSiteVideoRecording()">Cancel</button>
            </div>
          </div>

          <input id="siteCameraPhoto" type="file" accept="image/*" capture="environment" multiple hidden>
          <input id="siteCameraVideoFallback" type="file" accept="video/*" capture="environment" hidden>
          <input id="siteAudioFallback" type="file" accept="audio/*" capture hidden>
          <input id="sitePlans" type="file" accept="image/*,application/pdf" multiple hidden>

          <details style="margin-top:10px;">
            <summary><strong>Choose existing files</strong></summary>
            <label for="siteSurveyPhotos" style="margin-top:8px;">Existing photos</label>
            <input id="siteSurveyPhotos" type="file" accept="image/*" multiple>
            <label for="siteSurveyVideo" style="margin-top:8px;">Existing video</label>
            <input id="siteSurveyVideo" type="file" accept="video/*">
            <label for="siteSurveyAudio" style="margin-top:8px;">Existing audio</label>
            <input id="siteSurveyAudio" type="file" accept="audio/*">
          </details>

          <label for="siteVisitNotes" style="margin-top:10px;">Site notes</label>
          <textarea id="siteVisitNotes" placeholder="Optional notes, measurements, customer choices or anything not said in the recording."></textarea>
        </div>

        <div id="siteCaptureSummary" class="small" style="margin-top:8px;">No site information added yet.</div>

        <div class="history-actions" style="grid-template-columns:2fr 1fr;gap:8px;margin-top:10px;">
          <button type="button" id="aiQuoteButton" class="btn-green" onclick="analyseAndBuildQuote()">✨ Analyse Site & Build Quote</button>
          <button type="button" class="btn-light" onclick="clearSiteSurvey()">Clear</button>
        </div>
        <div id="siteSurveyStatus" class="small" style="margin-top:8px;"></div>
        <div id="siteSurveyResult" style="margin-top:8px;"></div>
        <div id="aiQuoteStatus" class="small" style="margin-top:8px;"></div>
        <div id="aiQuoteResult" style="margin-top:8px;"></div>
      </div>


      <div id="bathroomFields" class="hidden">
        <h3>Bathroom / tiling</h3>

        <div class="check-row">
          <input type="checkbox" id="tiling">
          <span>Include tiling</span>
        </div>

        <label for="wall_tiling_m2">Wall tiling (m²)</label>
        <input id="wall_tiling_m2" type="number" step="0.1" placeholder="0">

        <label for="floor_tiling_m2">Floor tiling (m²)</label>
        <input id="floor_tiling_m2" type="number" step="0.1" placeholder="0">

        <label for="wall_height">Wall height</label>
        <select id="wall_height">
          <option value="half">Half height</option>
          <option value="full">Full height</option>
        </select>

        <div class="check-row">
          <input type="checkbox" id="customer_supplies_tiles">
          <span>Customer supplies tiles</span>
        </div>
      </div>

      <h3>Materials</h3>
      <p class="small">AI-added materials appear here. You can edit quantities, suppliers and prices before producing the quote.</p>
      <div id="materials"></div>

      <div class="history-actions no-print" style="grid-template-columns:1fr 1fr;gap:8px;margin-top:8px;">
        <button type="button" class="btn-light" onclick="toggleManualMaterialSearch()">+ Add Material</button>
        <button type="button" class="btn-light" onclick="addMaterial()">+ Blank Material Row</button>
      </div>

      <div id="manualMaterialSearchPanel" class="quote-box small no-print" style="margin-top:8px;display:none;">
        <strong>Find a material</strong><br>
        <span class="small">Search saved materials, then use Update price on a material row to look for a current merchant match. Smart quantities remain active.</span>
        <input id="materialSearch" placeholder="e.g. 15mm elbow, basin waste, kitchen tap" oninput="searchMaterials()" style="margin-top:8px;">
        <div id="searchResults" class="search-results hidden"></div>
      </div>

      <h3>Pricing</h3>
      <label for="labour">Labour cost (£)</label>
      <input id="labour" type="number" step="0.01" placeholder="180" oninput="scheduleLabourIntelligence()">

      <div class="quote-box" style="margin-top:12px;border-color:#f59e0b;background:#fffbeb;">
        <div class="check-row" style="margin-top:0;">
          <input type="checkbox" id="include_callout_charge">
          <span><strong>Include call-out charge</strong></span>
        </div>
        <label for="callout_charge">Call-out charge (£)</label>
        <input id="callout_charge" type="number" step="0.01" min="0" value="200" placeholder="200">
        <div class="small">Use this for an emergency, evening or out-of-hours call-out. You can change the amount for each job.</div>
      </div>

      <div class="quote-box" style="margin-top:12px;border-color:#0ea5e9;background:#f0f9ff;">
        <div class="check-row" style="margin-top:0;">
          <input type="checkbox" id="include_travel_charge">
          <span><strong>Include travel charge</strong></span>
        </div>
        <label for="travel_charge">Travel charge (£)</label>
        <input id="travel_charge" type="number" step="0.01" min="0" value="0" placeholder="0">
        <div class="small">Optional charge for jobs outside your normal working area. Shown separately from labour and call-out charges.</div>
      </div>

      <div class="small" id="labourSuggestion" style="margin-top:8px;"></div>
      <div id="learningInsights" class="quote-box small" style="margin-top:10px; display:none;"></div>
      <div id="labourIntelligence" class="quote-box small" style="margin-top:10px; display:none;"></div>
      <div id="forgottenItemWarnings" class="quote-box small" style="margin-top:10px; display:none; border-color:#f59e0b; background:#fffbeb;"></div>

      <div class="check-row">
        <input type="checkbox" id="include_materials_handling" checked>
        <span>Include materials procurement & handling</span>
      </div>

      <label for="materials_handling_percent">Materials procurement & handling %</label>
      <select id="materials_handling_percent">
        <option value="20">20%</option>
        <option value="25" selected>25%</option>
        <option value="30">30%</option>
      </select>

      <label for="deposit_percent">Deposit % (optional)</label>
      <select id="deposit_percent">
        <option value="0" selected>0%</option>
        <option value="10">10%</option>
        <option value="25">25%</option>
        <option value="50">50%</option>
      </select>

      <details class="quote-box small no-print" style="margin-top:14px;">
        <summary style="cursor:pointer;font-weight:700;">Advanced quote tools</summary>
        <p class="small" style="margin-top:8px;">Templates, favourites and the master material library are still available when you need to manually override or maintain the AI-generated quote.</p>

        <div class="check-row">
          <input type="checkbox" id="internal_mode">
          <span>Internal mode</span>
        </div>

        <h3>Saved templates</h3>
        <div class="quote-box small">
          <label for="templateSearch">Search job template</label>
          <input id="templateSearch" placeholder="e.g. outside tap, leak, bath taps, fridge feed" oninput="renderTemplateSearch()">
          <div id="templateSearchResults" class="search-results hidden"></div>
          <div class="history-actions" style="grid-template-columns:1fr 1fr;gap:8px;margin-top:10px;">
            <button type="button" class="btn-light" onclick="clearQuoteMaterials()">Clear Materials</button>
            <button type="button" class="btn-light" onclick="duplicateLastMaterial()">Duplicate Last Material</button>
          </div>
        </div>

        <div id="templateButtons" class="templates"></div>

        <h3>Favourite materials</h3>
        <div id="favouriteButtons" class="favourites"></div>

        <h3>Master material library</h3>
        <div class="quote-box small" style="margin-top:10px;">
          <strong>Supplier Preference Engine</strong><br>
          <span class="small">Learns your most-used supplier per material from quote history.</span>
          <div class="history-actions" style="grid-template-columns:1fr;margin-top:8px;">
            <button type="button" class="btn-light" onclick="loadSupplierPreferencesPanel()">Load supplier preferences</button>
          </div>
          <div id="supplierPreferencesPanel" style="margin-top:8px;"></div>
        </div>
        <div class="quote-box small">
          <p class="small">Core plumbing fittings grouped by proper material names. This remains the material brain used by quote learning and AI matching.</p>
          <div id="masterMaterialSearchBox" style="margin-bottom:10px;">
            <label for="masterMaterialSearch">Search master materials</label>
            <input id="masterMaterialSearch" placeholder="e.g. copper, elbow, valve, waste, pan connector" oninput="renderMasterMaterialSuggestions()">
          </div>
          <div id="master-material-library" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;"></div>
        </div>
      </details>

      <button type="button" class="no-print" onclick="generateQuote()">Generate Quote</button>
      <div id="error" class="error"></div>
      <div id="notice" class="notice"></div>
    </div>

    <div id="invoicesTab" class="tab-panel">
      <h2>Invoices</h2>
      <div id="invoiceList" class="small">No invoices yet.</div>
    </div>

    <div id="customersTab" class="tab-panel">
      <h2>Customers</h2>
      <input id="customerSearch" placeholder="Search customer by name, phone or address" oninput="loadCustomers()">
      <div id="customerList" class="small" style="margin-top:10px;">No customers yet.</div>
    </div>

    <div id="leadsTab" class="tab-panel">
      <h2>Lead Generator</h2>
      <div class="small">Public quote request page: <a href="/request-quote" target="_blank">/request-quote</a></div>
      <div class="lead-filter-row">
        <input id="leadSearch" placeholder="Search leads by name, phone, email, address or job" oninput="loadLeads()">
        <select id="leadStatusFilter" onchange="loadLeads()">
          <option value="all">All statuses</option>
          <option value="new">New</option>
          <option value="contacted">Contacted</option>
          <option value="quoted">Quoted</option>
          <option value="won">Won</option>
          <option value="lost">Lost</option>
        </select>
      </div>
      <div id="leadList" class="small" style="margin-top:10px;">No leads yet.</div>
    </div>
    <div id="materialsDbTab" class="tab-panel">
      <h2>Material Price Database</h2>
      <p class="small">These are materials saved from product URLs you use in quotes. Live prices are refreshed from the supplier where possible, otherwise the app keeps the last saved live price.</p>

      <div class="grid2">
        <div>
          <label for="materialDbSearch">Search materials</label>
          <input id="materialDbSearch" placeholder="Search name, supplier or URL" oninput="renderMaterialDbList()">
        </div>
        <div>
          <label for="materialDbSupplier">Supplier filter</label>
          <select id="materialDbSupplier" onchange="renderMaterialDbList()">
            <option value="">All suppliers</option>
          </select>
        </div>
      </div>

      <div class="history-actions" style="grid-template-columns:1fr 1fr;gap:10px;margin:12px 0;">
        <button type="button" class="btn-primary" onclick="loadMaterialDb()">Reload Database</button>
        <button type="button" class="btn-green" onclick="refreshMaterialDbPrices()">Refresh Live Prices</button>
      </div>

      <div class="small" id="materialDbSummary" style="margin:8px 0;"></div>
      <div id="materialDbList" class="history-list">No saved materials yet.</div>
    </div>

  </div>

    <div id="intelligenceTab" class="tab-panel">
      <h2>Business Intelligence</h2>
      <p class="small">This is where the app starts learning from your quotes and material prices.</p>
      <button type="button" class="btn-primary" onclick="loadIntelligence()">Refresh Intelligence</button>
      <h3>Job averages</h3>
      <div id="jobIntelligenceList" class="small">No intelligence yet.</div>
      <h3>Material price history</h3>
      <div id="materialIntelligenceList" class="small">No price history yet.</div>
    </div>


    <div id="safetyTab" class="tab-panel">
      <h2>Safety & Backups</h2>
      <p class="small">Use this before big changes. It protects your customers, quotes, invoices and material database.</p>

      <div class="history-actions" style="grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px;">
        <button type="button" class="btn-primary" onclick="createBackupNow()">Create Backup Now</button>
        <button type="button" class="btn-light" onclick="loadSafety()">Reload Status</button>
      </div>

      <div id="safetyStatus" class="quote-box small" style="margin-top:12px;">Click Reload Status to check backups.</div>
      <h3 style="margin-top:16px;">Backups</h3>
      <div id="backupList" class="history-list small" style="margin-top:12px;">No backups loaded.</div>
    </div>

  <div id="resultCard" class="card result quote-sheet">
    <div class="quote-header print-head">
      <div><div class="quote-company">Nigel Harvey Ltd</div>
      <div class="quote-meta">
        125 Bushy Hill Drive, Guildford, GU1 2UG<br>
        07595 725547<br>
        Nigelharveyplumbing@gmail.com
      </div>
      <div class="logo-box">__COMPANY_LOGO_HTML__</div>
    </div>

    <div class="doc-grid-two">
      <div class="doc-panel">
        <div class="doc-panel-title">Works</div>
        <div id="r_job" class="doc-work-text"></div>
      </div>
      <div class="doc-panel doc-summary">
        <div class="doc-panel-title">Quote details</div>
        <div class="row"><span class="muted">Date</span><span id="r_date"></span></div>
        <div class="row"><span class="muted">Type</span><span id="r_type"></span></div>
        <div class="row"><span class="muted">Customer</span><span id="r_customer"></span></div>
        <div class="row"><span class="muted">Phone</span><span id="r_phone"></span></div>
        <div class="row"><span class="muted">Address</span><span id="r_address"></span></div>
      </div>
    </div>

    <div class="doc-grid-bottom">
      <div class="doc-panel">
        <div class="doc-panel-title">Materials used</div>
        <div id="r_material_lines" class="material-lines"></div>
      </div>
      <div class="doc-panel doc-summary">
        <div class="doc-panel-title">Pricing summary</div>
        <div class="row"><span class="muted">Labour</span><span id="r_labour"></span></div>
        <div class="row" id="r_callout_row" style="display:none;"><span class="muted">Call-out charge</span><span id="r_callout"></span></div>
        <div class="row" id="r_travel_row" style="display:none;"><span class="muted">Travel charge</span><span id="r_travel"></span></div>
        <div class="row"><span class="muted">Materials supplied</span><span id="r_materials_base"></span></div>
        <div class="row" id="r_procurement_row"><span class="muted">Materials procurement &amp; handling <span id="r_procurement_percent"></span></span><span id="r_procurement_amount"></span></div>
        <div class="row"><span class="muted">Materials total</span><span id="r_materials"></span></div>
        <div class="row"><span class="muted">Deposit</span><span id="r_deposit"></span></div>
        <div class="doc-total-box">
          <div class="muted">Total price</div>
          <div class="quote-total" id="r_total"></div>
        </div>
      </div>
    </div>

    <div id="internalBox" class="quote-box internal-box hidden">
      <div class="quote-section-title" style="margin-top:0;">Internal only</div>
      <div class="row"><span class="muted">Raw materials</span><span id="r_internal_raw"></span></div>
      <div class="row"><span class="muted">Job multiplier</span><span id="r_internal_job_multiplier"></span></div>
      <div class="row"><span class="muted">After job markup</span><span id="r_internal_after_job"></span></div>
      <div class="row"><span class="muted">Handling %</span><span id="r_internal_handling_percent"></span></div>
      <div class="row"><span class="muted">After handling</span><span id="r_internal_after_handling"></span></div>
      <div class="row"><span class="muted">Hidden uplift</span><span id="r_internal_hidden_uplift"></span></div>
      <div class="row"><span class="muted">Gross profit</span><span id="r_internal_profit"></span></div>
      <div class="row"><span class="muted">Margin %</span><span id="r_internal_margin"></span></div>
    </div>

    <div class="doc-panel doc-notes">
      <div class="doc-panel-title">Notes</div>
      <div class="doc-notes-content">
        Includes labour, supplied materials and materials procurement where selected.<br>
        Materials procurement covers sourcing, collection, transportation, supplier coordination and warranty handling.<br>
        Payment due as agreed.<br>
        Late payment fee may be applied after 14 days.<br>
        Materials remain the property of Nigel Harvey Ltd until paid in full.<br>
        Deposit required before works begin where applicable.<br>
        Quote subject to site conditions and any unforeseen issues.
      </div>
    </div>

    <div class="actions no-print">
      <a id="whatsappBtn" class="btn-link btn-secondary" href="#" target="_blank">Send Quote to WhatsApp</a>
      <button class="btn-blue" onclick="convertCurrentQuoteToInvoice()">Convert to Invoice</button>
      <button class="btn-light" type="button" onclick="downloadCurrentQuotePdf()">Download Quote PDF</button>
    </div>
  </div>

  <div id="invoiceCard" class="card result invoice-sheet" style="position:relative;">
    <div id="invoicePaidWatermark" class="hidden" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:96px;font-weight:900;color:rgba(22,163,74,.13);transform:rotate(-24deg);pointer-events:none;z-index:2;">PAID</div>
    <div class="quote-header print-head">
      <div><div class="quote-company">Nigel Harvey Ltd</div>
      <div class="quote-meta">
        125 Bushy Hill Drive, Guildford, GU1 2UG<br>
        07595 725547<br>
        Nigelharveyplumbing@gmail.com
      </div>
    </div>

    <div class="doc-grid-two">
      <div class="doc-panel">
        <div class="doc-panel-title">Work</div>
        <div id="i_job" class="doc-work-text"></div>
      </div>
      <div class="doc-panel doc-summary">
        <div class="doc-panel-title">Invoice details</div>
        <div class="row"><span class="muted">Invoice number</span><span id="i_number"></span></div>
        <div class="row"><span class="muted">Job Ref</span><span id="i_job_reference">-</span></div>
        <div class="row"><span class="muted">Date</span><span id="i_date"></span></div>
        <div class="row"><span class="muted">Due date</span><span id="i_due_date"></span></div>
        <div class="row"><span class="muted">Status</span><span id="i_status"></span></div>
        <div class="row"><span class="muted">Customer</span><span id="i_customer"></span></div>
        <div class="row"><span class="muted">Phone</span><span id="i_phone"></span></div>
        <div class="row"><span class="muted">Address</span><span id="i_address"></span></div>
      </div>
    </div>

    <div class="doc-grid-bottom">
      <div class="doc-panel">
        <div class="doc-panel-title">Payment</div>
        <div id="i_payment_link_box"></div>
      </div>
      <div class="doc-panel doc-summary">
        <div class="doc-panel-title">Invoice totals</div>
        <div class="row"><span class="muted">Labour</span><span id="i_labour"></span></div>
        <div class="row" id="i_callout_row" style="display:none;"><span class="muted">Call-out charge</span><span id="i_callout"></span></div>
        <div class="row" id="i_travel_row" style="display:none;"><span class="muted">Travel charge</span><span id="i_travel"></span></div>
        <div class="row"><span class="muted">Materials</span><span id="i_materials"></span></div>
        <div class="row"><span class="muted">Total</span><span id="i_total"></span></div>
        <div class="row"><span class="muted">Amount paid</span><span id="i_paid"></span></div>
        <div class="row"><span class="muted">Outstanding</span><span id="i_balance"></span></div>
        <div class="doc-total-box">
          <div class="muted">Balance due</div>
          <div class="quote-total" id="i_balance_big"></div>
        </div>
      </div>
    </div>

    <div id="invoiceEditPanel" class="hidden no-print"
      style="display:none;position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.55);padding:18px;overflow:auto;">
      <div style="max-width:760px;margin:24px auto;background:#fff;border-radius:16px;padding:20px;box-shadow:0 20px 60px rgba(0,0,0,.3);">
      <div class="quote-section-title" style="margin-top:0;">Edit invoice</div>
      <label for="edit_invoice_customer_name">Customer name</label>
      <input id="edit_invoice_customer_name" placeholder="Customer name">
      <label for="edit_invoice_customer_address">Customer address</label>
      <textarea id="edit_invoice_customer_address" placeholder="Customer address"></textarea>
      <label for="edit_invoice_customer_phone">Customer phone</label>
      <input id="edit_invoice_customer_phone" placeholder="Customer phone">
      <label for="edit_invoice_job">Job</label>
      <textarea id="edit_invoice_job" placeholder="Job details"></textarea>
      <div style="margin:14px 0;padding:14px;border:2px solid #2563eb;border-radius:12px;background:#eff6ff;">
        <label for="edit_invoice_job_reference" style="margin-top:0;font-size:18px;">Job Ref</label>
        <input id="edit_invoice_job_reference"
               placeholder="Type the company's job reference"
               style="font-size:18px;font-weight:700;background:white;">
        <div class="small" style="margin-top:6px;">This is the reference supplied by the company for the job you are invoicing.</div>
      </div>
      <label for="edit_invoice_labour">Labour (£)</label>
      <input id="edit_invoice_labour" type="number" step="0.01" placeholder="0">
      <label for="edit_invoice_callout_charge">Call-out charge (£)</label>
      <input id="edit_invoice_callout_charge" type="number" step="0.01" min="0" placeholder="0">
      <label for="edit_invoice_travel_charge">Travel charge (£)</label>
      <input id="edit_invoice_travel_charge" type="number" step="0.01" min="0" placeholder="0">
      <label for="edit_invoice_materials">Materials (£)</label>
      <input id="edit_invoice_materials" type="number" step="0.01" placeholder="0">
      <label for="edit_invoice_due_date">Due date</label>
      <input id="edit_invoice_due_date" placeholder="dd/mm/yyyy">
      <label for="edit_invoice_payment_link">Payment link</label>
      <input id="edit_invoice_payment_link" placeholder="https://...">
      <label for="edit_invoice_amount_paid">Amount paid (£)</label>
      <input id="edit_invoice_amount_paid" type="number" step="0.01" placeholder="0">
      <label for="edit_invoice_reminder_email">Reminder email</label>
      <input id="edit_invoice_reminder_email" type="email" placeholder="accounts@customer.co.uk">
      <div class="check-row">
        <input id="edit_invoice_reminders_enabled" type="checkbox">
        <span>Enable optional overdue email reminders</span>
      </div>
      <div class="history-actions" style="grid-template-columns:1fr 1fr; margin-top:12px;">
        <button type="button" class="btn-blue" onclick="saveInvoiceEdit()">Save Invoice Changes</button>
        <button type="button" class="btn-light" onclick="cancelInvoiceEdit()">Cancel</button>
      </div>
      </div>
    </div>

    <div class="quote-box no-print" style="margin-top:16px;border-color:#2563eb;background:#eff6ff;">
      <div class="quote-section-title" style="margin-top:0;">Job photos</div>
      <span class="small">Take or upload before, during and completed photos. They are compressed and included at the end of the invoice PDF.</span>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px;">
        <div>
          <label for="invoicePhotoCategory">Category</label>
          <select id="invoicePhotoCategory">
            <option value="before">Before</option>
            <option value="during">During</option>
            <option value="after" selected>Completed</option>
            <option value="hidden_pipework">Hidden pipework</option>
            <option value="damage">Damage found</option>
            <option value="parts_replaced">Parts replaced</option>
            <option value="compliance">Compliance</option>
            <option value="customer_supplied">Customer supplied</option>
            <option value="other">Other</option>
          </select>
        </div>
        <div>
          <label for="invoicePhotoFiles">Take or choose photos</label>
          <input id="invoicePhotoFiles" type="file" accept="image/*" capture="environment" multiple>
        </div>
      </div>
      <label for="invoicePhotoCaption">Photo note</label>
      <input id="invoicePhotoCaption" placeholder="Example: New tap fitted, tested and left leak-free.">
      <div class="history-actions" style="grid-template-columns:1fr;margin-top:10px;">
        <button type="button" class="btn-blue" onclick="uploadInvoicePhotos()">Add Photos to Invoice</button>
      </div>
      <div id="invoicePhotoUploadStatus" class="small" style="margin-top:8px;"></div>
      <div id="invoicePhotoGallery" style="margin-top:10px;"></div>
    </div>

    <div class="actions no-print">
      <a id="invoiceWhatsappBtn" class="btn-link btn-secondary" href="#" target="_blank">Send Invoice to WhatsApp</a>
      <button id="invoiceEmailBtn" class="btn-blue" type="button" onclick="sendInvoiceEmail()">Email Invoice PDF</button>
      <button class="btn-light" type="button" onclick="copyInvoiceBankDetails()">Copy Bank Details</button>
      <button class="btn-light" type="button" onclick="sendCurrentOverdueReminder()">Send Overdue Reminder</button>
      <a id="invoiceOpenBtn" class="btn-link btn-light" href="#" target="_blank">Open Invoice Page</a>
      <button class="btn-light" type="button" onclick="downloadCurrentInvoicePdf()">Download Invoice PDF</button>
    </div>
  </div>

  <div class="card no-print">
    <h2>Saved Quotes</h2>
    <div id="historyList" class="small">No saved quotes yet.</div>
  </div>

</div>

<script>
let MATERIAL_LIBRARY = __MATERIAL_LIBRARY__;
const FAVOURITE_MATERIALS = __FAVOURITE_MATERIALS__;
const JOB_TEMPLATES = __JOB_TEMPLATES__;

const MATERIAL_ALIAS_RULES = __MATERIAL_ALIAS_RULES__;





async function getSupplierPreference(name) {
  try {
    const res = await fetch(`/api/supplier-preference?q=${encodeURIComponent(name || "")}`);
    if (!res.ok) throw new Error();
    return await res.json();
  } catch (e) {
    return null;
  }
}

async function applySupplierPreferenceToRow(row) {
  const name = row.querySelector(".m-name")?.value || "";
  const supplierSelect = row.querySelector(".m-supplier");
  if (!name || !supplierSelect) return;

  const pref = await getSupplierPreference(name);
  if (pref && pref.preferred_supplier && pref.source === "history") {
    supplierSelect.value = pref.preferred_supplier;
    const note = row.querySelector(".supplier-preference-note");
    if (note) {
      const counts = pref.supplier_counts || {};
      const count = counts[pref.preferred_supplier] || 0;
      note.innerHTML = `Supplier learned from history: ${escapeHtml(pref.preferred_supplier)} used ${count} time(s).`;
    }
  }
}

function updateSupplierPreferenceNotes() {
  document.querySelectorAll("#materials .material-row").forEach(row => {
    applySupplierPreferenceToRow(row);
  });
}

async function loadSupplierPreferencesPanel() {
  const box = document.getElementById("supplierPreferencesPanel");
  if (!box) return;

  try {
    const res = await fetch("/api/supplier-preferences");
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not save invoice.");
    const items = data.items || [];

    if (!items.length) {
      box.innerHTML = "No supplier history yet.";
      return;
    }

    box.innerHTML = items.slice(0, 30).map(item => {
      const counts = item.supplier_counts || {};
      const countText = Object.keys(counts).map(k => `${escapeHtml(k)}: ${counts[k]}`).join(" · ");
      const prices = item.average_prices || {};
      const priceText = Object.keys(prices).map(k => `${escapeHtml(k)} avg ${pounds(prices[k])}`).join(" · ");
      return `
        <div class="history-item" style="padding:8px;margin-top:6px;">
          <strong>${escapeHtml(item.material || "Material")}</strong><br>
          Preferred: <strong>${escapeHtml(item.preferred_supplier || "-")}</strong> · Uses: ${item.total_uses || 0}<br>
          <span class="small">${countText}</span><br>
          ${priceText ? `<span class="small">${priceText}</span>` : ""}
        </div>
      `;
    }).join("");
  } catch (e) {
    box.innerHTML = "Could not load supplier preferences.";
  }
}


const FORGOTTEN_ITEM_RULES = [
  {
    trigger: ["outside tap", "hose union bib tap", "wall plate elbow"],
    missing: ["15mm isolating valve", "double check valve 15mm", "pipe clips 15mm", "drain off cock 15mm"],
    job_keywords: ["outside tap", "garden tap", "external tap"],
    reason: "Outside taps usually need isolation, backflow protection, pipe clips and a drain off where freezing is possible."
  },
  {
    trigger: ["trv", "thermostatic radiator valve", "angled trv"],
    missing: ["angled lockshield valve", "radiator valve tail", "ptfe tape", "15mm copper olive", "central heating inhibitor"],
    job_keywords: ["trv", "radiator valve", "heating"],
    reason: "TRV jobs often need a matching lockshield, tails, olives, PTFE and inhibitor if draining/refilling."
  },
  {
    trigger: ["radiator", "radiator replacement"],
    missing: ["angled trv", "angled lockshield valve", "radiator valve tail", "central heating inhibitor", "radiator bleed valve"],
    job_keywords: ["radiator", "rad"],
    reason: "Radiator replacements commonly need valves, tails, inhibitor and bleed parts."
  },
  {
    trigger: ["filling loop", "braided filling loop"],
    missing: ["15mm isolating valve", "double check valve 15mm", "central heating inhibitor"],
    job_keywords: ["filling loop", "pressure", "low pressure", "repressurise"],
    reason: "Filling loop jobs often need isolation/check valve parts and inhibitor if system is topped up/refilled."
  },
  {
    trigger: ["basin waste", "bottle trap", "p trap"],
    missing: ["32mm waste pipe", "32mm waste pipe clips", "32mm solvent weld bend", "silicone"],
    job_keywords: ["basin", "waste", "trap"],
    reason: "Basin waste jobs often need pipe, clips, bends and sealant."
  },
  {
    trigger: ["kitchen sink waste", "sink waste"],
    missing: ["40mm waste pipe", "40mm waste pipe clips", "40mm solvent weld bend", "appliance waste spigot"],
    job_keywords: ["kitchen sink", "sink waste", "waste"],
    reason: "Kitchen sink waste jobs often need 40mm pipe, clips, bends and sometimes appliance spigots."
  },
  {
    trigger: ["tap", "kitchen tap", "basin tap"],
    missing: ["15mm isolating valve", "flexi hose 300mm", "ptfe tape"],
    job_keywords: ["tap", "kitchen tap", "basin tap"],
    reason: "Tap replacements often need isolation valves, flexis and PTFE/sundries."
  },
  {
    trigger: ["toilet", "replace toilet", "toilet replacement"],
    missing: ["straight pan connector", "toilet fixing kit", "15mm isolating valve", "15mm x 1/2 flexi hose", "doughnut washer"],
    job_keywords: ["toilet", "wc"],
    reason: "Toilet jobs often need pan connector, fixings, isolation/flexi and close-coupling seals."
  }
];

function currentMaterialsForForgottenCheck() {
  return [...document.querySelectorAll("#materials .material-row")].map(row => ({
    name: row.querySelector(".m-name")?.value || "",
    quantity: Number(row.querySelector(".m-qty")?.value || 1),
    supplier: row.querySelector(".m-supplier")?.value || "",
    url: row.querySelector(".m-url")?.value || "",
    manual_price: Number(row.querySelector(".m-manual")?.value || 0)
  })).filter(m => m.name.trim());
}

function detectForgottenItemsFrontend() {
  const job = (document.getElementById("job")?.value || "").toLowerCase();
  const materials = currentMaterialsForForgottenCheck();
  const canonicalNames = materials.map(m => canonicalMaterialName(m.name || ""));
  const hay = `${job} ${materials.map(m => m.name).join(" ")} ${canonicalNames.join(" ")}`.toLowerCase();

  const warnings = [];
  const seen = new Set();

  FORGOTTEN_ITEM_RULES.forEach(rule => {
    const triggerHit = (rule.trigger || []).some(t => hay.includes(t)) || (rule.job_keywords || []).some(k => job.includes(k));
    if (!triggerHit) return;

    const missing = [];
    (rule.missing || []).forEach(item => {
      const itemCan = canonicalMaterialName(item);
      const exists = canonicalNames.some(c => itemCan === c || itemCan.includes(c) || c.includes(itemCan));
      if (!exists && !seen.has(itemCan)) {
        seen.add(itemCan);
        missing.push(item);
      }
    });

    if (missing.length) {
      warnings.push({reason: rule.reason, missing});
    }
  });

  return warnings;
}

function addForgottenItem(name) {
  addMaterial({name, quantity: suggestMaterialQuantity(name), supplier: "City Plumbing", manual_price: 0});
  updateForgottenItemWarnings();
  showNotice(`${name} added.`);
}

function updateForgottenItemWarnings() {
  const box = document.getElementById("forgottenItemWarnings");
  if (!box) return;

  const warnings = detectForgottenItemsFrontend();

  if (!warnings.length) {
    box.style.display = "none";
    box.innerHTML = "";
    return;
  }

  box.style.display = "block";
  box.innerHTML = `
    <strong>Possible forgotten materials</strong><br>
    <span class="small">These are not compulsory, but check them before sending the quote.</span>
    ${warnings.map(w => `
      <div class="history-item" style="margin-top:8px;padding:8px;">
        <strong>${escapeHtml(w.reason || "Check missing items")}</strong><br>
        ${(w.missing || []).map(item => `
          <div style="display:grid;grid-template-columns:1fr auto;gap:8px;align-items:center;margin-top:6px;">
            <span>• ${escapeHtml(item)}</span>
            <button type="button" class="btn-light" onclick='addForgottenItem(${JSON.stringify(item)})'>Add</button>
          </div>
        `).join("")}
      </div>
    `).join("")}
  `;
}


const SMART_QUANTITY_RULES = [
  {match: ["pipe clips 15mm", "15mm pipe clips"], default_quantity: 6, job_keywords: ["outside tap", "fridge", "pipe run"]},
  {match: ["32mm waste pipe clips", "waste pipe clips 32"], default_quantity: 4, job_keywords: ["basin", "waste"]},
  {match: ["40mm waste pipe clips", "waste pipe clips 40"], default_quantity: 4, job_keywords: ["sink", "shower", "waste"]},
  {match: ["15mm copper pipe"], default_quantity: 1, job_keywords: ["small", "tap", "fridge", "outside tap"]},
  {match: ["15mm endfeed elbow", "endfeed elbow"], default_quantity: 4, job_keywords: ["outside tap", "pipe run", "leak"]},
  {match: ["15mm endfeed tee", "endfeed tee"], default_quantity: 1, job_keywords: ["outside tap", "branch"]},
  {match: ["15mm compression coupler", "compression coupler"], default_quantity: 2, job_keywords: ["repair", "leak", "extension"]},
  {match: ["15mm isolating valve", "isolating valve"], default_quantity: 1, job_keywords: ["fridge", "appliance"]},
  {match: ["15mm isolating valve", "isolating valve"], default_quantity: 2, job_keywords: ["tap", "basin tap", "kitchen tap"]},
  {match: ["flexi hose 300mm", "flexi hose 500mm", "flexible tap connector"], default_quantity: 2, job_keywords: ["tap", "basin", "kitchen"]},
  {match: ["15mm copper olive", "olive"], default_quantity: 2, job_keywords: ["trv", "valve", "compression"]},
  {match: ["radiator valve tail", "radiator tail"], default_quantity: 2, job_keywords: ["radiator", "trv"]},
  {match: ["angled trv", "thermostatic radiator valve"], default_quantity: 1, job_keywords: ["trv", "radiator"]},
  {match: ["angled lockshield valve", "lockshield"], default_quantity: 1, job_keywords: ["trv", "radiator"]},
  {match: ["ptfe tape"], default_quantity: 1, job_keywords: ["any"]},
  {match: ["silicone"], default_quantity: 1, job_keywords: ["bath", "basin", "toilet", "sink"]}
];

function learnedQuantityFromCurrentJob(name) {
  if (!LAST_LEARNING_DATA || !LAST_LEARNING_DATA.common_materials) return null;

  const canonical = canonicalMaterialName(name || "");
  const match = (LAST_LEARNING_DATA.common_materials || []).find(m => canonicalMaterialName(m.name || "") === canonical);

  if (!match) return null;

  const avgQty = Number(match.average_quantity || 0);
  const usedCount = Number(match.used_count || 0);

  if (avgQty > 0 && usedCount >= 1) {
    return {
      quantity: Math.max(1, Math.round(avgQty)),
      average_quantity: avgQty,
      used_count: usedCount,
      used_percent: Number(match.used_percent || 0),
      source: "learned"
    };
  }

  return null;
}

function ruleQuantitySuggestion(name, jobText = "") {
  const canonical = canonicalMaterialName(name || "");
  const hay = `${canonical} ${name || ""}`.toLowerCase();
  const job = (jobText || document.getElementById("job")?.value || "").toLowerCase();

  let best = null;
  let bestScore = -1;

  SMART_QUANTITY_RULES.forEach(rule => {
    if (!(rule.match || []).some(term => hay.includes(term))) return;

    let score = 1;
    const kws = rule.job_keywords || [];
    if (kws.includes("any")) score += 1;
    kws.forEach(kw => {
      if (kw && kw !== "any" && job.includes(kw)) score += 3;
    });

    if (score > bestScore) {
      best = rule;
      bestScore = score;
    }
  });

  return best ? Number(best.default_quantity || 1) : 1;
}

function suggestMaterialQuantityInfo(name, jobText = "") {
  const learned = learnedQuantityFromCurrentJob(name);
  if (learned) return learned;

  return {
    quantity: ruleQuantitySuggestion(name, jobText),
    average_quantity: null,
    used_count: 0,
    used_percent: 0,
    source: "rule"
  };
}

function suggestMaterialQuantity(name, jobText = "") {
  return Number(suggestMaterialQuantityInfo(name, jobText).quantity || 1);
}

function applySmartQuantityToMaterial(material) {
  const out = {...material};
  const hasExplicitQty = out.quantity !== undefined && out.quantity !== null && String(out.quantity).trim() !== "";
  if (!hasExplicitQty || Number(out.quantity) === 1) {
    const info = suggestMaterialQuantityInfo(out.name || "");
    const suggested = Number(info.quantity || 1);
    if (suggested && suggested > 1) out.quantity = suggested;
    out.quantity_source = info.source;
    out.learned_average_quantity = info.average_quantity;
    out.learned_used_count = info.used_count;
  }
  return out;
}


const MATERIAL_CHARGING_RULES = {
  "ptfe tape": {
    material_type: "consumable",
    charge_method: "partial",
    default_charge: 0.50,
    customer_label: "Small consumable allowance",
    note: "Partial use only. Do not charge whole roll unless specifically supplied."
  },
  "silicone": {
    material_type: "consumable",
    charge_method: "partial",
    default_charge: 3.00,
    customer_label: "Sealant allowance",
    note: "Partial tube use unless full tube supplied."
  },
  "solvent weld cement": {
    material_type: "consumable",
    charge_method: "partial",
    default_charge: 2.00,
    customer_label: "Solvent cement allowance",
    note: "Partial use only."
  },
  "central heating inhibitor": {
    material_type: "chargeable",
    charge_method: "full",
    default_charge: null,
    customer_label: "Central heating inhibitor",
    note: "Normally charged as full bottle when used."
  },
  "15mm copper olive": {
    material_type: "small_part",
    charge_method: "small_part",
    default_charge: 0.30,
    customer_label: "Compression olives",
    note: "Small fittings normally charged individually or absorbed into sundries."
  }
};

function getMaterialChargingRule(name) {
  const canonical = canonicalMaterialName(name);
  return MATERIAL_CHARGING_RULES[canonical] || {
    material_type: "chargeable",
    charge_method: "full",
    default_charge: null,
    customer_label: canonical,
    note: "Full chargeable material."
  };
}

function applyChargingRuleToMaterial(material) {
  const rule = getMaterialChargingRule(material.name || "");
  const out = {...material};
  out.material_type = rule.material_type;
  out.charge_method = rule.charge_method;
  out.customer_label = rule.customer_label;
  out.charge_note = rule.note;

  // Keep the full product/manual price for memory.
  // Use a separate quote charge for partial consumables.
  if ((rule.charge_method === "partial" || rule.charge_method === "small_part") && Number(rule.default_charge || 0) > 0) {
    out.quote_charge_override = Number(rule.default_charge);
  }

  return out;
}


function cleanMaterialNameForMatching(name) {
  return (name || "")
    .toLowerCase()
    .replace(/https?:\/\/\S+/g, " ")
    .replace(/(\d+)\s*mm\b/g, "$1mm")
    .replace(/\bend[\s-]?feed\b/g, "endfeed")
    .replace(/\b90\s*(?:degree|degrees|deg)\b/g, " ")
    .replace(/\b(plumbright|plumbfix|regin|kudox|stelrad|city plumbing|screwfix|toolstation|selco|topps tiles)\b/g, " ")
    .replace(/\b(white|chrome plated|chrome|copper|each|single|individual|pack of|pack)\b/g, " ")
    .replace(/\b(fitting|fittings|connector|connectors)\b/g, " ")
    .replace(/[^a-z0-9/.\- ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function materialMatchTokens(name) {
  const cleaned = cleanMaterialNameForMatching(name);
  const stop = new Set(["the", "and", "for", "with", "type", "degree", "degrees"]);
  return cleaned
    .split(/\s+/)
    .filter(Boolean)
    .filter(token => !stop.has(token));
}

function materialDimensions(name) {
  const cleaned = String(name || "").toLowerCase().replace(/\s+/g, " ");
  const sizes = [...cleaned.matchAll(/\b(\d{1,4})\s*mm\b/g)].map(match => Number(match[1]));
  return [...new Set(sizes)].sort((a, b) => a - b);
}

function materialFamily(name) {
  const cleaned = cleanMaterialNameForMatching(name);
  if (/\breducing tee\b|\btee\b/.test(cleaned)) return "tee";
  if (/\belbow\b|\bbend\b/.test(cleaned)) return "elbow";
  if (/\bcoupler\b|\bcoupling\b/.test(cleaned)) return "coupler";
  if (/\bcopper pipe\b|\bpipe 3m\b/.test(cleaned)) return "pipe";
  if (/\bradiator valve set\b/.test(cleaned)) return "radiator valve set";
  if (/\btrv\b|\bthermostatic radiator valve\b/.test(cleaned)) return "trv";
  if (/\blockshield\b/.test(cleaned)) return "lockshield";
  if (/\binhibitor\b/.test(cleaned)) return "inhibitor";
  if (/\bptfe\b/.test(cleaned)) return "ptfe";
  if (/\bradiator\b/.test(cleaned)) return "radiator";
  return "";
}

function savedMaterialPrice(item) {
  return Number(
    item?.last_live_price ||
    item?.last_price ||
    item?.last_manual_price ||
    item?.default_price ||
    0
  );
}

function scoreSavedMaterialMatch(requestedName, candidate) {
  const requestedTokens = materialMatchTokens(requestedName);
  const candidateTokens = materialMatchTokens(candidate?.name || "");
  if (!requestedTokens.length || !candidateTokens.length) return 0;

  const requestedFamily = materialFamily(requestedName);
  const candidateFamily = materialFamily(candidate?.name || "");
  if (requestedFamily && candidateFamily && requestedFamily !== candidateFamily) return 0;

  const requestedSizes = materialDimensions(requestedName);
  const candidateSizes = materialDimensions(candidate?.name || "");
  if (requestedSizes.length && candidateSizes.length) {
    const sameSizes = requestedSizes.length === candidateSizes.length &&
      requestedSizes.every((size, index) => size === candidateSizes[index]);
    if (!sameSizes) return 0;
  }

  const candidateSet = new Set(candidateTokens);
  const shared = requestedTokens.filter(token => candidateSet.has(token));
  let score = (shared.length / Math.max(requestedTokens.length, candidateTokens.length)) * 70;

  if (requestedFamily && requestedFamily === candidateFamily) score += 20;
  if (requestedSizes.length && candidateSizes.length) score += 10;
  if (candidate?.url) score += 4;
  if (savedMaterialPrice(candidate) > 0) score += 4;
  if (String(candidate?.last_status || "").toLowerCase().includes("live")) score += 2;

  return Math.min(100, Math.round(score));
}

function findBestSavedMaterialMatch(name) {
  const candidates = [
    ...(Array.isArray(SAVED_MATERIAL_DB) ? SAVED_MATERIAL_DB : []),
    ...(Array.isArray(MATERIAL_LIBRARY) ? MATERIAL_LIBRARY : [])
  ];

  const seen = new Set();
  let best = null;

  for (const candidate of candidates) {
    const key = `${candidate?.name || ""}|${candidate?.supplier || ""}|${candidate?.url || ""}`;
    if (!candidate?.name || seen.has(key)) continue;
    seen.add(key);

    const score = scoreSavedMaterialMatch(name, candidate);
    if (!best || score > best.score) best = {candidate, score};
  }

  return best && best.score >= 72 ? best : null;
}

function enrichMaterialFromSavedDatabase(material) {
  if (!material || !material.name) return material;
  const currentPrice = Number(material.manual_price || material.price || 0);
  const currentUrl = String(material.url || "").trim();

  // Preserve an already confirmed live product.
  if (currentUrl && currentPrice > 0) return material;

  const match = findBestSavedMaterialMatch(material.name);
  if (!match) {
    material.database_match_status = "not_found";
    material.database_match_score = 0;
    return material;
  }

  const saved = match.candidate;
  const savedPrice = savedMaterialPrice(saved);

  material.original_requested_name = material.original_requested_name || material.name;
  material.name = saved.name || material.name;
  material.supplier = saved.supplier || material.supplier || "City Plumbing";
  material.url = saved.url || material.url || "";
  material.manual_price = savedPrice || currentPrice || 0;
  material.price = savedPrice || Number(material.price || 0);
  material.data_source = saved.url ? "saved_database_match" : (material.data_source || "saved_database_match");
  material.source = material.data_source;
  material.database_match_status = "matched";
  material.database_match_score = match.score;
  material.material_confidence = Math.max(Number(material.material_confidence || 0), match.score);
  material.price_status = saved.last_status || material.price_status || (savedPrice ? "cached" : "unpriced");
  material.saved_material_id = saved.id || material.saved_material_id || null;

  return material;
}

function enrichDraftMaterialsFromSavedDatabase(draft) {
  if (!draft || !Array.isArray(draft.materials)) return draft;
  draft.materials = draft.materials.map(item => enrichMaterialFromSavedDatabase(item));
  return draft;
}

function materialAliasInfo(name) {
  const cleaned = cleanMaterialNameForMatching(name);
  for (const rule of MATERIAL_ALIAS_RULES) {
    if ((rule.keywords || []).some(k => cleaned.includes(k))) {
      return { canonical: rule.canonical, category: rule.category || "other", matched: true };
    }
  }
  return { canonical: cleaned || (name || "").trim().toLowerCase(), category: "other", matched: false };
}

function canonicalMaterialName(name) {
  return materialAliasInfo(name).canonical;
}


let SAVED_QUOTES = [];
let SAVED_INVOICES = [];
let SAVED_CUSTOMERS = [];
let SAVED_LEADS = [];
let SAVED_MATERIAL_DB = [];
let CURRENT_QUOTE_ID = null;
let CURRENT_QUOTE_DATA = null;
let CURRENT_INVOICE_ID = null;
let CURRENT_EDITING_INVOICE_ID = null;

function showNotice(message, type = "success") {
  const box = document.getElementById("appNotice");
  if (!box) return;
  box.className = "notice " + (type === "error" ? "error" : "success");
  box.innerText = message || "";
  box.style.display = message ? "block" : "none";
  if (message) {
    window.clearTimeout(showNotice._timer);
    showNotice._timer = window.setTimeout(() => {
      box.style.display = "none";
      box.innerText = "";
    }, 2600);
  }
}

function clearNotice() {
  const box = document.getElementById("appNotice");
  if (!box) return;
  box.style.display = "none";
  box.innerText = "";
}

function pounds(value) {
  return String.fromCharCode(163) + Number(value || 0).toFixed(2);
}

function escapeHtml(text) {
  return (text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function showNotice(message) {
  const box = document.getElementById("notice");
  if (!box) return;
  box.innerText = message;
  box.style.display = "block";
  if (typeof updateQuantityLearningNotes === 'function') if (typeof updateQuantityLearningNotes === 'function') updateQuantityLearningNotes();
  setTimeout(() => { box.style.display = "none"; }, 4000);
}

function showTab(id) {
  document.querySelectorAll(".tab-panel").forEach(x => x.classList.remove("active"));
  const panel = document.getElementById(id);
  if (panel) panel.classList.add("active");

  if (id === "dashboardTab") loadDashboard();
  if (id === "quotesTab") loadHistory();
  if (id === "invoicesTab") loadInvoices();
  if (id === "customersTab") loadCustomers();
  if (id === "leadsTab") loadLeads();
  if (id === "safetyTab") loadSafety();
  if (id === "materialsDbTab") loadMaterialDb();
  if (id === "intelligenceTab") loadIntelligence();
  if (id === "quotesTab") renderMasterMaterialSuggestions();
}

function toggleBathroomFields() {
  const quoteType = document.getElementById("quote_type").value;
  const bathroomFields = document.getElementById("bathroomFields");
  if (quoteType === "bathroom") bathroomFields.classList.remove("hidden");
  else bathroomFields.classList.add("hidden");
}

function renderTemplates() {
  const box = document.getElementById("templateButtons");
  box.innerHTML = JOB_TEMPLATES.map((t, i) => `
    <button type="button" class="btn-template" onclick="applyTemplate(${i})">${escapeHtml(t.name)}</button>
  `).join("");
}

function renderFavourites() {
  const box = document.getElementById("favouriteButtons");
  box.innerHTML = FAVOURITE_MATERIALS.map((t, i) => `
    <button type="button" class="btn-template" onclick="addFavouriteMaterial(${i})">${escapeHtml(t.name)}</button>
  `).join("");
}

function resolveTemplateMaterial(templateItem) {
  const wanted = (templateItem.name || "").toLowerCase();
  let item = MATERIAL_LIBRARY.find(x => (x.name || "").toLowerCase() === wanted)
    || MATERIAL_LIBRARY.find(x => (x.name || "").toLowerCase().includes(wanted));

  if (!item) {
    item = { name: templateItem.name || "Material", supplier: "", default_price: 0, url: "" };
  }

  return {
    name: item.name || templateItem.name || "Material",
    supplier: item.supplier || templateItem.supplier || "",
    url: item.url || templateItem.url || "",
    default_price: item.default_price || templateItem.default_price || 0,
    manual_price: item.default_price || templateItem.default_price || 0,
    quantity: templateItem.quantity || 1,
  };
}

function applyTemplate(index) {
  const t = JOB_TEMPLATES[index];
  document.getElementById("quote_type").value = t.quote_type;
  document.getElementById("job").value = t.job;
  document.getElementById("labour").value = t.labour;

  if (Array.isArray(t.materials) && t.materials.length) {
    if (confirm("Load the usual material kit for " + t.name + "?")) {
      clearMaterials();
      t.materials.forEach(m => addMaterial(resolveTemplateMaterial(m)));
      showNotice("Template material kit loaded.");
    }
  }

  toggleBathroomFields();
  updateLabourSuggestion();
}

function addFavouriteMaterial(index) {
  addMaterial(FAVOURITE_MATERIALS[index]);
}



let LABOUR_INTELLIGENCE_TIMER = null;

function scheduleLabourIntelligence() {
  window.clearTimeout(LABOUR_INTELLIGENCE_TIMER);
  LABOUR_INTELLIGENCE_TIMER = window.setTimeout(loadLabourIntelligence, 500);
}

async function loadLabourIntelligence() {
  const box = document.getElementById("labourIntelligence");
  if (!box) return;

  const job = document.getElementById("job")?.value || "";
  const quoteType = document.getElementById("quote_type")?.value || "";
  const labour = Number(document.getElementById("labour")?.value || 0);

  if (!job.trim() || job.trim().length < 3) {
    box.style.display = "none";
    box.innerHTML = "";
    return;
  }

  try {
    const res = await fetch(`/api/labour-intelligence?job=${encodeURIComponent(job)}&quote_type=${encodeURIComponent(quoteType)}&labour=${encodeURIComponent(labour)}`);
    if (!res.ok) throw new Error();
    const data = await res.json();
    renderLabourIntelligence(data);
  } catch (e) {
    box.style.display = "none";
    box.innerHTML = "";
  }
}

function renderLabourIntelligence(data) {
  const box = document.getElementById("labourIntelligence");
  if (!box) return;

  if (!data || !Number(data.average_labour || 0)) {
    box.style.display = "none";
    box.innerHTML = "";
    return;
  }

  const status = data.status || "unknown";
  let border = "#d1d5db";
  let bg = "#f9fafb";
  let title = "Labour intelligence";

  if (status === "too_low") {
    border = "#dc2626";
    bg = "#fef2f2";
    title = "Labour warning";
  } else if (status === "ok") {
    border = "#16a34a";
    bg = "#f0fdf4";
  } else if (status === "high") {
    border = "#f59e0b";
    bg = "#fffbeb";
  }

  const similarHtml = (data.similar_quotes || []).length ? `
    <details style="margin-top:8px;">
      <summary>Similar labour history</summary>
      ${(data.similar_quotes || []).map(q => `
        <div class="history-item" style="padding:8px;margin-top:6px;">
          Quote #${q.id} · Labour ${pounds(q.labour || 0)} · Total ${pounds(q.total_price || 0)}<br>
          <span class="small">${escapeHtml((q.job || "").slice(0, 130))}</span>
        </div>
      `).join("")}
    </details>
  ` : "";

  box.style.display = "block";
  box.style.borderColor = border;
  box.style.background = bg;
  box.innerHTML = `
    <strong>${title}</strong><br>
    Similar jobs found: <strong>${data.similar_count || 0}</strong><br>
    Your average labour: <strong>${pounds(data.average_labour || 0)}</strong><br>
    Usual range: <strong>${pounds(data.low_range || 0)} - ${pounds(data.high_range || 0)}</strong><br>
    Current labour: <strong>${pounds(data.current_labour || 0)}</strong><br>
    ${data.warning ? `<div style="margin-top:6px;"><strong>${escapeHtml(data.warning)}</strong></div>` : ""}
    <div class="history-actions" style="grid-template-columns:1fr;margin-top:8px;">
      <button type="button" class="btn-light" onclick="applyAverageLabour(${Number(data.average_labour || 0)})">Use average labour</button>
    </div>
    ${similarHtml}
  `;
}

function applyAverageLabour(value) {
  if (!value || Number(value) <= 0) return;
  document.getElementById("labour").value = Number(value).toFixed(2);
  scheduleLabourIntelligence();
  showNotice("Average labour applied.");
}


let QUOTE_LEARNING_TIMER = null;
let LAST_LEARNING_DATA = null;

function currentMaterialNames() {
  return [...document.querySelectorAll("#materials .m-name")]
    .map(x => (x.value || "").trim().toLowerCase())
    .filter(Boolean);
}

function scheduleQuoteLearning() {
  window.clearTimeout(QUOTE_LEARNING_TIMER);
  QUOTE_LEARNING_TIMER = window.setTimeout(loadQuoteLearning, 450);
}


function renderMasterMaterialSuggestions() {
  const box = document.getElementById("master-material-library");
  if (!box) return;

  const input = document.getElementById("masterMaterialSearch");
  const q = input ? input.value.trim().toLowerCase() : "";

  const rules = MATERIAL_ALIAS_RULES.filter(rule => {
    if (!q) return true;
    const hay = `${rule.canonical || ""} ${rule.category || ""} ${(rule.keywords || []).join(" ")}`.toLowerCase();
    return hay.includes(q);
  }).slice(0, 24);

  box.innerHTML = rules.length ? rules.map((rule, idx) => `
    <div class="card">
      <strong>${escapeHtml(rule.canonical)}</strong><br>
      <small>${escapeHtml(rule.category || "other")}</small><br>
      <small>Aliases: ${escapeHtml((rule.keywords || []).slice(0, 3).join(", "))}</small>
      <div style="margin-top:8px;">
        <button type="button" class="btn-light" onclick="addMasterMaterialByIndex(${idx})">Add to quote</button>
      </div>
    </div>
  `).join("") : "No master materials found.";

  window.CURRENT_MASTER_MATERIAL_RESULTS = rules;
}

function addMasterMaterialByIndex(index) {
  const list = window.CURRENT_MASTER_MATERIAL_RESULTS || MATERIAL_ALIAS_RULES;
  const item = list[index];
  if (!item) return;
  addMaterial({
    name: item.canonical,
    supplier: "City Plumbing",
    manual_price: 0
  });
  showNotice("Master material added.");
}


function renderQuoteLearning(data) {
  LAST_LEARNING_DATA = data;
  const box = document.getElementById("learningInsights");
  if (!box) return;

  if (!data || !data.query || data.query.trim().length < 3) {
    box.style.display = "none";
    box.innerHTML = "";
    return;
  }

  const averages = data.averages || {};
  const common = data.common_materials || [];
  const similar = data.similar_quotes || [];
  const currentNames = currentMaterialNames();

  const missing = common.filter(m => {
    const name = (m.name || "").toLowerCase();
    const canonical = canonicalMaterialName(name);
    const already = currentNames.some(n => {
      const existingCanonical = canonicalMaterialName(n);
      return existingCanonical === canonical || n.includes(name) || name.includes(n);
    });
    return !already && Number(m.used_percent || 0) >= 40;
  }).slice(0, 6);

  const materialHtml = common.slice(0, 8).map(m => `
    <div class="history-item" style="padding:8px;margin-top:6px;">
      <strong>${escapeHtml(m.name)}</strong>${m.alias_matched ? ' <span class="badge green">grouped</span>' : ""}<br>
      <span>Used in ${m.used_percent}% of similar quotes · avg qty ${m.average_quantity} · avg unit ${pounds(m.average_unit_price || 0)} · ${escapeHtml(m.category || "other")}</span>
      <div class="history-actions" style="grid-template-columns:1fr;margin-top:6px;">
        <button type="button" class="btn-light" onclick='addLearningMaterial(${JSON.stringify(m)})'>Add to quote</button>
      </div>
    </div>
  `).join("");

  const missingHtml = missing.length ? `
    <div style="margin-top:10px;padding:10px;border:1px solid #f59e0b;border-radius:12px;background:#fffbeb;">
      <strong>Possible missing materials</strong><br>
      ${missing.map(m => `• ${escapeHtml(m.name)} — used in ${m.used_percent}% of similar quotes`).join("<br>")}
    </div>
  ` : "";

  const bundle = data.suggested_bundle || {};
  const essential = bundle.essential || [];
  const commonBundle = bundle.common || [];
  const optional = bundle.optional || [];
  const bundleItems = [...essential, ...commonBundle];

  const bundleHtml = bundleItems.length ? `
    <div style="margin-top:10px;padding:10px;border:1px solid #16a34a;border-radius:12px;background:#f0fdf4;">
      <strong>Suggested material bundle</strong><br>
      <span class="small">Built from previous similar quotes. Essential = used in 80%+ of similar quotes. Common = used in 40%+.</span>

      <div style="margin-top:8px;">
        ${essential.length ? `<strong>Essential</strong><br>${essential.map(m => `• ${escapeHtml(m.name)} × ${m.average_quantity} (${m.used_percent}%)`).join("<br>")}` : ""}
        ${commonBundle.length ? `<br><strong>Common</strong><br>${commonBundle.map(m => `• ${escapeHtml(m.name)} × ${m.average_quantity} (${m.used_percent}%)`).join("<br>")}` : ""}
      </div>

      <div class="history-actions" style="grid-template-columns:1fr 1fr;gap:8px;margin-top:10px;">
        <button type="button" class="btn-green" onclick="addLearningBundle('core')">Add Full Bundle</button>
        <button type="button" class="btn-light" onclick="addLearningBundle('essential')">Add Essential Only</button>
      </div>

      ${optional.length ? `
        <details style="margin-top:8px;">
          <summary>Optional extras</summary>
          ${optional.map(m => `
            <div class="history-item" style="padding:8px;margin-top:6px;">
              <strong>${escapeHtml(m.name)}</strong>${m.alias_matched ? ' <span class="badge green">grouped</span>' : ""}<br>
              <span class="small">Used in ${m.used_percent}% · avg qty ${m.average_quantity}</span>
              <div class="history-actions" style="grid-template-columns:1fr;margin-top:6px;">
                <button type="button" class="btn-light" onclick='addLearningMaterial(${JSON.stringify(m)})'>Add optional item</button>
              </div>
            </div>
          `).join("")}
        </details>
      ` : ""}
    </div>
  ` : "";


  const similarHtml = similar.length ? `
    <details style="margin-top:10px;">
      <summary>Similar quotes found (${data.similar_count})</summary>
      ${similar.map(q => `
        <div class="history-item" style="padding:8px;margin-top:6px;">
          <strong>Quote #${q.id}</strong> — ${escapeHtml(q.created_at || "")}<br>
          ${escapeHtml((q.job || "").slice(0, 160))}<br>
          Labour ${pounds(q.labour)} · Materials ${pounds(q.materials)} · Total ${pounds(q.total_price)}
        </div>
      `).join("")}
    </details>
  ` : "";

  box.innerHTML = `
    <strong>Learning from previous quotes</strong><br>
    ${escapeHtml(data.message || "")}<br>
    <div style="margin-top:8px;">
      Avg labour: <strong>${pounds(averages.labour || 0)}</strong> ·
      Avg materials: <strong>${pounds(averages.materials || 0)}</strong> ·
      Avg total: <strong>${pounds(averages.total_price || 0)}</strong>
    </div>
    ${missingHtml}
    ${bundleHtml}
    <details style="margin-top:10px;" ${common.length ? "open" : ""}>
      <summary>Common materials</summary>
      ${materialHtml || "No common materials yet."}
    </details>
    ${similarHtml}
  `;
  box.style.display = "block";
}

async function loadQuoteLearning() {
  const job = document.getElementById("job")?.value || "";
  const quoteType = document.getElementById("quote_type")?.value || "";
  const box = document.getElementById("learningInsights");

  if (!job.trim() || job.trim().length < 3) {
    if (box) {
      box.style.display = "none";
      box.innerHTML = "";
    }
    return;
  }

  try {
    const res = await fetch(`/api/quote-learning?q=${encodeURIComponent(job)}&quote_type=${encodeURIComponent(quoteType)}`);
    if (!res.ok) throw new Error();
    const data = await res.json();
    renderQuoteLearning(data);
    scheduleLabourIntelligence();
  } catch (e) {
    if (box) {
      box.style.display = "block";
      box.innerHTML = "Could not load quote learning.";
    }
  }
}


function materialAlreadyInQuote(materialName) {
  const name = (materialName || "").trim().toLowerCase();
  if (!name) return false;
  const canonical = canonicalMaterialName(name);
  return currentMaterialNames().some(existing => {
    const existingCanonical = canonicalMaterialName(existing);
    return existingCanonical === canonical || existing.includes(name) || name.includes(existing);
  });
}

function addLearningBundle(mode = "core") {
  if (!LAST_LEARNING_DATA || !LAST_LEARNING_DATA.suggested_bundle) {
    alert("No suggested bundle available yet.");
    return;
  }

  const bundle = LAST_LEARNING_DATA.suggested_bundle;
  let items = [];

  if (mode === "essential") {
    items = bundle.essential || [];
  } else {
    items = [...(bundle.essential || []), ...(bundle.common || [])];
  }

  const newItems = items.filter(m => !materialAlreadyInQuote(m.name));

  if (!newItems.length) {
    showNotice("Bundle materials are already in this quote.");
    return;
  }

  newItems.forEach(m => addLearningMaterial(m, false));
  scheduleQuoteLearning();
  showNotice(`${newItems.length} bundle material(s) added.`);
}


function addLearningMaterial(m, refresh = true) {
  addMaterial({
    name: m.name || "",
    quantity: m.average_quantity || 1,
    supplier: m.supplier || "City Plumbing",
    url: m.url || "",
    manual_price: m.average_unit_price || 0,
    default_price: m.average_unit_price || 0,
  });
  if (refresh) scheduleQuoteLearning();
  showNotice("Material added from quote history.");
}

function applyLearningLabour() {
  if (!LAST_LEARNING_DATA || !LAST_LEARNING_DATA.averages) return;
  const labour = Number(LAST_LEARNING_DATA.averages.labour || 0);
  if (labour > 0) {
    document.getElementById("labour").value = labour.toFixed(2);
    showNotice("Average labour applied.");
  }
}


function updateLabourSuggestion() {
  const quoteType = document.getElementById("quote_type").value;
  const text = document.getElementById("job").value.toLowerCase();
  const box = document.getElementById("labourSuggestion");

  let message = "Small jobs: use your judgement and minimum charge where needed.";
  if (quoteType === "bathroom") message = "Typical bathroom labour is often higher. Adjust to suit your job.";
  if (quoteType === "heating") message = "Heating jobs often vary by size and access. Adjust labour as needed.";

  if (quoteType === "small" && text.includes("tap")) message = "Suggested labour: around £120. Typical range: £100 - £140.";
  if (quoteType === "small" && (text.includes("toilet") || text.includes("wc"))) message = "Suggested labour: around £180. Typical range: £160 - £220.";
  if (quoteType === "small" && (text.includes("waste") || text.includes("trap"))) message = "Suggested labour: around £120. Typical range: £90 - £140.";
  if (quoteType === "small" && text.includes("outside tap")) message = "Suggested labour: around £150. Typical range: £140 - £180.";
  if (quoteType === "bathroom" && text.includes("refurb")) message = "Suggested labour: around £2,200. Typical range: £2,000 - £2,800.";
  if (quoteType === "bathroom" && text.includes("install")) message = "Suggested labour: around £1,800. Typical range: £1,600 - £2,200.";
  if (quoteType === "heating" && text.includes("radiator")) message = "Suggested labour: around £180. Typical range: £160 - £220.";
  if (quoteType === "heating" && text.includes("repair")) message = "Suggested labour: around £150. Typical range: £120 - £220.";

  box.innerText = message;
}



function updateMaterialLiveBadge(row) {
  if (!row) return;
  const status = row.querySelector(".material-live-status");
  if (!status) return;
  const url = String(row.querySelector(".m-url")?.value || "").trim();
  const checkedAt = row.dataset.checkedAt || "";
  const sku = row.dataset.sku || "";
  const imageUrl = row.dataset.imageUrl || "";
  if (/^https?:\/\//i.test(url)) {
    status.innerHTML = `
      <span style="display:inline-block;padding:3px 7px;border-radius:999px;background:#dcfce7;color:#166534;font-weight:700;">Live priced</span>
      ${sku ? ` · SKU ${escapeHtml(sku)}` : ""}
      ${checkedAt ? ` · checked ${escapeHtml(new Date(checkedAt).toLocaleString())}` : ""}
      ${imageUrl ? ` · <a href="${escapeHtml(imageUrl)}" target="_blank" rel="noopener">product image</a>` : ""}
    `;
  } else {
    status.innerHTML = `<span style="color:#92400e;">No product URL saved — database and live-product matching did not find a confirmed product.</span>`;
  }
}

async function refreshMaterialRowPrice(button) {
  const row = button.closest(".material-row");
  if (!row) return;
  const url = String(row.querySelector(".m-url")?.value || "").trim();
  const name = String(row.querySelector(".m-name")?.value || "").trim();
  const supplier = String(row.querySelector(".m-supplier")?.value || "").trim();
  if (!/^https?:\/\//i.test(url)) {
    showNotice("Add a confirmed product URL before refreshing the price.");
    return;
  }

  const original = button.textContent;
  button.disabled = true;
  button.textContent = "Checking…";
  try {
    const response = await fetch(
      "/api/live-product-refresh?url=" + encodeURIComponent(url) +
      "&name=" + encodeURIComponent(name) +
      "&supplier=" + encodeURIComponent(supplier)
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Price refresh failed.");
    if (Number(data.live_price || 0) > 0) {
      row.querySelector(".m-manual").value = Number(data.live_price).toFixed(2);
    }
    if (data.name) row.querySelector(".m-name").value = data.name;
    if (data.url) row.querySelector(".m-url").value = data.url;
    if (data.supplier) row.querySelector(".m-supplier").value = data.supplier;
    row.dataset.liveProduct = "1";
    row.dataset.sku = data.sku || row.dataset.sku || "";
    row.dataset.imageUrl = data.image_url || row.dataset.imageUrl || "";
    row.dataset.checkedAt = data.checked_at || new Date().toISOString();
    updateMaterialLiveBadge(row);
    showNotice(Number(data.live_price || 0) > 0 ? "Live price updated." : "Product page confirmed, but no live price was available.");
  } catch (error) {
    showNotice(error.message || "Price refresh failed.");
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

function materialQuoteUnitPrice(material) {
  const ruled = applyChargingRuleToMaterial(material || {});
  if (ruled.quote_charge_override !== undefined && ruled.quote_charge_override !== null && Number(ruled.quote_charge_override) >= 0) {
    return Number(ruled.quote_charge_override);
  }
  return Number(ruled.live_price || ruled.manual_price || ruled.default_price || ruled.price || 0);
}

function clearMaterials() {
  const materialsBox = document.getElementById("materials");
  materialsBox.innerHTML = `
    <div id="emptyMaterialsMessage" class="quote-box small" style="background:#f8fafc;">
      No materials added yet. Build the quote with AI or press <strong>+ Add Material</strong>.
    </div>
  `;
  updateForgottenItemWarnings();
}

function changeMaterialQty(button, delta) {
  const row = button.closest(".material-row");
  const input = row?.querySelector(".m-qty");
  if (!input) return;
  const current = Number(input.value || 0);
  const smallStep = current > 0 && current < 1;
  const step = smallStep ? 0.1 : 1;
  input.value = Math.max(0, Math.round((current + delta * step) * 100) / 100);
  input.dispatchEvent(new Event("input", {bubbles:true}));
}

function addMaterial(prefill = null) {
  const emptyMessage = document.getElementById("emptyMaterialsMessage");
  if (emptyMessage) emptyMessage.remove();

  if (prefill) prefill = applySmartQuantityToMaterial(prefill);

  if (prefill) prefill = applyChargingRuleToMaterial(prefill);

  // Consumable/small-part duplicate guard
  if (prefill && prefill.name) {
    const incomingRule = getMaterialChargingRule(prefill.name || "");
    const incomingCanonical = canonicalMaterialName(prefill.name || "");
    if (incomingRule.charge_method === "partial" || incomingRule.charge_method === "small_part") {
      const exists = [...document.querySelectorAll("#materials .m-name")].some(input => canonicalMaterialName(input.value || "") === incomingCanonical);
      if (exists) {
        showNotice(`${incomingCanonical} is already in this quote.`);
        return;
      }
    }
  }
  const div = document.createElement("div");
  div.className = "material-row";
  div.dataset.liveProduct = prefill && prefill.source === "live_merchant_search" ? "1" : "";
  div.dataset.sku = prefill && prefill.sku ? String(prefill.sku) : "";
  div.dataset.imageUrl = prefill && prefill.image_url ? String(prefill.image_url) : "";
  div.dataset.checkedAt = prefill && prefill.checked_at ? String(prefill.checked_at) : "";

  const qty = prefill && prefill.quantity ? prefill.quantity : 1;
  const manualPrice = prefill && prefill.manual_price != null
    ? prefill.manual_price
    : (prefill && prefill.default_price != null ? prefill.default_price : "");

  div.innerHTML = `
    <label>Item name</label>
    <input class="m-name" placeholder="e.g. kitchen tap" value="${prefill ? escapeHtml(prefill.name) : ""}">

    <label>Quantity</label>
    <div style="display:grid;grid-template-columns:52px 1fr 52px;gap:8px;align-items:center;">
      <button type="button" class="btn-light" style="padding:10px 6px;" onclick="changeMaterialQty(this,-1)">−</button>
      <input class="m-qty" type="number" step="0.01" min="0" placeholder="1" value="${qty}" style="text-align:center;margin:0;">
      <button type="button" class="btn-light" style="padding:10px 6px;" onclick="changeMaterialQty(this,1)">+</button>
    </div>

    <label>Supplier</label>
    <select class="m-supplier">
      <option value="City Plumbing">City Plumbing</option>
      <option value="Screwfix">Screwfix</option>
      <option value="Toolstation">Toolstation</option>
      <option value="Topps Tiles">Topps Tiles</option>
      <option value="Selco">Selco</option>
    </select>

    <label>Product URL</label>
    <input class="m-url" placeholder="https://..." value="${prefill && prefill.url ? escapeHtml(prefill.url) : ""}">

    <label>Manual price (£)</label>
      <div class="small charging-note"></div>
      <div class="small quantity-learning-note"></div>
    <input class="m-manual" type="number" step="0.01" placeholder="0" value="${manualPrice}">

    <div class="material-live-status small" style="margin-top:8px;"></div>
    <div class="history-actions" style="grid-template-columns:1fr 1fr;gap:8px;margin-top:8px;">
      <button type="button" class="btn-light refresh-material-price" onclick="refreshMaterialRowPrice(this)">Update price</button>
      <button type="button" class="btn-red" onclick="this.closest('.material-row').remove(); refreshAfterBundleChange()">Remove</button>
    </div>
  `;
  document.getElementById("materials").appendChild(div);

  if (prefill) {
    div.querySelector(".m-supplier").value = prefill.supplier || "City Plumbing";
  }
  updateMaterialLiveBadge(div);
  updateForgottenItemWarnings();
  updateSupplierPreferenceNotes();
}



let MATERIAL_SEARCH_TIMER = null;

function renderMaterialSearchResults(results) {
  const resultsBox = document.getElementById("searchResults");

  if (!results.length) {
    resultsBox.innerHTML = `<div class="search-item">No matches found</div>`;
    resultsBox.classList.remove("hidden");
    return;
  }

  resultsBox.innerHTML = results.map((item) => {
    const source = item.source === "saved" ? "saved database" : "built-in";
    const status = item.last_status ? " · " + escapeHtml(item.last_status) : "";
    const used = item.times_used ? " · used " + item.times_used + "x" : "";
    return `
      <div class="search-item" style="touch-action:manipulation;cursor:pointer;" onpointerdown='event.preventDefault(); addMaterialFromLibrary(${JSON.stringify(item)})'>
        <strong>${escapeHtml(item.name)}</strong><br>
        <span class="small">${escapeHtml(item.supplier || "")} · ${pounds(item.default_price || 0)} · ${source}${status}${used}</span>
      </div>
    `;
  }).join("");

  resultsBox.classList.remove("hidden");
}

function localMaterialSearch(query) {
  const terms = query.split(" ").filter(Boolean);
  return MATERIAL_LIBRARY.filter(item => {
    const hay = ((item.name || "") + " " + (item.supplier || "") + " " + (item.url || "")).toLowerCase();
    return terms.every(term => hay.includes(term));
  }).slice(0, 15);
}


function toggleManualMaterialSearch() {
  const panel = document.getElementById("manualMaterialSearchPanel");
  if (!panel) return;

  const isClosed = panel.style.display === "none" || !panel.style.display;
  panel.style.display = isClosed ? "block" : "none";

  if (isClosed) {
    const input = document.getElementById("materialSearch");
    if (input) {
      setTimeout(() => input.focus(), 50);
    }
  }
}

function searchMaterials() {
  const query = document.getElementById("materialSearch").value.trim().toLowerCase();
  const resultsBox = document.getElementById("searchResults");

  if (!query) {
    resultsBox.classList.add("hidden");
    resultsBox.innerHTML = "";
    return;
  }

  renderMaterialSearchResults(localMaterialSearch(query));

  window.clearTimeout(MATERIAL_SEARCH_TIMER);
  MATERIAL_SEARCH_TIMER = window.setTimeout(async () => {
    try {
      const res = await fetch("/api/material-search?q=" + encodeURIComponent(query));
      if (!res.ok) return;
      const results = await res.json();

      // Keep new saved DB items in the browser list too, so future typing feels instant.
      const seen = new Set(MATERIAL_LIBRARY.map(x => `${(x.name||"").toLowerCase()}|${(x.supplier||"").toLowerCase()}|${x.url||""}`));
      results.forEach(item => {
        const key = `${(item.name||"").toLowerCase()}|${(item.supplier||"").toLowerCase()}|${item.url||""}`;
        if (!seen.has(key)) {
          MATERIAL_LIBRARY.push(item);
          seen.add(key);
        }
      });

      renderMaterialSearchResults(results);
    } catch (e) {
      // Keep local results if backend search fails.
    }
  }, 250);
}

function addMaterialFromLibrary(item) {
  addMaterial(item);
  document.getElementById("materialSearch").value = "";
  document.getElementById("searchResults").classList.add("hidden");
  document.getElementById("searchResults").innerHTML = "";
}



function normaliseTemplateNameForDedup(name) {
  return (name || "")
    .toLowerCase()
    .replace(/[^a-z0-9 ]+/g, " ")
    .replace(/\breplace\b/g, "")
    .replace(/\breplacement\b/g, "")
    .replace(/\binstall\b/g, "")
    .replace(/\bfit\b/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function templatePriority(t) {
  let score = 0;
  if (t.source === "trade_knowledge") score += 100;
  if (t.risk_notes && t.risk_notes.length) score += 20;
  if (t.materials && t.materials.length) score += t.materials.length;
  if (t.essential && t.essential.length) score += t.essential.length;
  if ((t.name || "").toLowerCase().includes("toilet replacement")) score += 10;
  return score;
}

function getCleanJobTemplates() {
  const map = new Map();

  JOB_TEMPLATES.forEach(t => {
    let key = normaliseTemplateNameForDedup(t.name);

    // Merge obvious naming variants.
    if (key === "toilet" || key === "toilet ") key = "toilet";
    if ((t.name || "").toLowerCase() === "replace toilet") key = "toilet";
    if ((t.name || "").toLowerCase() === "toilet replacement") key = "toilet";

    const existing = map.get(key);
    if (!existing || templatePriority(t) > templatePriority(existing)) {
      map.set(key, t);
    }
  });

  return Array.from(map.values());
}


function findBestMaterialForTemplate(name) {
  const target = (name || "").toLowerCase().trim();
  if (!target) return null;

  const targetCanonical = canonicalMaterialName(target);
  const saved = MATERIAL_LIBRARY.filter(x => x.source === "saved");

  let found = saved.find(x => canonicalMaterialName(x.name || "") === targetCanonical);
  if (found) return found;

  found = saved.find(x => (x.name || "").toLowerCase() === target);
  if (found) return found;

  found = saved.find(x => (x.name || "").toLowerCase().includes(target) || target.includes((x.name || "").toLowerCase()));
  if (found) return found;

  found = MATERIAL_LIBRARY.find(x => canonicalMaterialName(x.name || "") === targetCanonical);
  if (found) return found;

  found = MATERIAL_LIBRARY.find(x => (x.name || "").toLowerCase() === target);
  if (found) return found;

  found = MATERIAL_LIBRARY.find(x => (x.name || "").toLowerCase().includes(target) || target.includes((x.name || "").toLowerCase()));
  return found || { name: name, quantity: 1, supplier: "City Plumbing", default_price: 0 };
}

function applyJobTemplate(templateName) {
  const template = getCleanJobTemplates().find(t => t.name === templateName);
  if (!template) return;

  document.getElementById("quote_type").value = template.quote_type || "small";
  let jobText = template.job || "";
  if (template.risk_notes && template.risk_notes.length) {
    jobText += "\n\nNotes to check:\n" + template.risk_notes.map(n => "- " + n).join("\n");
  }
  document.getElementById("job").value = jobText;
  document.getElementById("labour").value = template.labour || "";
  toggleBathroomFields();
  updateLabourSuggestion();
  scheduleQuoteLearning();

  const materialsBox = document.getElementById("materials");
  materialsBox.innerHTML = "";

  (template.materials || []).forEach(templateMaterial => {
    const material = findBestMaterialForTemplate(templateMaterial.name);
    addMaterial({
      ...material,
      quantity: templateMaterial.quantity || 1,
      manual_price: material.default_price || material.last_price || material.last_live_price || material.last_manual_price || 0
    });
  });

  const search = document.getElementById("templateSearch");
  const results = document.getElementById("templateSearchResults");
  if (search) search.value = "";
  if (results) {
    results.classList.add("hidden");
    results.innerHTML = "";
  }

  showNotice("Template loaded: " + template.name);
}


function getMaterialAliasKeywordsForTemplate(t) {
  const materialNames = [];
  (t.materials || []).forEach(m => materialNames.push(m.name || ""));
  (t.essential || []).forEach(m => materialNames.push(m.name || ""));
  (t.common || []).forEach(m => materialNames.push(m.name || ""));
  (t.optional || []).forEach(m => materialNames.push(m.name || ""));

  const keywords = [];
  materialNames.forEach(name => {
    const alias = materialAliasInfo(name);
    keywords.push(name);
    keywords.push(alias.canonical || "");
    keywords.push(alias.category || "");

    MATERIAL_ALIAS_RULES.forEach(rule => {
      if ((rule.canonical || "").toLowerCase() === (alias.canonical || "").toLowerCase()) {
        keywords.push(rule.canonical || "");
        (rule.keywords || []).forEach(k => keywords.push(k));
      }
    });
  });

  return keywords.join(" ");
}

function getTemplateSearchHaystack(t) {
  return [
    t.name || "",
    t.category || "",
    t.quote_type || "",
    t.job || "",
    (t.search_terms || []).join(" "),
    (t.risk_notes || []).join(" "),
    getMaterialAliasKeywordsForTemplate(t)
  ].join(" ").toLowerCase();
}

function expandTradeSearchTerms(q) {
  const raw = (q || "").toLowerCase().trim();
  const expansions = [raw];

  const rules = [
    [["aav", "auto air vent", "automatic air vent", "air vent"], "automatic air vent aav heating leak pressure loss air vent replacement"],
    [["filling loop", "fill loop", "boiler filling loop"], "system repressurisation boiler pressure low pressure top up pressure braided filling loop"],
    [["pressure dropping", "low pressure", "boiler pressure", "pressure loss", "keeps losing pressure"], "system repressurisation filling loop heating leak prv expansion vessel"],
    [["prv", "pressure relief", "overflow pipe dripping", "discharge pipe"], "pressure relief valve prv discharge expansion vessel pressure loss"],
    [["expansion vessel", "vessel", "ev"], "expansion vessel pressure dropping low pressure prv"],
    [["trv", "thermostatic radiator valve"], "thermostatic radiator valve angled trv radiator valve replace trv"],
    [["lockshield"], "lockshield valve radiator valve balancing"],
    [["rad"], "radiator"],
    [["leaking radiator", "radiator leak", "leaking rad"], "heating leak repair trv lockshield valve radiator valve"],
    [["not heating", "cold radiator", "cold rad", "air lock"], "cold radiator diagnosis radiator not heating bleed valve stuck trv balancing"],
    [["bleed", "bleeding radiator"], "radiator bleed valve air in radiator cold radiator"],
  ];

  rules.forEach(([triggers, extra]) => {
    if (triggers.some(trigger => raw.includes(trigger))) expansions.push(extra);
  });

  return expansions.join(" ");
}


function renderTemplateSearch() {
  const input = document.getElementById("templateSearch");
  const box = document.getElementById("templateSearchResults");
  if (!input || !box) return;

  const q = input.value.trim().toLowerCase();
  if (!q) {
    box.classList.add("hidden");
    box.innerHTML = "";
    return;
  }

  const expandedQuery = expandTradeSearchTerms(q);
  const rawTerms = q.toLowerCase().split(/\s+/).filter(Boolean);
  const expandedTerms = expandedQuery.split(/\s+/).filter(Boolean);

  function templateScore(t) {
    const hay = getTemplateSearchHaystack(t);
    const name = (t.name || "").toLowerCase();
    const searchTerms = ((t.search_terms || []).join(" ")).toLowerCase();

    let score = 0;

    rawTerms.forEach(term => {
      if (name.includes(term)) score += 30;
      if (searchTerms.includes(term)) score += 25;
      if (hay.includes(term)) score += 8;
    });

    expandedTerms.forEach(term => {
      if (name.includes(term)) score += 8;
      if (searchTerms.includes(term)) score += 6;
      if (hay.includes(term)) score += 2;
    });

    if (hay.includes(q.toLowerCase())) score += 40;
    if (t.category && String(t.category).toLowerCase().includes("heating")) score += 3;
    return score;
  }

  const matches = getCleanJobTemplates()
    .map(t => ({ t, score: templateScore(t) }))
    .filter(x => x.score > 0)
    .sort((a, b) => b.score - a.score)
    .map(x => x.t)
    .slice(0, 12);

  if (!matches.length) {
    box.innerHTML = '<div class="search-item">No template found</div>';
    box.classList.remove("hidden");
    return;
  }

  box.innerHTML = matches.map(t => `
    <div class="search-item" onclick='applyJobTemplate(${JSON.stringify(t.name)})'>
      <strong>${escapeHtml(t.name)}</strong><br>
      <span class="small">${t.source === "trade_knowledge" ? "Trade library" : "Saved template"} · Labour: ${pounds(t.labour || 0)} · ${(t.materials || []).length} materials · auto-loads kit</span><br>
      <span class="small">${escapeHtml((t.job || "").slice(0, 120))}</span>
    </div>
  `).join("");
  box.classList.remove("hidden");
}

function clearQuoteMaterials() {
  if (!confirm("Clear all materials from this quote?")) return;
  document.getElementById("materials").innerHTML = "";
  showNotice("Materials cleared.");
}

function duplicateLastMaterial() {
  const rows = [...document.querySelectorAll("#materials .material-row")];
  if (!rows.length) {
    addMaterial();
    return;
  }
  const last = rows[rows.length - 1];
  addMaterial({
    name: last.querySelector(".m-name")?.value || "",
    quantity: last.querySelector(".m-qty")?.value || 1,
    supplier: last.querySelector(".m-supplier")?.value || "City Plumbing",
    url: last.querySelector(".m-url")?.value || "",
    manual_price: last.querySelector(".m-manual")?.value || 0,
  });
  showNotice("Last material duplicated.");
}

function renderTemplateButtons() {
  const box = document.getElementById("templateButtons");
  if (!box) return;
  box.innerHTML = getCleanJobTemplates().slice(0, 16).map(t => `
    <button type="button" class="btn-light" onclick='applyJobTemplate(${JSON.stringify(t.name)})'>${escapeHtml(t.name)}</button>
  `).join("");
}


function normalisePhone(phone) {
  const digits = (phone || "").replace(/\D/g, "");
  if (!digits) return "";
  if (digits.startsWith("44")) return digits;
  if (digits.startsWith("0")) return "44" + digits.slice(1);
  return digits;
}

function setEditingStatus(text = "", show = false) {
  const box = document.getElementById("editingStatus");
  if (show) {
    box.innerText = text;
    box.classList.remove("hidden");
  } else {
    box.innerText = "";
    box.classList.add("hidden");
  }
}

function collectFormPayload() {
  const materials = [];
  document.querySelectorAll(".material-row").forEach(row => {
    const name = row.querySelector(".m-name").value;
    const baseMaterial = {
      name,
      quantity: parseFloat(row.querySelector(".m-qty").value || 1),
      supplier: row.querySelector(".m-supplier").value,
      url: row.querySelector(".m-url").value,
      manual_price: parseFloat(row.querySelector(".m-manual").value || 0)
    };
    const chargedMaterial = applyChargingRuleToMaterial(baseMaterial);
    materials.push(chargedMaterial);
  });

  return {
    quote_type: document.getElementById("quote_type").value,
    customer_name: document.getElementById("customer_name").value,
    customer_address: document.getElementById("customer_address").value,
    customer_phone: document.getElementById("customer_phone").value,
    job_description: document.getElementById("job").value,
    labour_cost: parseFloat(document.getElementById("labour").value || 0),
    include_callout_charge: document.getElementById("include_callout_charge").checked,
    callout_charge: parseFloat(document.getElementById("callout_charge").value || 0),
    include_travel_charge: document.getElementById("include_travel_charge").checked,
    travel_charge: parseFloat(document.getElementById("travel_charge").value || 0),
    include_materials_handling: document.getElementById("include_materials_handling").checked,
    materials_handling_percent: parseFloat(document.getElementById("materials_handling_percent").value || 25),
    materials: materials,
    tiling: document.getElementById("tiling").checked,
    wall_tiling_m2: parseFloat(document.getElementById("wall_tiling_m2").value || 0),
    floor_tiling_m2: parseFloat(document.getElementById("floor_tiling_m2").value || 0),
    wall_height: document.getElementById("wall_height").value,
    customer_supplies_tiles: document.getElementById("customer_supplies_tiles").checked,
    deposit_percent: parseFloat(document.getElementById("deposit_percent").value || 0)
  };
}


function buildQuoteMaterialsWhatsappText(data) {
  const lines = data.material_lines || [];
  if (!lines.length) return "Materials used:\n- No itemised materials listed";

  const rows = lines.map(x => {
    const source = x.price_source || (x.live_price_used ? "live" : "manual");
    const sourceLabel = source === "cached" ? "cached live" : source;
    return `- ${x.name || "Material"}\n  Qty: ${x.quantity || 1} × ${pounds(x.unit_price_used || 0)} each = ${pounds(x.line_total || 0)} (${sourceLabel})`;
  });

  return "Materials used:\n" + rows.join("\n");
}

function buildQuoteWhatsappMessage(data) {
  const quotePdfUrl = CURRENT_QUOTE_ID
    ? `${window.location.origin}/api/quotes/${CURRENT_QUOTE_ID}/pdf`
    : "";

  const pdfLine = quotePdfUrl
    ? `View/download your quote PDF:\n${quotePdfUrl}`
    : "I can send the PDF once the quote is saved.";

  const customerName = data.customer_name ? ` ${data.customer_name}` : "";

  return `Hi${customerName},

Please find your quote below.

Quote total: ${pounds(data.total_price)}

${pdfLine}

If you have any questions, just let me know.

Nigel Harvey Ltd
07595 725547`;
}


function renderQuoteResult(data) {
  CURRENT_QUOTE_DATA = data;
  document.getElementById("invoiceCard").style.display = "none";

  document.getElementById("r_date").innerText = data.created_at || "-";
  document.getElementById("r_type").innerText = data.quote_type || "-";
  document.getElementById("r_customer").innerText = data.customer_name || "-";
  document.getElementById("r_phone").innerText = data.customer_phone || "-";
  document.getElementById("r_address").innerText = data.customer_address || "-";
  document.getElementById("r_job").innerText = data.job || "-";
  document.getElementById("r_labour").innerText = pounds(data.labour);
  const calloutCharge = Number(data.callout_charge || 0);
  document.getElementById("r_callout").innerText = pounds(calloutCharge);
  document.getElementById("r_callout_row").style.display = calloutCharge > 0 ? "flex" : "none";
  const travelCharge = Number(data.travel_charge || 0);
  document.getElementById("r_travel").innerText = pounds(travelCharge);
  document.getElementById("r_travel_row").style.display = travelCharge > 0 ? "flex" : "none";
  document.getElementById("r_materials").innerText = pounds(data.materials);

  const materialsBase = data.materials_base != null ? Number(data.materials_base) : Number(data.materials || 0);
  const procurementAmount = Number(data.materials_procurement_amount || 0);
  const procurementPercent = Number(data.materials_procurement_percent || 0);
  document.getElementById("r_materials_base").innerText = pounds(materialsBase);
  document.getElementById("r_procurement_amount").innerText = pounds(procurementAmount);
  document.getElementById("r_procurement_percent").innerText = procurementPercent > 0 ? "(" + procurementPercent.toFixed(0) + "%)" : "";
  document.getElementById("r_procurement_row").style.display = procurementAmount > 0 ? "flex" : "none";

  document.getElementById("r_deposit").innerText = data.deposit_amount ? pounds(data.deposit_amount) + " (" + Number(data.deposit_percent).toFixed(0) + "%)" : String.fromCharCode(163) + "0.00";
  document.getElementById("r_total").innerText = pounds(data.total_price);

  const lines = data.material_lines || [];
  document.getElementById("r_material_lines").innerHTML = lines.length
    ? lines.map(x => {
        const source = x.price_source || (x.live_price_used ? "live" : "manual");
        const badge = source === "live"
          ? '<span class="badge green">live</span>'
          : (source === "cached" ? '<span class="badge green">cached live</span>' : '<span class="badge">manual</span>');
        return `<div>${escapeHtml(x.name || "")} × ${x.quantity} @ ${pounds(x.unit_price_used || 0)} each — ${pounds(x.line_total)} ${badge}</div>`;
      }).join("")
    : "<div>No materials added.</div>";

  const internalMode = document.getElementById("internal_mode").checked;
  const internalBox = document.getElementById("internalBox");
  if (internalMode) {
    internalBox.classList.remove("hidden");
    document.getElementById("r_internal_raw").innerText = pounds(data.internal_raw_materials);
    document.getElementById("r_internal_job_multiplier").innerText = data.internal_job_multiplier + "x";
    document.getElementById("r_internal_after_job").innerText = pounds(data.internal_after_job_markup);
    document.getElementById("r_internal_handling_percent").innerText = data.internal_handling_percent + "%";
    document.getElementById("r_internal_after_handling").innerText = pounds(data.internal_after_handling);
    document.getElementById("r_internal_hidden_uplift").innerText = pounds(data.internal_hidden_uplift);
    document.getElementById("r_internal_profit").innerText = pounds(data.gross_profit);
    document.getElementById("r_internal_margin").innerText = Number(data.margin_percent || 0).toFixed(1) + "%";
  } else {
    internalBox.classList.add("hidden");
  }

  const message = buildQuoteWhatsappMessage(data);

  const cleanPhone = normalisePhone(data.customer_phone || "");
  document.getElementById("whatsappBtn").href = cleanPhone
    ? "https://wa.me/" + cleanPhone + "?text=" + encodeURIComponent(message)
    : "https://wa.me/?text=" + encodeURIComponent(message);

  document.getElementById("resultCard").style.display = "block";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderStatusBadge(status) {
  const s = (status || "").toLowerCase();
  if (s === "paid") return '<span class="badge green">Paid</span>';
  if (s === "part paid") return '<span class="badge orange">Part Paid</span>';
  return '<span class="badge red">Unpaid</span>';
}


function renderInvoicePhotoGallery(photos) {
  const box = document.getElementById("invoicePhotoGallery");
  if (!box) return;
  const items = photos || [];
  if (!items.length) {
    box.innerHTML = `<div class="small">No job photos attached yet.</div>`;
    return;
  }
  box.innerHTML = `
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;">
      ${items.map(photo => `
        <div style="border:1px solid #d1d5db;border-radius:10px;background:white;padding:8px;">
          <img src="${escapeHtml(photo.url || "")}" alt="" loading="lazy"
            style="width:100%;height:130px;object-fit:cover;border-radius:7px;background:#f3f4f6;">
          <strong style="display:block;margin-top:7px;">${escapeHtml(photo.category_label || "Job photo")}</strong>
          <span class="small">${escapeHtml(photo.caption || "")}</span>
          <button type="button" class="btn-red" style="margin-top:8px;width:100%;"
            onclick="deleteInvoicePhoto(${Number(photo.id || 0)})">Remove</button>
        </div>
      `).join("")}
    </div>`;
}

async function uploadInvoicePhotos() {
  if (!CURRENT_INVOICE_ID) {
    alert("Open or create an invoice first.");
    return;
  }
  const input = document.getElementById("invoicePhotoFiles");
  const files = [...(input?.files || [])];
  if (!files.length) {
    alert("Take or choose at least one photo.");
    return;
  }

  const status = document.getElementById("invoicePhotoUploadStatus");
  const form = new FormData();
  form.append("category", document.getElementById("invoicePhotoCategory")?.value || "after");
  form.append("caption", document.getElementById("invoicePhotoCaption")?.value || "");
  files.forEach(file => form.append("photos", file));

  status.innerHTML = `Preparing and uploading ${files.length} photo${files.length === 1 ? "" : "s"}…`;
  try {
    const response = await fetch(`/api/invoices/${CURRENT_INVOICE_ID}/photos`, {
      method: "POST",
      body: form
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Photo upload failed.");
    if (input) input.value = "";
    const caption = document.getElementById("invoicePhotoCaption");
    if (caption) caption.value = "";
    renderInvoicePhotoGallery(data.photos || []);
    status.innerHTML = `✓ ${Number(data.added || 0)} photo${Number(data.added || 0) === 1 ? "" : "s"} added to the invoice PDF.`;
    showNotice("Job photos added to invoice.");
  } catch (error) {
    status.innerHTML = `<span style="color:#b91c1c;">${escapeHtml(error.message || "Photo upload failed.")}</span>`;
  }
}

async function deleteInvoicePhoto(photoId) {
  if (!CURRENT_INVOICE_ID || !confirm("Remove this photo from the invoice?")) return;
  try {
    const response = await fetch(
      `/api/invoices/${CURRENT_INVOICE_ID}/photos/${photoId}`,
      {method: "DELETE"}
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not remove photo.");
    renderInvoicePhotoGallery(data.photos || []);
    showNotice("Invoice photo removed.");
  } catch (error) {
    alert(error.message || "Could not remove photo.");
  }
}


async function copyInvoiceBankDetails() {
  const details = window.CURRENT_INVOICE_PAYMENT_DETAILS;
  if (!details) return;
  const value = [
    `Bank: ${details.bank}`,
    `Account name: ${details.accountName}`,
    `Sort code: ${details.sortCode}`,
    `Account number: ${details.accountNumber}`,
    `Amount due: ${pounds(details.amount)}`,
    `Reference: ${details.reference}`
  ].join("\n");
  try {
    await navigator.clipboard.writeText(value);
    showNotice("Bank details copied.");
  } catch (error) {
    prompt("Copy these bank details:", value);
  }
}

async function sendCurrentOverdueReminder() {
  if (!CURRENT_INVOICE_ID) return;
  try {
    const response = await fetch(`/api/invoices/${CURRENT_INVOICE_ID}/send-overdue-reminder`, {method:"POST"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Reminder could not be sent.");
    renderInvoiceCard(data);
    showNotice("Overdue reminder sent.");
  } catch (error) {
    alert(error.message || "Reminder could not be sent.");
  }
}

function renderInvoiceCard(item) {
  CURRENT_INVOICE_ID = item.id;
  document.getElementById("resultCard").style.display = "none";
  document.getElementById("invoiceCard").style.display = "block";
  cancelInvoiceEdit();

  const invoice = item.invoice;
  const quoteResult = item.quote_result;

  document.getElementById("i_number").innerText = item.invoice_number || "-";
  document.getElementById("i_job_reference").innerText = item.job_reference || "-";
  document.getElementById("i_date").innerText = item.created_at || "-";
  document.getElementById("i_due_date").innerText = item.due_date || "-";
  document.getElementById("i_status").innerHTML = renderStatusBadge(item.status);
  document.getElementById("i_customer").innerText = invoice.customer_name || "-";
  document.getElementById("i_phone").innerText = invoice.customer_phone || "-";
  document.getElementById("i_address").innerText = invoice.customer_address || "-";
  document.getElementById("i_job").innerText = invoice.job || "-";
  document.getElementById("i_labour").innerText = pounds(invoice.labour);
  document.getElementById("i_materials").innerText = pounds(invoice.materials);
  document.getElementById("i_total").innerText = pounds(item.total_price);
  document.getElementById("i_paid").innerText = pounds(item.amount_paid);
  document.getElementById("i_balance").innerText = pounds(item.balance_due);
  document.getElementById("i_balance_big").innerText = pounds(item.balance_due);
  renderInvoicePhotoGallery(item.photos || []);

  const paymentBox = document.getElementById("i_payment_link_box");
  const isSmallJob = ((quoteResult.quote_type || "").toLowerCase() === "small");
  const bankDetails = {
    bank: "Monzo",
    accountName: "NIGEL HARVEY LTD",
    sortCode: "04-00-04",
    accountNumber: "23669594",
    reference: item.invoice_number || "",
    amount: Number(item.balance_due || 0)
  };
  const termsHtml = isSmallJob
    ? `<div class="invoice-note">Please pay by the due date shown above.<br>Late payment fee may be applied after 14 days.<br>Materials remain the property of Nigel Harvey Ltd until paid in full.</div>`
    : `<div class="invoice-note">Please pay by the due date shown above.<br>Late payment fee may be applied after 14 days.<br>Materials remain the property of Nigel Harvey Ltd until paid in full.<br>Deposit required before works begin where applicable.</div>`;

  paymentBox.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr auto;gap:12px;align-items:start;">
      <div>
        <strong>Bank transfer</strong><br>
        Bank: ${escapeHtml(bankDetails.bank)}<br>
        Account name: ${escapeHtml(bankDetails.accountName)}<br>
        Sort code: <strong>${escapeHtml(bankDetails.sortCode)}</strong><br>
        Account number: <strong>${escapeHtml(bankDetails.accountNumber)}</strong><br>
        Reference: <strong>${escapeHtml(bankDetails.reference)}</strong><br>
        Amount due: <strong>${pounds(bankDetails.amount)}</strong>
      </div>
      ${item.qr_available === false ? `
        <div class="small" style="width:112px;padding:10px;border:1px solid #ddd;border-radius:8px;background:#fafafa;">
          QR unavailable<br>Install qrcode[pil]
        </div>
      ` : `
        <img src="/api/invoices/${item.id}/payment-qr" alt="Payment details QR"
          onerror="this.style.display='none'"
          style="width:112px;height:112px;border:1px solid #ddd;border-radius:8px;background:white;">
      `}
    </div>
    <div class="history-actions" style="grid-template-columns:1fr;margin-top:8px;">
      <button type="button" class="btn-light" onclick="copyInvoiceBankDetails()">Copy bank details</button>
    </div>
    <div class="small" style="margin-top:6px;">The QR contains the bank details, outstanding amount and invoice reference. Bank-app support for automatic prefilling varies.</div>
    ${item.payment_link ? `<div style="margin-top:8px;"><strong>Payment link:</strong> <a href="${escapeHtml(item.payment_link)}" target="_blank">${escapeHtml(item.payment_link)}</a></div>` : ""}
    ${termsHtml}
  `;
  const watermark = document.getElementById("invoicePaidWatermark");
  if (watermark) watermark.classList.toggle("hidden", String(item.status || "").toLowerCase() !== "paid");
  window.CURRENT_INVOICE_PAYMENT_DETAILS = bankDetails;

  const invoiceUrl = window.location.origin + "/invoice/" + item.id;

  const msg =
`Nigel Harvey Ltd Invoice

Invoice: ${item.invoice_number}
Customer: ${invoice.customer_name || "-"}
Balance due: ${pounds(item.balance_due)}

View your invoice:
${invoiceUrl}`;

  const cleanPhone = normalisePhone(invoice.customer_phone || quoteResult.customer_phone || "");
  document.getElementById("invoiceWhatsappBtn").href = cleanPhone
    ? "https://wa.me/" + cleanPhone + "?text=" + encodeURIComponent(msg)
    : "https://wa.me/?text=" + encodeURIComponent(msg);

  document.getElementById("invoiceOpenBtn").href = invoiceUrl;

  window.scrollTo({ top: 0, behavior: "smooth" });
}

function downloadCurrentQuotePdf() {
  if (!CURRENT_QUOTE_ID) { window.print(); return; }
  window.open(`/api/quotes/${CURRENT_QUOTE_ID}/pdf`, "_blank");
}

function downloadCurrentInvoicePdf() {
  if (!CURRENT_INVOICE_ID) { window.print(); return; }
  window.open(`/api/invoices/${CURRENT_INVOICE_ID}/pdf`, "_blank");
}

async function sendInvoiceEmail() {
  if (!CURRENT_INVOICE_ID) return;
  const toEmail = prompt("Send invoice PDF to which email address?");
  if (!toEmail) return;
  const customMessage = prompt("Optional message to include in the email:", "Please find your invoice attached as a PDF.") || "";
  try {
    const r = await fetch(`/api/invoices/${CURRENT_INVOICE_ID}/send-email`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ to_email: toEmail, message: customMessage })
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "Failed to send email");
    showNotice("Invoice email sent successfully.");
  } catch (e) {
    alert(e.message || "Failed to send email");
  }
}

function setQuoteButtonMode(isEditing = false) {
  const btn = document.querySelector('#quotesTab button[onclick="generateQuote()"]');
  if (btn) btn.innerText = isEditing ? "Update Quote" : "Generate Quote";
}

function resetQuoteFormState() {
  CURRENT_QUOTE_ID = null;
  setEditingStatus("", false);
  setQuoteButtonMode(false);
}

function fillFormFromRequest(requestData, quoteId = null) {
  document.getElementById("quote_type").value = requestData.quote_type || "small";
  document.getElementById("customer_name").value = requestData.customer_name || "";
  document.getElementById("customer_address").value = requestData.customer_address || "";
  document.getElementById("customer_phone").value = requestData.customer_phone || "";
  document.getElementById("job").value = requestData.job_description || "";
  document.getElementById("labour").value = requestData.labour_cost || "";
  document.getElementById("include_callout_charge").checked = !!requestData.include_callout_charge;
  document.getElementById("callout_charge").value = requestData.callout_charge != null ? requestData.callout_charge : 200;
  document.getElementById("include_travel_charge").checked = !!requestData.include_travel_charge;
  document.getElementById("travel_charge").value = requestData.travel_charge != null ? requestData.travel_charge : 0;
  document.getElementById("include_materials_handling").checked = !!requestData.include_materials_handling;
  document.getElementById("materials_handling_percent").value = String(requestData.materials_handling_percent || 25);
  document.getElementById("tiling").checked = !!requestData.tiling;
  document.getElementById("wall_tiling_m2").value = requestData.wall_tiling_m2 || "";
  document.getElementById("floor_tiling_m2").value = requestData.floor_tiling_m2 || "";
  document.getElementById("wall_height").value = requestData.wall_height || "half";
  document.getElementById("customer_supplies_tiles").checked = !!requestData.customer_supplies_tiles;
  document.getElementById("deposit_percent").value = String(requestData.deposit_percent || 0);

  clearMaterials();
  const materials = requestData.materials || [];
  if (materials.length) materials.forEach(item => addMaterial(item));

  CURRENT_QUOTE_ID = quoteId;
  if (quoteId) {
    setEditingStatus("Editing saved quote #" + quoteId, true);
    setQuoteButtonMode(true);
  } else {
    setEditingStatus("", false);
    setQuoteButtonMode(false);
  }

  toggleBathroomFields();
  updateLabourSuggestion();
  showTab("quotesTab");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderProfitChart(data) {
  const box = document.getElementById("profitChart");
  if (!data || !data.length) {
    box.innerHTML = "No monthly data yet.";
    return;
  }

  const maxValue = Math.max(...data.map(x => x.profit), 1);
  box.innerHTML = data.map(x => {
    const width = Math.max(4, Math.round((x.profit / maxValue) * 100));
    return `
      <div style="margin-bottom:10px;">
        <div style="display:flex;justify-content:space-between;gap:10px;">
          <span>${escapeHtml(x.label)}</span>
          <strong>${pounds(x.profit)}</strong>
        </div>
        <div style="background:#e9e9e9;border-radius:999px;height:10px;margin-top:6px;overflow:hidden;">
          <div style="background:#1f7a1f;height:10px;width:${width}%;"></div>
        </div>
      </div>
    `;
  }).join("");
}

function renderDashboardSummary(data) {
  const box = document.getElementById("dashboardSummary");
  if (!box) return;
  if (!data || !data.length) {
    box.innerHTML = "";
    return;
  }

  const sorted = [...data].sort((a, b) => Number(b.profit || 0) - Number(a.profit || 0));
  const best = sorted[0];
  const worst = sorted[sorted.length - 1];

  box.innerHTML = `
    <div class="dashboard-item">
      <div class="small">Best profit month</div>
      <div><strong>${escapeHtml(best.label || "-")}</strong></div>
      <div class="num">${pounds(best.profit || 0)}</div>
    </div>
    <div class="dashboard-item">
      <div class="small">Lowest profit month</div>
      <div><strong>${escapeHtml(worst.label || "-")}</strong></div>
      <div class="num">${pounds(worst.profit || 0)}</div>
    </div>
  `;
}

async function loadDashboard() {
  try {
    const [res, chartRes] = await Promise.all([
      fetch("/api/dashboard"),
      fetch("/api/dashboard/monthly-profit")
    ]);
    const data = await res.json();
    const chartData = await chartRes.json();
    document.getElementById("dashboardMonth").innerText = data.month_label || "";
    document.getElementById("dashboardGrid").innerHTML = `
      <div class="dashboard-item"><div class="small">Quotes this month</div><div class="num">${data.quote_count}</div></div>
      <div class="dashboard-item"><div class="small">Quoted total</div><div class="num">${pounds(data.quoted_total)}</div></div>
      <div class="dashboard-item"><div class="small">Gross profit</div><div class="num">${pounds(data.gross_profit_total)}</div></div>
      <div class="dashboard-item"><div class="small">Average quote</div><div class="num">${pounds(data.avg_quote)}</div></div>
      <div class="dashboard-item"><div class="small">Invoices this month</div><div class="num">${data.invoice_count}</div></div>
      <div class="dashboard-item"><div class="small">Invoiced total</div><div class="num">${pounds(data.invoiced_total)}</div></div>
      <div class="dashboard-item"><div class="small">Paid this month</div><div class="num">${pounds(data.paid_total)}</div></div>
      <div class="dashboard-item"><div class="small">Outstanding</div><div class="num">${pounds(data.balance_total)}</div></div>
      <div class="dashboard-item"><div class="small">Customers</div><div class="num">${data.customer_count}</div></div>
    `;
    renderProfitChart(chartData);
    renderDashboardSummary(chartData);
  } catch (e) {
    document.getElementById("profitChart").innerHTML = "Could not load chart.";
    document.getElementById("dashboardSummary").innerHTML = "";
  }
}

async function deleteCustomer(id) {
  const check = prompt("Type DELETE to confirm");
  if (!check || check.trim().toUpperCase() !== "DELETE") return;

  try {
    const res = await fetch("/api/customers/" + id, {
      method: "DELETE"
    });

    const text = await res.text();
    if (!res.ok) {
      alert("Delete failed: " + text);
      return;
    }

    await loadCustomers();
    await loadHistory();
    await loadInvoices();
    await loadDashboard();

    showNotice("Customer deleted.");
  } catch (e) {
    if (String(e).includes("updateQuantityLearningNotes")) {
      showNotice("Customer deleted.");
      try { await loadCustomers(); } catch (_) {}
    } else {
      alert("Could not delete customer: " + e);
    }
  }
}

async function loadHistory() {
  try {
    const res = await fetch("/api/quotes");
    const data = await res.json();
    SAVED_QUOTES = data;
    const history = document.getElementById("historyList");

    if (!data.length) {
      history.innerHTML = "No saved quotes yet.";
      return;
    }

    history.innerHTML = data.map(q => `
      <div class="history-item">
        <div><strong>${escapeHtml(q.customer_name || "No customer name")}</strong></div>
        <div>${escapeHtml(q.job || "")}</div>
        <div class="small">${escapeHtml(q.created_at || "")} · Total ${pounds(q.total_price)} · Profit ${pounds(q.gross_profit)} · Margin ${Number(q.margin_percent || 0).toFixed(1)}%</div>
        <div class="history-actions">
          <button type="button" class="btn-light" onclick="loadSavedQuote(${q.id})">Load</button>
          <button type="button" class="btn-blue" onclick="editSavedQuote(${q.id})">Edit</button>
          <button type="button" class="btn-secondary" onclick="sendSavedQuoteWhatsApp(${q.id})">WhatsApp</button>
          <button type="button" class="btn-blue" onclick="convertQuoteToInvoice(${q.id})">To Invoice</button>
          <button type="button" class="btn-light" onclick="printSavedQuote(${q.id})">Print</button>
          <button type="button" class="btn-red" onclick="deleteSavedQuote(${q.id})">Delete</button>
        </div>
      </div>
    `).join("");
  } catch (e) {
    document.getElementById("historyList").innerHTML = "Unable to load saved quotes.";
  }
}

async function loadInvoices() {
  try {
    const res = await fetch("/api/invoices");
    const data = await res.json();
    SAVED_INVOICES = data;
    const box = document.getElementById("invoiceList");

    if (!data.length) {
      box.innerHTML = "No invoices yet.";
      return;
    }

    box.innerHTML = data.map(i => `
      <div class="history-item">
        <div><strong>${escapeHtml(i.invoice_number)}</strong> — ${escapeHtml(i.customer_name || "No customer name")}</div>
        <div>${renderStatusBadge(i.status)}</div>
        <div class="small">${escapeHtml(i.created_at || "")} · Total ${pounds(i.total_price)} · Paid ${pounds(i.amount_paid)} · Balance ${pounds(i.balance_due)}</div>
        <div class="small" style="margin-top:4px;"><strong>Job Ref:</strong> ${escapeHtml(i.job_reference || "Not entered")}</div>

        <label style="margin-top:10px;">Update payment</label>
        <div class="row">
          <input id="paid_${i.id}" type="number" step="0.01" placeholder="Amount paid" value="${i.amount_paid || 0}">
          <button type="button" class="btn-blue" style="max-width:180px;" onclick="updateInvoicePaid(${i.id})">Save Amount</button>
        </div>

        <label style="margin-top:10px;">Payment link</label>
        <div class="row">
          <input id="payment_link_${i.id}" type="text" placeholder="https://..." value="${escapeHtml(i.payment_link || "")}">
          <button type="button" class="btn-blue" style="max-width:180px;" onclick="savePaymentLink(${i.id})">Save Link</button>
        </div>

        <div class="history-actions" style="grid-template-columns:repeat(3, 1fr);">
          <button type="button" class="btn-secondary" onclick="markInvoicePaid(${i.id}, ${i.total_price})">Mark Paid</button>
          <button type="button" class="btn-light" onclick="markInvoiceUnpaid(${i.id})">Mark Unpaid</button>
          <button type="button" class="btn-blue" onclick="editInvoice(${i.id})">Edit Invoice / Job Ref</button>
          <button type="button" class="btn-light" onclick="openInvoice(${i.id})">Open</button>
          <button type="button" class="btn-secondary" onclick="sendInvoiceWhatsApp(${i.id})">WhatsApp</button>
          <button type="button" class="btn-blue" onclick="emailInvoice(${i.id})">Email</button>
          <button type="button" class="btn-light" onclick="openInvoicePage(${i.id})">Invoice Page</button>
          <button type="button" class="btn-light" onclick="printInvoice(${i.id})">Print</button>
          <button type="button" class="btn-red" onclick="deleteInvoice(${i.id})">Delete</button>
        </div>
      </div>
    `).join("");
  } catch (e) {
    document.getElementById("invoiceList").innerHTML = "Unable to load invoices.";
  }
}

function renderLeadBadge(status) {
  const s = (status || 'new').toLowerCase();
  if (s === 'won') return '<span class="badge green">Won</span>';
  if (s === 'lost') return '<span class="badge red">Lost</span>';
  if (s === 'quoted') return '<span class="badge blue">Quoted</span>';
  if (s === 'contacted') return '<span class="badge orange">Contacted</span>';
  return '<span class="badge gray">New</span>';
}

async function loadLeads() {
  try {
    const res = await fetch('/api/leads');
    const data = await res.json();
    SAVED_LEADS = data;
    const box = document.getElementById('leadList');
    const q = (document.getElementById('leadSearch')?.value || '').trim().toLowerCase();
    const status = (document.getElementById('leadStatusFilter')?.value || 'all').toLowerCase();
    const filtered = data.filter(l => {
      const hay = `${l.name || ''} ${l.phone || ''} ${l.email || ''} ${l.address || ''} ${l.description || ''}`.toLowerCase();
      const statusOk = status === 'all' || (l.status || '').toLowerCase() === status;
      return statusOk && (!q || hay.includes(q));
    });
    if (!filtered.length) {
      box.innerHTML = q || status !== 'all' ? 'No matching leads.' : 'No leads yet.';
      return;
    }
    box.innerHTML = filtered.map(l => `
      <div class="history-item">
        <div style="display:flex;justify-content:space-between;gap:10px;align-items:center;">
          <div><strong>${escapeHtml(l.name || 'Website lead')}</strong></div>
          <div>${renderLeadBadge(l.status)}</div>
        </div>
        <div>${escapeHtml(l.phone || '')}${l.email ? ' · ' + escapeHtml(l.email) : ''}</div>
        <div class="small">${escapeHtml(l.address || '')}</div>
        <div style="margin-top:8px;">${escapeHtml(l.description || '')}</div>
        <div class="small" style="margin-top:8px;">${escapeHtml(l.created_at || '')} · ${escapeHtml((l.job_type || 'small').toUpperCase())} · ${escapeHtml(l.source || 'website')}</div>
        <div class="history-actions" style="grid-template-columns:repeat(2,1fr);">
          <button type="button" class="btn-light" onclick="startQuoteFromLead(${l.id})">Start Quote</button>
          <button type="button" class="btn-blue" onclick="updateLeadStatus(${l.id}, 'contacted')">Mark Contacted</button>
        </div>
        <div class="history-actions" style="grid-template-columns:repeat(3,1fr);">
          <button type="button" class="btn-secondary" onclick="updateLeadStatus(${l.id}, 'quoted')">Quoted</button>
          <button type="button" class="btn-secondary" onclick="updateLeadStatus(${l.id}, 'won')">Won</button>
          <button type="button" class="btn-red" onclick="updateLeadStatus(${l.id}, 'lost')">Lost</button>
        </div>
        <div class="history-actions" style="grid-template-columns:1fr 1fr;">
          <a class="btn-link btn-secondary" href="${buildLeadWhatsappHref(l)}" target="_blank">WhatsApp</a>
          <button type="button" class="btn-red" onclick="deleteLead(${l.id})">Delete</button>
        </div>
      </div>
    `).join('');
  } catch (e) {
    document.getElementById('leadList').innerHTML = 'Unable to load leads.';
  }
}

function buildLeadWhatsappHref(lead) {
  const cleanPhone = normalisePhone(lead.phone || '');
  const msg = `Hi ${lead.name || ''}, thanks for contacting Nigel Harvey Ltd about: ${lead.description || ''}`.trim();
  return cleanPhone ? `https://wa.me/${cleanPhone}?text=${encodeURIComponent(msg)}` : `https://wa.me/?text=${encodeURIComponent(msg)}`;
}

function startQuoteFromLead(id) {
  const lead = SAVED_LEADS.find(x => x.id === id);
  if (!lead) return;
  startNewQuote();
  document.getElementById('customer_name').value = lead.name || '';
  document.getElementById('customer_address').value = lead.address || '';
  document.getElementById('customer_phone').value = lead.phone || '';
  document.getElementById('quote_type').value = lead.job_type || 'small';
  document.getElementById('job').value = lead.description || '';
  toggleBathroomFields();
  updateLabourSuggestion();
  scheduleQuoteLearning();
  showTab('quotesTab');
  setEditingStatus('Lead loaded into quote builder.', true);
}

async function updateLeadStatus(id, status) {
  try {
    const res = await fetch('/api/leads/' + id + '/status', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Could not update lead.');
    await loadLeads();
    showNotice('Lead updated.');
  } catch (e) {
    alert('Could not update lead: ' + e);
  }
}

async function deleteLead(id) {
  if (!confirm('Delete this lead?')) return;
  try {
    const res = await fetch('/api/leads/' + id, { method: 'DELETE' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Could not delete lead.');
    await loadLeads();
    showNotice('Lead deleted.');
  } catch (e) {
    alert('Could not delete lead: ' + e);
  }
}


async function loadIntelligence() {
  try {
    const res = await fetch("/api/intelligence");
    if (!res.ok) throw new Error();
    const data = await res.json();

    const jobs = data.jobs || [];
    document.getElementById("jobIntelligenceList").innerHTML = jobs.length ? jobs.map(j => `
      <div class="history-item">
        <strong>${escapeHtml(j.quote_type || "Unknown")}</strong><br>
        Quotes: ${j.count || 0}<br>
        Avg labour: ${pounds(j.avg_labour || 0)} · Avg materials: ${pounds(j.avg_materials || 0)} · Avg total: ${pounds(j.avg_total || 0)}<br>
        Avg profit: ${pounds(j.avg_profit || 0)} · Avg margin: ${Number(j.avg_margin || 0).toFixed(1)}%
      </div>
    `).join("") : "No quote intelligence yet.";

    const materials = data.materials || [];
    document.getElementById("materialIntelligenceList").innerHTML = materials.length ? materials.map(m => `
      <div class="history-item">
        <strong>${escapeHtml(m.name || "Material")}</strong><br>
        ${escapeHtml(m.supplier || "")} · Checks: ${m.checks || 0}<br>
        Avg: ${pounds(m.avg_price || 0)} · Low: ${pounds(m.min_price || 0)} · High: ${pounds(m.max_price || 0)}<br>
        Last checked: ${escapeHtml(formatMaterialDate(m.last_checked || ""))}
      </div>
    `).join("") : "No material price history yet.";
  } catch (e) {
    document.getElementById("jobIntelligenceList").innerHTML = "Unable to load intelligence.";
  }
}

function formatMaterialDate(value) {
  if (!value) return "";
  try {
    const d = new Date(value);
    if (!isNaN(d.getTime())) return d.toLocaleString();
  } catch (e) {}
  return value;
}

async function loadMaterialDb() {
  try {
    const res = await fetch("/api/material-prices");
    if (!res.ok) throw new Error();
    SAVED_MATERIAL_DB = await res.json();

    const suppliers = [...new Set(SAVED_MATERIAL_DB.map(x => x.supplier || "").filter(Boolean))].sort();
    const supplierSelect = document.getElementById("materialDbSupplier");
    if (supplierSelect) {
      const current = supplierSelect.value;
      supplierSelect.innerHTML = '<option value="">All suppliers</option>' + suppliers.map(s => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join("");
      supplierSelect.value = current;
    }

    renderMaterialDbList();
  } catch (e) {
    const box = document.getElementById("materialDbList");
    if (box) box.innerHTML = "Unable to load material database.";
  }
}

function renderMaterialDbList() {
  const box = document.getElementById("materialDbList");
  const summary = document.getElementById("materialDbSummary");
  if (!box) return;

  const q = (document.getElementById("materialDbSearch")?.value || "").trim().toLowerCase();
  const supplier = document.getElementById("materialDbSupplier")?.value || "";

  let rows = SAVED_MATERIAL_DB.filter(item => {
    const hay = `${item.name || ""} ${item.supplier || ""} ${item.url || ""}`.toLowerCase();
    const supplierOk = !supplier || (item.supplier || "") === supplier;
    return supplierOk && (!q || hay.includes(q));
  });

  if (summary) summary.innerText = `${rows.length} shown / ${SAVED_MATERIAL_DB.length} saved materials`;

  if (!rows.length) {
    box.innerHTML = "No saved materials found yet. Add product URLs to a quote first, then generate the quote.";
    return;
  }

  box.innerHTML = rows.map(item => {
    const price = item.last_live_price || item.last_price || item.last_manual_price || 0;
    const status = item.last_status || "unknown";
    const badge = status === "live"
      ? '<span class="badge green">live</span>'
      : (status === "cached" ? '<span class="badge green">cached live</span>' : '<span class="badge">manual</span>');

    return `
      <div class="history-item">
        <div><strong>${escapeHtml(item.name || "Unnamed material")}</strong> ${badge}</div>
        <div class="small">${escapeHtml(item.supplier || "")}</div>
        <div style="font-size:22px;font-weight:800;margin:6px 0;">${pounds(price)}</div>
        <div class="small">Times used: ${item.times_used || 0}</div>
        <div class="small">Last checked: ${escapeHtml(formatMaterialDate(item.last_checked_at || ""))}</div>
        <div class="small">Last live success: ${escapeHtml(formatMaterialDate(item.last_success_at || ""))}</div>
        <div class="small" style="word-break:break-all;">${item.url ? `<a href="${escapeHtml(item.url)}" target="_blank">${escapeHtml(item.url)}</a>` : ""}</div>

        <details style="margin-top:10px;">
          <summary>Edit material</summary>
          <label>Name</label>
          <input id="mat_name_${item.id}" value="${escapeHtml(item.name || "")}">
          <label>Supplier</label>
          <input id="mat_supplier_${item.id}" value="${escapeHtml(item.supplier || "")}">
          <label>Product URL</label>
          <input id="mat_url_${item.id}" value="${escapeHtml(item.url || "")}">
          <label>Manual fallback price (£)</label>
          <input id="mat_manual_${item.id}" type="number" step="0.01" value="${Number(item.last_manual_price || item.last_price || 0).toFixed(2)}">
          <div class="history-actions" style="grid-template-columns:1fr 1fr;gap:8px;margin-top:8px;">
            <button type="button" class="btn-primary" onclick="saveMaterialDbItem(${item.id})">Save</button>
            <button type="button" class="btn-red" onclick="deleteMaterialDbItem(${item.id})">Delete</button>
          </div>
        </details>
      </div>
    `;
  }).join("");
}

async function saveMaterialDbItem(id) {
  try {
    const payload = {
      name: document.getElementById("mat_name_" + id).value,
      supplier: document.getElementById("mat_supplier_" + id).value,
      url: document.getElementById("mat_url_" + id).value,
      manual_price: parseFloat(document.getElementById("mat_manual_" + id).value || 0),
    };
    const res = await fetch("/api/material-prices/" + id, {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error();
    await loadMaterialDb();
    showNotice("Material updated.");
  } catch (e) {
    alert("Could not update material.");
  }
}

async function deleteMaterialDbItem(id) {
  if (!confirm("Delete this material from the database?")) return;
  try {
    const res = await fetch("/api/material-prices/" + id, { method: "DELETE" });
    if (!res.ok) throw new Error();
    await loadMaterialDb();
    showNotice("Material deleted.");
  } catch (e) {
    alert("Could not delete material.");
  }
}

async function refreshMaterialDbPrices() {
  try {
    showNotice("Refreshing material prices...");
    const res = await fetch("/api/material-prices/refresh", { method: "POST" });
    if (!res.ok) throw new Error();
    await loadMaterialDb();
    showNotice("Material prices refreshed.");
  } catch (e) {
    alert("Could not refresh live prices.");
  }
}



async function loadSafety() {
  const statusBox = document.getElementById("safetyStatus");
  const backupBox = document.getElementById("backupList");
  if (!statusBox || !backupBox) return;

  try {
    const res = await fetch("/api/backups");
    if (!res.ok) throw new Error();
    const data = await res.json();
    const counts = data.counts || {};

    statusBox.innerHTML = `
      <strong>App version:</strong> ${escapeHtml(data.version || "-")}<br>
      <strong>Customers:</strong> ${counts.customers ?? "-"}<br>
      <strong>Quotes:</strong> ${counts.quotes ?? "-"}<br>
      <strong>Invoices:</strong> ${counts.invoices ?? "-"}<br>
      <strong>Leads:</strong> ${counts.leads ?? "-"}<br>
      <strong>Saved materials:</strong> ${counts.material_price_cache ?? "-"}<br>
      <strong>Backups:</strong> ${(data.backups || []).length}
    `;

    const backups = data.backups || [];
    backupBox.innerHTML = backups.length ? backups.map(b => `
      <div class="history-item">
        <div><strong>${escapeHtml(b.filename)}</strong></div>
        <div>${Number((b.size_bytes || 0) / 1024).toFixed(1)} KB</div>
        <div>${escapeHtml(b.created_at || "")}</div>
        <div class="history-actions">
          <a class="btn-link btn-light" href="/api/backups/${encodeURIComponent(b.filename)}" target="_blank">Download Backup</a>
        </div>
      </div>
    `).join("") : "No backups yet.";
  } catch (e) {
    statusBox.innerHTML = "Could not load safety status.";
    backupBox.innerHTML = "";
  }
}

async function createBackupNow() {
  try {
    const res = await fetch("/api/backups", { method: "POST" });
    if (!res.ok) throw new Error();
    await loadSafety();
    showNotice("Backup created.");
  } catch (e) {
    alert("Could not create backup.");
  }
}


async function loadCustomers() {
  try {
    const res = await fetch("/api/customers");
    const data = await res.json();
    SAVED_CUSTOMERS = data;
    const box = document.getElementById("customerList");
    const q = (document.getElementById("customerSearch")?.value || "").trim().toLowerCase();
    const filtered = data.filter(c => {
      const hay = `${c.name || ""} ${c.phone || ""} ${c.address || ""}`.toLowerCase();
      return !q || hay.includes(q);
    });

    if (!filtered.length) {
      box.innerHTML = q ? "No matching customers." : "No customers yet.";
      return;
    }

    box.innerHTML = filtered.map(c => `
      <div class="history-item">
        <div><strong>${escapeHtml(c.name || "No customer name")}</strong></div>
        <div>${escapeHtml(c.phone || "")}</div>
        <div class="small">${escapeHtml(c.address || "")}</div>
        <div class="history-actions" style="grid-template-columns:1fr 1fr;">
          <button type="button" class="btn-light" onclick="viewCustomerHistory(${c.id})">View History</button>
          <button type="button" class="btn-light" onclick="startQuoteForCustomer(${c.id})">Start Quote</button>
        </div>
        <div class="history-actions">
          <button type="button" class="btn-red" onclick="deleteCustomer(${c.id})">Delete Customer</button>
        </div>
        <div id="customer_history_${c.id}" class="small" style="margin-top:10px;"></div>
      </div>
    `).join("");
  } catch (e) {
    document.getElementById("customerList").innerHTML = "Unable to load customers.";
  }
}

async function viewCustomerHistory(id) {
  try {
    const res = await fetch("/api/customers/" + id + "/history");
    const data = await res.json();
    const box = document.getElementById("customer_history_" + id);

    const quotes = data.quotes || [];
    const invoices = data.invoices || [];

    const quoteRows = quotes.length
      ? quotes.slice(0,10).map(q => `
          <div class="history-item" style="margin-top:10px;padding:10px;background:#fff;">
            <div><strong>${escapeHtml(q.created_at || "")}</strong> — ${pounds(q.total_price || 0)}</div>
            <div>${escapeHtml(q.job || "")}</div>
            <div class="history-actions" style="grid-template-columns:repeat(4,1fr);gap:8px;margin-top:8px;">
              <button type="button" class="btn-light" onclick="loadSavedQuote(${q.id})">Open</button>
              <button type="button" class="btn-light" onclick="editSavedQuote(${q.id})">Edit</button>
              <button type="button" class="btn-green" onclick="sendSavedQuoteWhatsApp(${q.id})">WhatsApp</button>
              <button type="button" class="btn-primary" onclick="convertQuoteToInvoice(${q.id})">Invoice</button>
            </div>
            <div class="history-actions" style="grid-template-columns:1fr 1fr;gap:8px;margin-top:8px;">
              <button type="button" class="btn-light" onclick="printSavedQuote(${q.id})">Print / PDF</button>
              <button type="button" class="btn-red" onclick="deleteSavedQuote(${q.id}); setTimeout(() => viewCustomerHistory(${id}), 500);">Delete Quote</button>
            </div>
          </div>
        `).join("")
      : "<div>None</div>";

    const invoiceRows = invoices.length
      ? invoices.slice(0,10).map(i => `
          <div class="history-item" style="margin-top:10px;padding:10px;background:#fff;">
            <div><strong>${escapeHtml(i.invoice_number || "")}</strong> — ${pounds(i.total_price || 0)} — ${escapeHtml(i.status || "")}</div>
            <div class="history-actions" style="grid-template-columns:repeat(3,1fr);gap:8px;margin-top:8px;">
              <button type="button" class="btn-light" onclick="openInvoice(${i.id})">Open</button>
              <button type="button" class="btn-light" onclick="editInvoice(${i.id})">Edit</button>
              <button type="button" class="btn-primary" onclick="window.open('/invoice/${i.id}', '_blank')">Public Link</button>
            </div>
          </div>
        `).join("")
      : "<div>None</div>";

    box.innerHTML = `
      <div><strong>Quotes:</strong> ${quotes.length}</div>
      ${quoteRows}
      <div style="margin-top:12px;"><strong>Invoices:</strong> ${invoices.length}</div>
      ${invoiceRows}
    `;
  } catch (e) {
    alert("Could not load customer history.");
  }
}

function startQuoteForCustomer(id) {
  const c = SAVED_CUSTOMERS.find(x => x.id === id);
  if (!c) return;
  resetQuoteFormState();
  showTab("quotesTab");
  document.getElementById("customer_name").value = c.name || "";
  document.getElementById("customer_address").value = c.address || "";
  document.getElementById("customer_phone").value = c.phone || "";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function startNewQuote() {
  resetQuoteFormState();
  CURRENT_QUOTE_DATA = null;
  document.getElementById("resultCard").style.display = "none";
  document.getElementById("invoiceCard").style.display = "none";
  document.getElementById("quote_type").value = "small";
  document.getElementById("customer_name").value = "";
  document.getElementById("customer_address").value = "";
  document.getElementById("customer_phone").value = "";
  document.getElementById("job").value = "";
  document.getElementById("labour").value = "";
  document.getElementById("include_materials_handling").checked = true;
  document.getElementById("materials_handling_percent").value = "25";
  document.getElementById("tiling").checked = false;
  document.getElementById("wall_tiling_m2").value = "";
  document.getElementById("floor_tiling_m2").value = "";
  document.getElementById("wall_height").value = "half";
  document.getElementById("customer_supplies_tiles").checked = false;
  document.getElementById("deposit_percent").value = "0";
  clearMaterials();
  const materialSearchPanel = document.getElementById("manualMaterialSearchPanel");
  if (materialSearchPanel) materialSearchPanel.style.display = "none";
  const materialSearchInput = document.getElementById("materialSearch");
  if (materialSearchInput) materialSearchInput.value = "";
  const materialSearchResults = document.getElementById("searchResults");
  if (materialSearchResults) {
    materialSearchResults.innerHTML = "";
    materialSearchResults.classList.add("hidden");
  }
  toggleBathroomFields();
  updateLabourSuggestion();
  showTab("quotesTab");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function loadSavedQuote(id) {
  try {
    const res = await fetch("/api/quotes/" + id);
    if (!res.ok) throw new Error();
    const data = await res.json();
    fillFormFromRequest(data.request, data.id);
    renderQuoteResult(data.result);
    showTab("quotesTab");
    window.scrollTo({ top: 0, behavior: "smooth" });
    showNotice("Quote opened.");
  } catch (e) {
    alert("Could not load saved quote.");
  }
}

async function editSavedQuote(id) {
  try {
    const res = await fetch("/api/quotes/" + id);
    if (!res.ok) throw new Error();
    const data = await res.json();

    const q = normaliseQuoteDataForEditing(data);
    fillFormFromRequest(q, data.id || id);

    if (data.result) {
      renderQuoteResult(data.result);
    }

    showTab("quotesTab");
    window.scrollTo({ top: 0, behavior: "smooth" });
    showNotice("Quote loaded for editing.");
  } catch (e) {
    console.error("Edit quote failed", e);
    alert("Could not load quote for editing: " + e.message);
  }
}

async function sendSavedQuoteWhatsApp(id) {
  try {
    const res = await fetch("/api/quotes/" + id);
    if (!res.ok) throw new Error();
    const data = await res.json();
    fillFormFromRequest(data.request, data.id);
    renderQuoteResult(data.result);
    showTab("quotesTab");
    setTimeout(() => document.getElementById("whatsappBtn").click(), 250);
  } catch (e) {
    alert("Could not open WhatsApp for this quote.");
  }
}

async function printSavedQuote(id) {
  try {
    const res = await fetch("/api/quotes/" + id);
    if (!res.ok) throw new Error();
    const data = await res.json();
    fillFormFromRequest(data.request, data.id);
    renderQuoteResult(data.result);
    showTab("quotesTab");
    setTimeout(() => window.print(), 250);
  } catch (e) {
    alert("Could not print this quote.");
  }
}

async function deleteSavedQuote(id) {
  if (!confirm("Delete this saved quote?")) return;
  try {
    const res = await fetch("/api/quotes/" + id, { method: "DELETE" });
    if (!res.ok) throw new Error();
    await loadHistory();
    await loadCustomers();
    await loadDashboard();
    showNotice("Saved quote deleted.");
  } catch (e) {
    alert("Could not delete saved quote.");
  }
}


let LAST_AI_QUOTE_DRAFT = null;

async function checkAIQuoteStatus() {
  const status = document.getElementById("aiQuoteStatus");
  if (!status) return;

  try {
    const res = await fetch("/api/ai-quote-status");
    const data = await res.json();
    if (data.configured) {
      status.innerHTML = `AI connected · model: ${escapeHtml(data.model || "")}`;
    } else {
      status.innerHTML = `<strong>Setup needed:</strong> add OPENAI_API_KEY in Render environment settings.`;
    }
  } catch (e) {
    status.innerHTML = "Could not check AI connection.";
  }
}


let CURRENT_SITE_SURVEY = null;
let RECORDED_SITE_AUDIO = null;
let SITE_AUDIO_RECORDER = null;
let SITE_AUDIO_STREAM = null;
let SITE_AUDIO_CHUNKS = [];
let SITE_AUDIO_TIMER = null;
let SITE_AUDIO_STARTED_AT = 0;
let CAPTURED_SITE_PHOTOS = [];
let RECORDED_SITE_VIDEO = null;
let SITE_MEDIA_RECORDER = null;
let SITE_CAMERA_STREAM = null;
let SITE_VIDEO_CHUNKS = [];
let SITE_RECORDING_TIMER = null;
let SITE_RECORDING_STARTED_AT = 0;
let SITE_SURVEY_ATTACHED = false;


function toggleSiteInformationPanel() {
  document.getElementById("siteInformationPanel")?.classList.toggle("hidden");
}

function preferredAudioMimeType() {
  if (!window.MediaRecorder) return "";
  const options = [
    "audio/mp4",
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus"
  ];
  return options.find(type => MediaRecorder.isTypeSupported(type)) || "";
}

async function startSiteAudioRecording() {
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    document.getElementById("siteAudioFallback")?.click();
    return;
  }

  try {
    SITE_AUDIO_STREAM = await navigator.mediaDevices.getUserMedia({audio: true});
    SITE_AUDIO_CHUNKS = [];
    const mimeType = preferredAudioMimeType();
    const options = {audioBitsPerSecond: 48000};
    if (mimeType) options.mimeType = mimeType;

    SITE_AUDIO_RECORDER = new MediaRecorder(SITE_AUDIO_STREAM, options);
    SITE_AUDIO_RECORDER.ondataavailable = event => {
      if (event.data && event.data.size) SITE_AUDIO_CHUNKS.push(event.data);
      const bytes = SITE_AUDIO_CHUNKS.reduce((sum, item) => sum + item.size, 0);
      document.getElementById("siteAudioSize").innerText = `Recorded ${formatMediaBytes(bytes)}`;
    };
    SITE_AUDIO_RECORDER.onstop = finishSiteAudioRecording;
    SITE_AUDIO_RECORDER.start(1000);

    SITE_AUDIO_STARTED_AT = Date.now();
    document.getElementById("siteAudioRecorder")?.classList.remove("hidden");
    document.getElementById("recordSiteAudioButton").disabled = true;

    SITE_AUDIO_TIMER = setInterval(() => {
      const seconds = Math.floor((Date.now() - SITE_AUDIO_STARTED_AT) / 1000);
      document.getElementById("siteAudioTimer").innerText =
        `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
      if (seconds >= 300) stopSiteAudioRecording();
    }, 250);
  } catch (error) {
    document.getElementById("siteAudioFallback")?.click();
  }
}

function stopSiteAudioRecording() {
  if (SITE_AUDIO_RECORDER && SITE_AUDIO_RECORDER.state !== "inactive") {
    SITE_AUDIO_RECORDER.stop();
  }
}

function finishSiteAudioRecording() {
  const mimeType = SITE_AUDIO_RECORDER?.mimeType || "audio/webm";
  const extension = mimeType.includes("mp4") ? "m4a" : mimeType.includes("ogg") ? "ogg" : "webm";
  const blob = new Blob(SITE_AUDIO_CHUNKS, {type: mimeType});
  RECORDED_SITE_AUDIO = new File(
    [blob],
    `job-walkthrough-${Date.now()}.${extension}`,
    {type: mimeType, lastModified: Date.now()}
  );
  cleanupSiteAudioRecorder();
  updateSiteCaptureSummary();
  document.getElementById("siteSurveyStatus").innerHTML =
    `Audio walkthrough recorded (${formatMediaBytes(RECORDED_SITE_AUDIO.size)}). Press Analyse Site Visit.`;
}

function cancelSiteAudioRecording() {
  SITE_AUDIO_CHUNKS = [];
  RECORDED_SITE_AUDIO = null;
  cleanupSiteAudioRecorder();
  updateSiteCaptureSummary();
}

function cleanupSiteAudioRecorder() {
  if (SITE_AUDIO_TIMER) clearInterval(SITE_AUDIO_TIMER);
  SITE_AUDIO_TIMER = null;
  if (SITE_AUDIO_STREAM) SITE_AUDIO_STREAM.getTracks().forEach(track => track.stop());
  SITE_AUDIO_STREAM = null;
  document.getElementById("siteAudioRecorder")?.classList.add("hidden");
  const button = document.getElementById("recordSiteAudioButton");
  if (button) button.disabled = false;
  const timer = document.getElementById("siteAudioTimer");
  if (timer) timer.innerText = "00:00";
}

function formatMediaBytes(bytes) {
  const value = Number(bytes || 0);
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function updateSiteCaptureSummary() {
  const existingPhotos = [...(document.getElementById("siteSurveyPhotos")?.files || [])];
  const existingVideo = document.getElementById("siteSurveyVideo")?.files?.[0];
  const existingAudio = document.getElementById("siteSurveyAudio")?.files?.[0];
  const plans = [...(document.getElementById("sitePlans")?.files || [])];
  const notes = String(document.getElementById("siteVisitNotes")?.value || "").trim();

  const photoCount = CAPTURED_SITE_PHOTOS.length + existingPhotos.length;
  const video = RECORDED_SITE_VIDEO || existingVideo;
  const audio = RECORDED_SITE_AUDIO || existingAudio;
  const parts = [];

  if (audio) parts.push(`audio ${formatMediaBytes(audio.size)}`);
  if (video) parts.push(`video ${formatMediaBytes(video.size)}`);
  if (photoCount) parts.push(`${photoCount} photo${photoCount === 1 ? "" : "s"}`);
  if (plans.length) parts.push(`${plans.length} plan${plans.length === 1 ? "" : "s"}`);
  if (notes) parts.push("notes");

  document.getElementById("siteCaptureSummary").innerHTML =
    parts.length ? `Ready: ${parts.join(" · ")}` : "No site information added yet.";
}

function takeSitePhoto() {
  document.getElementById("siteCameraPhoto")?.click();
}

function preferredRecorderMimeType() {
  if (!window.MediaRecorder) return "";
  const options = [
    "video/mp4;codecs=h264,aac",
    "video/mp4",
    "video/webm;codecs=vp8,opus",
    "video/webm"
  ];
  return options.find(type => MediaRecorder.isTypeSupported(type)) || "";
}

async function startSiteVideoRecording() {
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    document.getElementById("siteCameraVideoFallback")?.click();
    return;
  }

  try {
    SITE_CAMERA_STREAM = await navigator.mediaDevices.getUserMedia({
      video: {
        facingMode: {ideal: "environment"},
        width: {ideal: 1280, max: 1280},
        height: {ideal: 720, max: 720},
        frameRate: {ideal: 24, max: 30}
      },
      audio: true
    });

    const preview = document.getElementById("siteVideoPreview");
    preview.srcObject = SITE_CAMERA_STREAM;
    document.getElementById("siteVideoRecorder").classList.remove("hidden");

    SITE_VIDEO_CHUNKS = [];
    const mimeType = preferredRecorderMimeType();
    const options = {
      videoBitsPerSecond: 900000,
      audioBitsPerSecond: 48000
    };
    if (mimeType) options.mimeType = mimeType;

    SITE_MEDIA_RECORDER = new MediaRecorder(SITE_CAMERA_STREAM, options);
    SITE_MEDIA_RECORDER.ondataavailable = event => {
      if (event.data && event.data.size) SITE_VIDEO_CHUNKS.push(event.data);
      const bytes = SITE_VIDEO_CHUNKS.reduce((sum, item) => sum + item.size, 0);
      document.getElementById("siteVideoSize").innerText = `Recorded ${formatMediaBytes(bytes)}`;
    };
    SITE_MEDIA_RECORDER.onstop = finishSiteVideoRecording;
    SITE_MEDIA_RECORDER.start(1000);

    SITE_RECORDING_STARTED_AT = Date.now();
    document.getElementById("recordSiteVideoButton").disabled = true;
    SITE_RECORDING_TIMER = setInterval(() => {
      const seconds = Math.floor((Date.now() - SITE_RECORDING_STARTED_AT) / 1000);
      const minutes = Math.floor(seconds / 60);
      const remainder = seconds % 60;
      document.getElementById("siteVideoTimer").innerText =
        `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
      if (seconds >= 90) stopSiteVideoRecording();
    }, 250);
  } catch (error) {
    document.getElementById("siteCameraVideoFallback")?.click();
  }
}

function stopSiteVideoRecording() {
  if (SITE_MEDIA_RECORDER && SITE_MEDIA_RECORDER.state !== "inactive") {
    SITE_MEDIA_RECORDER.stop();
  }
}

function cancelSiteVideoRecording() {
  SITE_VIDEO_CHUNKS = [];
  RECORDED_SITE_VIDEO = null;
  cleanupSiteRecorder();
  updateSiteCaptureSummary();
}

function finishSiteVideoRecording() {
  const mimeType = SITE_MEDIA_RECORDER?.mimeType || "video/webm";
  const extension = mimeType.includes("mp4") ? "mp4" : "webm";
  const blob = new Blob(SITE_VIDEO_CHUNKS, {type: mimeType});
  RECORDED_SITE_VIDEO = new File(
    [blob],
    `site-survey-${Date.now()}.${extension}`,
    {type: mimeType, lastModified: Date.now()}
  );
  cleanupSiteRecorder();
  updateSiteCaptureSummary();
  document.getElementById("siteSurveyStatus").innerHTML =
    `Video recorded (${formatMediaBytes(RECORDED_SITE_VIDEO.size)}). Press Analyse captured media.`;
}

function cleanupSiteRecorder() {
  if (SITE_RECORDING_TIMER) clearInterval(SITE_RECORDING_TIMER);
  SITE_RECORDING_TIMER = null;
  if (SITE_CAMERA_STREAM) {
    SITE_CAMERA_STREAM.getTracks().forEach(track => track.stop());
  }
  SITE_CAMERA_STREAM = null;
  const preview = document.getElementById("siteVideoPreview");
  if (preview) preview.srcObject = null;
  document.getElementById("siteVideoRecorder")?.classList.add("hidden");
  const button = document.getElementById("recordSiteVideoButton");
  if (button) button.disabled = false;
  document.getElementById("siteVideoTimer").innerText = "00:00";
}

document.getElementById("siteCameraPhoto")?.addEventListener("change", event => {
  const file = event.target.files?.[0];
  if (file) {
    if (CAPTURED_SITE_PHOTOS.length >= 6) {
      alert("You can use up to 6 site photos.");
    } else {
      CAPTURED_SITE_PHOTOS.push(file);
      CURRENT_SITE_SURVEY = null;
      SITE_SURVEY_ATTACHED = false;
    }
  }
  event.target.value = "";
  updateSiteCaptureSummary();
});

document.getElementById("siteCameraVideoFallback")?.addEventListener("change", event => {
  const file = event.target.files?.[0];
  if (file) {
    RECORDED_SITE_VIDEO = file;
    CURRENT_SITE_SURVEY = null;
    SITE_SURVEY_ATTACHED = false;
  }
  event.target.value = "";
  updateSiteCaptureSummary();
});

document.getElementById("siteSurveyPhotos")?.addEventListener("change", updateSiteCaptureSummary);
document.getElementById("siteSurveyVideo")?.addEventListener("change", updateSiteCaptureSummary);
document.getElementById("siteSurveyAudio")?.addEventListener("change", updateSiteCaptureSummary);
document.getElementById("sitePlans")?.addEventListener("change", updateSiteCaptureSummary);
document.getElementById("siteVisitNotes")?.addEventListener("input", updateSiteCaptureSummary);
document.getElementById("siteAudioFallback")?.addEventListener("change", event => {
  const file = event.target.files?.[0];
  if (file) RECORDED_SITE_AUDIO = file;
  event.target.value = "";
  updateSiteCaptureSummary();
});

function surveyStatusLabel(value) {
  return ({
    confirmed_visible: "Confirmed visible",
    not_visible: "Not visible",
    present_condition_unconfirmed: "Present — condition unconfirmed",
    confirmed_by_nigel: "Confirmed by Nigel",
    ai_inferred: "AI inferred"
  })[value] || value || "Unknown";
}

function surveyActionLabel(value) {
  return ({
    reuse_existing: "Reuse existing",
    keep_optional: "Keep optional",
    include_required: "Include required",
    site_check: "Site check",
    no_quote_change: "No quote change"
  })[value] || value || "";
}

async function analyseSiteSurvey() {
  const chosenPhotos = [...(document.getElementById("siteSurveyPhotos")?.files || [])];
  const photos = [...CAPTURED_SITE_PHOTOS, ...chosenPhotos];
  const chosenVideo = document.getElementById("siteSurveyVideo")?.files?.[0];
  const video = RECORDED_SITE_VIDEO || chosenVideo;
  const chosenAudio = document.getElementById("siteSurveyAudio")?.files?.[0];
  const audio = RECORDED_SITE_AUDIO || chosenAudio;
  const plans = [...(document.getElementById("sitePlans")?.files || [])];
  const siteNotes = document.getElementById("siteVisitNotes")?.value || "";
  const status = document.getElementById("siteSurveyStatus");

  if (!photos.length && !video && !audio && !plans.length && !siteNotes.trim()) {
    alert("Record a job walkthrough, or add video, photos, plans or notes.");
    return;
  }
  if (photos.length > 6) {
    alert("V12.4 analyses up to 6 photos at a time.");
    return;
  }
  const oversizedPhoto = photos.find(file => file.size > 10 * 1024 * 1024);
  if (oversizedPhoto) {
    alert(`${oversizedPhoto.name} is over the 10 MB photo limit.`);
    return;
  }
  if (video && video.size > 80 * 1024 * 1024) {
    alert("This video is over 80 MB. Use the in-app recorder or record a shorter video.");
    return;
  }
  if (audio && audio.size > 40 * 1024 * 1024) {
    alert("Keep the audio walkthrough below 40 MB.");
    return;
  }

  const form = new FormData();
  form.append("job_description", document.getElementById("job")?.value || "");
  form.append("site_notes", siteNotes);
  photos.forEach(file => form.append("photos", file));
  plans.forEach(file => form.append("plans", file));
  if (video) form.append("video", video);
  if (audio) form.append("audio", audio);

  status.innerHTML = "Analysing the walkthrough, transcript, visual evidence, plans and notes…";
  document.getElementById("siteSurveyResult").innerHTML = "";
  SITE_SURVEY_ATTACHED = false;

  try {
    const response = await fetch("/api/site-survey", {method: "POST", body: form});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Site survey failed.");

    CURRENT_SITE_SURVEY = data;
    SITE_SURVEY_ATTACHED = true;

    const jobField = document.getElementById("job");
    if (jobField && !String(jobField.value || "").trim()) {
      jobField.value = data.proposed_job_description || data.summary || "";
      jobField.dispatchEvent(new Event("input", {bubbles: true}));
      CURRENT_SITE_SURVEY.merged_job_description = jobField.value;
      CURRENT_SITE_SURVEY.description_merge_mode = "created";
    }

    renderSiteSurvey(data);
    status.innerHTML =
      `✓ Site visit analysed and attached · ${(data.input_modes || []).join(", ") || "notes"} used.`;
    showNotice("Site visit analysed. Building the quote next…");
    return true;
  } catch (error) {
    CURRENT_SITE_SURVEY = null;
    SITE_SURVEY_ATTACHED = false;
    status.innerHTML =
      `<span style="color:#b91c1c;">${escapeHtml(error.message || "Site survey failed.")}</span>`;
    return false;
  }
}

async function analyseAndBuildQuote() {
  const button = document.getElementById("aiQuoteButton");
  const hasSiteInfo = Boolean(
    CAPTURED_SITE_PHOTOS.length || RECORDED_SITE_VIDEO || RECORDED_SITE_AUDIO ||
    document.getElementById("siteSurveyPhotos")?.files?.length ||
    document.getElementById("siteSurveyVideo")?.files?.length ||
    document.getElementById("siteSurveyAudio")?.files?.length ||
    document.getElementById("sitePlans")?.files?.length ||
    document.getElementById("siteVisitNotes")?.value?.trim()
  );
  if (button) { button.disabled = true; button.innerText = "Working…"; }
  try {
    if (hasSiteInfo) {
      const ok = await analyseSiteSurvey();
      if (!ok) return;
    }
    await generateAIQuoteDraft();
  } finally {
    if (button) { button.disabled = false; button.innerText = "✨ Analyse Site & Build Quote"; }
  }
}


function normaliseDescriptionText(value) {
  return String(value || "")
    .replace(/\s+/g, " ")
    .replace(/\s+([.,;:])/g, "$1")
    .trim();
}

function descriptionSentenceKeys(value) {
  return normaliseDescriptionText(value)
    .split(/(?<=[.!?])\s+/)
    .map(sentence => sentence.toLowerCase().replace(/[^a-z0-9 ]/g, "").trim())
    .filter(Boolean);
}

function mergeSurveyDescription(existingText, additionText) {
  const existing = String(existingText || "").trim();
  const addition = String(additionText || "").trim();
  if (!existing) return addition;
  if (!addition) return existing;

  const existingKeys = descriptionSentenceKeys(existing);
  const newSentences = addition
    .split(/(?<=[.!?])\s+/)
    .map(sentence => sentence.trim())
    .filter(Boolean)
    .filter(sentence => {
      const key = sentence.toLowerCase().replace(/[^a-z0-9 ]/g, "").trim();
      if (!key) return false;
      return !existingKeys.some(existingKey =>
        existingKey === key ||
        existingKey.includes(key) ||
        key.includes(existingKey)
      );
    });

  if (!newSentences.length) return existing;
  return `${existing}\n\nSite visit findings:\n${newSentences.join(" ")}`.trim();
}

function applySurveyDescription(mode = "append") {
  if (!CURRENT_SITE_SURVEY) {
    alert("Analyse the site media first.");
    return;
  }

  const jobField = document.getElementById("job");
  if (!jobField) return;

  const existing = jobField.value || "";
  const completeDescription =
    CURRENT_SITE_SURVEY.proposed_job_description ||
    CURRENT_SITE_SURVEY.summary ||
    "";
  const addition =
    CURRENT_SITE_SURVEY.site_visit_addition ||
    CURRENT_SITE_SURVEY.summary ||
    "";

  if (mode === "replace" || !existing.trim()) {
    jobField.value = completeDescription;
  } else {
    jobField.value = mergeSurveyDescription(existing, addition);
  }

  jobField.dispatchEvent(new Event("input", {bubbles: true}));
  CURRENT_SITE_SURVEY.merged_job_description = jobField.value;
  CURRENT_SITE_SURVEY.description_merge_mode =
    existing.trim() && mode !== "replace" ? "appended" : "created";

  const mergeStatus = document.getElementById("surveyDescriptionStatus");
  if (mergeStatus) {
    mergeStatus.innerHTML =
      existing.trim() && mode !== "replace"
        ? "✓ New site findings added. Original enquiry preserved."
        : "✓ Job description created from the site survey.";
  }

  showNotice(
    existing.trim() && mode !== "replace"
      ? "Site findings added to the existing job description."
      : "Job description created from the site survey."
  );
}

function surveyDescriptionPreview(data) {
  const jobField = document.getElementById("job");
  const existing = String(jobField?.value || "").trim();
  const completeDescription =
    data.proposed_job_description || data.summary || "";
  const addition = data.site_visit_addition || data.summary || "";
  const preview = existing
    ? mergeSurveyDescription(existing, addition)
    : completeDescription;

  return `
    <div style="margin-top:10px;padding:10px;border:1px solid #7c3aed;border-radius:9px;background:#faf5ff;">
      <strong>${existing ? "Add site findings to existing enquiry" : "Create job description from survey"}</strong>
      <div class="small" style="margin-top:4px;">
        ${existing
          ? "The website enquiry will stay unchanged at the top. Only new site-visit information will be appended."
          : "The survey has enough information to fill the job description box."}
      </div>
      <div style="margin-top:8px;padding:8px;border:1px solid #ddd;border-radius:8px;background:white;white-space:pre-wrap;">${escapeHtml(preview)}</div>
      <div id="surveyDescriptionStatus" class="small" style="margin-top:6px;"></div>
      <div class="history-actions" style="grid-template-columns:1fr 1fr;gap:8px;margin-top:8px;">
        <button type="button" class="btn-green" onclick="applySurveyDescription('append')">
          ${existing ? "Add new findings" : "Use this description"}
        </button>
        <button type="button" class="btn-light" onclick="applySurveyDescription('replace')">
          Replace description
        </button>
      </div>
    </div>`;
}

function renderSiteSurvey(data) {
  const box = document.getElementById("siteSurveyResult");
  const components = data.components || [];
  const actions = data.material_actions || [];
  const warnings = data.warnings || [];

  box.innerHTML = `<div class="history-item" style="padding:10px;border-color:#2563eb;">
    <strong>AI site visit summary</strong><br>${escapeHtml(data.summary || "")}
    <div style="margin-top:6px;color:#166534;"><strong>✓ Attached to the next AI quote</strong></div>
    ${surveyDescriptionPreview(data)}
    ${data.transcript ? `<details style="margin-top:7px;"><summary><strong>Walkthrough transcript</strong></summary><div style="margin-top:5px;">${escapeHtml(data.transcript)}</div></details>` : ""}
    ${components.length ? `<div style="margin-top:9px;"><strong>Components reviewed</strong>${components.map(item => `<div style="margin-top:6px;padding:8px;border:1px solid #ddd;border-radius:8px;background:white;"><strong>${escapeHtml(item.component || "")}</strong><br><span class="small">${escapeHtml(surveyStatusLabel(item.status))} · ${Number(item.confidence || 0)}%</span><br>${escapeHtml(item.condition || "")}<br><strong>Quote action:</strong> ${escapeHtml(surveyActionLabel(item.quote_action))}${item.evidence ? `<br><span class="small">${escapeHtml(item.evidence)}</span>` : ""}</div>`).join("")}</div>` : ""}
    ${actions.length ? `<div style="margin-top:9px;"><strong>Material decisions</strong><br>${actions.map(item => `• ${escapeHtml(item.material_name)}: ${escapeHtml(surveyActionLabel(item.action))} — ${escapeHtml(item.reason)} (${Number(item.confidence || 0)}%)`).join("<br>")}</div>` : ""}
    ${warnings.length ? `<div style="margin-top:9px;"><strong>Limitations</strong><br>${warnings.map(item => `△ ${escapeHtml(item)}`).join("<br>")}</div>` : ""}
  </div>`;
}

function useSiteSurveyInQuote() {
  if (!CURRENT_SITE_SURVEY) return alert("Analyse the site media first.");
  SITE_SURVEY_ATTACHED = true;
  document.getElementById("siteSurveyStatus").innerHTML =
    "✓ Survey attached. Press Build Quote with AI.";
  showNotice("Site survey attached to the next AI quote draft.");
}

function clearSiteSurvey() {
  cancelSiteVideoRecording();
  CURRENT_SITE_SURVEY = null;
  SITE_SURVEY_ATTACHED = false;
  CAPTURED_SITE_PHOTOS = [];
  RECORDED_SITE_VIDEO = null;
  RECORDED_SITE_AUDIO = null;

  const photos = document.getElementById("siteSurveyPhotos");
  const video = document.getElementById("siteSurveyVideo");
  const audio = document.getElementById("siteSurveyAudio");
  const plans = document.getElementById("sitePlans");
  const notes = document.getElementById("siteVisitNotes");
  if (photos) photos.value = "";
  if (video) video.value = "";
  if (audio) audio.value = "";
  if (plans) plans.value = "";
  if (notes) notes.value = "";

  document.getElementById("siteSurveyResult").innerHTML = "";
  document.getElementById("siteSurveyStatus").innerHTML = "";
  updateSiteCaptureSummary();
}

function currentMaterialsForAI() {
  return [...document.querySelectorAll("#materials .material-row")].map(row => ({
    name: row.querySelector(".m-name")?.value || "",
    quantity: Number(row.querySelector(".m-qty")?.value || 1),
    supplier: row.querySelector(".m-supplier")?.value || "",
    url: row.querySelector(".m-url")?.value || "",
    manual_price: Number(row.querySelector(".m-manual")?.value || 0)
  })).filter(m => m.name.trim());
}

async function generateAIQuoteDraft() {
  if (!Array.isArray(SAVED_MATERIAL_DB) || !SAVED_MATERIAL_DB.length) {
    try { await loadMaterialDb(); } catch (e) {}
  }
  const button = document.getElementById("aiQuoteButton");
  const status = document.getElementById("aiQuoteStatus");
  const resultBox = document.getElementById("aiQuoteResult");
  let job = document.getElementById("job")?.value || "";

  if (!job.trim() && CURRENT_SITE_SURVEY) {
    applySurveyDescription("replace");
    job = document.getElementById("job")?.value || "";
  }

  if (!job.trim()) {
    alert("Enter the job description first.");
    return;
  }

  if (button) {
    button.disabled = true;
    button.innerText = "Building quote…";
  }
  if (status) {
    status.innerHTML = CURRENT_SITE_SURVEY
      ? "Using the attached site visit, audio transcript, any visual evidence, job history, materials and labour…"
      : "No site survey attached — using the written job description, history, materials and labour only…";
  }
  if (resultBox) resultBox.innerHTML = "";

  const hasUnanalysedMedia =
    CAPTURED_SITE_PHOTOS.length ||
    RECORDED_SITE_VIDEO ||
    document.getElementById("siteSurveyPhotos")?.files?.length ||
    document.getElementById("siteSurveyVideo")?.files?.length;

  if (hasUnanalysedMedia && !CURRENT_SITE_SURVEY) {
    const continueWithoutSurvey = confirm(
      "You have site media selected, but it has not been analysed. Continue without using the photos/video?"
    );
    if (!continueWithoutSurvey) {
      if (button) {
        button.disabled = false;
        button.innerText = "✨ Analyse Site & Build Quote";
      }
      return;
    }
  }

  const payload = {
    job_description: job,
    quote_type: document.getElementById("quote_type")?.value || "small",
    customer_name: document.getElementById("customer_name")?.value || "",
    customer_address: document.getElementById("customer_address")?.value || "",
    current_labour: Number(document.getElementById("labour")?.value || 0),
    current_materials: currentMaterialsForAI(),
    site_survey: CURRENT_SITE_SURVEY
      ? {
          ...CURRENT_SITE_SURVEY,
          merged_job_description: document.getElementById("job")?.value || ""
        }
      : {}
  };

  try {
    const res = await fetch("/api/ai-quote-draft", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Could not generate AI quote draft.");
    }

    LAST_AI_QUOTE_DRAFT = data.draft;
    renderAIQuoteDraft(data);
    if (status) {
      const context = data.context_summary || {};
      status.innerHTML = context.is_multi_job
        ? `Quote health check complete · ${context.multi_job_count || 0} physical job(s) · review any health warnings before applying it.`
        : context.smart_job_type
          ? `Quote health check complete · ${escapeHtml(context.smart_job_type)} · review any health warnings before applying it.`
          : `Estimator dashboard ready using database-first fallback.`;
    }
  } catch (e) {
    if (status) status.innerHTML = `<strong>AI error:</strong> ${escapeHtml(e.message || String(e))}`;
  } finally {
    if (button) {
      button.disabled = false;
      button.innerText = "✨ Analyse Site & Build Quote";
    }
  }
}


function addQuoteHealthSuggestion(suggestionId) {
  const draft = LAST_AI_QUOTE_DRAFT;
  if (!draft || !draft.quote_health) return;

  const suggestion = (draft.quote_health.missing_items || []).find(item => item.id === suggestionId);
  if (!suggestion) return;

  draft.materials = draft.materials || [];
  const alreadyExists = draft.materials.some(item =>
    canonicalMaterialName(item.name || "") === canonicalMaterialName(suggestion.name || "")
  );

  if (!alreadyExists) {
    draft.materials.push({
      name: suggestion.name || "",
      quantity: Number(suggestion.quantity || 1),
      supplier: suggestion.supplier || "City Plumbing",
      url: suggestion.url || "",
      manual_price: Number(suggestion.manual_price || 0),
      required: !suggestion.optional,
      display_status: suggestion.optional ? "optional" : "required",
      data_source: "quote_health_suggestion",
      reason: suggestion.reason || "",
      include_in_quote: true,
      optional_selected: Boolean(suggestion.optional)
    });
  }

  const selectedMaterial = draft.materials.find(item =>
    canonicalMaterialName(item.name || "") === canonicalMaterialName(suggestion.name || "")
  );
  if (selectedMaterial) {
    selectedMaterial.include_in_quote = true;
    if (suggestion.optional) selectedMaterial.optional_selected = true;
    mergeBundleMaterialIntoForm(selectedMaterial);
    mergeDuplicateMaterialRowsInForm();
  }

  draft.quote_health.missing_items = (draft.quote_health.missing_items || [])
    .filter(item => item.id !== suggestionId);
  draft.quote_health.score = Math.min(100, Number(draft.quote_health.score || 0) + (suggestion.optional ? 4 : 9));
  draft.quote_health.checks_passed = draft.quote_health.checks_passed || [];
  draft.quote_health.checks_passed.push(`${suggestion.name} was added for review.`);
  draft.quote_health.readiness = "review_recommended";
  draft.quote_health.readiness_label = "Review recommended";

  renderAIQuoteDraft({draft});
  showNotice(`${suggestion.name} added to the AI draft. Check its supplier and price.`);
}

function ignoreQuoteHealthSuggestion(suggestionId) {
  const draft = LAST_AI_QUOTE_DRAFT;
  if (!draft || !draft.quote_health) return;

  const suggestion = (draft.quote_health.missing_items || []).find(item => item.id === suggestionId);
  draft.quote_health.missing_items = (draft.quote_health.missing_items || [])
    .filter(item => item.id !== suggestionId);
  draft.quote_health.checks_passed = draft.quote_health.checks_passed || [];
  if (suggestion) {
    draft.quote_health.checks_passed.push(`${suggestion.name} was reviewed and ignored.`);
  }

  renderAIQuoteDraft({draft});
  showNotice("Suggestion ignored for this draft.");
}


function useSuggestedQuantity(warningId) {
  const draft = LAST_AI_QUOTE_DRAFT;
  if (!draft || !draft.quote_health) return;
  const warning = (draft.quote_health.quantity_warnings || []).find(x => x.id === warningId);
  if (!warning || warning.no_auto_fix) return;

  const target = canonicalMaterialName(warning.material || "");
  const matches = (draft.materials || []).filter(item => {
    const current = canonicalMaterialName(item.name || "");
    return current === target || current.includes(target) || target.includes(current);
  });

  if (!matches.length) return;

  matches[0].quantity = Number(warning.suggested_quantity || 1);
  for (let i = 1; i < matches.length; i++) matches[i].quantity = 0;
  draft.materials = (draft.materials || []).filter(item => Number(item.quantity || 0) > 0);
  draft.quote_health.quantity_warnings = (draft.quote_health.quantity_warnings || []).filter(x => x.id !== warningId);
  draft.quote_health.checks_passed = draft.quote_health.checks_passed || [];
  draft.quote_health.checks_passed.push(`${warning.material} quantity changed to ${warning.suggested_quantity}.`);
  draft.quote_health.score = Math.min(100, Number(draft.quote_health.score || 0) + 6);

  renderAIQuoteDraft({draft});
  showNotice(`${warning.material} quantity changed to ${warning.suggested_quantity}.`);
}

function keepCurrentQuantity(warningId) {
  const draft = LAST_AI_QUOTE_DRAFT;
  if (!draft || !draft.quote_health) return;
  const warning = (draft.quote_health.quantity_warnings || []).find(x => x.id === warningId);
  draft.quote_health.quantity_warnings = (draft.quote_health.quantity_warnings || []).filter(x => x.id !== warningId);
  if (warning) {
    draft.quote_health.checks_passed = draft.quote_health.checks_passed || [];
    draft.quote_health.checks_passed.push(`${warning.material} quantity reviewed and kept.`);
  }
  renderAIQuoteDraft({draft});
  showNotice("Current quantity kept for this draft.");
}



function bundleMaterialIdentity(name) {
  const raw = String(name || "").toLowerCase();
  const sizes = [...raw.matchAll(/\b(\d{1,3})\s*mm\b/g)]
    .map(match => Number(match[1]))
    .sort((a, b) => a - b);
  const sizeKey = sizes.length ? sizes.join("x") : "";

  if (/\bcopper\b/.test(raw) && /\b(pipe|tube)\b/.test(raw)) {
    return `copper-pipe:${sizeKey || "unknown"}`;
  }
  if (/\bplastic\b/.test(raw) && /\b(pipe|tube)\b/.test(raw)) {
    return `plastic-pipe:${sizeKey || "unknown"}`;
  }
  if (/\bend[\s-]?feed\b/.test(raw) && /\belbow\b|\bbend\b/.test(raw)) {
    return `endfeed-elbow:${sizeKey || "unknown"}`;
  }
  if (/\bend[\s-]?feed\b/.test(raw) && /\btee\b/.test(raw)) {
    return `endfeed-tee:${sizeKey || "unknown"}`;
  }
  if (/\bcoupler\b|\bcoupling\b/.test(raw)) {
    return `coupler:${sizeKey || "unknown"}`;
  }
  return `canonical:${canonicalMaterialName(name || "")}`;
}

function materialValuesScore(material) {
  let score = 0;
  if (String(material?.url || "").trim()) score += 8;
  if (Number(material?.manual_price || material?.live_price || 0) > 0) score += 6;
  if (String(material?.supplier || "").trim()) score += 2;
  if (String(material?.source || "").includes("live")) score += 2;
  return score;
}

function mergePreferredMaterialValues(target, incoming) {
  const targetScore = materialValuesScore(target);
  const incomingScore = materialValuesScore(incoming);

  // Keep the more useful product identity where one row has URL/price data.
  if (incomingScore > targetScore) {
    if (incoming.name) target.name = incoming.name;
    if (incoming.supplier) target.supplier = incoming.supplier;
    if (incoming.url) target.url = incoming.url;
    if (Number(incoming.manual_price || incoming.live_price || 0) > 0) {
      target.manual_price = Number(incoming.manual_price || incoming.live_price || 0);
    }
    if (incoming.source) target.source = incoming.source;
    if (incoming.price_source) target.price_source = incoming.price_source;
    if (incoming.sku) target.sku = incoming.sku;
    if (incoming.image_url) target.image_url = incoming.image_url;
    if (incoming.checked_at) target.checked_at = incoming.checked_at;
  } else {
    if (!target.supplier && incoming.supplier) target.supplier = incoming.supplier;
    if (!target.url && incoming.url) target.url = incoming.url;
    if (!Number(target.manual_price || 0) && Number(incoming.manual_price || incoming.live_price || 0) > 0) {
      target.manual_price = Number(incoming.manual_price || incoming.live_price || 0);
    }
  }

  target.required = Boolean(target.required || incoming.required);
  target.display_status = target.required ? "required" : (target.display_status || incoming.display_status || "optional");
  target.material_confidence = Math.max(
    Number(target.material_confidence || 0),
    Number(incoming.material_confidence || 0)
  );
  return target;
}

function findMaterialRowByCanonicalName(materialName) {
  const targetIdentity = bundleMaterialIdentity(materialName || "");
  return [...document.querySelectorAll("#materials .material-row")].find(row => {
    const existingName = row.querySelector(".m-name")?.value || "";
    return bundleMaterialIdentity(existingName) === targetIdentity;
  }) || null;
}

function mergeBundleMaterialIntoDraft(draft, item) {
  draft.materials = draft.materials || [];
  const targetIdentity = bundleMaterialIdentity(item.name || "");
  let existing = draft.materials.find(material =>
    bundleMaterialIdentity(material.name || "") === targetIdentity
  );

  const incomingQty = Number(item.quantity || 1);
  if (existing) {
    existing.quantity = Math.max(Number(existing.quantity || 0), incomingQty);
    mergePreferredMaterialValues(existing, {
      ...item,
      required: !item.optional,
      display_status: item.optional ? "optional" : "required",
      material_confidence: Number(item.confidence || 75),
      manual_price: Number(item.manual_price || item.live_price || item.price || 0)
    });
    return {material: existing, created: false};
  }

  existing = {
    name: item.name || "",
    quantity: incomingQty,
    supplier: item.supplier || "City Plumbing",
    url: item.url || "",
    manual_price: Number(item.manual_price || item.live_price || item.price || 0),
    required: !item.optional,
    display_status: item.optional ? "optional" : "required",
    data_source: "v15_1_job_bundle",
    material_confidence: Number(item.confidence || 75),
    reason: item.reason || "",
    source: item.source || "",
    price_source: item.price_source || "",
    sku: item.sku || "",
    image_url: item.image_url || "",
    checked_at: item.checked_at || ""
  };
  draft.materials.push(existing);
  return {material: existing, created: true};
}

function mergeBundleMaterialIntoForm(material) {
  const row = findMaterialRowByCanonicalName(material.name || "");
  const incomingQty = Number(material.quantity || 1);

  if (row) {
    const qtyInput = row.querySelector(".m-qty");
    const currentQty = Number(qtyInput?.value || 0);
    if (qtyInput) qtyInput.value = Math.max(currentQty, incomingQty);

    const supplier = row.querySelector(".m-supplier");
    const url = row.querySelector(".m-url");
    const manual = row.querySelector(".m-manual");

    if (supplier && material.supplier) supplier.value = material.supplier;
    if (url && !url.value && material.url) url.value = material.url;
    if (manual && !Number(manual.value || 0) && Number(material.manual_price || 0)) {
      manual.value = Number(material.manual_price || 0);
    }
    updateMaterialLiveBadge(row);
    return false;
  }

  addMaterial({
    name: material.name || "",
    quantity: incomingQty,
    supplier: material.supplier || "City Plumbing",
    url: material.url || "",
    manual_price: Number(material.manual_price || material.live_price || 0),
    source: material.source || "v15_1_job_bundle",
    price_source: material.price_source || "",
    sku: material.sku || "",
    image_url: material.image_url || "",
    checked_at: material.checked_at || "",
    quantity_source: "bundle"
  });
  return true;
}


function mergeDuplicateMaterialRowsInForm() {
  const rows = [...document.querySelectorAll("#materials .material-row")];
  const kept = new Map();

  rows.forEach(row => {
    const name = row.querySelector(".m-name")?.value || "";
    const identity = bundleMaterialIdentity(name);
    if (!identity) return;

    const existingRow = kept.get(identity);
    if (!existingRow) {
      kept.set(identity, row);
      return;
    }

    const currentMaterial = {
      name: existingRow.querySelector(".m-name")?.value || "",
      quantity: Number(existingRow.querySelector(".m-qty")?.value || 0),
      supplier: existingRow.querySelector(".m-supplier")?.value || "",
      url: existingRow.querySelector(".m-url")?.value || "",
      manual_price: Number(existingRow.querySelector(".m-manual")?.value || 0),
    };
    const incomingMaterial = {
      name: row.querySelector(".m-name")?.value || "",
      quantity: Number(row.querySelector(".m-qty")?.value || 0),
      supplier: row.querySelector(".m-supplier")?.value || "",
      url: row.querySelector(".m-url")?.value || "",
      manual_price: Number(row.querySelector(".m-manual")?.value || 0),
    };

    const preferred = mergePreferredMaterialValues(currentMaterial, incomingMaterial);
    existingRow.querySelector(".m-name").value = preferred.name || currentMaterial.name;
    existingRow.querySelector(".m-qty").value = Math.max(
      Number(currentMaterial.quantity || 0),
      Number(incomingMaterial.quantity || 0)
    );
    existingRow.querySelector(".m-supplier").value = preferred.supplier || "City Plumbing";
    existingRow.querySelector(".m-url").value = preferred.url || "";
    existingRow.querySelector(".m-manual").value = Number(preferred.manual_price || 0) || "";
    row.remove();
    updateMaterialLiveBadge(existingRow);
  });
}


let LIVE_QUOTE_REFRESH_TIMER = null;
let LIVE_QUOTE_REFRESH_RUNNING = false;
let LIVE_QUOTE_REFRESH_PENDING = false;

function quotePreviewIsActive() {
  const result = document.getElementById("result");
  return Boolean(
    CURRENT_QUOTE_ID &&
    result &&
    result.innerHTML.trim() &&
    !result.querySelector(".live-refresh-placeholder")
  );
}

function setLiveRefreshStatus(message, state = "working") {
  let box = document.getElementById("liveQuoteRefreshStatus");
  const result = document.getElementById("result");
  if (!result) return;

  if (!box) {
    box = document.createElement("div");
    box.id = "liveQuoteRefreshStatus";
    box.style.cssText = "margin:8px 0;padding:9px 11px;border-radius:10px;font-weight:700;font-size:13px;";
    result.prepend(box);
  }

  const colours = {
    working: ["#eff6ff", "#1d4ed8", "#93c5fd"],
    saved: ["#f0fdf4", "#166534", "#86efac"],
    waiting: ["#fffbeb", "#92400e", "#fcd34d"],
    error: ["#fef2f2", "#991b1b", "#fca5a5"]
  };
  const selected = colours[state] || colours.working;
  box.style.background = selected[0];
  box.style.color = selected[1];
  box.style.border = `1px solid ${selected[2]}`;
  box.textContent = message;
}

function scheduleLiveQuoteRefresh(reason = "Quote details changed") {
  clearTimeout(LIVE_QUOTE_REFRESH_TIMER);

  if (!CURRENT_QUOTE_ID) {
    // A draft has not yet been saved. The editable form still updates immediately.
    return;
  }

  const result = document.getElementById("result");
  if (!result || !result.innerHTML.trim()) return;

  setLiveRefreshStatus(`${reason}. Updating totals…`, "waiting");

  LIVE_QUOTE_REFRESH_TIMER = setTimeout(async () => {
    if (LIVE_QUOTE_REFRESH_RUNNING) {
      LIVE_QUOTE_REFRESH_PENDING = true;
      return;
    }

    LIVE_QUOTE_REFRESH_RUNNING = true;
    setLiveRefreshStatus("Updating quote totals and saved preview…", "working");

    try {
      await generateQuote({
        silent: true,
        autoRefresh: true,
        skipDashboardReload: true
      });
      setLiveRefreshStatus("✓ Quote totals and preview updated automatically.", "saved");
    } catch (error) {
      console.error("Live quote refresh failed", error);
      setLiveRefreshStatus("Automatic refresh failed. Use Update Quote to try again.", "error");
    } finally {
      LIVE_QUOTE_REFRESH_RUNNING = false;
      if (LIVE_QUOTE_REFRESH_PENDING) {
        LIVE_QUOTE_REFRESH_PENDING = false;
        scheduleLiveQuoteRefresh("Further changes detected");
      }
    }
  }, 850);
}

function installLiveQuoteRefreshListeners() {
  const watchedIds = new Set([
    "labour",
    "include_callout_charge",
    "callout_charge",
    "include_travel_charge",
    "travel_charge",
    "include_materials_handling",
    "materials_handling_percent",
    "deposit_percent",
    "job",
    "quote_type",
    "tiling",
    "wall_tiling_m2",
    "floor_tiling_m2",
    "wall_height",
    "customer_supplies_tiles"
  ]);

  document.addEventListener("input", event => {
    const target = event.target;
    if (!target) return;

    if (
      target.closest?.("#materials") &&
      target.matches?.(".m-name, .m-qty, .m-url, .m-manual")
    ) {
      scheduleLiveQuoteRefresh("Material changed");
      return;
    }

    if (watchedIds.has(target.id)) {
      scheduleLiveQuoteRefresh("Quote detail changed");
    }
  });

  document.addEventListener("change", event => {
    const target = event.target;
    if (!target) return;

    if (
      target.closest?.("#materials") &&
      target.matches?.(".m-supplier, .m-qty, .m-manual")
    ) {
      scheduleLiveQuoteRefresh("Material changed");
      return;
    }

    if (watchedIds.has(target.id)) {
      scheduleLiveQuoteRefresh("Quote detail changed");
    }
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", installLiveQuoteRefreshListeners);
} else {
  installLiveQuoteRefreshListeners();
}

function refreshAfterBundleChange() {
  mergeDuplicateMaterialRowsInForm();
  scheduleQuoteLearning();
  scheduleLabourIntelligence();
  updateForgottenItemWarnings();
  updateSupplierPreferenceNotes();
  scheduleLiveQuoteRefresh("Materials changed");
}

function addV151JobBundle(bundleIndex, essentialOnly = false) {
  const draft = LAST_AI_QUOTE_DRAFT;
  if (!draft || !draft.quote_health) {
    alert("Generate the AI quote draft first.");
    return;
  }

  const bundles = draft.quote_health.job_specific_bundles || [];
  const bundle = bundles[Number(bundleIndex)];
  if (!bundle) {
    alert("This bundle could not be found. Generate the draft again.");
    return;
  }

  let addedToDraft = 0;
  let addedToForm = 0;
  let merged = 0;
  const includedNames = [];

  (bundle.items || []).forEach(item => {
    if (essentialOnly && item.optional) return;

    const result = mergeBundleMaterialIntoDraft(draft, item);
    if (result.created) addedToDraft += 1;
    else merged += 1;

    if (mergeBundleMaterialIntoForm(result.material)) addedToForm += 1;
    result.material.include_in_quote = true;
    if (item.optional) result.material.optional_selected = true;
    item.already_in_quote = true;
    includedNames.push(item.name || "Material");
  });

  // Merge any duplicates already present in the draft.
  const combined = [];
  (draft.materials || []).forEach(material => {
    const identity = bundleMaterialIdentity(material.name || "");
    const existing = combined.find(item =>
      bundleMaterialIdentity(item.name || "") === identity
    );
    if (!existing) {
      combined.push({...material});
      return;
    }

    // Do not double the same bundle requirement. Keep the highest required
    // quantity and the row with the most useful URL/price information.
    existing.quantity = Math.max(
      Number(existing.quantity || 0),
      Number(material.quantity || 0)
    );
    mergePreferredMaterialValues(existing, material);
  });
  draft.materials = combined;

  draft.quote_health.checks_passed = draft.quote_health.checks_passed || [];
  if (includedNames.length) {
    draft.quote_health.checks_passed.push(
      `${bundle.display_name || "Bundle"} reviewed: ${includedNames.join(", ")}.`
    );
  }

  LAST_AI_QUOTE_DRAFT = draft;
  (draft.quote_health?.job_specific_bundles || []).forEach(bundle => {
    if (!bundle.health) return;
    const missingEssentials = (bundle.items || []).filter(item => !item.optional && !item.already_in_quote);
    bundle.health.missing_essential_count = missingEssentials.length;
    bundle.health.ready_to_apply = missingEssentials.length === 0;
    if (missingEssentials.length === 0 && bundle.health.score < 90) {
      bundle.health.score = Math.max(90, Number(bundle.health.score || 0));
      bundle.health.status = "healthy";
      bundle.health.label = "Healthy";
    }
  });
  refreshAfterBundleChange();
  renderAIQuoteDraft({draft});

  const mode = essentialOnly ? "essential material" : "bundle material";
  if (!includedNames.length) {
    showNotice("These bundle materials are already present.");
  } else {
    showNotice(
      `${includedNames.length} ${mode}(s) added or merged. The editable Materials section has been updated.`
    );
  }

  // Move the user to the editable material rows on mobile.
  document.getElementById("materials")?.scrollIntoView({behavior: "smooth", block: "start"});
}


let LIVE_PRODUCT_SEARCHES = {};
let LIVE_PRODUCT_RESULTS = {};


function numberFromWordsOrDigits(text, itemPattern) {
  const source = String(text || "").toLowerCase();
  const words = {
    one: 1, two: 2, three: 3, four: 4, five: 5,
    six: 6, seven: 7, eight: 8, nine: 9, ten: 10,
    eleven: 11, twelve: 12
  };
  const pattern = new RegExp(
    `\\b(\\d+(?:\\.\\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\\b[^.\\n]{0,35}${itemPattern}`,
    "i"
  );
  const match = source.match(pattern);
  if (!match) return 0;
  return words[match[1]] || Number(match[1] || 0);
}

function metresFromText(text) {
  const source = String(text || "").toLowerCase();
  const match = source.match(/\b(?:approximately|approx\.?|about|around)?\s*(\d+(?:\.\d+)?)\s*(?:m|metre|metres|meter|meters)\b/i);
  return match ? Number(match[1] || 0) : 0;
}

function upsertDraftMaterial(draft, material) {
  draft.materials = draft.materials || [];
  const incoming = canonicalMaterialName(material.name || "");
  const existing = draft.materials.find(item => {
    const current = canonicalMaterialName(item.name || "");
    return current === incoming ||
      (incoming && current && (current.includes(incoming) || incoming.includes(current)));
  });

  if (existing) {
    existing.quantity = Math.max(Number(existing.quantity || 0), Number(material.quantity || 0));
    existing.required = Boolean(existing.required || material.required);
    existing.display_status = existing.required ? "required" : (material.display_status || existing.display_status);
    existing.status = existing.required ? "required" : (material.status || existing.status);
    existing.reason = material.reason || existing.reason || "";
    existing.material_confidence = Math.max(
      Number(existing.material_confidence || 0),
      Number(material.material_confidence || 0)
    );
    return existing;
  }

  draft.materials.push(material);
  return material;
}

function mergeExplicitSurveyMaterialsIntoDraft(draft) {
  draft.materials = draft.materials || [];

  const jobText = [
    document.getElementById("job")?.value || "",
    draft.scope_of_work || "",
    CURRENT_SITE_SURVEY?.summary || "",
    CURRENT_SITE_SURVEY?.proposed_job_description || "",
    CURRENT_SITE_SURVEY?.site_visit_addition || "",
    CURRENT_SITE_SURVEY?.transcript || ""
  ].join("\n");

  const actions = CURRENT_SITE_SURVEY?.material_actions || [];
  const explicitRequiredText = actions
    .filter(action => action.action === "include_required")
    .map(action => `${action.material_name || ""}. ${action.reason || ""}`)
    .join("\n");

  const combined = `${jobText}\n${explicitRequiredText}`;
  const lower = combined.toLowerCase();

  // Copper pipe: convert stated total metres into purchasable 3m lengths.
  if (/\bcopper\b[^.\n]{0,50}\bpipe(work)?\b|\bpipe(work)?\b[^.\n]{0,50}\bcopper\b/i.test(combined)) {
    const metres = metresFromText(combined);
    if (metres > 0) {
      const lengths = Math.max(1, Math.ceil(metres / 3));
      upsertDraftMaterial(draft, {
        name: "15mm Copper Pipe 3m",
        quantity: lengths,
        supplier: "City Plumbing",
        url: "",
        manual_price: 0,
        required: true,
        display_status: "required",
        status: "required",
        source: "explicit_site_survey",
        data_source: "explicit_site_survey",
        material_confidence: 98,
        reason: `${metres} metres of 15mm copper pipe was explicitly stated; ${lengths} × 3m lengths required before wastage review.`
      });
    }
  }

  // Explicit elbows.
  const elbowQty = numberFromWordsOrDigits(combined, "(?:15\\s*mm\\s*)?(?:end[- ]?feed\\s*)?elbows?");
  if (elbowQty > 0) {
    upsertDraftMaterial(draft, {
      name: "15mm Endfeed Elbow",
      quantity: elbowQty,
      supplier: "City Plumbing",
      url: "",
      manual_price: 0,
      required: true,
      display_status: "required",
      status: "required",
      source: "explicit_site_survey",
      data_source: "explicit_site_survey",
      material_confidence: 99,
      reason: `${elbowQty} elbow fitting(s) were explicitly stated in the job description or site survey.`
    });
  }

  // Explicit tees. If a count is not stated, retain as a site-check item rather than omitting it.
  const teeMentioned = /\b(?:22\s*mm\s*)?(?:end[- ]?feed\s*)?tees?\b/i.test(combined);
  const teeQty = numberFromWordsOrDigits(combined, "(?:22\\s*mm\\s*)?(?:end[- ]?feed\\s*)?tees?");
  if (teeMentioned) {
    upsertDraftMaterial(draft, {
      name: /22\s*mm/i.test(combined) && /15\s*mm\s*(?:branch|reduc)/i.test(combined)
        ? "22mm x 15mm Endfeed Reducing Tee"
        : "Endfeed Tee",
      quantity: teeQty > 0 ? teeQty : 1,
      supplier: "City Plumbing",
      url: "",
      manual_price: 0,
      required: teeQty > 0,
      display_status: teeQty > 0 ? "required" : "site_check",
      status: teeQty > 0 ? "required" : "site_check",
      source: "explicit_site_survey",
      data_source: "explicit_site_survey",
      material_confidence: teeQty > 0 ? 99 : 70,
      reason: teeQty > 0
        ? `${teeQty} tee fitting(s) were explicitly stated.`
        : "Tee fittings were explicitly mentioned, but the quantity was not stated. Confirm before ordering."
    });
  }

  // Explicit radiator valve arrangement.
  const asksTrv = /\btrv\b|thermostatic radiator valve/i.test(combined);
  const asksLockshield = /\blockshield\b/i.test(combined);
  const asksValveSet = /\bradiator valve set\b/i.test(combined) || (asksTrv && asksLockshield);

  if (asksValveSet) {
    upsertDraftMaterial(draft, {
      name: "Radiator Valve Set",
      quantity: 1,
      supplier: "Screwfix",
      url: "",
      manual_price: 0,
      required: true,
      display_status: "required",
      status: "required",
      source: "explicit_site_survey",
      data_source: "explicit_site_survey",
      material_confidence: 99,
      reason: "A TRV and lockshield arrangement was explicitly specified."
    });
  }

  // Inhibitor is required where the description explicitly says refill with inhibitor.
  if (/\binhibitor\b/i.test(combined)) {
    upsertDraftMaterial(draft, {
      name: "Inhibitor 1L",
      quantity: 1,
      supplier: "Toolstation",
      url: "",
      manual_price: 0,
      required: true,
      display_status: "required",
      status: "required",
      source: "explicit_site_survey",
      data_source: "explicit_site_survey",
      material_confidence: 95,
      reason: "Inhibitor was explicitly included in the works."
    });
  }

  return draft;
}

function prepareDraftForV125(draft) {
  draft.materials = draft.materials || [];
  draft = mergeExplicitSurveyMaterialsIntoDraft(draft);
  const scope = String(draft.scope_of_work || document.getElementById("job")?.value || "").toLowerCase();
  const names = draft.materials.map(item => String(item.name || "").toLowerCase());

  // Remove duplicate radiator valve entries. A complete valve set already contains
  // one operating valve/TRV and one lockshield, so separate generic duplicates are removed.
  const hasValveSet = names.some(name => name.includes("radiator valve set"));
  const radiatorMentions = [...scope.matchAll(/\b(?:install|replace|fit|supply)\b[^.\n]{0,80}\bradiator\b/g)].length;
  const likelyRadiatorCount = Math.max(1, radiatorMentions || 1);

  if (hasValveSet) {
    let keptSet = false;
    draft.materials = draft.materials.filter(item => {
      const name = String(item.name || "").toLowerCase().trim();
      if (name.includes("radiator valve set")) {
        if (keptSet) return false;
        keptSet = true;
        item.quantity = Math.min(Number(item.quantity || 1), likelyRadiatorCount);
        return true;
      }
      if (
        name === "trv valve" ||
        name === "thermostatic radiator valve" ||
        name === "lockshield valve" ||
        name === "radiator valve"
      ) return false;
      return true;
    });
  } else {
    // If separate TRV and lockshield are used, allow one of each per radiator only.
    draft.materials.forEach(item => {
      const name = String(item.name || "").toLowerCase().trim();
      if (
        name === "trv valve" ||
        name === "thermostatic radiator valve" ||
        name === "lockshield valve"
      ) {
        item.quantity = Math.min(Number(item.quantity || 1), likelyRadiatorCount);
      }
    });
  }

  // Concealed/new copper routes need fittings, but exact elbows/couplers must not be invented.
  const routeNeedsFittings = /(copper|pipework|flow and return)/.test(scope) && /(metre|meter|route|floorboard|carpet|concealed)/.test(scope);
  const hasFittings = draft.materials.some(item => /elbow|coupler|tee|fittings allowance/i.test(String(item.name || "")));
  if (routeNeedsFittings && !hasFittings) {
    draft.materials.push({
      name: "15mm copper fittings allowance",
      quantity: 1,
      supplier: "City Plumbing",
      url: "",
      manual_price: 0,
      required: false,
      display_status: "site_check",
      status: "site_check",
      source: "v12.5_provisional_allowance",
      material_confidence: 55,
      reason: "Provisional allowance only. Confirm elbow, tee and coupler quantities after the route is exposed or clearly stated."
    });
  }
  draft = enrichDraftMaterialsFromSavedDatabase(draft);
  return draft;
}

function liveProductQueriesFromDraft(draft) {
  const searches = [];
  const existing = (draft.materials || []).map(item => String(item.name || "").toLowerCase());
  const surveyActions = CURRENT_SITE_SURVEY?.material_actions || [];
  const scope = String(draft.scope_of_work || document.getElementById("job")?.value || "").toLowerCase();

  const addSearch = (query, label, reason, productType = "general") => {
    if (!query || searches.some(item => item.query.toLowerCase() === query.toLowerCase())) return;
    searches.push({query, label, reason, productType, requiresChoice: productType === "radiator"});
  };

  surveyActions.forEach(action => {
    if (action.action !== "include_required") return;
    const name = String(action.material_name || "").trim();
    const lower = name.toLowerCase();
    if (/radiator/.test(lower) && !/valve|pipework|connection/.test(lower)) {
      addSearch(name, name, action.reason || "Required by the site survey.", "radiator");
    }
  });

  const radiatorMatch = scope.match(/(\d{3,4})\s*[x×]\s*(\d{3,4})\s*mm?\s*radiator/i);
  if (radiatorMatch && !existing.some(name => name.includes("radiator") && !name.includes("valve"))) {
    addSearch(
      `${radiatorMatch[1]} x ${radiatorMatch[2]}mm white central heating panel radiator`,
      `${radiatorMatch[1]} × ${radiatorMatch[2]} mm radiator`,
      "The quote requires a radiator, but no priced radiator product is in the material list.",
      "radiator"
    );
  }

  // Search for required main valve products that still have no product link.
  (draft.materials || []).forEach(material => {
    const name = String(material.name || "").trim();
    const lower = name.toLowerCase();
    const required = (material.status || material.display_status || (material.required ? "required" : "optional")) === "required";
    if (!required || material.url) return;
    if (lower.includes("radiator valve set")) addSearch("angled thermostatic radiator valve and lockshield set 15mm", name, "Required valve set has no product link.", "radiator_valve_set");
    else if (lower.includes("trv")) addSearch("angled thermostatic radiator valve TRV 15mm", name, "Required TRV has no product link.", "trv");
    else if (lower.includes("lockshield")) addSearch("angled lockshield radiator valve 15mm", name, "Required lockshield has no product link.", "lockshield");
  });

  return searches.slice(0, 6);
}

function liveProductFinderHtml(draft) {
  const searches = liveProductQueriesFromDraft(draft);
  LIVE_PRODUCT_SEARCHES = Object.fromEntries(searches.map((item, index) => [String(index), item]));
  if (!searches.length) return "";

  return `
    <div style="margin-top:10px;padding:10px;border:2px solid #0284c7;border-radius:10px;background:#f0f9ff;">
      <strong>Live merchant product finder</strong><br>
      <span class="small">V13 matches every material against your saved database first, ignoring brand names, word order and common filler words. Saved URLs and cached prices are inherited automatically before a blank material is created. For radiators, you must choose the type before searching. A confirmed product is added directly to the Materials list with its supplier, current price and product URL.</span>
      ${searches.map((item, index) => `
        <div style="margin-top:9px;padding:9px;border:1px solid #bae6fd;border-radius:9px;background:white;">
          <strong>${escapeHtml(item.label)}</strong><br>
          <span class="small">${escapeHtml(item.reason)}</span>
          ${item.productType === "radiator" ? `
            <label class="small" style="display:block;margin-top:9px;font-weight:700;">Choose radiator type before searching</label>
            <select id="radiatorType-${index}" onchange="updateRadiatorSearchButton('${index}')">
              <option value="">— Select radiator type —</option>
              <optgroup label="Standard panel radiators">
                <option value="type 11 panel radiator">Type 11 — single panel, single convector</option>
                <option value="type 21 panel radiator">Type 21 — double panel, single convector</option>
                <option value="type 22 panel radiator">Type 22 — double panel, double convector</option>
              </optgroup>
              <optgroup label="Other radiator styles">
                <option value="towel radiator">Towel radiator</option>
                <option value="vertical radiator">Vertical radiator</option>
                <option value="designer radiator">Designer radiator</option>
                <option value="column radiator">Column radiator</option>
              </optgroup>
              <optgroup label="Existing or customer choice">
                <option value="like for like radiator">Like for like / match existing</option>
                <option value="customer selected radiator">Customer-selected product</option>
              </optgroup>
            </select>
            <div id="radiatorChoiceNote-${index}" class="small" style="margin-top:5px;color:#92400e;">
              The app will not choose Type 11, 21 or 22 automatically.
            </div>` : ""}
          <div class="history-actions" style="grid-template-columns:1fr;margin-top:7px;">
            <button type="button" id="liveSearchButton-${index}" class="btn-green" ${item.productType === "radiator" ? "disabled" : ""} onclick="searchLiveMerchantProduct('${index}')">Find matching products</button>
          </div>
          <div id="liveProductResults-${index}" style="margin-top:7px;"></div>
        </div>
      `).join("")}
      <div class="small" style="margin-top:8px;">Prices and availability can change. Open the merchant page and confirm before ordering.</div>
    </div>`;
}


function updateRadiatorSearchButton(searchId) {
  const select = document.getElementById(`radiatorType-${searchId}`);
  const button = document.getElementById(`liveSearchButton-${searchId}`);
  const note = document.getElementById(`radiatorChoiceNote-${searchId}`);
  if (!select || !button) return;

  const value = String(select.value || "").trim();
  button.disabled = !value;

  if (!note) return;
  if (!value) {
    note.textContent = "The app will not choose Type 11, 21 or 22 automatically.";
  } else if (value === "like for like radiator") {
    note.textContent = "The search will look for a matching radiator, but the existing type and depth still need confirming.";
  } else if (value === "customer selected radiator") {
    note.textContent = "No merchant product will be assumed. Choose the customer’s exact product or paste its URL.";
  } else {
    note.textContent = `Search locked to: ${select.options[select.selectedIndex].text}.`;
  }
}

async function searchLiveMerchantProduct(searchId) {
  const search = LIVE_PRODUCT_SEARCHES[String(searchId)];
  const box = document.getElementById(`liveProductResults-${searchId}`);
  if (!search || !box) return;
  box.innerHTML = "Searching City Plumbing, Screwfix, Toolstation and Selco…";

  try {
    const typeSelect = document.getElementById(`radiatorType-${searchId}`);
    const selectedType = String(typeSelect?.value || "").trim();

    if (search.productType === "radiator" && !selectedType) {
      box.innerHTML = `<div class="notice" style="border-color:#d97706;">Choose the radiator type first. No type has been assumed.</div>`;
      return;
    }

    if (selectedType === "customer selected radiator") {
      box.innerHTML = `
        <div class="notice">
          Customer-selected radiator: open the customer’s product, then add its exact product URL, supplier and price to the Materials list.
          The app will not substitute a different radiator automatically.
        </div>`;
      return;
    }

    const refinedQuery = [search.query, selectedType].filter(Boolean).join(" ");
    const response = await fetch("/api/live-product-search?q=" + encodeURIComponent(refinedQuery));
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Merchant search failed.");
    const results = data.results || [];
    LIVE_PRODUCT_RESULTS[String(searchId)] = results;

    if (!results.length) {
      box.innerHTML = `<div class="notice">No merchant matches were found. Try a more specific product description.</div>`;
      return;
    }

    box.innerHTML = results.map((item, resultIndex) => `
      <div style="margin-top:7px;padding:9px;border:1px solid #ddd;border-radius:9px;background:#fff;">
        <strong>${escapeHtml(item.name || "")}</strong><br>
        <span class="small">
          ${escapeHtml(item.supplier || "")}
          ${item.live_price ? ` · <strong>${pounds(item.live_price)}</strong>` : " · price unavailable"}
          ${item.availability ? ` · ${escapeHtml(item.availability)}` : ""}
          ${item.sku ? ` · SKU ${escapeHtml(item.sku)}` : ""}
          ${item.search_only ? "" : ` · ${Number(item.match_score || 0)}% strict match`}
        </span>
        ${item.image_url ? `<img src="${escapeHtml(item.image_url)}" alt="" loading="lazy" style="display:block;max-width:110px;max-height:90px;object-fit:contain;margin-top:7px;border-radius:6px;">` : ""}
        <div class="history-actions" style="grid-template-columns:1fr 1fr;gap:7px;margin-top:7px;">
          <button type="button" class="btn-light" onclick='window.open(${JSON.stringify(item.url || "")}, "_blank", "noopener")'>
            ${item.search_only ? "Open merchant search" : "View product"}
          </button>
          ${item.search_only ? "" : `<button type="button" class="btn-green" onclick="addLiveMerchantProduct('${searchId}', ${resultIndex})">Add to quote</button>`}
        </div>
      </div>
    `).join("");
  } catch (error) {
    box.innerHTML = `<div class="notice" style="border-color:#dc2626;">${escapeHtml(error.message || "Merchant search failed.")}</div>`;
  }
}

function findExistingMaterialRowByUrlOrName(url, name) {
  const cleanUrl = String(url || "").split("?")[0].replace(/\/+$/, "").toLowerCase();
  const canonical = canonicalMaterialName(name || "");
  return [...document.querySelectorAll("#materials .material-row")].find(row => {
    const rowUrl = String(row.querySelector(".m-url")?.value || "").split("?")[0].replace(/\/+$/, "").toLowerCase();
    const rowName = canonicalMaterialName(row.querySelector(".m-name")?.value || "");
    return (cleanUrl && rowUrl === cleanUrl) || (canonical && rowName === canonical);
  });
}

function addLiveMerchantProduct(searchId, resultIndex) {
  const item = LIVE_PRODUCT_RESULTS[String(searchId)]?.[Number(resultIndex)];
  if (!item || !LAST_AI_QUOTE_DRAFT) return;

  const productUrl = String(item.url || "").trim();
  if (!/^https?:\/\//i.test(productUrl) || item.search_only) {
    showNotice("Open the merchant result and choose a confirmed product page before adding it.");
    return;
  }

  const product = {
    name: item.name || "",
    quantity: 1,
    supplier: item.supplier || "City Plumbing",
    url: productUrl,
    manual_price: Number(item.live_price || item.default_price || 0),
    live_price: Number(item.live_price || item.default_price || 0),
    status: "required",
    source: "live_merchant_search",
    price_source: item.price_source || "live",
    image_url: item.image_url || "",
    sku: item.sku || "",
    checked_at: item.checked_at || new Date().toISOString()
  };

  LAST_AI_QUOTE_DRAFT.materials = LAST_AI_QUOTE_DRAFT.materials || [];
  const canonical = canonicalMaterialName(product.name);
  const existingDraftIndex = LAST_AI_QUOTE_DRAFT.materials.findIndex(existing => {
    const existingUrl = String(existing.url || "").split("?")[0].replace(/\/+$/, "").toLowerCase();
    const incomingUrl = product.url.split("?")[0].replace(/\/+$/, "").toLowerCase();
    return (existingUrl && existingUrl === incomingUrl) ||
           canonicalMaterialName(existing.name || "") === canonical;
  });

  if (existingDraftIndex >= 0) {
    LAST_AI_QUOTE_DRAFT.materials[existingDraftIndex] = {
      ...LAST_AI_QUOTE_DRAFT.materials[existingDraftIndex],
      ...product
    };
  } else {
    LAST_AI_QUOTE_DRAFT.materials.unshift(product);
  }

  // Re-merge explicitly stated ancillary materials after selecting the main
  // merchant product. This prevents the radiator choice from becoming the
  // only material in the applied quote.
  LAST_AI_QUOTE_DRAFT = prepareDraftForV125(LAST_AI_QUOTE_DRAFT);

  const existingRow = findExistingMaterialRowByUrlOrName(product.url, product.name);
  if (existingRow) {
    existingRow.querySelector(".m-name").value = product.name;
    existingRow.querySelector(".m-qty").value = product.quantity;
    existingRow.querySelector(".m-supplier").value = product.supplier;
    existingRow.querySelector(".m-url").value = product.url;
    existingRow.querySelector(".m-manual").value = product.manual_price || "";
    existingRow.dataset.liveProduct = "1";
    existingRow.dataset.sku = product.sku || "";
    existingRow.dataset.imageUrl = product.image_url || "";
    existingRow.dataset.checkedAt = product.checked_at || "";
    updateMaterialLiveBadge(existingRow);
  } else {
    addMaterial(product);
  }

  renderAIQuoteDraft({draft: LAST_AI_QUOTE_DRAFT});
  showNotice(`${product.name} added to the materials list with supplier, price and product URL.`);
}



function isOptionalDraftMaterial(material) {
  const status = String(
    material?.display_status ||
    material?.status ||
    (material?.required ? "required" : "optional")
  ).toLowerCase();
  return !material?.required && status !== "required" && status !== "customer_supplied";
}

function optionalMaterialIsSelected(material) {
  if (!isOptionalDraftMaterial(material)) return true;
  return material?.include_in_quote === true || material?.optional_selected === true;
}

function removeMaterialRowByIdentity(materialName) {
  const identity = bundleMaterialIdentity(materialName || "");
  const row = [...document.querySelectorAll("#materials .material-row")].find(candidate =>
    bundleMaterialIdentity(candidate.querySelector(".m-name")?.value || "") === identity
  );
  if (row) row.remove();
}

function toggleOptionalDraftMaterial(materialIndex, forceValue = null) {
  const draft = LAST_AI_QUOTE_DRAFT;
  if (!draft || !Array.isArray(draft.materials)) return;

  const material = draft.materials[Number(materialIndex)];
  if (!material || !isOptionalDraftMaterial(material)) return;

  const selected = forceValue === null
    ? !optionalMaterialIsSelected(material)
    : Boolean(forceValue);

  material.include_in_quote = selected;
  material.optional_selected = selected;

  if (selected) {
    const enriched = enrichMaterialFromSavedDatabase({...material});
    Object.assign(material, enriched);
    mergeBundleMaterialIntoForm(material);
    mergeDuplicateMaterialRowsInForm();
    showNotice(`${material.name} added to the editable Materials list.`);
  } else {
    removeMaterialRowByIdentity(material.name || "");
    showNotice(`${material.name} removed from the editable Materials list.`);
  }

  LAST_AI_QUOTE_DRAFT = draft;
  refreshAfterBundleChange();
  renderAIQuoteDraft({draft});
}

function optionalMaterialControl(material, index) {
  if (!isOptionalDraftMaterial(material)) {
    return `<span style="display:inline-block;padding:4px 8px;border-radius:999px;background:#dcfce7;color:#166534;font-size:12px;font-weight:700;">Included</span>`;
  }

  const selected = optionalMaterialIsSelected(material);
  return `
    <label style="display:inline-flex;align-items:center;gap:6px;cursor:pointer;white-space:nowrap;">
      <input type="checkbox" ${selected ? "checked" : ""}
        onchange="toggleOptionalDraftMaterial(${index}, this.checked)"
        style="width:18px;height:18px;margin:0;">
      <span style="font-size:12px;font-weight:700;color:${selected ? "#166534" : "#374151"};">
        ${selected ? "Added" : "Add"}
      </span>
    </label>`;
}

function initialiseOptionalMaterialSelections(draft) {
  (draft?.materials || []).forEach(material => {
    if (!isOptionalDraftMaterial(material)) {
      material.include_in_quote = true;
      return;
    }
    if (typeof material.include_in_quote !== "boolean") {
      material.include_in_quote = false;
      material.optional_selected = false;
    }
  });
  return draft;
}


function bundleHealthColour(status) {
  if (status === "healthy") return {border:"#16a34a", background:"#f0fdf4", text:"#166534"};
  if (status === "incomplete") return {border:"#dc2626", background:"#fef2f2", text:"#991b1b"};
  return {border:"#d97706", background:"#fffbeb", text:"#92400e"};
}

function bundleHealthIssueIcon(severity) {
  if (severity === "high") return "✕";
  if (severity === "medium") return "△";
  if (severity === "low") return "•";
  return "ℹ";
}

function renderBundleHealth(bundle) {
  const health = bundle.health || {};
  const colours = bundleHealthColour(health.status || "review");
  const issues = health.issues || [];
  const checks = health.checks || [];

  return `
    <div style="margin-top:8px;padding:9px;border:1px solid ${colours.border};border-radius:9px;background:${colours.background};color:${colours.text};">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;">
        <div>
          <strong>Bundle health</strong><br>
          <span class="small">${escapeHtml(health.label || "Review recommended")}</span>
        </div>
        <strong style="font-size:22px;">${Number(health.score || 0)}%</strong>
      </div>
      ${issues.length ? `<div style="margin-top:7px;">${issues.map(issue => `
        <div style="margin-top:4px;">
          ${bundleHealthIssueIcon(issue.severity)} ${escapeHtml(issue.message || "")}
          ${(issue.items || []).length ? `<br><span class="small" style="display:inline-block;margin-left:14px;">${(issue.items || []).map(escapeHtml).join(", ")}</span>` : ""}
        </div>`).join("")}</div>` : ""}
      ${checks.length ? `<details style="margin-top:7px;"><summary style="cursor:pointer;font-weight:700;">Passed checks</summary><div class="small" style="margin-top:5px;">${checks.map(check => `✓ ${escapeHtml(check)}`).join("<br>")}</div></details>` : ""}
    </div>`;
}

function renderAIQuoteDraft(data) {
  const box = document.getElementById("aiQuoteResult");
  if (!box) return;

  const draft = initialiseOptionalMaterialSelections(
    prepareDraftForV125(data.draft || {})
  );
  LAST_AI_QUOTE_DRAFT = draft;
  const materials = draft.materials || [];
  const professional = draft.professional_quote || {};
  const confidence = professional.confidence || {};
  const quality = draft.quote_quality || {};
  const assumptions = professional.assumptions || [];
  const exclusions = professional.exclusions || [];
  const questions = professional.questions || [];
  const risks = professional.risk_notes || [];
  const technical = draft.technical_detail || {};
  const evidence = professional.material_evidence || [];
  const preview = draft.customer_preview || {};
  const health = draft.quote_health || {};
  const healthMissing = health.missing_items || [];
  const healthQuantities = health.quantity_warnings || [];
  const healthLabour = health.labour_warnings || [];
  const healthPassed = health.checks_passed || [];
  const jobBundles = health.job_specific_bundles || [];
  const surveySummary = draft.site_survey_summary || {};

  const statusBadge = (status) => {
    if (status === "required") return `<span style="display:inline-block;padding:2px 7px;border-radius:999px;background:#dcfce7;font-size:12px;">Required</span>`;
    if (status === "customer_supplied") return `<span style="display:inline-block;padding:2px 7px;border-radius:999px;background:#dbeafe;font-size:12px;">Customer supplied</span>`;
    if (status === "site_check") return `<span style="display:inline-block;padding:2px 7px;border-radius:999px;background:#fef3c7;font-size:12px;">Site check</span>`;
    return `<span style="display:inline-block;padding:2px 7px;border-radius:999px;background:#f3f4f6;font-size:12px;">Optional</span>`;
  };

  const stars = "★".repeat(Number(quality.stars || 0)) + "☆".repeat(Math.max(0, 5 - Number(quality.stars || 0)));

  box.innerHTML = `
    <div class="history-item" style="padding:10px;border-color:#7c3aed;">
      <div style="display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center;padding:12px;background:#f3f4f6;border-radius:10px;">
        <div>
          <strong style="font-size:18px;">Estimator dashboard, learning & fixes</strong><br>
          <span style="font-size:22px;letter-spacing:2px;">${stars}</span><br>
          <span class="small">Overall estimate quality ${Number(quality.overall || 0)}%</span>
        </div>
        <div style="text-align:center;min-width:90px;">
          <div style="font-size:30px;font-weight:800;">${Number(confidence.score || 0)}%</div>
          <div class="small">${escapeHtml(confidence.level || "unknown")} confidence</div>
        </div>
      </div>

      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin-top:8px;">
        <div style="padding:8px;border:1px solid #ddd;border-radius:8px;"><strong>${Number(quality.materials || 0)}%</strong><br><span class="small">Materials</span></div>
        <div style="padding:8px;border:1px solid #ddd;border-radius:8px;"><strong>${Number(quality.labour || 0)}%</strong><br><span class="small">Labour</span></div>
        <div style="padding:8px;border:1px solid #ddd;border-radius:8px;"><strong>${Number(quality.understanding || 0)}%</strong><br><span class="small">AI understanding</span></div>
        <div style="padding:8px;border:1px solid #ddd;border-radius:8px;"><strong>${Number(quality.site_confirmation || 0)}%</strong><br><span class="small">Needs site confirmation</span></div>
      </div>

      <div style="margin-top:9px;padding:10px;border:2px solid ${health.readiness === "ready_to_send" ? "#16a34a" : health.readiness === "do_not_send" ? "#dc2626" : "#d97706"};border-radius:9px;background:${health.readiness === "ready_to_send" ? "#f0fdf4" : health.readiness === "do_not_send" ? "#fef2f2" : "#fffbeb"};">
        <div style="display:flex;justify-content:space-between;gap:10px;align-items:center;">
          <div><strong>Quote health</strong><br><span class="small">${escapeHtml(health.readiness_label || "Review recommended")}</span></div>
          <div style="font-size:25px;font-weight:800;">${Number(health.score || 0)}%</div>
        </div>

        ${healthPassed.length ? `<div style="margin-top:7px;">${healthPassed.map(x => `✓ ${escapeHtml(x)}`).join("<br>")}</div>` : ""}

        ${healthMissing.length ? `<div style="margin-top:9px;"><strong>Possible missing items</strong>
          ${healthMissing.map(item => `<div style="margin-top:6px;padding:8px;background:white;border:1px solid #ddd;border-radius:8px;">
            <strong>${escapeHtml(item.name || "")}</strong> × ${Number(item.quantity || 1)} ${item.optional ? `<span class="small">(optional)</span>` : ""}<br>
            <span class="small">${escapeHtml(item.reason || "")}</span>
            <div class="history-actions" style="grid-template-columns:1fr 1fr;gap:6px;margin-top:7px;">
              <button type="button" class="btn-light" onclick='addQuoteHealthSuggestion(${JSON.stringify(item.id)})'>Add item</button>
              <button type="button" class="btn-light" onclick='ignoreQuoteHealthSuggestion(${JSON.stringify(item.id)})'>Ignore</button>
            </div>
          </div>`).join("")}
        </div>` : ""}

        ${healthQuantities.length ? `<div style="margin-top:9px;"><strong>Quantities to check</strong>
          ${healthQuantities.map(x => `<div style="margin-top:6px;padding:8px;background:white;border:1px solid #ddd;border-radius:8px;">
            <strong>${escapeHtml(x.material || "")}</strong><br>
            <span class="small">${escapeHtml(x.message || "")}</span>
            ${x.no_auto_fix ? "" : `<div style="margin-top:6px;"><strong>Current:</strong> ${Number(x.actual_quantity || 0)} &nbsp; <strong>Suggested:</strong> ${Number(x.suggested_quantity || 0)}</div>
            <div class="history-actions" style="grid-template-columns:1fr 1fr;gap:6px;margin-top:7px;">
              <button type="button" class="btn-light" onclick='useSuggestedQuantity(${JSON.stringify(x.id)})'>Use suggested</button>
              <button type="button" class="btn-light" onclick='keepCurrentQuantity(${JSON.stringify(x.id)})'>Keep current</button>
            </div>`}
          </div>`).join("")}
        </div>` : ""}
        ${healthLabour.length ? `<div style="margin-top:9px;"><strong>Labour checks</strong><br>${healthLabour.map(x => `△ ${escapeHtml(x.message || "")}`).join("<br>")}</div>` : ""}
        <div class="small" style="margin-top:7px;">Advisory only — nothing is added or repriced unless you approve it.</div>
      </div>

      ${jobBundles.length ? `<div style="margin-top:10px;"><strong>Recommended job bundles</strong>
        ${jobBundles.map((bundle, bundleIndex) => {
          const pendingAll = (bundle.items || []).filter(item => !item.already_in_quote).length;
          const pendingEssential = (bundle.items || []).filter(item => !item.already_in_quote && !item.optional).length;
          const health = bundle.health || {};
          const colours = bundleHealthColour(health.status || "review");
          return `<div style="margin-top:7px;padding:9px;border:1px solid ${colours.border};border-radius:9px;background:white;">
            <strong>${escapeHtml(bundle.display_name || "")}</strong>
            <span class="small"> · ${Number(bundle.required_count || 0)} essential · ${Number(bundle.optional_count || 0)} optional</span><br>
            ${(bundle.items || []).map(item => `• <strong>${escapeHtml(item.name)}</strong> × ${Number(item.quantity || 1)} — ${Number(item.confidence || 0)}% ${item.already_in_quote ? "✓ already included" : item.optional ? "(optional)" : "(essential)"}${item.reason ? `<br><span class="small" style="display:inline-block;margin-left:12px;">${escapeHtml(item.reason)}</span>` : ""}`).join("<br>")}
            ${renderBundleHealth(bundle)}
            <div class="history-actions" style="grid-template-columns:1fr 1fr;gap:6px;margin-top:7px;">
              <button type="button" class="btn-green" ${pendingAll ? "" : "disabled"} onclick="addV151JobBundle(${bundleIndex}, false)">
                ${pendingAll ? `Add full bundle (${pendingAll})` : "Full bundle added"}
              </button>
              <button type="button" class="btn-light" ${pendingEssential ? "" : "disabled"} onclick="addV151JobBundle(${bundleIndex}, true)">
                ${pendingEssential ? `Fix missing essentials (${pendingEssential})` : "Essentials complete"}
              </button>
            </div>
          </div>`;
        }).join("")}
      </div>` : ""}

      ${(confidence.positive_reasons || []).length || (confidence.gaps || []).length ? `
        <div style="margin-top:8px;padding:9px;border:1px solid #ddd;border-radius:8px;">
          <strong>Why this estimate is reliable</strong><br>
          ${(confidence.positive_reasons || []).map(x => `✓ ${escapeHtml(x)}`).join("<br>")}
          ${(confidence.gaps || []).map(x => `<br>△ ${escapeHtml(x)}`).join("")}
        </div>` : ""}

      ${surveySummary.used ? `<div style="margin-top:10px;padding:9px;border:1px solid #2563eb;border-radius:8px;background:#eff6ff;"><strong>Site survey used</strong><br>${escapeHtml(surveySummary.summary || "")}${(surveySummary.material_actions_applied || []).length ? `<div style="margin-top:6px;">${(surveySummary.material_actions_applied || []).map(item => `• ${escapeHtml(item.material_name)} — ${escapeHtml(surveyActionLabel(item.action))} (${Number(item.confidence || 0)}%)`).join("<br>")}</div>` : ""}</div>` : ""}

      <div style="margin-top:12px;"><strong>Scope of works</strong></div>
      ${(draft.job_breakdown || []).length ? `
        ${(draft.job_breakdown || []).map(job => `
          <div style="margin-top:7px;padding:9px;border:1px solid #ddd;border-radius:8px;">
            <strong>${escapeHtml(job.display_name || job.job_type || "")}</strong><br>
            ${escapeHtml(job.scope || job.original_text || "")}
          </div>`).join("")}
      ` : `<div style="margin-top:5px;">${escapeHtml(draft.scope_of_work || "")}</div>`}

      <div style="margin-top:12px;"><strong>Labour breakdown</strong>
        <div style="overflow-x:auto;margin-top:5px;">
          <table style="width:100%;border-collapse:collapse;">
            <thead><tr>
              <th style="text-align:left;padding:5px;border-bottom:1px solid #ddd;">Job</th>
              <th style="text-align:right;padding:5px;border-bottom:1px solid #ddd;">Labour</th>
            </tr></thead>
            <tbody>
              ${(draft.job_breakdown || []).length ? (draft.job_breakdown || []).map(job => `<tr>
                <td style="padding:5px;border-bottom:1px solid #eee;">${escapeHtml(job.display_name || job.job_type || "")}</td>
                <td style="padding:5px;text-align:right;border-bottom:1px solid #eee;">${pounds(job.labour_suggestion || 0)}</td>
              </tr>`).join("") : `<tr><td style="padding:5px;border-bottom:1px solid #eee;">Estimated labour</td><td style="padding:5px;text-align:right;border-bottom:1px solid #eee;">${pounds(draft.labour_suggestion || 0)}</td></tr>`}
              <tr><td style="padding:6px;font-weight:800;">Total</td><td style="padding:6px;text-align:right;font-weight:800;">${pounds(draft.labour_suggestion || 0)}</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div style="margin-top:12px;"><strong>Materials</strong><br>
        <span class="small">Required items are included automatically. Tick an optional item to add it directly to the editable Materials list.</span>
        <div style="overflow-x:auto;margin-top:5px;">
          <table style="width:100%;border-collapse:collapse;min-width:720px;">
            <thead><tr>
              <th style="text-align:left;padding:5px;border-bottom:1px solid #ddd;">Item</th>
              <th style="text-align:left;padding:5px;border-bottom:1px solid #ddd;">Status</th>
              <th style="text-align:center;padding:5px;border-bottom:1px solid #ddd;">Include</th>
              <th style="text-align:right;padding:5px;border-bottom:1px solid #ddd;">Qty</th>
              <th style="text-align:right;padding:5px;border-bottom:1px solid #ddd;">Price</th>
              <th style="text-align:center;padding:5px;border-bottom:1px solid #ddd;">Confidence</th>
              <th style="text-align:left;padding:5px;border-bottom:1px solid #ddd;">Supplier</th>
            </tr></thead>
            <tbody>${materials.length ? materials.map((m, materialIndex) => `<tr style="background:${isOptionalDraftMaterial(m) && !optionalMaterialIsSelected(m) ? "#fafafa" : "white"};">
              <td style="padding:5px;border-bottom:1px solid #eee;"><strong>${escapeHtml(m.name || "")}</strong>${m.reason ? `<br><span class="small">${escapeHtml(m.reason)}</span>` : ""}</td>
              <td style="padding:5px;border-bottom:1px solid #eee;">${statusBadge(m.display_status || (m.required ? "required" : "optional"))}</td>
              <td style="padding:5px;text-align:center;border-bottom:1px solid #eee;">${optionalMaterialControl(m, materialIndex)}</td>
              <td style="padding:5px;text-align:right;border-bottom:1px solid #eee;">${Number(m.quantity || 1)}</td>
              <td style="padding:5px;text-align:right;border-bottom:1px solid #eee;">${Number(m.manual_price || 0) > 0 ? pounds(m.manual_price) : "TBC"}</td>
              <td style="padding:5px;text-align:center;border-bottom:1px solid #eee;">${Number(m.material_confidence || 65)}%</td>
              <td style="padding:5px;border-bottom:1px solid #eee;">${escapeHtml(m.supplier || "")}</td>
            </tr>`).join("") : `<tr><td colspan="7" style="padding:7px;">No materials suggested.</td></tr>`}</tbody>
          </table>
        </div>
      </div>

      ${assumptions.length ? `<div style="margin-top:12px;"><strong>Assumptions</strong>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:7px;margin-top:6px;">
          ${assumptions.map(x => `<div style="padding:8px;border:1px solid #ddd;border-radius:8px;">✓ ${escapeHtml(x)}</div>`).join("")}
        </div>
      </div>` : ""}

      ${exclusions.length ? `<div style="margin-top:12px;"><strong>Exclusions</strong><br>${exclusions.map(x => `• ${escapeHtml(x)}`).join("<br>")}</div>` : ""}
      ${questions.length ? `<div style="margin-top:12px;"><strong>Site checks required</strong><br>${questions.map(x => `• ${escapeHtml(x)}`).join("<br>")}</div>` : ""}
      ${risks.length ? `<div style="margin-top:12px;"><strong>Possible additional work</strong><br>${risks.map(x => `• ${escapeHtml(x)}`).join("<br>")}</div>` : ""}

      ${draft.multi_job_summary ? `<div style="margin-top:12px;padding:9px;background:#eef6ff;border-radius:8px;"><strong>Quote summary</strong><br>
        ${Number(draft.multi_job_summary.job_count || 0)} job(s) ·
        ${Number(draft.multi_job_summary.combined_material_count || 0)} unique material item(s) ·
        ${Number(draft.multi_job_summary.duplicates_merged || 0)} duplicate item(s) merged ·
        labour ${pounds(draft.multi_job_summary.combined_labour || 0)} ·
        materials ${pounds(draft.multi_job_summary.materials_total_before_handling || 0)} before handling
      </div>` : ""}

      ${liveProductFinderHtml(draft)}

      <details style="margin-top:10px;">
        <summary><strong>Internal estimator detail</strong></summary>
        <div style="margin-top:8px;padding:8px;background:#fafafa;border-radius:8px;">
          ${evidence.length ? `<strong>Material evidence</strong><br>${evidence.map(x => `• ${escapeHtml(x.name)} — ${escapeHtml(x.source)} · ${Number(x.confidence || 0)}%${Number(x.used_count || 0) ? ` · ${Number(x.used_count)} prior use(s)` : ""}`).join("<br>")}<br><br>` : ""}
          ${(technical.all_risk_notes || []).length ? `<strong>All risk notes</strong><br>${(technical.all_risk_notes || []).map(x => `• ${escapeHtml(x)}`).join("<br>")}<br><br>` : ""}
          ${(technical.all_questions || []).length ? `<strong>All questions</strong><br>${(technical.all_questions || []).map(x => `• ${escapeHtml(x)}`).join("<br>")}<br><br>` : ""}
          ${(technical.all_warnings || []).length ? `<strong>All warnings</strong><br>${(technical.all_warnings || []).map(x => `• ${escapeHtml(x)}`).join("<br>")}` : ""}
        </div>
      </details>

      <details style="margin-top:10px;">
        <summary><strong>Customer preview</strong></summary>
        <div style="margin-top:8px;padding:12px;background:white;border:1px solid #ddd;border-radius:8px;">
          <h3 style="margin:0 0 8px 0;">Nigel Harvey Ltd</h3>
          <strong>Works included</strong><br>
          ${escapeHtml(preview.scope_of_work || draft.scope_of_work || "")}
          <div style="margin-top:10px;"><strong>Labour</strong><br>${pounds(preview.labour_total || draft.labour_suggestion || 0)}</div>
          ${(preview.exclusions || exclusions).length ? `<div style="margin-top:10px;"><strong>Exclusions</strong><br>${(preview.exclusions || exclusions).map(x => `• ${escapeHtml(x)}`).join("<br>")}</div>` : ""}
        </div>
      </details>

      <div class="history-actions" style="grid-template-columns:1fr 1fr;gap:8px;margin-top:10px;">
        <button type="button" class="btn-green" onclick="applyAIQuoteDraft()">Apply draft to form</button>
        <button type="button" class="btn-light" onclick="discardAIQuoteDraft()">Discard</button>
      </div>
    </div>`;
}

function applyAIQuoteDraft() {
  let draft = LAST_AI_QUOTE_DRAFT;
  if (!draft) return;
  draft = prepareDraftForV125(draft);
  LAST_AI_QUOTE_DRAFT = draft;

  if (draft.scope_of_work) {
    document.getElementById("job").value = draft.scope_of_work;
  }

  if (Number(draft.labour_suggestion || 0) > 0) {
    document.getElementById("labour").value = Number(draft.labour_suggestion).toFixed(2);
  }

  clearMaterials();
  (draft.materials || [])
    .filter(m => !isOptionalDraftMaterial(m) || optionalMaterialIsSelected(m))
    .forEach(m => {
      addMaterial({
        name: m.name || "",
        quantity: Number(m.quantity || 1),
        supplier: m.supplier || "City Plumbing",
        url: m.url || "",
        manual_price: Number(m.manual_price || m.live_price || m.default_price || 0),
        source: m.source || "",
        price_source: m.price_source || "",
        sku: m.sku || "",
        image_url: m.image_url || "",
        checked_at: m.checked_at || "",
        quantity_source: m.quantity_source || "ai",
        learned_used_count: Number(m.learned_used_count || 0)
      });
    });
  mergeDuplicateMaterialRowsInForm();

  scheduleQuoteLearning();
  scheduleLabourIntelligence();
  updateForgottenItemWarnings();
  updateSupplierPreferenceNotes();

  const box = document.getElementById("aiQuoteResult");
  if (box) {
    box.innerHTML = `<div class="notice">AI draft applied. Check quantities, product links, prices, labour and scope before saving.</div>`;
  }
  showNotice("AI quote draft applied for review.");
}

function discardAIQuoteDraft() {
  LAST_AI_QUOTE_DRAFT = null;
  const box = document.getElementById("aiQuoteResult");
  if (box) box.innerHTML = "";
  showNotice("AI draft discarded.");
}


async function generateQuote(options = {}) {
  const {
    silent = false,
    autoRefresh = false,
    skipDashboardReload = false
  } = options || {};

  const errorBox = document.getElementById("error");
  errorBox.style.display = "none";

  const payload = collectFormPayload();
  const isEditing = !!CURRENT_QUOTE_ID;
  const url = isEditing ? "/api/quotes/" + CURRENT_QUOTE_ID : "/api/quote";
  const method = isEditing ? "PUT" : "POST";

  try {
    const res = await fetch(url, {
      method,
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });

    if (!res.ok) throw new Error();
    const data = await res.json();

    CURRENT_QUOTE_ID = data.id || null;
    setEditingStatus(CURRENT_QUOTE_ID ? "Editing saved quote #" + CURRENT_QUOTE_ID : "", !!CURRENT_QUOTE_ID);
    setQuoteButtonMode(!!CURRENT_QUOTE_ID);

    renderQuoteResult(data.result);

    // Clear any stale error message after a successful save/update.
    if (errorBox) {
      errorBox.innerText = "";
      errorBox.style.display = "none";
    }

    if (!skipDashboardReload) {
      await loadHistory();
      await loadCustomers();
      await loadDashboard();
    }
    if (!silent) {
      showNotice(isEditing ? "Quote updated." : "Quote saved.");
    }
    return data;
  } catch (err) {
    if (!silent) {
      errorBox.innerText = isEditing ? "Something went wrong updating the quote." : "Something went wrong generating the quote.";
      errorBox.style.display = "block";
    }
    if (autoRefresh || silent) throw err;
    return null;
  }
}

async function convertQuoteToInvoice(quoteId) {
  try {
    const res = await fetch("/api/quotes/" + quoteId + "/to-invoice", { method: "POST" });
    if (!res.ok) throw new Error();
    const data = await res.json();
    renderInvoiceCard(data);
    showTab("invoicesTab");
    await loadInvoices();
    await loadDashboard();
    showNotice("Invoice created from quote.");
  } catch (e) {
    alert("Could not convert quote to invoice.");
  }
}

async function convertCurrentQuoteToInvoice() {
  if (!CURRENT_QUOTE_ID) {
    alert("Generate and save the quote first.");
    return;
  }
  await convertQuoteToInvoice(CURRENT_QUOTE_ID);
}


function normaliseQuoteDataForEditing(data) {
  const q = data && (data.request || data.quote || data.result || data);
  return {
    quote_type: q.quote_type || q.type || "small",
    customer_name: q.customer_name || q.customer || "",
    customer_address: q.customer_address || q.address || "",
    customer_phone: q.customer_phone || q.phone || "",
    job_description: q.job_description || q.job || "",
    labour_cost: q.labour_cost || q.labour || 0,
    include_callout_charge: !!q.include_callout_charge || Number(q.callout_charge || 0) > 0,
    callout_charge: q.callout_charge || 0,
    include_travel_charge: !!q.include_travel_charge || Number(q.travel_charge || 0) > 0,
    travel_charge: q.travel_charge || 0,
    include_materials_handling: q.include_materials_handling !== false,
    materials_handling_percent: q.materials_handling_percent || 25,
    deposit_percent: q.deposit_percent || 0,
    materials: q.materials || q.material_lines || []
  };
}



function normaliseQuoteDataForEditing(data) {
  const root = data || {};
  const request = root.request || {};
  const result = root.result || {};
  const quote = root.quote || {};

  const q = {
    quote_type: request.quote_type || result.quote_type || quote.quote_type || root.quote_type || "small",
    customer_name: request.customer_name || result.customer_name || quote.customer_name || root.customer_name || "",
    customer_address: request.customer_address || result.customer_address || quote.customer_address || root.customer_address || "",
    customer_phone: request.customer_phone || result.customer_phone || quote.customer_phone || root.customer_phone || "",
    job_description: request.job_description || result.job || result.job_description || quote.job_description || root.job_description || root.job || "",
    labour_cost: request.labour_cost || result.labour || quote.labour_cost || root.labour_cost || root.labour || 0,
    include_callout_charge: request.include_callout_charge !== undefined ? request.include_callout_charge : Number(result.callout_charge || 0) > 0,
    callout_charge: request.callout_charge || result.callout_charge || quote.callout_charge || root.callout_charge || 0,
    include_travel_charge: request.include_travel_charge !== undefined ? request.include_travel_charge : Number(result.travel_charge || 0) > 0,
    travel_charge: request.travel_charge || result.travel_charge || quote.travel_charge || root.travel_charge || 0,
    include_materials_handling: request.include_materials_handling !== undefined ? request.include_materials_handling : true,
    materials_handling_percent: request.materials_handling_percent || result.materials_handling_percent || quote.materials_handling_percent || root.materials_handling_percent || 25,
    deposit_percent: request.deposit_percent || result.deposit_percent || quote.deposit_percent || root.deposit_percent || 0,
    materials: request.materials || result.material_lines || quote.materials || root.materials || root.material_lines || []
  };

  q.materials = (q.materials || []).map(m => ({
    name: m.name || "",
    quantity: m.quantity || 1,
    supplier: m.supplier || "",
    url: m.url || "",
    manual_price: m.manual_price || m.full_unit_price || m.unit_price_used || m.price || 0,
    quote_charge_override: m.quote_charge_override,
    material_type: m.material_type || "chargeable",
    charge_method: m.charge_method || "full",
    quantity_source: m.quantity_source || "rule",
    learned_average_quantity: m.learned_average_quantity || null,
    learned_used_count: m.learned_used_count || null
  }));

  return q;
}

function safeSetValue(id, value) {
  const el = document.getElementById(id);
  if (el) el.value = value ?? "";
}

function safeSetChecked(id, value) {
  const el = document.getElementById(id);
  if (el) el.checked = !!value;
}

function populateInvoiceEditForm(item) {
  const invoice = item.invoice || {};
  document.getElementById("edit_invoice_customer_name").value = invoice.customer_name || "";
  document.getElementById("edit_invoice_customer_address").value = invoice.customer_address || "";
  document.getElementById("edit_invoice_customer_phone").value = invoice.customer_phone || "";
  document.getElementById("edit_invoice_job").value = invoice.job || "";
  document.getElementById("edit_invoice_job_reference").value = item.job_reference || invoice.job_reference || "";
  document.getElementById("edit_invoice_labour").value = invoice.labour || 0;
  document.getElementById("edit_invoice_callout_charge").value = invoice.callout_charge || item.quote_result?.callout_charge || 0;
  document.getElementById("edit_invoice_travel_charge").value = invoice.travel_charge || item.quote_result?.travel_charge || 0;
  document.getElementById("edit_invoice_materials").value = invoice.materials || 0;
  document.getElementById("edit_invoice_due_date").value = item.due_date || "";
  document.getElementById("edit_invoice_payment_link").value = item.payment_link || "";
  document.getElementById("edit_invoice_amount_paid").value = item.amount_paid || 0;
  document.getElementById("edit_invoice_reminder_email").value = item.reminder_email || "";
  document.getElementById("edit_invoice_reminders_enabled").checked = !!item.reminders_enabled;
}

function showInvoiceEditPanel(item) {
  CURRENT_EDITING_INVOICE_ID = item.id;
  const panel = document.getElementById("invoiceEditPanel");
  if (!panel) {
    alert("Invoice editor could not be found.");
    return;
  }

  // The editor was originally inside a tab panel. Move it directly under
  // document.body so it remains visible even while the Invoices tab is active.
  if (panel.parentElement !== document.body) {
    document.body.appendChild(panel);
  }

  populateInvoiceEditForm(item);
  panel.classList.remove("hidden");
  panel.style.display = "block";
  document.body.style.overflow = "hidden";

  window.setTimeout(() => {
    const ref = document.getElementById("edit_invoice_job_reference");
    if (ref) {
      ref.focus();
      ref.select();
    }
  }, 100);
}

function cancelInvoiceEdit() {
  CURRENT_EDITING_INVOICE_ID = null;
  const panel = document.getElementById("invoiceEditPanel");
  if (panel) {
    panel.classList.add("hidden");
    panel.style.display = "none";
  }
  document.body.style.overflow = "";
}

async function openInvoice(id) {
  try {
    const res = await fetch("/api/invoices/" + id);
    if (!res.ok) throw new Error();
    const data = await res.json();
    renderInvoiceCard(data);
  } catch (e) {
    alert("Could not open invoice.");
  }
}

async function editInvoice(id) {
  try {
    const res = await fetch("/api/invoices/" + id);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not load invoice.");
    showInvoiceEditPanel(data);
    showNotice("Invoice loaded for editing.");
  } catch (e) {
    alert(e.message || "Could not load invoice for editing.");
  }
}

async function sendInvoiceWhatsApp(id) {
  try {
    const res = await fetch("/api/invoices/" + id);
    if (!res.ok) throw new Error();
    const data = await res.json();
    renderInvoiceCard(data);
    document.getElementById("invoiceWhatsappBtn").click();
  } catch (e) {
    alert("Could not open WhatsApp for this invoice.");
  }
}

function openInvoicePage(id) {
  window.open("/invoice/" + id, "_blank");
}

async function emailInvoice(id) {
  try {
    const res = await fetch("/api/invoices/" + id);
    if (!res.ok) throw new Error();
    const data = await res.json();
    renderInvoiceCard(data);
    document.getElementById("invoiceEmailBtn").click();
  } catch (e) {
    alert("Could not open email for this invoice.");
  }
}

async function saveInvoiceEdit() {
  if (!CURRENT_EDITING_INVOICE_ID) return;
  try {
    const payload = {
      customer_name: document.getElementById("edit_invoice_customer_name").value || "",
      customer_address: document.getElementById("edit_invoice_customer_address").value || "",
      customer_phone: document.getElementById("edit_invoice_customer_phone").value || "",
      job: document.getElementById("edit_invoice_job").value || "",
      job_reference: document.getElementById("edit_invoice_job_reference").value || "",
      labour: parseFloat(document.getElementById("edit_invoice_labour").value || 0),
      callout_charge: parseFloat(document.getElementById("edit_invoice_callout_charge").value || 0),
      travel_charge: parseFloat(document.getElementById("edit_invoice_travel_charge").value || 0),
      materials: parseFloat(document.getElementById("edit_invoice_materials").value || 0),
      due_date: document.getElementById("edit_invoice_due_date").value || "",
      payment_link: document.getElementById("edit_invoice_payment_link").value || "",
      amount_paid: parseFloat(document.getElementById("edit_invoice_amount_paid").value || 0),
      reminder_email: document.getElementById("edit_invoice_reminder_email").value || "",
      reminders_enabled: !!document.getElementById("edit_invoice_reminders_enabled").checked
    };

    const res = await fetch("/api/invoices/" + CURRENT_EDITING_INVOICE_ID, {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error();
    const data = await res.json();
    renderInvoiceCard(data);
    await loadInvoices();
    await loadCustomers();
    await loadDashboard();
    cancelInvoiceEdit();
    showNotice("Invoice updated. Job Ref saved.");
  } catch (e) {
    alert("Could not save invoice changes.");
  }
}

async function savePaymentLink(id) {
  try {
    const paymentLink = document.getElementById("payment_link_" + id).value || "";
    const res = await fetch("/api/invoices/" + id + "/payment-link", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ payment_link: paymentLink })
    });
    if (!res.ok) throw new Error();
    await loadInvoices();
    showNotice("Payment link saved.");
  } catch (e) {
    alert("Could not save payment link.");
  }
}

async function printInvoice(id) {
  try {
    const res = await fetch("/api/invoices/" + id);
    if (!res.ok) throw new Error();
    const data = await res.json();
    renderInvoiceCard(data);
    window.print();
  } catch (e) {
    alert("Could not print this invoice.");
  }
}

async function updateInvoicePaid(id) {
  try {
    const amount = parseFloat(document.getElementById("paid_" + id).value || 0);
    const res = await fetch("/api/invoices/" + id + "/status", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ status: "unpaid", amount_paid: amount })
    });
    if (!res.ok) throw new Error();
    await loadInvoices();
    await loadDashboard();
    showNotice("Invoice payment updated.");
  } catch (e) {
    alert("Could not update invoice.");
  }
}

async function markInvoicePaid(id, total) {
  try {
    const res = await fetch("/api/invoices/" + id + "/status", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ status: "paid", amount_paid: total })
    });
    if (!res.ok) throw new Error();
    await loadInvoices();
    await loadDashboard();
    showNotice("Invoice marked paid.");
  } catch (e) {
    alert("Could not mark invoice as paid.");
  }
}

async function markInvoiceUnpaid(id) {
  try {
    const res = await fetch("/api/invoices/" + id + "/status", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ status: "unpaid", amount_paid: 0 })
    });
    if (!res.ok) throw new Error();
    await loadInvoices();
    await loadDashboard();
    showNotice("Invoice marked unpaid.");
  } catch (e) {
    alert("Could not mark invoice as unpaid.");
  }
}

async function deleteInvoice(id) {
  if (!confirm("Delete this invoice?")) return;
  try {
    const res = await fetch("/api/invoices/" + id, { method: "DELETE" });
    if (!res.ok) throw new Error();
    await loadInvoices();
    await loadDashboard();
    showNotice("Invoice deleted.");
  } catch (e) {
    alert("Could not delete invoice.");
  }
}

toggleBathroomFields();
renderTemplates();
renderFavourites();
clearMaterials();
const initialMaterialSearchPanel = document.getElementById("manualMaterialSearchPanel");
if (initialMaterialSearchPanel) initialMaterialSearchPanel.style.display = "none";
setQuoteButtonMode(false);
updateLabourSuggestion();
renderTemplateButtons();
checkAIQuoteStatus();
renderMasterMaterialSuggestions();
loadDashboard();
loadHistory();
loadInvoices();
loadCustomers();
loadLeads();
</script>
</body>
</html>
'''


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
<link rel="canonical" href="https://www.nigelharveyplumbing.co.uk/">
<meta name="robots" content="index,follow,max-image-preview:large">
<meta property="og:title" content="Plumber in Guildford & Surrey | Nigel Harvey Plumbing">
<meta property="og:description" content="Local Guildford plumber serving Surrey for general plumbing, leaks, bathrooms, radiators, toilets, taps and pipework.">
<meta property="og:type" content="website">
<meta property="og:url" content="https://www.nigelharveyplumbing.co.uk/">
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
    html = NEW_HOMEPAGE_PREVIEW_HTML
    html = html.replace("__COMPANY_PHONE__", COMPANY_PHONE)
    html = html.replace("__COMPANY_PHONE_TEL__", COMPANY_PHONE_TEL)
    html = html.replace("__COMPANY_EMAIL__", COMPANY_EMAIL)
    html = html.replace("__GOOGLE_REVIEWS_URL__", GOOGLE_REVIEWS_URL)
    html = html.replace("__GOOGLE_REVIEWS_HTML__", _google_reviews_html())
    return HTMLResponse(content=html, media_type="text/html; charset=utf-8")


@app.get("/", response_class=HTMLResponse)
def landing_home(request: Request):
    html = NEW_HOMEPAGE_PREVIEW_HTML
    html = html.replace("__COMPANY_PHONE__", COMPANY_PHONE)
    html = html.replace("__COMPANY_PHONE_TEL__", COMPANY_PHONE_TEL)
    html = html.replace("__COMPANY_EMAIL__", COMPANY_EMAIL)
    html = html.replace("__GOOGLE_REVIEWS_URL__", GOOGLE_REVIEWS_URL)
    html = html.replace("__GOOGLE_REVIEWS_HTML__", _google_reviews_html())
    return HTMLResponse(content=html, media_type="text/html; charset=utf-8")


@app.get("/robots.txt")
def robots_txt(request: Request):
    sitemap_url = "https://www.nigelharveyplumbing.co.uk/sitemap.xml"
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
    BASE_URL = "https://www.nigelharveyplumbing.co.uk"
    body = "".join(f"<url><loc>{BASE_URL + url}</loc></url>" for url in urls)
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
    conn = get_db()
    rows = conn.execute("""
        SELECT id, url, name, supplier, last_price, last_live_price, last_manual_price,
               last_status, times_used, created_at, updated_at, last_checked_at, last_success_at
        FROM material_price_cache
        ORDER BY updated_at DESC, id DESC
        LIMIT 500
    """).fetchall()
    conn.close()
    return JSONResponse([dict(row) for row in rows])


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

    if cur.rowcount <= 0:
        raise HTTPException(status_code=404, detail="Material not found")
    return {"ok": True}


@app.delete("/api/material-prices/{material_id}")
def api_delete_material_price(material_id: int, request: Request):
    if not check_basic_auth(request):
        raise HTTPException(status_code=401, detail="Authentication required")

    conn = get_db()
    cur = conn.execute("DELETE FROM material_price_cache WHERE id = ?", (material_id,))
    conn.commit()
    conn.close()

    if cur.rowcount <= 0:
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
    conn = get_db()

    customer = conn.execute(
        "SELECT id FROM customers WHERE id = ?", (customer_id,)
    ).fetchone()

    if not customer:
        conn.close()
        raise HTTPException(status_code=404, detail="Customer not found")

    deleted_invoices = conn.execute(
        "DELETE FROM invoices WHERE customer_id = ?", (customer_id,)
    ).rowcount
    deleted_quotes = conn.execute(
        "DELETE FROM quotes WHERE customer_id = ?", (customer_id,)
    ).rowcount
    deleted_customers = conn.execute(
        "DELETE FROM customers WHERE id = ?", (customer_id,)
    ).rowcount

    conn.commit()
    conn.close()

    return {
        "ok": True,
        "deleted_customers": deleted_customers,
        "deleted_quotes": deleted_quotes,
        "deleted_invoices": deleted_invoices,
    }


@app.get("/api/customers/{customer_id}/history")
def api_customer_history(customer_id: int):
    history = get_customer_history(customer_id)
    if not history:
        raise HTTPException(status_code=404, detail="Customer not found")
    return history

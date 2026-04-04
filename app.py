from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup
import re
import json
import sqlite3
from pathlib import Path

app = FastAPI(title="Nigel Harvey Ltd Business App")

DB_PATH = Path("quotes.db")
UK_TZ = ZoneInfo("Europe/London")

COMPANY_NAME = "Nigel Harvey Ltd"
COMPANY_ADDRESS = "125 Bushy Hill Drive, Guildford, GU1 2UG"
COMPANY_PHONE = "07595 725547"
COMPANY_EMAIL = "Nigelharveyplumbing@gmail.com"

# Optional: set this later if you want invoice payment links.
# Example: "https://pay.example.com/invoice/"
PAYMENT_LINK_BASE = ""

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
    {"name": "Replace tap", "quote_type": "small", "job": "Remove existing tap and fit new tap including testing for leaks.", "labour": 120},
    {"name": "Replace toilet", "quote_type": "small", "job": "Remove existing toilet and fit new close-coupled toilet including waste connection and testing.", "labour": 180},
    {"name": "Basin waste", "quote_type": "small", "job": "Remove faulty basin waste and fit new basin waste including testing for leaks.", "labour": 90},
    {"name": "Outside tap", "quote_type": "small", "job": "Supply and fit outside tap kit with isolation and testing.", "labour": 150},
    {"name": "Kitchen sink waste", "quote_type": "small", "job": "Remove existing sink waste and fit new waste/trap arrangement including testing.", "labour": 120},
    {"name": "Bathroom install", "quote_type": "bathroom", "job": "Bathroom plumbing installation including first fix, second fix and sanitaryware connections.", "labour": 1800},
    {"name": "Bathroom refurb", "quote_type": "bathroom", "job": "Bathroom refurbishment plumbing works including sanitaryware, wastes and connections.", "labour": 2200},
    {"name": "Heating repair", "quote_type": "heating", "job": "Heating repair works including diagnosis, replacement parts and testing.", "labour": 150},
    {"name": "Radiator install", "quote_type": "heating", "job": "Supply and fit radiator including valves and testing.", "labour": 180},
    {"name": "Full heating system", "quote_type": "heating", "job": "Full heating system installation including pipework, controls, radiators and commissioning.", "labour": 3500},
]

LABOUR_HINTS = {
    "small": [
        {"keywords": ["tap"], "suggestion": 120, "range": "£100–£140"},
        {"keywords": ["toilet", "wc"], "suggestion": 180, "range": "£160–£220"},
        {"keywords": ["waste", "trap"], "suggestion": 120, "range": "£90–£140"},
        {"keywords": ["outside tap"], "suggestion": 150, "range": "£140–£180"},
    ],
    "bathroom": [
        {"keywords": ["install"], "suggestion": 1800, "range": "£1,600–£2,200"},
        {"keywords": ["refurb"], "suggestion": 2200, "range": "£2,000–£2,800"},
        {"keywords": ["bathroom"], "suggestion": 2000, "range": "£1,600–£2,800"},
    ],
    "heating": [
        {"keywords": ["radiator"], "suggestion": 180, "range": "£160–£220"},
        {"keywords": ["repair"], "suggestion": 150, "range": "£120–£220"},
        {"keywords": ["system"], "suggestion": 3500, "range": "£3,000–£4,500"},
    ],
}


class MaterialItem(BaseModel):
    name: str = ""
    quantity: float = 1
    supplier: str = ""
    url: str = ""
    manual_price: float = 0


class QuoteRequest(BaseModel):
    quote_type: str = "small"
    customer_name: str = ""
    customer_address: str = ""
    customer_phone: str = ""
    job_description: str = ""
    labour_cost: float = 0
    include_materials_handling: bool = True
    materials_handling_percent: float = 25
    materials: list[MaterialItem] = Field(default_factory=list)
    tiling: bool = False
    wall_tiling_m2: float = 0
    floor_tiling_m2: float = 0
    wall_height: str = "half"
    customer_supplies_tiles: bool = False
    deposit_percent: float = 0


class InvoiceStatusRequest(BaseModel):
    status: str
    amount_paid: float = 0


def now_uk():
    return datetime.now(UK_TZ)


def format_dt(dt: datetime):
    return dt.strftime("%d/%m/%Y %H:%M")


def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def pounds(value):
    return f"£{safe_float(value):.2f}"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            address TEXT,
            phone TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            customer_name TEXT,
            job TEXT,
            total_price REAL,
            gross_profit REAL,
            margin_percent REAL,
            created_at TEXT NOT NULL,
            created_at_sort TEXT NOT NULL,
            request_json TEXT NOT NULL,
            result_json TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quote_id INTEGER,
            customer_id INTEGER,
            invoice_number TEXT NOT NULL,
            customer_name TEXT,
            total_price REAL,
            amount_paid REAL,
            balance_due REAL,
            status TEXT NOT NULL,
            due_date TEXT NOT NULL,
            payment_link TEXT,
            created_at TEXT NOT NULL,
            created_at_sort TEXT NOT NULL,
            quote_result_json TEXT NOT NULL,
            invoice_json TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


@app.on_event("startup")
def startup():
    init_db()


def fetch_price(url: str):
    if not url:
        return None
    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "en-GB,en;q=0.9",
        }
        r = requests.get(url, headers=headers, timeout=8, allow_redirects=True)
        if r.status_code != 200 or not r.text:
            return None

        soup = BeautifulSoup(r.text, "html.parser")

        meta_candidates = []
        for selector, attr in [
            ('meta[property="product:price:amount"]', "content"),
            ('meta[property="og:price:amount"]', "content"),
            ('meta[itemprop="price"]', "content"),
        ]:
            tag = soup.select_one(selector)
            if tag and tag.get(attr):
                meta_candidates.append(tag.get(attr))

        for value in meta_candidates:
            price = safe_float(value, None)
            if price and 0 < price < 100000:
                return round(price, 2)

        text = soup.get_text(" ", strip=True)

        domain_patterns = []
        lower_url = url.lower()
        if "cityplumbing" in lower_url:
            domain_patterns = [
                r'£\s?(\d+(?:\.\d{2})?)\s*each,\s*Inc\.?\s*VAT',
                r'£\s?(\d+(?:\.\d{2})?)\s*Inc\.?\s*VAT',
                r'£\s?(\d+(?:\.\d{2})?)\s*each',
            ]
        elif "toppstiles" in lower_url:
            domain_patterns = [
                r'£\s?(\d+(?:\.\d{2})?)\s*(?:per m2|/m2|m2)',
                r'£\s?(\d+(?:\.\d{2})?)'
            ]

        for pattern in domain_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                price = safe_float(match, None)
                if price and 0 < price < 100000:
                    return round(price, 2)

        generic_matches = re.findall(r'£\s?(\d+(?:\.\d{2})?)', text)
        prices = []
        for match in generic_matches:
            price = safe_float(match, None)
            if price and 0 < price < 100000:
                prices.append(price)

        if prices:
            return round(min(prices), 2)
    except Exception:
        return None
    return None


def find_labour_suggestion(quote_type: str, job_description: str):
    text = (job_description or "").lower()
    rules = LABOUR_HINTS.get(quote_type, [])
    for rule in rules:
        if any(keyword in text for keyword in rule["keywords"]):
            return rule
    if quote_type == "bathroom":
        return {"suggestion": 2000, "range": "£1,600–£2,800"}
    if quote_type == "heating":
        return {"suggestion": 180, "range": "£150–£300"}
    return {"suggestion": 120, "range": "£90–£180"}


def calculate_quote(data: QuoteRequest):
    raw_materials = 0.0
    material_lines = []

    for item in data.materials:
        url = item.url.strip() if item.url else ""
        live_price = fetch_price(url) if url else None
        unit_price = live_price if live_price is not None else (item.manual_price or 0)
        line_total = unit_price * item.quantity
        raw_materials += line_total
        material_lines.append({
            "name": item.name,
            "quantity": item.quantity,
            "supplier": item.supplier,
            "url": item.url,
            "manual_price": item.manual_price,
            "unit_price_used": round(unit_price, 2),
            "line_total": round(line_total, 2),
            "live_price_used": live_price is not None,
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
    total_price = labour_total + quoted_materials

    deposit_percent = max(0.0, min(100.0, data.deposit_percent or 0))
    deposit_amount = total_price * (deposit_percent / 100.0)

    job_text = data.job_description.strip()
    if data.tiling and data.quote_type == "bathroom":
        job_text = f"{job_text} + Tiling" if job_text else "Bathroom works + Tiling"

    hidden_uplift = quoted_materials - raw_materials_with_tiling
    gross_profit = (quoted_materials - raw_materials_with_tiling) + labour_total
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
        "materials": round(quoted_materials, 2),
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


def row_to_quote(row):
    return {
        "id": row["id"],
        "customer_id": row["customer_id"],
        "customer_name": row["customer_name"] or "",
        "job": row["job"] or "",
        "total_price": round(row["total_price"] or 0, 2),
        "gross_profit": round(row["gross_profit"] or 0, 2),
        "margin_percent": round(row["margin_percent"] or 0, 2),
        "created_at": row["created_at"],
        "request": json.loads(row["request_json"]),
        "result": json.loads(row["result_json"]),
    }


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
        "created_at": row["created_at"],
        "quote_result": json.loads(row["quote_result_json"]),
        "invoice": json.loads(row["invoice_json"]),
    }


def save_quote(request_data: dict, result_data: dict):
    customer_id = upsert_customer(
        request_data.get("customer_name", ""),
        request_data.get("customer_address", ""),
        request_data.get("customer_phone", ""),
    )
    conn = get_db()
    conn.execute("""
        INSERT INTO quotes (
            customer_id, customer_name, job, total_price, gross_profit, margin_percent,
            created_at, created_at_sort, request_json, result_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        customer_id,
        result_data.get("customer_name", ""),
        result_data.get("job", ""),
        result_data.get("total_price", 0),
        result_data.get("gross_profit", 0),
        result_data.get("margin_percent", 0),
        result_data.get("created_at", ""),
        result_data.get("created_at_sort", ""),
        json.dumps(request_data),
        json.dumps(result_data),
    ))
    quote_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return quote_id


def load_quotes():
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM quotes
        ORDER BY created_at_sort DESC, id DESC
        LIMIT 200
    """).fetchall()
    conn.close()
    return [row_to_quote(r) for r in rows]


def get_quote_by_id(quote_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM quotes WHERE id = ?", (quote_id,)).fetchone()
    conn.close()
    return row_to_quote(row) if row else None


def delete_quote_by_id(quote_id: int):
    conn = get_db()
    cur = conn.execute("DELETE FROM quotes WHERE id = ?", (quote_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def next_invoice_number():
    year = now_uk().strftime("%Y")
    conn = get_db()
    row = conn.execute("""
        SELECT COUNT(*) AS cnt
        FROM invoices
        WHERE invoice_number LIKE ?
    """, (f"INV-{year}-%",)).fetchone()
    conn.close()
    seq = (row["cnt"] or 0) + 1
    return f"INV-{year}-{seq:04d}"


def build_payment_link(invoice_number: str):
    if PAYMENT_LINK_BASE:
        return PAYMENT_LINK_BASE.rstrip("/") + "/" + invoice_number
    return ""


def create_invoice_from_quote(quote_id: int):
    quote = get_quote_by_id(quote_id)
    if not quote:
        return None

    result = quote["result"]
    invoice_number = next_invoice_number()
    due_date = (now_uk() + timedelta(days=7)).strftime("%d/%m/%Y")
    payment_link = build_payment_link(invoice_number)

    invoice_payload = {
        "invoice_number": invoice_number,
        "quote_id": quote["id"],
        "customer_name": result.get("customer_name", ""),
        "customer_address": result.get("customer_address", ""),
        "customer_phone": result.get("customer_phone", ""),
        "job": result.get("job", ""),
        "labour": result.get("labour", 0),
        "materials": result.get("materials", 0),
        "total_price": result.get("total_price", 0),
        "deposit_percent": result.get("deposit_percent", 0),
        "deposit_amount": result.get("deposit_amount", 0),
        "due_date": due_date,
        "payment_link": payment_link,
        "status": "unpaid",
        "amount_paid": 0.0,
        "balance_due": result.get("total_price", 0),
    }

    conn = get_db()
    conn.execute("""
        INSERT INTO invoices (
            quote_id, customer_id, invoice_number, customer_name, total_price, amount_paid, balance_due,
            status, due_date, payment_link, created_at, created_at_sort, quote_result_json, invoice_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        quote["id"],
        quote["customer_id"],
        invoice_number,
        result.get("customer_name", ""),
        result.get("total_price", 0),
        0.0,
        result.get("total_price", 0),
        "unpaid",
        due_date,
        payment_link,
        format_dt(now_uk()),
        now_uk().isoformat(),
        json.dumps(result),
        json.dumps(invoice_payload),
    ))
    invoice_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return get_invoice_by_id(invoice_id)


def get_invoice_by_id(invoice_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    conn.close()
    return row_to_invoice(row) if row else None


def load_invoices():
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM invoices
        ORDER BY created_at_sort DESC, id DESC
        LIMIT 200
    """).fetchall()
    conn.close()
    return [row_to_invoice(r) for r in rows]


def delete_invoice_by_id(invoice_id: int):
    conn = get_db()
    cur = conn.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def update_invoice_status(invoice_id: int, status: str, amount_paid: float):
    invoice = get_invoice_by_id(invoice_id)
    if not invoice:
        return None

    total = safe_float(invoice["total_price"])
    amount_paid = max(0.0, min(total, safe_float(amount_paid)))
    balance_due = max(0.0, total - amount_paid)

    status = (status or "").lower().strip()
    if status not in {"unpaid", "part paid", "paid"}:
        status = "unpaid"

    if amount_paid <= 0:
        status = "unpaid"
    elif amount_paid >= total:
        status = "paid"
    else:
        status = "part paid"

    invoice_payload = invoice["invoice"]
    invoice_payload["status"] = status
    invoice_payload["amount_paid"] = round(amount_paid, 2)
    invoice_payload["balance_due"] = round(balance_due, 2)

    conn = get_db()
    conn.execute("""
        UPDATE invoices
        SET amount_paid = ?, balance_due = ?, status = ?, invoice_json = ?
        WHERE id = ?
    """, (
        round(amount_paid, 2),
        round(balance_due, 2),
        status,
        json.dumps(invoice_payload),
        invoice_id,
    ))
    conn.commit()
    conn.close()
    return get_invoice_by_id(invoice_id)


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

    customers = conn.execute("""
        SELECT COUNT(*) AS customer_count FROM customers
    """).fetchone()

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


HTML = r"""
<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nigel Harvey Ltd Business App</title>
<style>
body { font-family: Arial, sans-serif; background:#f5f5f5; margin:0; padding:12px; color:#111; }
.wrap { max-width:1100px; margin:0 auto; }
.card { background:white; padding:16px; border-radius:14px; margin-bottom:14px; box-shadow:0 2px 10px rgba(0,0,0,0.06); }
h1 { margin:0 0 6px 0; font-size:30px; }
h2 { margin:0 0 12px 0; font-size:22px; }
h3 { margin:18px 0 8px 0; }
.sub { color:#666; margin-bottom:16px; }
label { display:block; font-weight:700; margin:12px 0 6px; }
input, textarea, select { width:100%; box-sizing:border-box; padding:12px; border:1px solid #ccc; border-radius:10px; font-size:16px; background:white; }
textarea { min-height:100px; resize:vertical; }
button, .btn-link { width:100%; padding:12px; border:none; border-radius:10px; background:black; color:white; font-size:16px; font-weight:700; text-align:center; text-decoration:none; display:inline-block; box-sizing:border-box; cursor:pointer; }
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
.tabs { display:grid; grid-template-columns:repeat(4, 1fr); gap:8px; margin-bottom:14px; }
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
@media print {
  .no-print { display:none !important; }
  body { background:white; padding:0; }
  .card { box-shadow:none; border:none; padding:0; margin:0 0 12px 0; }
  .wrap { max-width:100%; }
}
</style>
</head>
<body>
<div class="wrap">

  <div class="card">
    <h1>Nigel Harvey Ltd</h1>
    <div class="sub">Quotes, invoices, customers, profit tracking</div>

    <div class="tabs no-print">
      <button class="btn-light" onclick="showTab('dashboardTab')">Dashboard</button>
      <button class="btn-light" onclick="showTab('quotesTab')">Quotes</button>
      <button class="btn-light" onclick="showTab('invoicesTab')">Invoices</button>
      <button class="btn-light" onclick="showTab('customersTab')">Customers</button>
    </div>

    <div id="dashboardTab" class="tab-panel active">
      <h2>Dashboard</h2>
      <div class="small" id="dashboardMonth"></div>
      <div id="dashboardGrid" class="dashboard-grid"></div>
    </div>

    <div id="quotesTab" class="tab-panel">
      <h2>Quote Builder</h2>
      <div id="editingStatus" class="status-bar hidden"></div>

      <div class="check-row no-print">
        <input type="checkbox" id="internal_mode">
        <span>Internal mode</span>
      </div>

      <h3>Job templates</h3>
      <div id="templateButtons" class="templates"></div>

      <h3>Favourite materials</h3>
      <div id="favouriteButtons" class="favourites"></div>

      <label for="quote_type">Quote type</label>
      <select id="quote_type" onchange="toggleBathroomFields(); updateLabourSuggestion();">
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
      <textarea id="job" placeholder="Example: Replace kitchen tap" oninput="updateLabourSuggestion()"></textarea>

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

      <h3>Smart material search</h3>
      <input id="materialSearch" placeholder="Search materials e.g. 15mm speedfit elbow, basin waste, kitchen tap" oninput="searchMaterials()">
      <div id="searchResults" class="search-results hidden"></div>

      <h3>Materials</h3>
      <div id="materials"></div>
      <button type="button" class="btn-light no-print" onclick="addMaterial()">+ Add Manual Material Row</button>

      <h3>Pricing</h3>
      <label for="labour">Labour cost (£)</label>
      <input id="labour" type="number" step="0.01" placeholder="180">
      <div class="small" id="labourSuggestion" style="margin-top:8px;"></div>

      <div class="check-row">
        <input type="checkbox" id="include_materials_handling" checked>
        <span>Include materials handling</span>
      </div>

      <label for="materials_handling_percent">Materials handling %</label>
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

      <button type="button" class="no-print" onclick="generateQuote()">Generate Quote</button>
      <div id="error" class="error"></div>
    </div>

    <div id="invoicesTab" class="tab-panel">
      <h2>Invoices</h2>
      <div id="invoiceList" class="small">No invoices yet.</div>
    </div>

    <div id="customersTab" class="tab-panel">
      <h2>Customers</h2>
      <div id="customerList" class="small">No customers yet.</div>
    </div>
  </div>

  <div id="resultCard" class="card result quote-sheet">
    <div class="quote-header">
      <div class="quote-company">Nigel Harvey Ltd</div>
      <div class="quote-meta">
        125 Bushy Hill Drive, Guildford, GU1 2UG<br>
        07595 725547<br>
        Nigelharveyplumbing@gmail.com
      </div>
    </div>

    <div class="quote-section-title">Quote details</div>
    <div class="quote-box">
      <div class="row"><span class="muted">Date</span><span id="r_date"></span></div>
      <div class="row"><span class="muted">Type</span><span id="r_type"></span></div>
      <div class="row"><span class="muted">Customer</span><span id="r_customer"></span></div>
      <div class="row"><span class="muted">Phone</span><span id="r_phone"></span></div>
      <div class="row"><span class="muted">Address</span><span id="r_address"></span></div>
    </div>

    <div class="quote-section-title">Works</div>
    <div class="quote-box">
      <div id="r_job"></div>
    </div>

    <div class="quote-section-title">Price</div>
    <div class="quote-box">
      <div class="row"><span class="muted">Labour</span><span id="r_labour"></span></div>
      <div class="row"><span class="muted">Materials</span><span id="r_materials"></span></div>
      <div class="row"><span class="muted">Deposit</span><span id="r_deposit"></span></div>
      <div class="row quote-total"><span>Total price</span><span id="r_total"></span></div>
    </div>

    <div class="quote-section-title">Materials used</div>
    <div class="quote-box">
      <div id="r_material_lines" class="material-lines"></div>
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

    <div class="quote-section-title">Notes</div>
    <div class="quote-box">
      Includes labour and materials.<br>
      Payment due as agreed.<br>
      Quote subject to site conditions and any unforeseen issues.
    </div>

    <div class="actions no-print">
      <a id="whatsappBtn" class="btn-link btn-secondary" href="#" target="_blank">Send Quote to WhatsApp</a>
      <button class="btn-blue" onclick="convertCurrentQuoteToInvoice()">Convert to Invoice</button>
      <button class="btn-light" onclick="window.print()">Download / Print PDF</button>
    </div>
  </div>

  <div id="invoiceCard" class="card result invoice-sheet">
    <div class="quote-header">
      <div class="quote-company">Nigel Harvey Ltd</div>
      <div class="quote-meta">
        125 Bushy Hill Drive, Guildford, GU1 2UG<br>
        07595 725547<br>
        Nigelharveyplumbing@gmail.com
      </div>
    </div>

    <div class="quote-section-title">Invoice details</div>
    <div class="quote-box">
      <div class="row"><span class="muted">Invoice number</span><span id="i_number"></span></div>
      <div class="row"><span class="muted">Date</span><span id="i_date"></span></div>
      <div class="row"><span class="muted">Due date</span><span id="i_due_date"></span></div>
      <div class="row"><span class="muted">Status</span><span id="i_status"></span></div>
      <div class="row"><span class="muted">Customer</span><span id="i_customer"></span></div>
      <div class="row"><span class="muted">Phone</span><span id="i_phone"></span></div>
      <div class="row"><span class="muted">Address</span><span id="i_address"></span></div>
    </div>

    <div class="quote-section-title">Work</div>
    <div class="quote-box">
      <div id="i_job"></div>
    </div>

    <div class="quote-section-title">Invoice totals</div>
    <div class="quote-box">
      <div class="row"><span class="muted">Labour</span><span id="i_labour"></span></div>
      <div class="row"><span class="muted">Materials</span><span id="i_materials"></span></div>
      <div class="row"><span class="muted">Total</span><span id="i_total"></span></div>
      <div class="row"><span class="muted">Amount paid</span><span id="i_paid"></span></div>
      <div class="row quote-total"><span>Balance due</span><span id="i_balance"></span></div>
    </div>

    <div class="quote-section-title">Payment</div>
    <div class="quote-box">
      <div id="i_payment_link_box"></div>
      <div class="invoice-note">Please pay by the due date shown above.</div>
    </div>

    <div class="actions no-print">
      <a id="invoiceWhatsappBtn" class="btn-link btn-secondary" href="#" target="_blank">Send Invoice to WhatsApp</a>
      <button class="btn-light" onclick="window.print()">Download / Print Invoice PDF</button>
    </div>
  </div>

  <div class="card no-print">
    <h2>Saved Quotes</h2>
    <div id="historyList" class="small">No saved quotes yet.</div>
  </div>

</div>

<script>
const MATERIAL_LIBRARY = __MATERIAL_LIBRARY__;
const FAVOURITE_MATERIALS = __FAVOURITE_MATERIALS__;
const JOB_TEMPLATES = __JOB_TEMPLATES__;

let SAVED_QUOTES = [];
let SAVED_INVOICES = [];
let SAVED_CUSTOMERS = [];
let CURRENT_QUOTE_ID = null;
let CURRENT_QUOTE_DATA = null;
let CURRENT_INVOICE_ID = null;

function pounds(value) {
  return "£" + Number(value || 0).toFixed(2);
}

function escapeHtml(text) {
  return (text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function showTab(id) {
  document.querySelectorAll(".tab-panel").forEach(x => x.classList.remove("active"));
  document.getElementById(id).classList.add("active");
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

function applyTemplate(index) {
  const t = JOB_TEMPLATES[index];
  document.getElementById("quote_type").value = t.quote_type;
  document.getElementById("job").value = t.job;
  document.getElementById("labour").value = t.labour;
  toggleBathroomFields();
  updateLabourSuggestion();
}

function addFavouriteMaterial(index) {
  addMaterial(FAVOURITE_MATERIALS[index]);
}

function updateLabourSuggestion() {
  const quoteType = document.getElementById("quote_type").value;
  const text = document.getElementById("job").value.toLowerCase();
  const box = document.getElementById("labourSuggestion");

  let message = "Small jobs: use your judgement and minimum charge where needed.";
  if (quoteType === "bathroom") {
    message = "Typical bathroom labour is often higher. Adjust to suit your job.";
  } else if (quoteType === "heating") {
    message = "Heating jobs often vary by size and access. Adjust labour as needed.";
  }

  if (quoteType === "small" && text.includes("tap")) {
    message = "Suggested labour: around £120. Typical range: £100–£140.";
  }
  if (quoteType === "small" && (text.includes("toilet") || text.includes("wc"))) {
    message = "Suggested labour: around £180. Typical range: £160–£220.";
  }
  if (quoteType === "small" && (text.includes("waste") || text.includes("trap"))) {
    message = "Suggested labour: around £120. Typical range: £90–£140.";
  }
  if (quoteType === "small" && text.includes("outside tap")) {
    message = "Suggested labour: around £150. Typical range: £140–£180.";
  }
  if (quoteType === "bathroom" && text.includes("refurb")) {
    message = "Suggested labour: around £2,200. Typical range: £2,000–£2,800.";
  }
  if (quoteType === "bathroom" && text.includes("install")) {
    message = "Suggested labour: around £1,800. Typical range: £1,600–£2,200.";
  }
  if (quoteType === "heating" && text.includes("radiator")) {
    message = "Suggested labour: around £180. Typical range: £160–£220.";
  }
  if (quoteType === "heating" && text.includes("repair")) {
    message = "Suggested labour: around £150. Typical range: £120–£220.";
  }

  box.innerText = message;
}

function clearMaterials() {
  document.getElementById("materials").innerHTML = "";
}

function addMaterial(prefill = null) {
  const div = document.createElement("div");
  div.className = "material-row";

  const qty = prefill && prefill.quantity ? prefill.quantity : 1;
  const manualPrice = prefill && prefill.manual_price != null
    ? prefill.manual_price
    : (prefill && prefill.default_price != null ? prefill.default_price : "");

  div.innerHTML = `
    <label>Item name</label>
    <input class="m-name" placeholder="e.g. kitchen tap" value="${prefill ? escapeHtml(prefill.name) : ""}">

    <label>Quantity</label>
    <input class="m-qty" type="number" step="0.01" placeholder="1" value="${qty}">

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
    <input class="m-manual" type="number" step="0.01" placeholder="0" value="${manualPrice}">

    <button type="button" class="btn-red" style="margin-top:12px;" onclick="this.parentElement.remove()">Remove</button>
  `;
  document.getElementById("materials").appendChild(div);

  if (prefill) {
    div.querySelector(".m-supplier").value = prefill.supplier || "City Plumbing";
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

  const terms = query.split(" ").filter(Boolean);

  const results = MATERIAL_LIBRARY.filter(item => {
    const hay = (item.name + " " + item.supplier).toLowerCase();
    return terms.every(term => hay.includes(term));
  }).slice(0, 15);

  if (!results.length) {
    resultsBox.innerHTML = `<div class="search-item">No matches found</div>`;
    resultsBox.classList.remove("hidden");
    return;
  }

  resultsBox.innerHTML = results.map((item) => `
    <div class="search-item" onclick='addMaterialFromLibrary(${JSON.stringify(item)})'>
      <strong>${escapeHtml(item.name)}</strong><br>
      <span class="small">${escapeHtml(item.supplier)} · ${pounds(item.default_price)}</span>
    </div>
  `).join("");

  resultsBox.classList.remove("hidden");
}

function addMaterialFromLibrary(item) {
  addMaterial(item);
  document.getElementById("materialSearch").value = "";
  document.getElementById("searchResults").classList.add("hidden");
  document.getElementById("searchResults").innerHTML = "";
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
    materials.push({
      name: row.querySelector(".m-name").value,
      quantity: parseFloat(row.querySelector(".m-qty").value || 1),
      supplier: row.querySelector(".m-supplier").value,
      url: row.querySelector(".m-url").value,
      manual_price: parseFloat(row.querySelector(".m-manual").value || 0)
    });
  });

  return {
    quote_type: document.getElementById("quote_type").value,
    customer_name: document.getElementById("customer_name").value,
    customer_address: document.getElementById("customer_address").value,
    customer_phone: document.getElementById("customer_phone").value,
    job_description: document.getElementById("job").value,
    labour_cost: parseFloat(document.getElementById("labour").value || 0),
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
  document.getElementById("r_materials").innerText = pounds(data.materials);
  document.getElementById("r_deposit").innerText = data.deposit_amount ? pounds(data.deposit_amount) + " (" + Number(data.deposit_percent).toFixed(0) + "%)" : "£0.00";
  document.getElementById("r_total").innerText = pounds(data.total_price);

  const lines = data.material_lines || [];
  document.getElementById("r_material_lines").innerHTML = lines.length
    ? lines.map(x => `<div>${escapeHtml(x.name || "")} × ${x.quantity} — ${pounds(x.line_total)} ${x.live_price_used ? '<span class="badge green">live</span>' : '<span class="badge">manual</span>'}</div>`).join("")
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

  const message =
`Nigel Harvey Ltd Quote

Date: ${data.created_at || "-"}
Type: ${data.quote_type || "-"}
Customer: ${data.customer_name || "-"}
Address: ${data.customer_address || "-"}

Job: ${data.job || "-"}

Labour: ${pounds(data.labour)}
Materials: ${pounds(data.materials)}
Total price: ${pounds(data.total_price)}

Nigel Harvey Ltd
${"07595 725547"}
${"Nigelharveyplumbing@gmail.com"}`;

  const cleanPhone = normalisePhone(data.customer_phone || "");
  document.getElementById("whatsappBtn").href = cleanPhone
    ? "https://wa.me/" + cleanPhone + "?text=" + encodeURIComponent(message)
    : "https://wa.me/?text=" + encodeURIComponent(message);

  document.getElementById("resultCard").style.display = "block";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderInvoiceCard(item) {
  CURRENT_INVOICE_ID = item.id;
  document.getElementById("resultCard").style.display = "none";
  document.getElementById("invoiceCard").style.display = "block";

  const invoice = item.invoice;
  const quoteResult = item.quote_result;

  document.getElementById("i_number").innerText = item.invoice_number || "-";
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

  const paymentBox = document.getElementById("i_payment_link_box");
  if (item.payment_link) {
    paymentBox.innerHTML = `<div><strong>Payment link:</strong> <a href="${item.payment_link}" target="_blank">${escapeHtml(item.payment_link)}</a></div>`;
  } else {
    paymentBox.innerHTML = `<div>No online payment link set yet.</div>`;
  }

  const msg =
`Nigel Harvey Ltd Invoice

Invoice: ${item.invoice_number}
Date: ${item.created_at}
Due date: ${item.due_date}
Customer: ${invoice.customer_name || "-"}
Address: ${invoice.customer_address || "-"}

Job: ${invoice.job || "-"}

Total: ${pounds(item.total_price)}
Paid: ${pounds(item.amount_paid)}
Balance due: ${pounds(item.balance_due)}

Nigel Harvey Ltd
07595 725547
Nigelharveyplumbing@gmail.com${item.payment_link ? "\nPayment link: " + item.payment_link : ""}`;

  const cleanPhone = normalisePhone(invoice.customer_phone || quoteResult.customer_phone || "");
  document.getElementById("invoiceWhatsappBtn").href = cleanPhone
    ? "https://wa.me/" + cleanPhone + "?text=" + encodeURIComponent(msg)
    : "https://wa.me/?text=" + encodeURIComponent(msg);

  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderStatusBadge(status) {
  const s = (status || "").toLowerCase();
  if (s === "paid") return '<span class="badge green">Paid</span>';
  if (s === "part paid") return '<span class="badge orange">Part Paid</span>';
  return '<span class="badge red">Unpaid</span>';
}

function fillFormFromRequest(requestData, quoteId = null) {
  document.getElementById("quote_type").value = requestData.quote_type || "small";
  document.getElementById("customer_name").value = requestData.customer_name || "";
  document.getElementById("customer_address").value = requestData.customer_address || "";
  document.getElementById("customer_phone").value = requestData.customer_phone || "";
  document.getElementById("job").value = requestData.job_description || "";
  document.getElementById("labour").value = requestData.labour_cost || "";
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
  else addMaterial();

  CURRENT_QUOTE_ID = quoteId;
  if (quoteId) setEditingStatus("Loaded saved quote #" + quoteId, true);
  else setEditingStatus("", false);

  toggleBathroomFields();
  updateLabourSuggestion();
  showTab("quotesTab");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function loadDashboard() {
  try {
    const res = await fetch("/api/dashboard");
    const data = await res.json();
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
  } catch (e) {}
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

        <label style="margin-top:10px;">Update payment</label>
        <div class="row">
          <input id="paid_${i.id}" type="number" step="0.01" placeholder="Amount paid" value="${i.amount_paid || 0}">
          <button type="button" class="btn-blue" style="max-width:180px;" onclick="updateInvoicePaid(${i.id})">Save</button>
        </div>

        <div class="history-actions">
          <button type="button" class="btn-light" onclick="openInvoice(${i.id})">Open</button>
          <button type="button" class="btn-secondary" onclick="sendInvoiceWhatsApp(${i.id})">WhatsApp</button>
          <button type="button" class="btn-light" onclick="printInvoice(${i.id})">Print</button>
          <button type="button" class="btn-red" onclick="deleteInvoice(${i.id})">Delete</button>
        </div>
      </div>
    `).join("");
  } catch (e) {
    document.getElementById("invoiceList").innerHTML = "Unable to load invoices.";
  }
}

async function loadCustomers() {
  try {
    const res = await fetch("/api/customers");
    const data = await res.json();
    SAVED_CUSTOMERS = data;
    const box = document.getElementById("customerList");

    if (!data.length) {
      box.innerHTML = "No customers yet.";
      return;
    }

    box.innerHTML = data.map(c => `
      <div class="history-item">
        <div><strong>${escapeHtml(c.name || "No customer name")}</strong></div>
        <div>${escapeHtml(c.phone || "")}</div>
        <div class="small">${escapeHtml(c.address || "")}</div>
        <div class="history-actions" style="grid-template-columns:1fr 1fr;">
          <button type="button" class="btn-light" onclick="viewCustomerHistory(${c.id})">View History</button>
          <button type="button" class="btn-light" onclick="startQuoteForCustomer(${c.id})">Start Quote</button>
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

    box.innerHTML = `
      <div><strong>Quotes:</strong> ${quotes.length}</div>
      ${quotes.slice(0,5).map(q => `<div>• ${escapeHtml(q.created_at)} — ${escapeHtml(q.job || "")} — ${pounds(q.total_price)}</div>`).join("") || "<div>None</div>"}
      <div style="margin-top:8px;"><strong>Invoices:</strong> ${invoices.length}</div>
      ${invoices.slice(0,5).map(i => `<div>• ${escapeHtml(i.invoice_number)} — ${pounds(i.total_price)} — ${escapeHtml(i.status)}</div>`).join("") || "<div>None</div>"}
    `;
  } catch (e) {
    alert("Could not load customer history.");
  }
}

function startQuoteForCustomer(id) {
  const c = SAVED_CUSTOMERS.find(x => x.id === id);
  if (!c) return;
  showTab("quotesTab");
  document.getElementById("customer_name").value = c.name || "";
  document.getElementById("customer_address").value = c.address || "";
  document.getElementById("customer_phone").value = c.phone || "";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function loadSavedQuote(id) {
  try {
    const res = await fetch("/api/quotes/" + id);
    if (!res.ok) throw new Error();
    const data = await res.json();
    fillFormFromRequest(data.request, data.id);
    renderQuoteResult(data.result);
  } catch (e) {
    alert("Could not load saved quote.");
  }
}

async function sendSavedQuoteWhatsApp(id) {
  try {
    const res = await fetch("/api/quotes/" + id);
    if (!res.ok) throw new Error();
    const data = await res.json();
    renderQuoteResult(data.result);
    document.getElementById("whatsappBtn").click();
  } catch (e) {
    alert("Could not open WhatsApp for this quote.");
  }
}

async function printSavedQuote(id) {
  try {
    const res = await fetch("/api/quotes/" + id);
    if (!res.ok) throw new Error();
    const data = await res.json();
    renderQuoteResult(data.result);
    window.print();
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
    await loadDashboard();
  } catch (e) {
    alert("Could not delete saved quote.");
  }
}

async function generateQuote() {
  const errorBox = document.getElementById("error");
  errorBox.style.display = "none";

  const payload = collectFormPayload();

  try {
    const res = await fetch("/api/quote", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });

    if (!res.ok) throw new Error();
    const data = await res.json();

    CURRENT_QUOTE_ID = data.id || null;
    setEditingStatus(CURRENT_QUOTE_ID ? "Saved quote #" + CURRENT_QUOTE_ID : "", !!CURRENT_QUOTE_ID);

    renderQuoteResult(data.result);
    await loadHistory();
    await loadCustomers();
    await loadDashboard();
  } catch (err) {
    errorBox.innerText = "Something went wrong generating the quote.";
    errorBox.style.display = "block";
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
  } catch (e) {
    alert("Could not update invoice.");
  }
}

async function deleteInvoice(id) {
  if (!confirm("Delete this invoice?")) return;
  try {
    const res = await fetch("/api/invoices/" + id, { method: "DELETE" });
    if (!res.ok) throw new Error();
    await loadInvoices();
    await loadDashboard();
  } catch (e) {
    alert("Could not delete invoice.");
  }
}

toggleBathroomFields();
renderTemplates();
renderFavourites();
addMaterial();
updateLabourSuggestion();
loadDashboard();
loadHistory();
loadInvoices();
loadCustomers();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def home():
    html = HTML.replace("__MATERIAL_LIBRARY__", json.dumps(MATERIAL_LIBRARY))
    html = html.replace("__FAVOURITE_MATERIALS__", json.dumps(FAVOURITE_MATERIALS))
    html = html.replace("__JOB_TEMPLATES__", json.dumps(JOB_TEMPLATES))
    return HTMLResponse(content=html)


@app.get("/api/dashboard")
def api_dashboard():
    return get_dashboard()


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


@app.post("/api/quote")
def api_create_quote(data: QuoteRequest):
    request_data = data.model_dump()
    result_data = calculate_quote(data)
    quote_id = save_quote(request_data, result_data)
    quote = get_quote_by_id(quote_id)
    return JSONResponse(content=quote)


@app.post("/api/quotes/{quote_id}/to-invoice")
def api_quote_to_invoice(quote_id: int):
    invoice = create_invoice_from_quote(quote_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Quote not found")
    return invoice


@app.get("/api/invoices")
def api_invoices():
    return load_invoices()


@app.get("/api/invoices/{invoice_id}")
def api_invoice(invoice_id: int):
    invoice = get_invoice_by_id(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@app.post("/api/invoices/{invoice_id}/status")
def api_invoice_status(invoice_id: int, data: InvoiceStatusRequest):
    invoice = update_invoice_status(invoice_id, data.status, data.amount_paid)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@app.delete("/api/invoices/{invoice_id}")
def api_delete_invoice(invoice_id: int):
    if not delete_invoice_by_id(invoice_id):
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {"ok": True}


@app.get("/api/customers")
def api_customers():
    return get_customers()


@app.get("/api/customers/{customer_id}/history")
def api_customer_history(customer_id: int):
    history = get_customer_history(customer_id)
    if not history:
        raise HTTPException(status_code=404, detail="Customer not found")
    return history

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup
import re
import json
import sqlite3
from pathlib import Path

app = FastAPI(title="Nigel Harvey Ltd Quotes")

DB_PATH = Path("quotes.db")
UK_TZ = ZoneInfo("Europe/London")


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


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT,
            job TEXT,
            total_price REAL,
            created_at TEXT NOT NULL,
            created_at_sort TEXT NOT NULL,
            request_json TEXT NOT NULL,
            result_json TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


@app.on_event("startup")
def startup():
    init_db()


def row_to_history_item(row):
    result = json.loads(row["result_json"])
    request_data = json.loads(row["request_json"])
    return {
        "id": row["id"],
        "customer_name": row["customer_name"] or "",
        "job": row["job"] or "",
        "total_price": row["total_price"] or 0,
        "created_at": row["created_at"],
        "request": request_data,
        "result": result,
    }


def save_quote(request_data: dict, result_data: dict):
    conn = get_db()
    conn.execute(
        """
        INSERT INTO quotes (
            customer_name, job, total_price, created_at, created_at_sort, request_json, result_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            result_data.get("customer_name", ""),
            result_data.get("job", ""),
            result_data.get("total_price", 0),
            result_data.get("created_at", ""),
            result_data.get("created_at_sort", ""),
            json.dumps(request_data),
            json.dumps(result_data),
        )
    )
    conn.commit()
    conn.close()


def load_quotes():
    conn = get_db()
    rows = conn.execute("""
        SELECT *
        FROM quotes
        ORDER BY created_at_sort DESC, id DESC
        LIMIT 200
    """).fetchall()
    conn.close()
    return [row_to_history_item(row) for row in rows]


def get_quote_by_id(quote_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM quotes WHERE id = ?", (quote_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return row_to_history_item(row)


def delete_quote_by_id(quote_id: int):
    conn = get_db()
    cur = conn.execute("DELETE FROM quotes WHERE id = ?", (quote_id,))
    conn.commit()
    deleted = cur.rowcount
    conn.close()
    return deleted > 0


def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def fetch_price(url: str):
    if not url:
        return None

    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "en-GB,en;q=0.9"
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
        if "cityplumbing" in url.lower():
            domain_patterns = [
                r'£\s?(\d+(?:\.\d{2})?)\s*each,\s*Inc\.?\s*VAT',
                r'£\s?(\d+(?:\.\d{2})?)\s*Inc\.?\s*VAT',
                r'£\s?(\d+(?:\.\d{2})?)\s*each',
            ]
        elif "toppstiles" in url.lower():
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


def calculate_quote(data: QuoteRequest):
    raw_materials = 0.0

    for item in data.materials:
        url = item.url.strip() if item.url else ""
        price = fetch_price(url) if url else None
        if price is None:
            price = item.manual_price or 0
        raw_materials += price * item.quantity

    tiling_extra_materials = 0.0
    if data.quote_type == "bathroom" and data.tiling:
        if not data.customer_supplies_tiles:
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

    job_text = data.job_description.strip()
    if data.tiling and data.quote_type == "bathroom":
        job_text = f"{job_text} + Tiling" if job_text else "Bathroom works + Tiling"

    hidden_uplift = quoted_materials - raw_materials_with_tiling

    now = datetime.now(UK_TZ)

    return {
        "quote_type": data.quote_type,
        "customer_name": data.customer_name,
        "customer_address": data.customer_address,
        "customer_phone": data.customer_phone,
        "job": job_text,
        "labour": round(labour_total, 2),
        "materials": round(quoted_materials, 2),
        "total_price": round(total_price, 2),
        "created_at": now.strftime("%d/%m/%Y %H:%M"),
        "created_at_sort": now.isoformat(),
        "internal_raw_materials": round(raw_materials_with_tiling, 2),
        "internal_job_multiplier": round(job_multiplier, 2),
        "internal_after_job_markup": round(materials_after_job_markup, 2),
        "internal_handling_percent": round(handling_percent, 2),
        "internal_after_handling": round(quoted_materials, 2),
        "internal_hidden_uplift": round(hidden_uplift, 2),
    }


HTML = r"""
<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nigel Harvey Ltd Quotes</title>
<style>
body { font-family: Arial, sans-serif; background:#f5f5f5; margin:0; padding:12px; color:#111; }
.wrap { max-width:960px; margin:0 auto; }
.card { background:white; padding:16px; border-radius:14px; margin-bottom:14px; box-shadow:0 2px 10px rgba(0,0,0,0.06); }
h1 { margin:0 0 6px 0; font-size:30px; }
h2 { margin:0 0 12px 0; font-size:22px; }
h3 { margin:18px 0 8px 0; }
.sub { color:#666; margin-bottom:16px; }
label { display:block; font-weight:700; margin:12px 0 6px; }
input, textarea, select { width:100%; box-sizing:border-box; padding:12px; border:1px solid #ccc; border-radius:10px; font-size:16px; background:white; }
textarea { min-height:100px; resize:vertical; }
button, .btn-link { width:100%; padding:14px; border:none; border-radius:10px; background:black; color:white; font-size:18px; font-weight:700; text-align:center; text-decoration:none; display:inline-block; box-sizing:border-box; cursor:pointer; }
.btn-secondary { background:#1f7a1f; }
.btn-light { background:#ececec; color:#111; }
.btn-red { background:#b62323; color:white; }
.btn-template { background:#333; font-size:15px; padding:10px; }
.templates { display:grid; grid-template-columns:repeat(2, 1fr); gap:8px; }
.material-row { border:1px solid #ddd; padding:12px; border-radius:10px; margin-bottom:10px; background:#fafafa; }
.row { display:flex; justify-content:space-between; gap:10px; margin:8px 0; }
.muted { color:#666; }
.result { display:none; background:#f3faf3; border:1px solid #b7d7b7; }
.error { display:none; background:#fff3f3; border:1px solid #e0b7b7; color:#a33; padding:12px; border-radius:10px; margin-top:12px; }
.actions { display:grid; gap:10px; margin-top:14px; }
.history-item { border:1px solid #ddd; border-radius:10px; padding:12px; margin-bottom:10px; background:#fafafa; }
.history-actions { display:grid; grid-template-columns:repeat(2, 1fr); gap:8px; margin-top:10px; }
.history-actions button { font-size:15px; padding:10px; }
.small { font-size:14px; color:#666; }
.hidden { display:none; }
.check-row { display:flex; align-items:center; gap:10px; margin:12px 0 6px; font-weight:700; }
.check-row input[type="checkbox"] { width:auto; transform:scale(1.2); }
.quote-sheet { background:white; }
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

  <div class="card no-print">
    <h1>Nigel Harvey Ltd Quotes</h1>
    <div class="sub">Quick quote tool</div>
    <div id="editingStatus" class="status-bar hidden"></div>

    <div class="check-row">
      <input type="checkbox" id="internal_mode">
      <span>Internal mode</span>
    </div>

    <h3>Job templates</h3>
    <div id="templateButtons" class="templates"></div>

    <label for="quote_type">Quote type</label>
    <select id="quote_type" onchange="toggleBathroomFields()">
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
    <textarea id="job" placeholder="Example: Replace kitchen tap"></textarea>

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
    <button type="button" onclick="addMaterial()">+ Add Manual Material Row</button>

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

    <button type="button" onclick="generateQuote()">Generate Quote</button>

    <div id="error" class="error"></div>
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
      <div class="row quote-total"><span>Total price</span><span id="r_total"></span></div>
    </div>

    <div id="internalBox" class="quote-box internal-box hidden">
      <div class="quote-section-title" style="margin-top:0;">Internal only</div>
      <div class="row"><span class="muted">Raw materials</span><span id="r_internal_raw"></span></div>
      <div class="row"><span class="muted">Job multiplier</span><span id="r_internal_job_multiplier"></span></div>
      <div class="row"><span class="muted">After job markup</span><span id="r_internal_after_job"></span></div>
      <div class="row"><span class="muted">Handling %</span><span id="r_internal_handling_percent"></span></div>
      <div class="row"><span class="muted">After handling</span><span id="r_internal_after_handling"></span></div>
      <div class="row"><span class="muted">Hidden uplift</span><span id="r_internal_hidden_uplift"></span></div>
    </div>

    <div class="quote-section-title">Notes</div>
    <div class="quote-box">
      Includes labour and materials.<br>
      Payment due as agreed.<br>
      Quote subject to site conditions and any unforeseen issues.
    </div>

    <div class="actions no-print">
      <a id="whatsappBtn" class="btn-link btn-secondary" href="#" target="_blank">Send direct to customer WhatsApp</a>
      <button class="btn-light" onclick="window.print()">Download / Print PDF</button>
    </div>
  </div>

  <div class="card no-print">
    <h2>Saved Quotes</h2>
    <div id="historyList" class="small">No saved quotes yet.</div>
  </div>

</div>

<script>
const MATERIAL_LIBRARY = __MATERIAL_LIBRARY__;
const JOB_TEMPLATES = __JOB_TEMPLATES__;
let SAVED_QUOTES = [];
let CURRENT_HISTORY_ID = null;

function pounds(value) {
  return "£" + Number(value || 0).toFixed(2);
}

function escapeHtml(text) {
  return (text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function toggleBathroomFields() {
  const quoteType = document.getElementById("quote_type").value;
  const bathroomFields = document.getElementById("bathroomFields");

  if (quoteType === "bathroom") {
    bathroomFields.classList.remove("hidden");
  } else {
    bathroomFields.classList.add("hidden");
  }
}

function renderTemplates() {
  const box = document.getElementById("templateButtons");
  box.innerHTML = JOB_TEMPLATES.map((t, i) => `
    <button type="button" class="btn-template" onclick="applyTemplate(${i})">${escapeHtml(t.name)}</button>
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

function updateLabourSuggestion() {
  const quoteType = document.getElementById("quote_type").value;
  const box = document.getElementById("labourSuggestion");

  if (quoteType === "bathroom") {
    box.innerText = "Typical bathroom labour is often higher. Adjust to suit your job.";
  } else if (quoteType === "heating") {
    box.innerText = "Heating jobs often vary by size and access. Adjust labour as needed.";
  } else {
    box.innerText = "Small jobs: use your judgement and minimum charge where needed.";
  }
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
    customer_supplies_tiles: document.getElementById("customer_supplies_tiles").checked
  };
}

function renderQuoteResult(data) {
  const resultCard = document.getElementById("resultCard");
  const internalBox = document.getElementById("internalBox");
  const internalMode = document.getElementById("internal_mode").checked;

  document.getElementById("r_date").innerText = data.created_at || "-";
  document.getElementById("r_type").innerText = data.quote_type || "-";
  document.getElementById("r_customer").innerText = data.customer_name || "-";
  document.getElementById("r_phone").innerText = data.customer_phone || "-";
  document.getElementById("r_address").innerText = data.customer_address || "-";
  document.getElementById("r_job").innerText = data.job || "-";
  document.getElementById("r_labour").innerText = pounds(data.labour);
  document.getElementById("r_materials").innerText = pounds(data.materials);
  document.getElementById("r_total").innerText = pounds(data.total_price);

  if (internalMode) {
    internalBox.classList.remove("hidden");
    document.getElementById("r_internal_raw").innerText = pounds(data.internal_raw_materials);
    document.getElementById("r_internal_job_multiplier").innerText = data.internal_job_multiplier + "x";
    document.getElementById("r_internal_after_job").innerText = pounds(data.internal_after_job_markup);
    document.getElementById("r_internal_handling_percent").innerText = data.internal_handling_percent + "%";
    document.getElementById("r_internal_after_handling").innerText = pounds(data.internal_after_handling);
    document.getElementById("r_internal_hidden_uplift").innerText = pounds(data.internal_hidden_uplift);
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
07595 725547
Nigelharveyplumbing@gmail.com`;

  const cleanPhone = normalisePhone(data.customer_phone || "");
  document.getElementById("whatsappBtn").href = cleanPhone
    ? "https://wa.me/" + cleanPhone + "?text=" + encodeURIComponent(message)
    : "https://wa.me/?text=" + encodeURIComponent(message);

  resultCard.style.display = "block";
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

  clearMaterials();
  const materials = requestData.materials || [];
  if (materials.length) {
    materials.forEach(item => addMaterial(item));
  } else {
    addMaterial();
  }

  CURRENT_HISTORY_ID = quoteId;
  if (quoteId) {
    setEditingStatus("Editing saved quote #" + quoteId, true);
  } else {
    setEditingStatus("", false);
  }

  toggleBathroomFields();
  updateLabourSuggestion();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function loadHistory() {
  try {
    const res = await fetch("/quotes");
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
        <div class="small">${escapeHtml(q.created_at || "")} · Total ${pounds(q.total_price)}</div>

        <div class="history-actions">
          <button type="button" class="btn-light" onclick="loadSavedQuote(${q.id})">Load</button>
          <button type="button" class="btn-secondary" onclick="sendSavedQuoteWhatsApp(${q.id})">WhatsApp</button>
          <button type="button" class="btn-light" onclick="printSavedQuote(${q.id})">Print</button>
          <button type="button" class="btn-red" onclick="deleteSavedQuote(${q.id})">Delete</button>
        </div>
      </div>
    `).join("");
  } catch (e) {
    document.getElementById("historyList").innerHTML = "Unable to load saved quotes.";
  }
}

async function loadSavedQuote(id) {
  try {
    const res = await fetch("/quotes/" + id);
    if (!res.ok) throw new Error("Unable to load quote");
    const data = await res.json();
    fillFormFromRequest(data.request, data.id);
    renderQuoteResult(data.result);
  } catch (e) {
    alert("Could not load saved quote.");
  }
}

async function sendSavedQuoteWhatsApp(id) {
  try {
    const res = await fetch("/quotes/" + id);
    if (!res.ok) throw new Error("Unable to load quote");
    const data = await res.json();
    renderQuoteResult(data.result);
    document.getElementById("whatsappBtn").click();
  } catch (e) {
    alert("Could not open WhatsApp for this saved quote.");
  }
}

async function printSavedQuote(id) {
  try {
    const res = await fetch("/quotes/" + id);
    if (!res.ok) throw new Error("Unable to load quote");
    const data = await res.json();
    renderQuoteResult(data.result);
    window.print();
  } catch (e) {
    alert("Could not print this saved quote.");
  }
}

async function deleteSavedQuote(id) {
  const ok = confirm("Delete this saved quote?");
  if (!ok) return;

  try {
    const res = await fetch("/quotes/" + id, { method: "DELETE" });
    if (!res.ok) throw new Error("Delete failed");

    if (CURRENT_HISTORY_ID === id) {
      CURRENT_HISTORY_ID = null;
      setEditingStatus("", false);
    }

    await loadHistory();
  } catch (e) {
    alert("Could not delete saved quote.");
  }
}

async function generateQuote() {
  const errorBox = document.getElementById("error");
  errorBox.style.display = "none";

  const payload = collectFormPayload();

  try {
    const res = await fetch("/quote", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });

    if (!res.ok) throw new Error("Quote request failed");

    const data = await res.json();
    CURRENT_HISTORY_ID = data.id || null;
    if (CURRENT_HISTORY_ID) {
      setEditingStatus("Editing saved quote #" + CURRENT_HISTORY_ID, true);
    }

    renderQuoteResult(data.result);
    await loadHistory();
  } catch (err) {
    errorBox.innerText = "Something went wrong generating the quote.";
    errorBox.style.display = "block";
  }
}

toggleBathroomFields();
renderTemplates();
addMaterial();
updateLabourSuggestion();
document.getElementById("quote_type").addEventListener("change", updateLabourSuggestion);
loadHistory();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def home():
    html = HTML.replace("__MATERIAL_LIBRARY__", json.dumps(MATERIAL_LIBRARY))
    html = html.replace("__JOB_TEMPLATES__", json.dumps(JOB_TEMPLATES))
    return HTMLResponse(content=html)


@app.get("/quotes")
def get_quotes():
    return load_quotes()


@app.get("/quotes/{quote_id}")
def get_quote(quote_id: int):
    quote = get_quote_by_id(quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    return quote


@app.delete("/quotes/{quote_id}")
def delete_quote(quote_id: int):
    deleted = delete_quote_by_id(quote_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Quote not found")
    return {"ok": True}


@app.post("/quote")
def create_quote(data: QuoteRequest):
    request_data = data.model_dump()
    result_data = calculate_quote(data)
    save_quote(request_data, result_data)

    latest = load_quotes()
    latest_item = latest[0] if latest else None

    return JSONResponse(content=latest_item or {
        "id": None,
        "request": request_data,
        "result": result_data,
    })

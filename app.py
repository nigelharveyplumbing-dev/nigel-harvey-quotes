from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import re
import json

app = FastAPI(title="Nigel Harvey Ltd Quotes")

quotes_db = []

MATERIAL_LIBRARY = [
    {
        "name": "15mm Copper Pipe 3m",
        "supplier": "City Plumbing",
        "default_price": 18.00,
        "product_url": ""
    },
    {
        "name": "22mm Copper Pipe 3m",
        "supplier": "City Plumbing",
        "default_price": 32.00,
        "product_url": ""
    },
    {
        "name": "15mm Copper Elbow",
        "supplier": "Screwfix",
        "default_price": 1.20,
        "product_url": ""
    },
    {
        "name": "22mm Copper Elbow",
        "supplier": "Screwfix",
        "default_price": 2.10,
        "product_url": ""
    },
    {
        "name": "15mm Copper Tee",
        "supplier": "Screwfix",
        "default_price": 1.80,
        "product_url": ""
    },
    {
        "name": "22mm Copper Tee",
        "supplier": "Screwfix",
        "default_price": 3.20,
        "product_url": ""
    },
    {
        "name": "15mm Straight Coupler",
        "supplier": "Toolstation",
        "default_price": 1.10,
        "product_url": ""
    },
    {
        "name": "22mm Straight Coupler",
        "supplier": "Toolstation",
        "default_price": 1.90,
        "product_url": ""
    },
    {
        "name": "15mm Isolating Valve",
        "supplier": "Toolstation",
        "default_price": 3.50,
        "product_url": ""
    },
    {
        "name": "22mm Isolating Valve",
        "supplier": "Toolstation",
        "default_price": 5.50,
        "product_url": ""
    },
    {
        "name": "Flexible Tap Connector",
        "supplier": "Screwfix",
        "default_price": 6.50,
        "product_url": ""
    },
    {
        "name": "Sink Waste Kit",
        "supplier": "City Plumbing",
        "default_price": 22.00,
        "product_url": ""
    },
    {
        "name": "Basin Waste",
        "supplier": "City Plumbing",
        "default_price": 14.00,
        "product_url": ""
    },
    {
        "name": "Pop Up Basin Waste",
        "supplier": "City Plumbing",
        "default_price": 18.00,
        "product_url": ""
    },
    {
        "name": "P Trap 1.5in",
        "supplier": "Toolstation",
        "default_price": 7.50,
        "product_url": ""
    },
    {
        "name": "Bottle Trap Chrome",
        "supplier": "City Plumbing",
        "default_price": 24.00,
        "product_url": ""
    },
    {
        "name": "Outside Tap Kit",
        "supplier": "Screwfix",
        "default_price": 18.00,
        "product_url": ""
    },
    {
        "name": "Washing Machine Valve",
        "supplier": "Toolstation",
        "default_price": 6.00,
        "product_url": ""
    },
    {
        "name": "Service Valve",
        "supplier": "Screwfix",
        "default_price": 4.00,
        "product_url": ""
    },
    {
        "name": "Compression Coupler 15mm",
        "supplier": "Toolstation",
        "default_price": 1.80,
        "product_url": ""
    },
    {
        "name": "Compression Coupler 22mm",
        "supplier": "Toolstation",
        "default_price": 2.90,
        "product_url": ""
    },
    {
        "name": "Hep2O 15mm Pipe Coil",
        "supplier": "City Plumbing",
        "default_price": 65.00,
        "product_url": ""
    },
    {
        "name": "Hep2O 22mm Pipe Coil",
        "supplier": "City Plumbing",
        "default_price": 95.00,
        "product_url": ""
    },
    {
        "name": "Hep2O 15mm Straight Coupler",
        "supplier": "City Plumbing",
        "default_price": 4.50,
        "product_url": ""
    },
    {
        "name": "Hep2O 22mm Straight Coupler",
        "supplier": "City Plumbing",
        "default_price": 6.80,
        "product_url": ""
    },
    {
        "name": "Hep2O 15mm Elbow",
        "supplier": "City Plumbing",
        "default_price": 5.20,
        "product_url": ""
    },
    {
        "name": "Hep2O 22mm Elbow",
        "supplier": "City Plumbing",
        "default_price": 7.20,
        "product_url": ""
    },
    {
        "name": "Hep2O 15mm Tee",
        "supplier": "City Plumbing",
        "default_price": 6.00,
        "product_url": ""
    },
    {
        "name": "Hep2O 22mm Tee",
        "supplier": "City Plumbing",
        "default_price": 8.50,
        "product_url": ""
    },
    {
        "name": "Hep2O Pipe Insert 15mm",
        "supplier": "City Plumbing",
        "default_price": 0.80,
        "product_url": ""
    },
    {
        "name": "Hep2O Pipe Insert 22mm",
        "supplier": "City Plumbing",
        "default_price": 1.20,
        "product_url": ""
    },
    {
        "name": "Speedfit 15mm Pipe Coil",
        "supplier": "Screwfix",
        "default_price": 58.00,
        "product_url": ""
    },
    {
        "name": "Speedfit 22mm Pipe Coil",
        "supplier": "Screwfix",
        "default_price": 90.00,
        "product_url": ""
    },
    {
        "name": "Speedfit 15mm Straight Coupler",
        "supplier": "Screwfix",
        "default_price": 4.20,
        "product_url": ""
    },
    {
        "name": "Speedfit 22mm Straight Coupler",
        "supplier": "Screwfix",
        "default_price": 6.20,
        "product_url": ""
    },
    {
        "name": "Speedfit 15mm Elbow",
        "supplier": "Screwfix",
        "default_price": 5.00,
        "product_url": ""
    },
    {
        "name": "Speedfit 22mm Elbow",
        "supplier": "Screwfix",
        "default_price": 7.00,
        "product_url": ""
    },
    {
        "name": "Speedfit 15mm Tee",
        "supplier": "Screwfix",
        "default_price": 5.80,
        "product_url": ""
    },
    {
        "name": "Speedfit 22mm Tee",
        "supplier": "Screwfix",
        "default_price": 8.00,
        "product_url": ""
    },
    {
        "name": "Speedfit Female Iron 15mm x 1/2",
        "supplier": "Screwfix",
        "default_price": 7.20,
        "product_url": ""
    },
    {
        "name": "Speedfit Male Iron 15mm x 1/2",
        "supplier": "Screwfix",
        "default_price": 7.20,
        "product_url": ""
    },
    {
        "name": "Speedfit Stop End 15mm",
        "supplier": "Screwfix",
        "default_price": 3.00,
        "product_url": ""
    },
    {
        "name": "Speedfit Pipe Insert 15mm",
        "supplier": "Screwfix",
        "default_price": 0.75,
        "product_url": ""
    },
    {
        "name": "Speedfit Pipe Insert 22mm",
        "supplier": "Screwfix",
        "default_price": 1.10,
        "product_url": ""
    },
    {
        "name": "Kitchen Mixer Tap",
        "supplier": "City Plumbing",
        "default_price": 85.00,
        "product_url": ""
    },
    {
        "name": "Basin Mixer Tap",
        "supplier": "City Plumbing",
        "default_price": 65.00,
        "product_url": ""
    },
    {
        "name": "Bath Mixer Tap",
        "supplier": "City Plumbing",
        "default_price": 95.00,
        "product_url": ""
    },
    {
        "name": "Thermostatic Shower Valve",
        "supplier": "City Plumbing",
        "default_price": 140.00,
        "product_url": ""
    },
    {
        "name": "Toilet Fill Valve",
        "supplier": "Screwfix",
        "default_price": 12.00,
        "product_url": ""
    },
    {
        "name": "Toilet Flush Valve",
        "supplier": "Screwfix",
        "default_price": 18.00,
        "product_url": ""
    },
    {
        "name": "Silicone",
        "supplier": "Toolstation",
        "default_price": 8.00,
        "product_url": ""
    },
    {
        "name": "Tile Adhesive 20kg",
        "supplier": "Topps Tiles",
        "default_price": 22.00,
        "product_url": ""
    },
    {
        "name": "Tile Grout 5kg",
        "supplier": "Topps Tiles",
        "default_price": 14.00,
        "product_url": ""
    },
    {
        "name": "Tile Trim 2.5m",
        "supplier": "Topps Tiles",
        "default_price": 9.00,
        "product_url": ""
    },
    {
        "name": "Ceramic Wall Tile per m2",
        "supplier": "Topps Tiles",
        "default_price": 25.00,
        "product_url": ""
    },
    {
        "name": "Porcelain Floor Tile per m2",
        "supplier": "Topps Tiles",
        "default_price": 35.00,
        "product_url": ""
    },
    {
        "name": "TRV Valve",
        "supplier": "Screwfix",
        "default_price": 14.00,
        "product_url": ""
    },
    {
        "name": "Lockshield Valve",
        "supplier": "Screwfix",
        "default_price": 8.00,
        "product_url": ""
    },
    {
        "name": "Radiator Valve Set",
        "supplier": "Screwfix",
        "default_price": 20.00,
        "product_url": ""
    },
    {
        "name": "Motorised Valve",
        "supplier": "City Plumbing",
        "default_price": 65.00,
        "product_url": ""
    },
    {
        "name": "Magnetic Filter",
        "supplier": "City Plumbing",
        "default_price": 95.00,
        "product_url": ""
    },
    {
        "name": "Inhibitor 1L",
        "supplier": "Toolstation",
        "default_price": 16.00,
        "product_url": ""
    },
    {
        "name": "Filling Loop",
        "supplier": "Toolstation",
        "default_price": 14.00,
        "product_url": ""
    },
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
    materials: list[MaterialItem] = []
    tiling: bool = False
    wall_tiling_m2: float = 0
    floor_tiling_m2: float = 0
    wall_height: str = "half"
    customer_supplies_tiles: bool = False


def fetch_price(url: str):
    if not url:
        return None

    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code != 200:
            return None

        html = r.text
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)

        if "cityplumbing" in url:
            patterns = [
                r'£\s?(\d+\.\d{2})\s*each,\s*Inc\.?\s*VAT',
                r'£\s?(\d+\.\d{2})\s*Inc\.?\s*VAT',
                r'£\s?(\d+\.\d{2})\s*each',
            ]
            for pattern in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                if matches:
                    return float(matches[0])

        if "toppstiles" in url:
            matches = re.findall(r'£\s?(\d+\.\d{2})', text)
            if matches:
                return float(matches[0])

        matches = re.findall(r'£\s?(\d+\.\d{2})', text)
        if matches:
            prices = []
            for m in matches:
                try:
                    value = float(m)
                    if 0 < value < 100000:
                        prices.append(value)
                except Exception:
                    pass
            if prices:
                return max(prices)

    except Exception:
        return None

    return None


@app.get("/material-search")
def material_search(q: str = ""):
    query = q.strip().lower()
    if not query:
        return []

    terms = [t for t in query.split() if t]
    matches = []

    for item in MATERIAL_LIBRARY:
        hay = f"{item['name']} {item['supplier']}".lower()
        if all(term in hay for term in terms):
            matches.append(item)

    matches = matches[:8]

    results = []
    for item in matches:
        live_price = None
        if item.get("product_url"):
            live_price = fetch_price(item["product_url"])

        results.append({
            "name": item["name"],
            "supplier": item["supplier"],
            "default_price": item["default_price"],
            "live_price": live_price,
            "product_url": item.get("product_url", "")
        })

    return JSONResponse(content=results)


HTML = """
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
.btn-template { background:#333; font-size:15px; padding:10px; }
.templates { display:grid; grid-template-columns:repeat(2, 1fr); gap:8px; }
.material-row { border:1px solid #ddd; padding:12px; border-radius:10px; margin-bottom:10px; background:#fafafa; }
.row { display:flex; justify-content:space-between; gap:10px; margin:8px 0; }
.muted { color:#666; }
.total { font-size:26px; font-weight:800; margin-top:10px; }
.result { display:none; background:#f3faf3; border:1px solid #b7d7b7; }
.error { display:none; background:#fff3f3; border:1px solid #e0b7b7; color:#a33; padding:12px; border-radius:10px; margin-top:12px; }
.actions { display:grid; gap:10px; margin-top:14px; }
.history-item { border:1px solid #ddd; border-radius:10px; padding:12px; margin-bottom:10px; background:#fafafa; }
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
.search-results { border:1px solid #ddd; border-radius:10px; max-height:260px; overflow:auto; background:#fff; margin-top:8px; }
.search-item { padding:10px; border-bottom:1px solid #eee; cursor:pointer; }
.search-item:last-child { border-bottom:none; }
.search-item:hover { background:#f2f2f2; }
.no-print { display:block; }
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

    <div class="check-row">
      <input type="checkbox" id="internal_mode">
      <span>Internal mode</span>
    </div>

    <h3>Job templates</h3>
    <div id="templateButtons" class="templates"></div>

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

    <h3>Live smart material search</h3>
    <input id="materialSearch" placeholder="Search materials e.g. 15mm speedfit elbow, basin waste, kitchen tap" oninput="debouncedSearch()">
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

  <div class="card">
    <h2>Saved Quotes</h2>
    <div id="historyList" class="small">No saved quotes yet.</div>
  </div>

</div>

<script>
const JOB_TEMPLATES = __JOB_TEMPLATES__;
let searchTimer = null;

function pounds(value) {
  return "£" + Number(value).toFixed(2);
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

function addMaterial(prefill = null) {
  const div = document.createElement("div");
  div.className = "material-row";
  div.innerHTML = `
    <label>Item name</label>
    <input class="m-name" placeholder="e.g. kitchen tap" value="${prefill ? escapeHtml(prefill.name) : ""}">

    <label>Quantity</label>
    <input class="m-qty" type="number" step="0.01" placeholder="1" value="${prefill ? 1 : ""}">

    <label>Supplier</label>
    <select class="m-supplier">
      <option value="City Plumbing">City Plumbing</option>
      <option value="Screwfix">Screwfix</option>
      <option value="Toolstation">Toolstation</option>
      <option value="Topps Tiles">Topps Tiles</option>
      <option value="Selco">Selco</option>
    </select>

    <label>Product URL</label>
    <input class="m-url" placeholder="https://..." value="${prefill ? escapeHtml(prefill.product_url || "") : ""}">

    <label>Manual price (£)</label>
    <input class="m-manual" type="number" step="0.01" placeholder="0" value="${prefill ? prefill.manual_price : ""}">
  `;
  document.getElementById("materials").appendChild(div);

  if (prefill) {
    div.querySelector(".m-supplier").value = prefill.supplier || "City Plumbing";
  }
}

function debouncedSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(searchMaterials, 300);
}

async function searchMaterials() {
  const query = document.getElementById("materialSearch").value.trim();
  const resultsBox = document.getElementById("searchResults");

  if (query.length < 2) {
    resultsBox.classList.add("hidden");
    resultsBox.innerHTML = "";
    return;
  }

  resultsBox.innerHTML = `<div class="search-item">Searching...</div>`;
  resultsBox.classList.remove("hidden");

  try {
    const res = await fetch("/material-search?q=" + encodeURIComponent(query));
    const results = await res.json();

    if (!results.length) {
      resultsBox.innerHTML = `<div class="search-item">No matches found</div>`;
      return;
    }

    resultsBox.innerHTML = results.map((item, idx) => {
      const bestPrice = item.live_price !== null ? item.live_price : item.default_price;
      const label = item.live_price !== null ? "live" : "default";
      return `
        <div class="search-item" onclick='selectSearchResult(${JSON.stringify(item)})'>
          <strong>${escapeHtml(item.name)}</strong><br>
          <span class="small">${escapeHtml(item.supplier)} · ${pounds(bestPrice)} (${label})</span>
        </div>
      `;
    }).join("");
  } catch (e) {
    resultsBox.innerHTML = `<div class="search-item">Search failed</div>`;
  }
}

function selectSearchResult(item) {
  const bestPrice = item.live_price !== null ? item.live_price : item.default_price;

  addMaterial({
    name: item.name,
    supplier: item.supplier,
    product_url: item.product_url || "",
    manual_price: bestPrice
  });

  document.getElementById("materialSearch").value = "";
  document.getElementById("searchResults").classList.add("hidden");
  document.getElementById("searchResults").innerHTML = "";
}

function normalisePhone(phone) {
  const digits = (phone || "").replace(/\\D/g, "");
  if (!digits) return "";
  if (digits.startsWith("44")) return digits;
  if (digits.startsWith("0")) return "44" + digits.slice(1);
  return digits;
}

async function loadHistory() {
  try {
    const res = await fetch("/quotes");
    const data = await res.json();
    const history = document.getElementById("historyList");

    if (!data.length) {
      history.innerHTML = "No saved quotes yet.";
      return;
    }

    history.innerHTML = data.slice().reverse().map(q => `
      <div class="history-item">
        <div><strong>${escapeHtml(q.customer_name || "No customer name")}</strong></div>
        <div>${escapeHtml(q.job)}</div>
        <div class="small">${escapeHtml(q.created_at)} · Total ${pounds(q.total_price)}</div>
      </div>
    `).join("");
  } catch (e) {
    document.getElementById("historyList").innerHTML = "Unable to load saved quotes.";
  }
}

async function generateQuote() {
  const errorBox = document.getElementById("error");
  const resultCard = document.getElementById("resultCard");
  const internalBox = document.getElementById("internalBox");
  const internalMode = document.getElementById("internal_mode").checked;
  errorBox.style.display = "none";

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

  const payload = {
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

  try {
    const res = await fetch("/quote", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });

    if (!res.ok) throw new Error("Quote request failed");

    const data = await res.json();

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
loadHistory();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def home():
    html = HTML.replace("__JOB_TEMPLATES__", json.dumps(JOB_TEMPLATES))
    return html


@app.get("/quotes")
def get_quotes():
    return quotes_db


@app.post("/quote")
def create_quote(data: QuoteRequest):
    total_materials = 0

    for item in data.materials:
        price = fetch_price(item.url) if item.url else None
        if price is None:
            price = item.manual_price or 0
        total_materials += price * item.quantity

    tiling_extra_materials = 0

    if data.quote_type == "bathroom" and data.tiling:
        total_area = data.wall_tiling_m2 + data.floor_tiling_m2
        if total_area > 0 and not data.customer_supplies_tiles:
            wall_multiplier = 1.2 if data.wall_height == "full" else 1.0
            wall_materials = data.wall_tiling_m2 * 20 * wall_multiplier
            floor_materials = data.floor_tiling_m2 * 15
            tiling_extra_materials += wall_materials + floor_materials

    raw_materials_with_tiling = total_materials + tiling_extra_materials

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
        handling_multiplier += (handling_percent / 100.0)

    materials_with_handling = materials_after_job_markup * handling_multiplier

    labour_total = data.labour_cost
    total = labour_total + materials_with_handling

    job_text = data.job_description
    if data.tiling and data.quote_type == "bathroom":
        job_text += " + Tiling"

    hidden_uplift = materials_with_handling - raw_materials_with_tiling

    quote = {
        "quote_type": data.quote_type,
        "customer_name": data.customer_name,
        "customer_address": data.customer_address,
        "customer_phone": data.customer_phone,
        "job": job_text,
        "labour": round(labour_total, 2),
        "materials": round(raw_materials_with_tiling, 2),
        "total_price": round(total, 2),
        "created_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "internal_raw_materials": round(raw_materials_with_tiling, 2),
        "internal_job_multiplier": round(job_multiplier, 2),
        "internal_after_job_markup": round(materials_after_job_markup, 2),
        "internal_handling_percent": round(handling_percent, 2),
        "internal_after_handling": round(materials_with_handling, 2),
        "internal_hidden_uplift": round(hidden_uplift, 2),
    }

    quotes_db.append(quote)
    return JSONResponse(content=quote)

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import re

app = FastAPI(title="Nigel Harvey Ltd Quotes")

quotes_db = []


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
        headers = {
            "User-Agent": "Mozilla/5.0"
        }
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text(" ", strip=True)

        matches = re.findall(r"£\s?\d+(?:\.\d{1,2})?", text)
        if matches:
            cleaned = matches[0].replace("£", "").strip().replace(",", "")
            return float(cleaned)
    except Exception:
        return None

    return None


HTML = """
<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nigel Harvey Ltd Quotes</title>
<style>
body {
  font-family: Arial, sans-serif;
  background: #f5f5f5;
  margin: 0;
  padding: 12px;
  color: #111;
}
.wrap {
  max-width: 780px;
  margin: 0 auto;
}
.card {
  background: white;
  padding: 16px;
  border-radius: 14px;
  margin-bottom: 14px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.06);
}
h1 {
  margin: 0 0 6px 0;
  font-size: 30px;
}
h2 {
  margin: 0 0 12px 0;
  font-size: 22px;
}
h3 {
  margin: 18px 0 8px 0;
}
.sub {
  color: #666;
  margin-bottom: 16px;
}
label {
  display: block;
  font-weight: 700;
  margin: 12px 0 6px;
}
input, textarea, select {
  width: 100%;
  box-sizing: border-box;
  padding: 12px;
  border: 1px solid #ccc;
  border-radius: 10px;
  font-size: 16px;
  background: white;
}
textarea {
  min-height: 100px;
  resize: vertical;
}
button, .btn-link {
  width: 100%;
  padding: 14px;
  border: none;
  border-radius: 10px;
  background: black;
  color: white;
  font-size: 18px;
  font-weight: 700;
  text-align: center;
  text-decoration: none;
  display: inline-block;
  box-sizing: border-box;
}
.btn-secondary {
  background: #2b2b2b;
}
.btn-light {
  background: #ececec;
  color: #111;
}
.material-row {
  border: 1px solid #ddd;
  padding: 12px;
  border-radius: 10px;
  margin-bottom: 10px;
  background: #fafafa;
}
.row {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  margin: 8px 0;
}
.muted {
  color: #666;
}
.total {
  font-size: 26px;
  font-weight: 800;
  margin-top: 10px;
}
.result {
  display: none;
  background: #f3faf3;
  border: 1px solid #b7d7b7;
}
.error {
  display: none;
  background: #fff3f3;
  border: 1px solid #e0b7b7;
  color: #a33;
  padding: 12px;
  border-radius: 10px;
  margin-top: 12px;
}
.actions {
  display: grid;
  gap: 10px;
  margin-top: 14px;
}
.history-item {
  border: 1px solid #ddd;
  border-radius: 10px;
  padding: 12px;
  margin-bottom: 10px;
  background: #fafafa;
}
.small {
  font-size: 14px;
  color: #666;
}
.hidden {
  display: none;
}
.check-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 12px 0 6px;
  font-weight: 700;
}
.check-row input[type="checkbox"] {
  width: auto;
  transform: scale(1.2);
}
@media print {
  .no-print {
    display: none !important;
  }
  body {
    background: white;
    padding: 0;
  }
  .card {
    box-shadow: none;
    border: none;
  }
}
</style>
</head>
<body>
<div class="wrap">

  <div class="card no-print">
    <h1>Nigel Harvey Ltd Quotes</h1>
    <div class="sub">Quick quote tool</div>

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
    <textarea id="job" placeholder="Example: Replace sink waste and install water softener"></textarea>

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
    <div id="materials"></div>
    <button type="button" onclick="addMaterial()">+ Add Material</button>

    <h3>Pricing</h3>

    <label for="labour">Labour cost (£)</label>
    <input id="labour" type="number" step="0.01" placeholder="180">

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

  <div id="resultCard" class="card result">
    <h2>Quote</h2>
    <div class="row"><span class="muted">Type</span><span id="r_type"></span></div>
    <div class="row"><span class="muted">Customer</span><span id="r_customer"></span></div>
    <div class="row"><span class="muted">Phone</span><span id="r_phone"></span></div>
    <div class="row"><span class="muted">Address</span><span id="r_address"></span></div>
    <div class="row"><span class="muted">Job</span><span id="r_job"></span></div>
    <div class="row"><span class="muted">Labour</span><span id="r_labour"></span></div>
    <div class="row"><span class="muted">Materials</span><span id="r_materials"></span></div>
    <div class="row total"><span>Total price</span><span id="r_total"></span></div>
    <div class="small">Includes labour and materials</div>

    <div class="actions no-print">
      <a id="whatsappBtn" class="btn-link btn-secondary" href="#" target="_blank">Send via WhatsApp</a>
      <button class="btn-light" onclick="window.print()">Download / Print PDF</button>
    </div>
  </div>

  <div class="card">
    <h2>Saved Quotes</h2>
    <div id="historyList" class="small">No saved quotes yet.</div>
  </div>

</div>

<script>
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

function addMaterial() {
  const div = document.createElement("div");
  div.className = "material-row";
  div.innerHTML = `
    <label>Item name</label>
    <input class="m-name" placeholder="e.g. kitchen tap">

    <label>Quantity</label>
    <input class="m-qty" type="number" step="0.01" placeholder="1">

    <label>Supplier</label>
    <select class="m-supplier">
      <option value="Screwfix">Screwfix</option>
      <option value="Toolstation">Toolstation</option>
      <option value="Selco">Selco</option>
      <option value="City Plumbing">City Plumbing</option>
      <option value="Topps Tiles">Topps Tiles</option>
    </select>

    <label>Product URL</label>
    <input class="m-url" placeholder="https://...">

    <label>Manual price (£)</label>
    <input class="m-manual" type="number" step="0.01" placeholder="0">
  `;
  document.getElementById("materials").appendChild(div);
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

    if (!res.ok) {
      throw new Error("Quote request failed");
    }

    const data = await res.json();

    document.getElementById("r_type").innerText = data.quote_type || "-";
    document.getElementById("r_customer").innerText = data.customer_name || "-";
    document.getElementById("r_phone").innerText = data.customer_phone || "-";
    document.getElementById("r_address").innerText = data.customer_address || "-";
    document.getElementById("r_job").innerText = data.job || "-";
    document.getElementById("r_labour").innerText = pounds(data.labour);
    document.getElementById("r_materials").innerText = pounds(data.materials);
    document.getElementById("r_total").innerText = pounds(data.total_price);

    const message =
`Nigel Harvey Ltd Quote

Type: ${data.quote_type || "-"}
Customer: ${data.customer_name || "-"}
Phone: ${data.customer_phone || "-"}
Address: ${data.customer_address || "-"}

Job: ${data.job || "-"}

Labour: ${pounds(data.labour)}
Materials: ${pounds(data.materials)}
Total price: ${pounds(data.total_price)}

Includes labour and materials`;

    document.getElementById("whatsappBtn").href =
      "https://wa.me/?text=" + encodeURIComponent(message);

    resultCard.style.display = "block";
    await loadHistory();
  } catch (err) {
    errorBox.innerText = "Something went wrong generating the quote.";
    errorBox.style.display = "block";
  }
}

toggleBathroomFields();
addMaterial();
loadHistory();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def home():
    return HTML


@app.get("/quotes")
def get_quotes():
    return quotes_db


@app.post("/quote")
def create_quote(data: QuoteRequest):
    total_materials = 0

    for item in data.materials:
        price = fetch_price(item.url) if item.url else None

        if price is None:
            price = item.manual_price

        total_materials += price * item.quantity

    handling_multiplier = 1.0
    if data.include_materials_handling:
        handling_multiplier += (data.materials_handling_percent / 100.0)

    materials_with_handling = total_materials * handling_multiplier

    tiling_extra_labour = 0
    tiling_extra_materials = 0

    if data.quote_type == "bathroom":
        if data.tiling:
            tiling_extra_labour += 300

        total_area = data.wall_tiling_m2 + data.floor_tiling_m2

        if total_area > 0:
            wall_multiplier = 1.2 if data.wall_height == "full" else 1.0

            wall_labour = data.wall_tiling_m2 * 45 * wall_multiplier
            floor_labour = data.floor_tiling_m2 * 50

            tiling_extra_labour += wall_labour + floor_labour

            if not data.customer_supplies_tiles:
                wall_materials = data.wall_tiling_m2 * 20
                floor_materials = data.floor_tiling_m2 * 15
                tiling_extra_materials += wall_materials + floor_materials

    labour_total = data.labour_cost + tiling_extra_labour
    materials_total_for_quote = materials_with_handling + tiling_extra_materials
    total = labour_total + materials_total_for_quote

    job_text = data.job_description
    if data.tiling and data.quote_type == "bathroom":
        job_text += " + Tiling"

    quote = {
        "quote_type": data.quote_type,
        "customer_name": data.customer_name,
        "customer_address": data.customer_address,
        "customer_phone": data.customer_phone,
        "job": job_text,
        "labour": round(labour_total, 2),
        "materials": round(total_materials + tiling_extra_materials, 2),
        "total_price": round(total, 2),
        "created_at": datetime.now().strftime("%d/%m/%Y %H:%M")
    }

    quotes_db.append(quote)
    return JSONResponse(content=quote)

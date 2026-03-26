from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import List
from datetime import datetime

app = FastAPI(title="Nigel Harvey Ltd Quotes")

quotes_db = []


class QuoteRequest(BaseModel):
    quote_type: str = "small"

    customer_name: str = ""
    customer_address: str = ""
    customer_phone: str = ""
    "job": data.job_description + (" + Tiling" if data.tiling else ""),
    labour_cost: float = 0
    materials_cost: float = 0
    tiling: bool = False
    wall_tiling_m2: float = 0
    floor_tiling_m2: float = 0
    wall_height: str = "half"
    customer_supplies_tiles: bool = False

HTML = """
<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Nigel Harvey Ltd Quotes</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      margin: 0;
      background: #f5f5f5;
      color: #111;
    }
    .wrap {
      max-width: 760px;
      margin: 0 auto;
      padding: 16px;
    }
    .card {
      background: white;
      border-radius: 14px;
      padding: 16px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.08);
      margin-bottom: 16px;
    }
    h1 {
      margin: 0 0 8px 0;
      font-size: 28px;
    }
    h2 {
      margin: 0 0 12px 0;
      font-size: 22px;
    }
    .sub {
      color: #666;
      margin-bottom: 16px;
    }
    label {
      display: block;
      font-weight: 600;
      margin: 12px 0 6px;
    }
    textarea, input {
      width: 100%;
      box-sizing: border-box;
      padding: 12px;
      border: 1px solid #ccc;
      border-radius: 10px;
      font-size: 16px;
    }
    textarea {
      min-height: 110px;
      resize: vertical;
    }
    button, .btn-link {
      width: 100%;
      border: 0;
      border-radius: 10px;
      padding: 14px;
      font-size: 17px;
      font-weight: 700;
      background: #111;
      color: white;
      margin-top: 16px;
      text-decoration: none;
      display: inline-block;
      text-align: center;
      box-sizing: border-box;
    }
    .btn-secondary {
      background: #2b2b2b;
    }
    .btn-light {
      background: #eaeaea;
      color: #111;
    }
    .result {
      display: none;
      margin-top: 16px;
      padding: 14px;
      border-radius: 10px;
      background: #f0f7f0;
      border: 1px solid #b9d7b9;
    }
    .error {
      display: none;
      margin-top: 16px;
      padding: 14px;
      border-radius: 10px;
      background: #fff2f2;
      border: 1px solid #e0b4b4;
      color: #a33;
    }
    .row {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin: 8px 0;
    }
    .muted {
      color: #666;
    }
    .total {
      font-size: 24px;
      font-weight: 800;
      margin-top: 10px;
    }
    .actions {
      display: grid;
      grid-template-columns: 1fr;
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
    @media print {
      body {
        background: white;
      }
      .no-print {
        display: none !important;
      }
      .card {
        box-shadow: none;
        border: 0;
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
<select id="quote_type">
  <option value="small">Small Job</option>
  <option value="bathroom">Bathroom</option>
  <option value="heating">Heating</option>
</select>
      <label for="customer_name">Customer name</label>
      <input id="customer_name" type="text" placeholder="John Smith" />

      <label for="customer_address">Customer address</label>
      <textarea id="customer_address" placeholder="125 Bushy Hill Drive, Guildford, GU1 2UG"></textarea>

      <label for="customer_phone">Customer phone</label>
      <input id="customer_phone" type="text" placeholder="07123 456789" />

      <label for="job">Job description</label>
      <textarea id="job" placeholder="Example: Replace sink waste and install water softener"></textarea>
       <label>
       <input type="checkbox" id="tiling">
        Include tiling
        </label>
      <label for="wall_tiling_m2">Wall tiling (m²)</label>
<input id="wall_tiling_m2" type="number" step="0.1" placeholder="0" />

<label for="floor_tiling_m2">Floor tiling (m²)</label>
<input id="floor_tiling_m2" type="number" step="0.1" placeholder="0" />

<label for="wall_height">Wall height</label>
<select id="wall_height">
  <option value="half">Half height</option>
  <option value="full">Full height</option>
</select>

<label>
  <input type="checkbox" id="customer_supplies_tiles">
  Customer supplies tiles
</label>
      <label for="labour">Labour cost (£)</label>
      <input id="labour" type="number" step="0.01" placeholder="180" />

      <label for="materials">Materials cost (£)</label>
      <input id="materials" type="number" step="0.01" placeholder="80" />

      <button onclick="generateQuote()">Generate Quote</button>

      <div id="error" class="error"></div>
    </div>

    <div id="resultCard" class="card result">
      <h2>Quote</h2>
      <div class="row"><span class="muted">Customer</span><span id="r_customer"></span></div>
      <div class="row"><span class="muted">Phone</span><span id="r_phone"></span></div>
      <div class="row"><span class="muted">Address</span><span id="r_address"></span></div>
      <div class="row"><span class="muted">Job</span><span id="r_job"></span></div>
      <div class="row"><span class="muted">Labour</span><span id="r_labour"></span></div>
      <div class="row"><span class="muted">Materials estimated</span><span id="r_materials"></span></div>
      <div class="row"><span class="muted">Materials with margin</span><span id="r_margin"></span></div>
      <div class="row total"><span>Total price</span><span id="r_total"></span></div>

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
    let latestQuote = null;

    function pounds(value) {
      return "£" + Number(value).toFixed(2);
    }

    function escapeHtml(text) {
      return (text || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    async function loadHistory() {
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
          <div>${escapeHtml(q.job_description)}</div>
          <div class="small">${escapeHtml(q.created_at)} · Total ${pounds(q.total_price)}</div>
        </div>
      `).join("");
    }

    async function generateQuote() {
      const customer_name = document.getElementById("customer_name").value;
      const customer_address = document.getElementById("customer_address").value;
      const customer_phone = document.getElementById("customer_phone").value;
      const tiling = document.getElementById("tiling").checked;
      const wall_tiling_m2 = parseFloat(document.getElementById("wall_tiling_m2").value || 0);
      const floor_tiling_m2 = parseFloat(document.getElementById("floor_tiling_m2").value || 0);
      const wall_height = document.getElementById("wall_height").value;
      const customer_supplies_tiles = document.getElementById("customer_supplies_tiles").checked;
      const quote_type = document.getElementById("quote_type").value;
      const job = document.getElementById("job").value;
      const labour = parseFloat(document.getElementById("labour").value || 0);
      const materials = parseFloat(document.getElementById("materials").value || 0);

      const errorBox = document.getElementById("error");
      const resultCard = document.getElementById("resultCard");

      errorBox.style.display = "none";

      try {
        const response = await fetch("/quote", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            quote_type: quote_type,
            tiling: tiling,
            wall_tiling_m2: wall_tiling_m2,
            floor_tiling_m2: floor_tiling_m2,
            wall_height: wall_height,
            customer_supplies_tiles: customer_supplies_tiles,
            customer_name,
            customer_address,
            customer_phone,
            job_description: job,
            labour_cost: labour,
            materials_cost: materials
          })
        });

        if (!response.ok) throw new Error("Quote request failed");

        const data = await response.json();
        latestQuote = data;

        document.getElementById("r_customer").innerText = data.customer_name || "-";
        document.getElementById("r_phone").innerText = data.customer_phone || "-";
        document.getElementById("r_address").innerText = data.customer_address || "-";
        document.getElementById("r_job").innerText = data.job;
        document.getElementById("r_labour").innerText = pounds(data.labour);
        document.getElementById("r_materials").innerText = pounds(data.materials_estimated);
        document.getElementById("r_margin").innerText = pounds(data.materials_with_margin);
        document.getElementById("r_total").innerText = pounds(data.total_price);

        const message =
`Nigel Harvey Ltd Quote

Customer: ${data.customer_name || "-"}
Phone: ${data.customer_phone || "-"}
Address: ${data.customer_address || "-"}

Job: ${data.job}

Labour: ${pounds(data.labour)}
Materials estimated: ${pounds(data.materials_estimated)}
Materials with margin: ${pounds(data.materials_with_margin)}
Total price: ${pounds(data.total_price)}

Nigel Harvey Ltd
07595 725547
Nigelharveyplumbing@gmail.com`;

        document.getElementById("whatsappBtn").href =
          "https://wa.me/?text=" + encodeURIComponent(message);

        resultCard.style.display = "block";
        await loadHistory();
      } catch (err) {
        errorBox.innerText = "Something went wrong generating the quote.";
        errorBox.style.display = "block";
      }
    }

    loadHistory();
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def home():
    return HTML


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/quotes")
def get_quotes():
    return quotes_db


@app.post("/quote")
def create_quote(data: QuoteRequest):
   if data.quote_type == "bathroom":
    materials_with_margin = round(data.materials_cost * 1.5, 2)

    # basic tiling checkbox
    if data.tiling:
        data.labour_cost += 300

    # m² tiling pricing
    total_area = data.wall_tiling_m2 + data.floor_tiling_m2

    if total_area > 0:
        wall_multiplier = 1.2 if data.wall_height == "full" else 1.0

        wall_labour = data.wall_tiling_m2 * 45 * wall_multiplier
        floor_labour = data.floor_tiling_m2 * 50

        wall_materials = data.wall_tiling_m2 * 20
        floor_materials = data.floor_tiling_m2 * 15

        data.labour_cost += wall_labour + floor_labour

        if not data.customer_supplies_tiles:
            materials_with_margin += wall_materials + floor_materials

elif data.quote_type == "heating":
    materials_with_margin = round(data.materials_cost * 1.3, 2)

else:
    materials_with_margin = round(data.materials_cost * 1.25, 2)

    quote = {
        "quote_type": data.quote_type,
        "customer_name": data.customer_name,
        "customer_address": data.customer_address,
        "customer_phone": data.customer_phone,
        "job": data.job_description,
        "job_description": data.job_description,
        "labour": data.labour_cost,
        "materials_estimated": data.materials_cost,
        "materials_with_margin": materials_with_margin,
        "total_price": total,
        "created_at": datetime.now().strftime("%d/%m/%Y %H:%M")
    }

    quotes_db.append(quote)
    return JSONResponse(content=quote)

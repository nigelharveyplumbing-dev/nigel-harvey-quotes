from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import re

app = FastAPI(title="Nigel Harvey Ltd Quotes")

quotes_db = []


# ---------- MODELS ----------

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


# ---------- IMPROVED PRICE FETCH ----------

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

        # ---------- CITY PLUMBING ----------
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

        # ---------- TOPPS TILES ----------
        if "toppstiles" in url:
            matches = re.findall(r'£\s?(\d+\.\d{2})', text)
            if matches:
                return float(matches[0])

        # ---------- GENERIC FALLBACK ----------
        matches = re.findall(r'£\s?(\d+\.\d{2})', text)

        if matches:
            prices = []
            for m in matches:
                try:
                    value = float(m)
                    if 0 < value < 100000:
                        prices.append(value)
                except:
                    pass

            if prices:
                return max(prices)

    except:
        return None

    return None


# ---------- HTML ----------

HTML = """
<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nigel Harvey Ltd Quotes</title>
<style>
body {font-family: Arial; background:#f5f5f5; padding:10px;}
.card {background:white; padding:15px; border-radius:10px; margin-bottom:10px;}
input, textarea, select {width:100%; padding:10px; margin:5px 0;}
button {padding:12px; width:100%; background:black; color:white; border:none;}
.material-row {border:1px solid #ddd; padding:10px; margin-bottom:10px;}
.result {font-size:18px; font-weight:bold;}
</style>
</head>

<body>

<div class="card">
<h2>Nigel Harvey Ltd Quote</h2>

<select id="quote_type">
<option value="small">Small Job</option>
<option value="bathroom">Bathroom</option>
<option value="heating">Heating</option>
</select>

<input id="customer_name" placeholder="Customer name">
<textarea id="job" placeholder="Job description"></textarea>

<h3>Materials</h3>
<div id="materials"></div>
<button onclick="addMaterial()">+ Add Material</button>

<input id="labour" placeholder="Labour £">

<label>
<input type="checkbox" id="include_materials_handling" checked>
 Include materials handling
</label>

<select id="materials_handling_percent">
<option value="20">20%</option>
<option value="25" selected>25%</option>
<option value="30">30%</option>
</select>

<button onclick="generate()">Generate Quote</button>
</div>

<div class="card result" id="result" style="display:none;"></div>

<script>

function addMaterial(){
  const div = document.createElement("div");
  div.className = "material-row";
  div.innerHTML = `
    <input placeholder="Item name">
    <input placeholder="Quantity">
    <select>
      <option>City Plumbing</option>
      <option>Screwfix</option>
      <option>Toolstation</option>
      <option>Topps Tiles</option>
    </select>
    <input placeholder="Product URL">
    <input placeholder="Manual price (£)">
  `;
  document.getElementById("materials").appendChild(div);
}

function pounds(v){
  return "£" + Number(v).toFixed(2);
}

async function generate(){

  const rows = document.querySelectorAll(".material-row");

  let materials = [];

  rows.forEach(r=>{
    const inputs = r.querySelectorAll("input");

    materials.push({
      name: inputs[0].value,
      quantity: parseFloat(inputs[1].value||1),
      url: inputs[2].value,
      manual_price: parseFloat(inputs[3].value||0)
    });
  });

  const res = await fetch("/quote", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body: JSON.stringify({
      quote_type: document.getElementById("quote_type").value,
      customer_name: document.getElementById("customer_name").value,
      job_description: document.getElementById("job").value,
      labour_cost: parseFloat(document.getElementById("labour").value||0),
      include_materials_handling: document.getElementById("include_materials_handling").checked,
      materials_handling_percent: parseFloat(document.getElementById("materials_handling_percent").value),
      materials: materials
    })
  });

  const data = await res.json();

  document.getElementById("result").style.display="block";
  document.getElementById("result").innerHTML = `
    <div>Job: ${data.job}</div>
    <div>Labour: ${pounds(data.labour)}</div>
    <div>Materials: ${pounds(data.materials)}</div>
    <div>Total Price: ${pounds(data.total_price)}</div>
  `;
}
</script>

</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def home():
    return HTML


# ---------- QUOTE ----------

@app.post("/quote")
def create_quote(data: QuoteRequest):

    total_materials = 0

    for item in data.materials:
        price = fetch_price(item.url) if item.url else None

        if price is None:
            price = item.manual_price

        total_materials += price * item.quantity

    multiplier = 1
    if data.include_materials_handling:
        multiplier += data.materials_handling_percent / 100

    materials_with_margin = total_materials * multiplier

    total = data.labour_cost + materials_with_margin

    return {
        "job": data.job_description,
        "labour": data.labour_cost,
        "materials": round(total_materials, 2),
        "total_price": round(total, 2)
    }

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup

app = FastAPI(title="Nigel Harvey Ltd Quotes")

# ---------- MODELS ----------

class MaterialItem(BaseModel):
    name: str
    quantity: float = 1
    url: str = ""
    manual_price: float = 0

class QuoteRequest(BaseModel):
    quote_type: str = "small"
    customer_name: str = ""
    job_description: str
    labour_cost: float = 0
    materials: list[MaterialItem] = []

# ---------- PRICE FETCH ----------

def fetch_price(url: str):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(r.text, "html.parser")

        import re
        text = soup.get_text()
        matches = re.findall(r"£\s?\d+\.?\d*", text)

        if matches:
            return float(matches[0].replace("£", "").strip())

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
      <option>Screwfix</option>
      <option>Toolstation</option>
      <option>Selco</option>
      <option>City Plumbing</option>
    </select>
    <input placeholder="Product URL">
    <input placeholder="Manual price (£)">
  `;
  document.getElementById("materials").appendChild(div);
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
      materials: materials
    })
  });

  const data = await res.json();

  document.getElementById("result").style.display="block";
  document.getElementById("result").innerHTML = `
    <div><strong>Job:</strong> ${data.job}</div>
    <div><strong>Total Price:</strong> £${data.total_price}</div>
    <div style="font-size:14px; color:#666;">Includes labour and materials</div>
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

    if data.quote_type == "bathroom":
        materials_with_margin = total_materials * 1.5
    elif data.quote_type == "heating":
        materials_with_margin = total_materials * 1.3
    else:
        materials_with_margin = total_materials * 1.25

    total = data.labour_cost + materials_with_margin

    return {
        "job": data.job_description,
        "total_price": round(total,2)
    }

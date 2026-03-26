from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI(title="Nigel Harvey Ltd Quotes")


class QuoteRequest(BaseModel):
    job_description: str
    labour_cost: float = 0
    materials_cost: float = 0


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
      max-width: 720px;
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
      min-height: 120px;
      resize: vertical;
    }
    button {
      width: 100%;
      border: 0;
      border-radius: 10px;
      padding: 14px;
      font-size: 17px;
      font-weight: 700;
      background: #111;
      color: white;
      margin-top: 16px;
    }
    .result {
      display: none;
      margin-top: 16px;
      padding: 14px;
      border-radius: 10px;
      background: #f0f7f0;
      border: 1px solid #b9d7b9;
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
      font-size: 22px;
      font-weight: 800;
      margin-top: 8px;
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
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Nigel Harvey Ltd Quotes</h1>
      <div class="sub">Quick quote tool</div>

      <label for="job">Job description</label>
      <textarea id="job" placeholder="Example: Replace sink waste and install water softener"></textarea>

      <label for="labour">Labour cost (£)</label>
      <input id="labour" type="number" step="0.01" placeholder="180" />

      <label for="materials">Materials cost (£)</label>
      <input id="materials" type="number" step="0.01" placeholder="80" />

      <button onclick="generateQuote()">Generate Quote</button>

      <div id="error" class="error"></div>

      <div id="result" class="result">
        <div class="row"><span class="muted">Job</span><span id="r_job"></span></div>
        <div class="row"><span class="muted">Labour</span><span id="r_labour"></span></div>
        <div class="row"><span class="muted">Materials estimated</span><span id="r_materials"></span></div>
        <div class="row"><span class="muted">Materials with margin</span><span id="r_margin"></span></div>
        <div class="row total"><span>Total price</span><span id="r_total"></span></div>
      </div>
    </div>
  </div>

  <script>
    async function generateQuote() {
      const job = document.getElementById("job").value;
      const labour = parseFloat(document.getElementById("labour").value || 0);
      const materials = parseFloat(document.getElementById("materials").value || 0);
      const errorBox = document.getElementById("error");
      const resultBox = document.getElementById("result");

      errorBox.style.display = "none";
      resultBox.style.display = "none";

      try {
        const response = await fetch("/quote", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            job_description: job,
            labour_cost: labour,
            materials_cost: materials
          })
        });

        if (!response.ok) {
          throw new Error("Quote request failed");
        }

        const data = await response.json();

        document.getElementById("r_job").innerText = data.job;
        document.getElementById("r_labour").innerText = "£" + Number(data.labour).toFixed(2);
        document.getElementById("r_materials").innerText = "£" + Number(data.materials_estimated).toFixed(2);
        document.getElementById("r_margin").innerText = "£" + Number(data.materials_with_margin).toFixed(2);
        document.getElementById("r_total").innerText = "£" + Number(data.total_price).toFixed(2);

        resultBox.style.display = "block";
      } catch (err) {
        errorBox.innerText = "Something went wrong generating the quote.";
        errorBox.style.display = "block";
      }
    }
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


@app.post("/quote")
def create_quote(data: QuoteRequest):
    materials_with_margin = round(data.materials_cost * 1.25, 2)
    total = round(data.labour_cost + materials_with_margin, 2)

    return {
        "job": data.job_description,
        "labour": data.labour_cost,
        "materials_estimated": data.materials_cost,
        "materials_with_margin": materials_with_margin,
        "total_price": total
    }

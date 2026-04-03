from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import re
import json
import sqlite3

app = FastAPI(title="Nigel Harvey Ltd Quotes")

DB_FILE = "nigel_quotes.db"

BASE_MATERIAL_LIBRARY = [
    {"name": "15mm Copper Pipe 3m", "supplier": "City Plumbing", "default_price": 14.50, "product_url": "https://www.cityplumbing.co.uk/p/wednesbury-plain-copper-tube-length-15mm-x-3m-x015l-3/p/313813"},
    {"name": "22mm Copper Pipe 3m", "supplier": "City Plumbing", "default_price": 28.00, "product_url": "https://www.cityplumbing.co.uk/p/wednesbury-plain-copper-tube-length-22mm-x-3m-x022l-3/p/313814"},
    {"name": "15mm Copper Elbow", "supplier": "Screwfix", "default_price": 1.20, "product_url": "https://www.screwfix.com/p/compression-equal-elbow-15mm/69341"},
    {"name": "22mm Copper Elbow", "supplier": "Screwfix", "default_price": 2.00, "product_url": "https://www.screwfix.com/p/compression-equal-elbow-22mm/69342"},
    {"name": "15mm Copper Tee", "supplier": "Screwfix", "default_price": 1.80, "product_url": "https://www.screwfix.com/p/compression-equal-tee-15mm/69347"},
    {"name": "22mm Copper Tee", "supplier": "Screwfix", "default_price": 3.20, "product_url": "https://www.screwfix.com/p/compression-equal-tee-22mm/69348"},
    {"name": "15mm Straight Coupler", "supplier": "Screwfix", "default_price": 1.00, "product_url": "https://www.screwfix.com/p/compression-coupler-15mm/69337"},
    {"name": "22mm Straight Coupler", "supplier": "Screwfix", "default_price": 1.80, "product_url": "https://www.screwfix.com/p/compression-coupler-22mm/69338"},
    {"name": "15mm Isolating Valve", "supplier": "Toolstation", "default_price": 3.50, "product_url": "https://www.toolstation.com/isolating-valve/p37037"},
    {"name": "22mm Isolating Valve", "supplier": "Toolstation", "default_price": 5.50, "product_url": "https://www.toolstation.com/isolating-valve/p37038"},
    {"name": "Flexible Tap Connector", "supplier": "Screwfix", "default_price": 6.50, "product_url": "https://www.screwfix.com/p/flexible-tap-connector-15mm-x-1-2-x-300mm/11494"},
    {"name": "Basin Waste", "supplier": "Screwfix", "default_price": 10.00, "product_url": "https://www.screwfix.com/p/basin-waste-with-plug-chain-chrome/12739"},
    {"name": "Sink Waste Kit", "supplier": "Screwfix", "default_price": 18.00, "product_url": "https://www.screwfix.com/p/kitchen-sink-waste-kit-40mm/12754"},
    {"name": "P Trap 40mm", "supplier": "Toolstation", "default_price": 6.00, "product_url": "https://www.toolstation.com/p-trap/p23741"},
    {"name": "Hep2O 15mm Pipe Coil", "supplier": "City Plumbing", "default_price": 65.00, "product_url": "https://www.cityplumbing.co.uk/p/hep2o-barrier-pipe-15mm-x-25m-hx15-25c/p/215674"},
    {"name": "Hep2O 15mm Elbow", "supplier": "City Plumbing", "default_price": 5.00, "product_url": "https://www.cityplumbing.co.uk/p/hep2o-equal-elbow-15mm-hx15-15/p/215676"},
    {"name": "Hep2O 15mm Coupler", "supplier": "City Plumbing", "default_price": 4.50, "product_url": "https://www.cityplumbing.co.uk/p/hep2o-straight-coupler-15mm-hx15-15/p/215675"},
    {"name": "Speedfit 15mm Elbow", "supplier": "Screwfix", "default_price": 5.00, "product_url": "https://www.screwfix.com/p/jg-speedfit-equal-elbow-15mm/97179"},
    {"name": "Speedfit 15mm Coupler", "supplier": "Screwfix", "default_price": 4.20, "product_url": "https://www.screwfix.com/p/jg-speedfit-straight-coupler-15mm/69363"},
    {"name": "Speedfit 15mm Pipe", "supplier": "Screwfix", "default_price": 55.00, "product_url": "https://www.screwfix.com/p/jg-speedfit-barrier-pipe-coil-15mm-x-25m/69386"},
    {"name": "Jointing Compound", "supplier": "Toolstation", "default_price": 6.50, "product_url": "https://www.toolstation.com/jointing-compound/p17635"},
    {"name": "PTFE Tape", "supplier": "Toolstation", "default_price": 1.00, "product_url": "https://www.toolstation.com/ptfe-tape/p31207"},
    {"name": "Pipe Freeze Spray", "supplier": "Toolstation", "default_price": 8.00, "product_url": "https://www.toolstation.com/pipe-freeze-spray/p23762"},
    {"name": "Outside Tap Kit", "supplier": "Screwfix", "default_price": 18.00, "product_url": "https://www.screwfix.com/p/outside-tap-kit/37241"},
    {"name": "Service Valve", "supplier": "Screwfix", "default_price": 4.00, "product_url": "https://www.screwfix.com/p/service-valve-15mm/27792"}
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
    {"name": "Full heating system", "quote_type": "heating", "job": "Full heating system installation including pipework, controls, radiators and commissioning.", "labour": 3500}
]

JOB_PACKS = [
    {
        "name": "Replace tap",
        "quote_type": "small",
        "job_description": "Remove existing tap and fit new tap including testing for leaks.",
        "labour_cost": 120,
        "materials": [
            {"name": "Flexible Tap Connector", "supplier": "Screwfix", "quantity": 2, "url": "https://www.screwfix.com/p/flexible-tap-connector-15mm-x-1-2-x-300mm/11494", "manual_price": 6.50},
            {"name": "15mm Isolating Valve", "supplier": "Toolstation", "quantity": 2, "url": "https://www.toolstation.com/isolating-valve/p37037", "manual_price": 3.50},
            {"name": "PTFE Tape", "supplier": "Toolstation", "quantity": 1, "url": "https://www.toolstation.com/ptfe-tape/p31207", "manual_price": 1.00}
        ]
    },
    {
        "name": "Outside tap",
        "quote_type": "small",
        "job_description": "Supply and fit outside tap kit with isolation and testing.",
        "labour_cost": 150,
        "materials": [
            {"name": "Outside Tap Kit", "supplier": "Screwfix", "quantity": 1, "url": "https://www.screwfix.com/p/outside-tap-kit/37241", "manual_price": 18.00},
            {"name": "15mm Isolating Valve", "supplier": "Toolstation", "quantity": 1, "url": "https://www.toolstation.com/isolating-valve/p37037", "manual_price": 3.50},
            {"name": "PTFE Tape", "supplier": "Toolstation", "quantity": 1, "url": "https://www.toolstation.com/ptfe-tape/p31207", "manual_price": 1.00}
        ]
    },
    {
        "name": "Radiator install",
        "quote_type": "heating",
        "job_description": "Supply and fit radiator including valves and testing.",
        "labour_cost": 180,
        "materials": [
            {"name": "15mm Copper Pipe 3m", "supplier": "City Plumbing", "quantity": 1, "url": "https://www.cityplumbing.co.uk/p/wednesbury-plain-copper-tube-length-15mm-x-3m-x015l-3/p/313813", "manual_price": 14.50},
            {"name": "Speedfit 15mm Elbow", "supplier": "Screwfix", "quantity": 2, "url": "https://www.screwfix.com/p/jg-speedfit-equal-elbow-15mm/97179", "manual_price": 5.00},
            {"name": "PTFE Tape", "supplier": "Toolstation", "quantity": 1, "url": "https://www.toolstation.com/ptfe-tape/p31207", "manual_price": 1.00}
        ]
    }
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


class SaveLibraryItemRequest(BaseModel):
    name: str
    supplier: str = ""
    product_url: str = ""
    default_price: float = 0


class DeleteLibraryItemRequest(BaseModel):
    id: int


class SaveCustomerRequest(BaseModel):
    customer_name: str
    customer_address: str = ""
    customer_phone: str = ""


class DeleteCustomerRequest(BaseModel):
    id: int


class UpdateQuoteStatusRequest(BaseModel):
    quote_ref: str
    status: str


class ScheduleJobRequest(BaseModel):
    quote_ref: str = ""
    customer_name: str = ""
    job_title: str = ""
    scheduled_date: str = ""
    scheduled_time: str = ""
    notes: str = ""


class DeleteScheduleJobRequest(BaseModel):
    id: int


def db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS library_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            supplier TEXT NOT NULL,
            default_price REAL NOT NULL DEFAULT 0,
            product_url TEXT NOT NULL DEFAULT '',
            UNIQUE(name, supplier)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            customer_address TEXT NOT NULL DEFAULT '',
            customer_phone TEXT NOT NULL DEFAULT ''
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quote_ref TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'draft',
            invoice_ref TEXT NOT NULL DEFAULT '',
            invoice_created_at TEXT NOT NULL DEFAULT '',
            quote_type TEXT NOT NULL,
            customer_name TEXT NOT NULL DEFAULT '',
            customer_address TEXT NOT NULL DEFAULT '',
            customer_phone TEXT NOT NULL DEFAULT '',
            job TEXT NOT NULL DEFAULT '',
            labour REAL NOT NULL DEFAULT 0,
            materials REAL NOT NULL DEFAULT 0,
            total_price REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            internal_raw_materials REAL NOT NULL DEFAULT 0,
            internal_job_multiplier REAL NOT NULL DEFAULT 1,
            internal_after_job_markup REAL NOT NULL DEFAULT 0,
            internal_handling_percent REAL NOT NULL DEFAULT 0,
            internal_after_handling REAL NOT NULL DEFAULT 0,
            internal_hidden_uplift REAL NOT NULL DEFAULT 0,
            materials_json TEXT NOT NULL DEFAULT '[]',
            include_materials_handling INTEGER NOT NULL DEFAULT 1,
            materials_handling_percent REAL NOT NULL DEFAULT 25,
            tiling INTEGER NOT NULL DEFAULT 0,
            wall_tiling_m2 REAL NOT NULL DEFAULT 0,
            floor_tiling_m2 REAL NOT NULL DEFAULT 0,
            wall_height TEXT NOT NULL DEFAULT 'half',
            customer_supplies_tiles INTEGER NOT NULL DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quote_ref TEXT NOT NULL DEFAULT '',
            customer_name TEXT NOT NULL DEFAULT '',
            job_title TEXT NOT NULL DEFAULT '',
            scheduled_date TEXT NOT NULL DEFAULT '',
            scheduled_time TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()

    cur.execute("SELECT COUNT(*) AS c FROM library_items")
    count = cur.fetchone()["c"]

    if count == 0:
        for item in BASE_MATERIAL_LIBRARY:
            cur.execute("""
                INSERT OR IGNORE INTO library_items (name, supplier, default_price, product_url)
                VALUES (?, ?, ?, ?)
            """, (item["name"], item["supplier"], item["default_price"], item["product_url"]))
        conn.commit()

    conn.close()


init_db()


def fetch_price(url: str):
    if not url:
        return None
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, "html.parser")
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


def generate_quote_ref():
    conn = db()
    cur = conn.cursor()
    today = datetime.now().strftime("%Y%m%d")
    cur.execute("SELECT COUNT(*) AS c FROM quotes WHERE quote_ref LIKE ?", (f"NHQ-{today}-%",))
    count = cur.fetchone()["c"]
    conn.close()
    return f"NHQ-{today}-{count + 1:03d}"


def generate_invoice_ref():
    conn = db()
    cur = conn.cursor()
    today = datetime.now().strftime("%Y%m%d")
    cur.execute("SELECT COUNT(*) AS c FROM quotes WHERE invoice_ref LIKE ?", (f"NHI-{today}-%",))
    count = cur.fetchone()["c"]
    conn.close()
    return f"NHI-{today}-{count + 1:03d}"


@app.get("/job-packs")
def get_job_packs():
    return JSONResponse(content=JOB_PACKS)


@app.get("/material-search")
def material_search(q: str = ""):
    query = q.strip().lower()
    if not query:
        return []

    terms = [t for t in query.split() if t]
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM library_items ORDER BY name ASC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    matches = []
    for item in rows:
        hay = f"{item.get('name', '')} {item.get('supplier', '')}".lower()
        if all(term in hay for term in terms):
            matches.append(item)

    matches = matches[:12]
    results = []
    for item in matches:
        live_price = fetch_price(item["product_url"]) if item.get("product_url") else None
        results.append({
            "id": item["id"],
            "name": item["name"],
            "supplier": item["supplier"],
            "default_price": item["default_price"],
            "live_price": live_price,
            "product_url": item["product_url"]
        })
    return JSONResponse(content=results)


@app.get("/library-items")
def library_items():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM library_items ORDER BY name ASC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return JSONResponse(content=rows)


@app.post("/save-library-item")
def save_library_item(data: SaveLibraryItemRequest):
    if not data.name.strip():
        return JSONResponse(content={"ok": False, "message": "Item name is required."})

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO library_items (name, supplier, default_price, product_url)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(name, supplier) DO UPDATE SET
            default_price=excluded.default_price,
            product_url=excluded.product_url
    """, (data.name.strip(), data.supplier.strip(), round(data.default_price, 2), data.product_url.strip()))
    conn.commit()
    conn.close()
    return JSONResponse(content={"ok": True, "message": "Item saved to library."})


@app.post("/delete-library-item")
def delete_library_item(data: DeleteLibraryItemRequest):
    conn = db()
    cur = conn.cursor()
    cur.execute("DELETE FROM library_items WHERE id = ?", (data.id,))
    conn.commit()
    deleted = cur.rowcount
    conn.close()
    if not deleted:
        return JSONResponse(content={"ok": False, "message": "Item not found."})
    return JSONResponse(content={"ok": True, "message": "Item deleted."})


@app.get("/customers")
def customers():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM customers ORDER BY customer_name ASC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return JSONResponse(content=rows)


@app.get("/customer-history")
def customer_history(customer_name: str = ""):
    customer_name = customer_name.strip()
    if not customer_name:
        return JSONResponse(content=[])

    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM quotes WHERE customer_name = ? ORDER BY id DESC", (customer_name,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return JSONResponse(content=rows)


@app.post("/save-customer")
def save_customer(data: SaveCustomerRequest):
    if not data.customer_name.strip():
        return JSONResponse(content={"ok": False, "message": "Customer name is required."})

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO customers (customer_name, customer_address, customer_phone)
        VALUES (?, ?, ?)
    """, (data.customer_name.strip(), data.customer_address.strip(), data.customer_phone.strip()))
    conn.commit()
    conn.close()
    return JSONResponse(content={"ok": True, "message": "Customer saved."})


@app.post("/delete-customer")
def delete_customer(data: DeleteCustomerRequest):
    conn = db()
    cur = conn.cursor()
    cur.execute("DELETE FROM customers WHERE id = ?", (data.id,))
    conn.commit()
    deleted = cur.rowcount
    conn.close()
    if not deleted:
        return JSONResponse(content={"ok": False, "message": "Customer not found."})
    return JSONResponse(content={"ok": True, "message": "Customer deleted."})


@app.get("/quotes")
def get_quotes():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM quotes ORDER BY id DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return JSONResponse(content=rows)


@app.get("/quote/{quote_ref}")
def get_quote_by_ref(quote_ref: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM quotes WHERE quote_ref = ?", (quote_ref,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return JSONResponse(status_code=404, content={"ok": False, "message": "Quote not found."})
    return JSONResponse(content=dict(row))


@app.post("/update-quote-status")
def update_quote_status(data: UpdateQuoteStatusRequest):
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE quotes SET status = ? WHERE quote_ref = ?", (data.status.strip() or "draft", data.quote_ref))
    conn.commit()
    updated = cur.rowcount
    conn.close()
    if not updated:
        return JSONResponse(content={"ok": False, "message": "Quote not found."})
    return JSONResponse(content={"ok": True, "message": "Quote status updated."})


@app.post("/convert-to-invoice/{quote_ref}")
def convert_to_invoice(quote_ref: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM quotes WHERE quote_ref = ?", (quote_ref,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return JSONResponse(status_code=404, content={"ok": False, "message": "Quote not found."})

    row = dict(row)
    if row.get("invoice_ref"):
        conn.close()
        return JSONResponse(content={"ok": True, "invoice_ref": row["invoice_ref"], "message": "Already invoiced."})

    invoice_ref = generate_invoice_ref()
    invoice_created_at = datetime.now().strftime("%d/%m/%Y %H:%M")

    cur.execute("""
        UPDATE quotes
        SET status = ?, invoice_ref = ?, invoice_created_at = ?
        WHERE quote_ref = ?
    """, ("invoiced", invoice_ref, invoice_created_at, quote_ref))
    conn.commit()
    conn.close()

    return JSONResponse(content={"ok": True, "invoice_ref": invoice_ref, "message": "Quote converted to invoice."})


@app.get("/profit-summary")
def profit_summary():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            COUNT(*) AS total_quotes,
            COALESCE(SUM(total_price), 0) AS revenue,
            COALESCE(SUM(labour), 0) AS labour_total,
            COALESCE(SUM(materials), 0) AS raw_materials_total,
            COALESCE(SUM(internal_hidden_uplift), 0) AS uplift_total
        FROM quotes
    """)
    row = dict(cur.fetchone())

    cur.execute("SELECT COUNT(*) AS c FROM quotes WHERE status = 'accepted'")
    accepted = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM quotes WHERE status = 'invoiced'")
    invoiced = cur.fetchone()["c"]

    conn.close()

    return JSONResponse(content={
        "total_quotes": row["total_quotes"],
        "revenue": round(row["revenue"], 2),
        "labour_total": round(row["labour_total"], 2),
        "raw_materials_total": round(row["raw_materials_total"], 2),
        "uplift_total": round(row["uplift_total"], 2),
        "accepted_quotes": accepted,
        "invoiced_quotes": invoiced
    })


@app.get("/scheduled-jobs")
def scheduled_jobs():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM scheduled_jobs ORDER BY scheduled_date ASC, scheduled_time ASC, id DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return JSONResponse(content=rows)


@app.post("/schedule-job")
def schedule_job(data: ScheduleJobRequest):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO scheduled_jobs (quote_ref, customer_name, job_title, scheduled_date, scheduled_time, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        data.quote_ref.strip(),
        data.customer_name.strip(),
        data.job_title.strip(),
        data.scheduled_date.strip(),
        data.scheduled_time.strip(),
        data.notes.strip(),
        datetime.now().strftime("%d/%m/%Y %H:%M")
    ))
    conn.commit()
    conn.close()
    return JSONResponse(content={"ok": True, "message": "Job scheduled."})


@app.post("/delete-scheduled-job")
def delete_scheduled_job(data: DeleteScheduleJobRequest):
    conn = db()
    cur = conn.cursor()
    cur.execute("DELETE FROM scheduled_jobs WHERE id = ?", (data.id,))
    conn.commit()
    deleted = cur.rowcount
    conn.close()
    if not deleted:
        return JSONResponse(content={"ok": False, "message": "Scheduled job not found."})
    return JSONResponse(content={"ok": True, "message": "Scheduled job deleted."})


HTML = r"""
<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nigel Harvey Ltd Quotes</title>
<style>
body { font-family: Arial, sans-serif; background:#f5f5f5; margin:0; padding:12px; color:#111; }
.wrap { max-width:1040px; margin:0 auto; }
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
.btn-save { background:#0b5ed7; margin-top:8px; }
.btn-delete { background:#b42318; font-size:14px; padding:8px; margin-top:8px; }
.btn-refresh { background:#555; font-size:14px; padding:10px; margin-top:8px; }
.btn-small { font-size:14px; padding:8px; }
.btn-pack { background:#6b21a8; font-size:15px; padding:10px; }
.templates, .packs { display:grid; grid-template-columns:repeat(2, 1fr); gap:8px; }
.material-row { border:1px solid #ddd; padding:12px; border-radius:10px; margin-bottom:10px; background:#fafafa; }
.row { display:flex; justify-content:space-between; gap:10px; margin:8px 0; }
.muted { color:#666; }
.result { display:none; background:#f3faf3; border:1px solid #b7d7b7; }
.error { display:none; background:#fff3f3; border:1px solid #e0b7b7; color:#a33; padding:12px; border-radius:10px; margin-top:12px; }
.notice { display:none; background:#eef6ff; border:1px solid #b9d3f0; color:#134; padding:12px; border-radius:10px; margin-top:12px; }
.actions { display:grid; gap:10px; margin-top:14px; }
.history-item, .library-item, .customer-item, .compare-item, .summary-item, .schedule-item { border:1px solid #ddd; border-radius:10px; padding:12px; margin-bottom:10px; background:#fafafa; }
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
.status-badge { display:inline-block; padding:4px 8px; border-radius:999px; background:#eee; font-size:12px; font-weight:700; }
.no-print { display:block; }

details.section-collapse {
  background:white;
  border-radius:14px;
  margin-bottom:14px;
  box-shadow:0 2px 10px rgba(0,0,0,0.06);
  overflow:hidden;
}

details.section-collapse summary {
  list-style:none;
  cursor:pointer;
  padding:16px;
  font-size:20px;
  font-weight:700;
  background:white;
  border-bottom:1px solid #eee;
}

details.section-collapse summary::-webkit-details-marker {
  display:none;
}

details.section-collapse summary::after {
  content:"▾";
  float:right;
  font-size:18px;
}

details.section-collapse[open] summary::after {
  content:"▴";
}

.section-inner {
  padding:16px;
  background:white;
}

@media print {
  .no-print { display:none !important; }
  body { background:white; padding:0; }
  .card, details.section-collapse { box-shadow:none; border:none; padding:0; margin:0 0 12px 0; }
  .section-inner { padding:0; }
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

    <h3>Job packs + auto materials</h3>
    <div id="packButtons" class="packs"></div>

    <label for="quote_type">Quote type</label>
    <select id="quote_type" onchange="toggleBathroomFields(); updateLabourSuggestion();">
      <option value="small">Small Job</option>
      <option value="bathroom">Bathroom</option>
      <option value="heating">Heating</option>
    </select>

    <label for="customer_name">Customer name</label>
    <input id="customer_name" placeholder="John Smith" onblur="loadCustomerHistoryForCurrent()">

    <label for="customer_address">Customer address</label>
    <textarea id="customer_address" placeholder="125 Bushy Hill Drive, Guildford, GU1 2UG"></textarea>

    <label for="customer_phone">Customer phone</label>
    <input id="customer_phone" placeholder="07123 456789">

    <button type="button" class="btn-save btn-small" onclick="saveCustomer()">Save customer</button>
    <div id="customerNotice" class="notice"></div>

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
  </div>

  <div class="card no-print">
    <h3>Live smart material search</h3>
    <input id="materialSearch" placeholder="Search materials e.g. 15mm speedfit elbow, basin waste, kitchen tap" oninput="debouncedSearch()">
    <div id="searchResults" class="search-results hidden"></div>

    <h3>Supplier comparison</h3>
    <div id="comparisonList" class="small">Search above to compare suppliers and prices.</div>

    <h3>Save / edit a product in library</h3>
    <input type="hidden" id="library_id">
    <label for="library_name">Item name</label>
    <input id="library_name" placeholder="e.g. Kitchen Mixer Tap">

    <label for="library_supplier">Supplier</label>
    <select id="library_supplier">
      <option value="City Plumbing">City Plumbing</option>
      <option value="Screwfix">Screwfix</option>
      <option value="Toolstation">Toolstation</option>
      <option value="Topps Tiles">Topps Tiles</option>
      <option value="Selco">Selco</option>
    </select>

    <label for="library_url">Product URL</label>
    <input id="library_url" placeholder="https://...">

    <label for="library_default_price">Fallback price (£)</label>
    <input id="library_default_price" type="number" step="0.01" placeholder="0">

    <button type="button" class="btn-save" onclick="saveLibraryItem()">Save / update library item</button>
    <div id="libraryNotice" class="notice"></div>
  </div>

  <details class="section-collapse no-print">
    <summary>👤 Customer database</summary>
    <div class="section-inner">
      <button type="button" class="btn-refresh" onclick="loadCustomers()">Refresh customers</button>
      <div id="customerList" class="small" style="margin-top:12px;">No saved customers yet.</div>
    </div>
  </details>

  <details class="section-collapse no-print">
    <summary>

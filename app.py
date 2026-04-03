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
.cols2 { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
.muted { color:#666; }
.result { display:none; background:#f3faf3; border:1px solid #b7d7b7; }
.error { display:none; background:#fff3f3; border:1px solid #e0b7b7; color:#a33; padding:12px; border-radius:10px; margin-top:12px; }
.notice { display:none; background:#eef6ff; border:1px solid #b9d3f0; color:#134; padding:12px; border-radius:10px; margin-top:12px; }
.actions { display:grid; gap:10px; margin-top:14px; }
.history-item, .library-item, .customer-item, .compare-item, .summary-item, .schedule-item { border:1px solid #ddd; border-radius:10px; padding:12px; margin-bottom:10px; background:#fafafa; }
.small { font-size:14px; color:#666; }
.hidden { display:none; }
.collapsible-header {
  background:#111;
  color:#fff;
  padding:12px;
  border-radius:10px;
  margin-bottom:8px;
  cursor:pointer;
  font-weight:700;
}

.collapsible-content {
  display:none;
}

.collapsible-content.active {
  display:block;
}
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

<div class="card no-print">
    <h2>Customer history per job</h2>
    <div id="customerHistory" class="small">Enter or select a customer to see history.</div>
  </div>

  <div class="card no-print">
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
      <div class="row"><span class="muted">Quote ref</span><span id="r_quote_ref"></span></div>
      <div class="row"><span class="muted">Invoice ref</span><span id="r_invoice_ref"></span></div>
      <div class="row"><span class="muted">Date</span><span id="r_date"></span></div>
      <div class="row"><span class="muted">Status</span><span id="r_status"></span></div>
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
      <button class="btn-save" onclick="convertCurrentQuoteToInvoice()">Convert to invoice</button>
    </div>
  </div>

  <div class="card">
    <h2>Saved Quotes</h2>
    <div id="historyList" class="small">No saved quotes yet.</div>
  </div>

</div>

<script>
function toggleSection(id){
  const el = document.getElementById(id);
  el.classList.toggle("active");
}
const JOB_TEMPLATES = __JOB_TEMPLATES__;
const JOB_PACKS = __JOB_PACKS__;
let searchTimer = null;
let currentOpenQuoteRef = "";

function pounds(value) {
  return "£" + Number(value || 0).toFixed(2);
}

function escapeHtml(text) {
  return (text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function showLibraryNotice(message) {
  const notice = document.getElementById("libraryNotice");
  notice.innerText = message;
  notice.style.display = "block";
}

function showCustomerNotice(message) {
  const notice = document.getElementById("customerNotice");
  notice.innerText = message;
  notice.style.display = "block";
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

function renderPacks() {
  const box = document.getElementById("packButtons");
  box.innerHTML = JOB_PACKS.map((p, i) => `
    <button type="button" class="btn-pack" onclick="applyJobPack(${i})">${escapeHtml(p.name)}</button>
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

function clearMaterials() {
  document.getElementById("materials").innerHTML = "";
}

function applyJobPack(index) {
  const p = JOB_PACKS[index];
  document.getElementById("quote_type").value = p.quote_type;
  document.getElementById("job").value = p.job_description;
  document.getElementById("labour").value = p.labour_cost;
  clearMaterials();
  (p.materials || []).forEach(m => addMaterial({
    name: m.name,
    supplier: m.supplier,
    product_url: m.url,
    manual_price: m.manual_price
  }, m.quantity));
  toggleBathroomFields();
  updateLabourSuggestion();
}

function updateLabourSuggestion() {
  const quoteType = document.getElementById("quote_type").value;
  const box = document.getElementById("labourSuggestion");
  if (quoteType === "bathroom") box.innerText = "Typical bathroom labour is often higher. Adjust to suit your job.";
  else if (quoteType === "heating") box.innerText = "Heating jobs often vary by size and access. Adjust labour as needed.";
  else box.innerText = "Small jobs: use your judgement and minimum charge where needed.";
}

function addMaterial(prefill = null, qtyOverride = null) {
  const qty = qtyOverride !== null ? qtyOverride : (prefill ? 1 : "");
  const div = document.createElement("div");
  div.className = "material-row";
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
    <input class="m-url" placeholder="https://..." value="${prefill ? escapeHtml(prefill.product_url || "") : ""}">
    <label>Manual price (£)</label>
    <input class="m-manual" type="number" step="0.01" placeholder="0" value="${prefill ? prefill.manual_price : ""}">
  `;
  document.getElementById("materials").appendChild(div);
  if (prefill) div.querySelector(".m-supplier").value = prefill.supplier || "City Plumbing";
}

function debouncedSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(searchMaterials, 300);
}

async function searchMaterials() {
  const query = document.getElementById("materialSearch").value.trim();
  const resultsBox = document.getElementById("searchResults");
  const comparisonBox = document.getElementById("comparisonList");

  if (query.length < 2) {
    resultsBox.classList.add("hidden");
    resultsBox.innerHTML = "";
    comparisonBox.innerHTML = "Search above to compare suppliers and prices.";
    return;
  }

  resultsBox.innerHTML = `<div class="search-item">Searching...</div>`;
  resultsBox.classList.remove("hidden");

  try {
    const res = await fetch("/material-search?q=" + encodeURIComponent(query));
    const results = await res.json();

    if (!results.length) {
      resultsBox.innerHTML = `<div class="search-item">No matches found</div>`;
      comparisonBox.innerHTML = "No supplier matches found.";
      return;
    }

    resultsBox.innerHTML = results.map((item) => {
      const bestPrice = item.live_price !== null ? item.live_price : item.default_price;
      const label = item.live_price !== null ? "live" : "default";
      return `
        <div class="search-item" onclick='selectSearchResult(${JSON.stringify(item)})'>
          <strong>${escapeHtml(item.name)}</strong><br>
          <span class="small">${escapeHtml(item.supplier)} · ${pounds(bestPrice)} (${label})</span>
        </div>
      `;
    }).join("");

    const sorted = [...results].sort((a, b) => {
      const pa = a.live_price !== null ? a.live_price : a.default_price;
      const pb = b.live_price !== null ? b.live_price : b.default_price;
      return pa - pb;
    });

    comparisonBox.innerHTML = sorted.map(item => {
      const bestPrice = item.live_price !== null ? item.live_price : item.default_price;
      const label = item.live_price !== null ? "live" : "default";
      return `
        <div class="compare-item">
          <strong>${escapeHtml(item.name)}</strong><br>
          <span class="small">${escapeHtml(item.supplier)} · ${pounds(bestPrice)} (${label})</span>
        </div>
      `;
    }).join("");
  } catch (e) {
    resultsBox.innerHTML = `<div class="search-item">Search failed</div>`;
    comparisonBox.innerHTML = "Comparison failed.";
  }
}

async function autoSaveSearchItem(item) {
  const bestPrice = item.live_price !== null ? item.live_price : item.default_price;
  try {
    await fetch("/save-library-item", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        name: item.name || "",
        supplier: item.supplier || "",
        product_url: item.product_url || "",
        default_price: bestPrice || 0
      })
    });
    loadLibraryManager();
  } catch (e) {}
}

async function selectSearchResult(item) {
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

  if ((item.name || "").trim() && (item.supplier || "").trim() && ((item.product_url || "").trim() || bestPrice > 0)) {
    await autoSaveSearchItem(item);
    showLibraryNotice("Search item auto-saved to library.");
  }
}

async function saveLibraryItem() {
  const payload = {
    name: document.getElementById("library_name").value,
    supplier: document.getElementById("library_supplier").value,
    product_url: document.getElementById("library_url").value,
    default_price: parseFloat(document.getElementById("library_default_price").value || 0)
  };

  if (!payload.name.trim()) {
    showLibraryNotice("Please enter an item name.");
    return;
  }

  try {
    const res = await fetch("/save-library-item", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    showLibraryNotice(data.message || "Saved.");
    if (data.ok) {
      clearLibraryForm();
      loadLibraryManager();
    }
  } catch (e) {
    showLibraryNotice("Could not save item.");
  }
}

function fillLibraryForm(item) {
  document.getElementById("library_id").value = item.id || "";
  document.getElementById("library_name").value = item.name || "";
  document.getElementById("library_supplier").value = item.supplier || "City Plumbing";
  document.getElementById("library_url").value = item.product_url || "";
  document.getElementById("library_default_price").value = item.default_price || 0;
  window.scrollTo({top: 0, behavior: "smooth"});
}

function clearLibraryForm() {
  document.getElementById("library_id").value = "";
  document.getElementById("library_name").value = "";
  document.getElementById("library_supplier").value = "City Plumbing";
  document.getElementById("library_url").value = "";
  document.getElementById("library_default_price").value = "";
}

async function loadLibraryManager() {
  const box = document.getElementById("libraryManagerList");
  box.innerHTML = "Loading...";

  try {
    const res = await fetch("/library-items");
    const items = await res.json();

    if (!items.length) {
      box.innerHTML = "No saved library items yet.";
      return;
    }

    box.innerHTML = items.map(item => `
      <div class="library-item">
        <div><strong>${escapeHtml(item.name || "")}</strong></div>
        <div class="small">${escapeHtml(item.supplier || "")} · fallback ${pounds(item.default_price || 0)}</div>
        <div class="small">${escapeHtml(item.product_url || "")}</div>
        <button type="button" class="btn-refresh btn-small" onclick='fillLibraryForm(${JSON.stringify(item)})'>Edit</button>
        <button type="button" class="btn-delete" onclick='deleteLibraryItem(${item.id})'>Delete</button>
      </div>
    `).join("");
  } catch (e) {
    box.innerHTML = "Could not load saved library items.";
  }
}

async function deleteLibraryItem(id) {
  if (!confirm("Delete this saved library item?")) return;
  try {
    const res = await fetch("/delete-library-item", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({id})
    });
    const data = await res.json();
    alert(data.message || "Done");
    loadLibraryManager();
  } catch (e) {
    alert("Could not delete item.");
  }
}

async function saveCustomer() {
  const payload = {
    customer_name: document.getElementById("customer_name").value,
    customer_address: document.getElementById("customer_address").value,
    customer_phone: document.getElementById("customer_phone").value
  };

  if (!payload.customer_name.trim()) {
    showCustomerNotice("Please enter a customer name.");
    return;
  }

  try {
    const res = await fetch("/save-customer", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    showCustomerNotice(data.message || "Customer saved.");
    if (data.ok) {
      loadCustomers();
      loadCustomerHistoryForCurrent();
    }
  } catch (e) {
    showCustomerNotice("Could not save customer.");
  }
}

function fillCustomerForm(customer) {
  document.getElementById("customer_name").value = customer.customer_name || "";
  document.getElementById("customer_address").value = customer.customer_address || "";
  document.getElementById("customer_phone").value = customer.customer_phone || "";
  loadCustomerHistoryForCurrent();
  window.scrollTo({top: 0, behavior: "smooth"});
}

async function loadCustomers() {
  const box = document.getElementById("customerList");
  box.innerHTML = "Loading...";

  try {
    const res = await fetch("/customers");
    const customers = await res.json();

    if (!customers.length) {
      box.innerHTML = "No saved customers yet.";
      return;
    }

    box.innerHTML = customers.map(c => `
      <div class="customer-item">
        <div><strong>${escapeHtml(c.customer_name || "")}</strong></div>
        <div class="small">${escapeHtml(c.customer_phone || "")}</div>
        <div class="small">${escapeHtml(c.customer_address || "")}</div>
        <button type="button" class="btn-refresh btn-small" onclick='fillCustomerForm(${JSON.stringify(c)})'>Use customer</button>
        <button type="button" class="btn-delete" onclick='deleteCustomer(${c.id})'>Delete</button>
      </div>
    `).join("");
  } catch (e) {
    box.innerHTML = "Could not load customers.";
  }
}

async function deleteCustomer(id) {
  if (!confirm("Delete this customer?")) return;
  try {
    const res = await fetch("/delete-customer", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({id})
    });
    const data = await res.json();
    alert(data.message || "Done");
    loadCustomers();
  } catch (e) {
    alert("Could not delete customer.");
  }
}

async function loadCustomerHistoryForCurrent() {
  const customerName = document.getElementById("customer_name").value.trim();
  const box = document.getElementById("customerHistory");
  if (!customerName) {
    box.innerHTML = "Enter or select a customer to see history.";
    return;
  }

  box.innerHTML = "Loading...";

  try {
    const res = await fetch("/customer-history?customer_name=" + encodeURIComponent(customerName));
    const items = await res.json();

    if (!items.length) {
      box.innerHTML = "No job history found for this customer yet.";
      return;
    }

    box.innerHTML = items.map(q => `
      <div class="history-item">
        <div><strong>${escapeHtml(q.quote_ref || "")}</strong></div>
        <div>${escapeHtml(q.job || "")}</div>
        <div class="small">${escapeHtml(q.created_at || "")} · ${pounds(q.total_price || 0)} · ${escapeHtml(q.status || "draft")}</div>
      </div>
    `).join("");
  } catch (e) {
    box.innerHTML = "Could not load customer history.";
  }
}

function normalisePhone(phone) {
  const digits = (phone || "").replace(/\D/g, "");
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

    history.innerHTML = data.map(q => `
      <div class="history-item">
        <div><strong>${escapeHtml(q.customer_name || "No customer name")}</strong></div>
        <div>${escapeHtml(q.job || "")}</div>
        <div class="small">${escapeHtml(q.quote_ref || "")} · ${escapeHtml(q.created_at || "")}</div>
        <div class="small">Total ${pounds(q.total_price)} · <span class="status-badge">${escapeHtml(q.status || "draft")}</span> ${q.invoice_ref ? '· Invoice ' + escapeHtml(q.invoice_ref) : ''}</div>
        <button type="button" class="btn-refresh btn-small" onclick='openSavedQuote(${JSON.stringify(q.quote_ref)})'>Open</button>
        <button type="button" class="btn-save btn-small" onclick='loadQuoteIntoForm(${JSON.stringify(q.quote_ref)})'>Load into form</button>
        <button type="button" class="btn-small" onclick='fillScheduleFromQuote(${JSON.stringify(q.quote_ref)}, ${JSON.stringify(q.customer_name)}, ${JSON.stringify(q.job)})'>Schedule</button>
        <button type="button" class="btn-save btn-small" onclick='convertQuoteToInvoice(${JSON.stringify(q.quote_ref)})'>Invoice</button>
        <label>Status</label>
        <select onchange='updateQuoteStatus(${JSON.stringify(q.quote_ref)}, this.value)'>
          <option value="draft" ${q.status === "draft" ? "selected" : ""}>draft</option>
          <option value="sent" ${q.status === "sent" ? "selected" : ""}>sent</option>
          <option value="accepted" ${q.status === "accepted" ? "selected" : ""}>accepted</option>
          <option value="declined" ${q.status === "declined" ? "selected" : ""}>declined</option>
          <option value="invoiced" ${q.status === "invoiced" ? "selected" : ""}>invoiced</option>
        </select>
      </div>
    `).join("");
  } catch (e) {
    document.getElementById("historyList").innerHTML = "Unable to load saved quotes.";
  }
}

async function updateQuoteStatus(quoteRef, status) {
  try {
    await fetch("/update-quote-status", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({quote_ref: quoteRef, status})
    });
    loadHistory();
    if (currentOpenQuoteRef === quoteRef) {
      openSavedQuote(quoteRef);
    }
  } catch (e) {
    alert("Could not update quote status.");
  }
}

function renderQuoteView(data) {
  currentOpenQuoteRef = data.quote_ref || "";
  document.getElementById("r_quote_ref").innerText = data.quote_ref || "-";
  document.getElementById("r_invoice_ref").innerText = data.invoice_ref || "-";
  document.getElementById("r_date").innerText = data.created_at || "-";
  document.getElementById("r_status").innerText = data.status || "-";
  document.getElementById("r_type").innerText = data.quote_type || "-";
  document.getElementById("r_customer").innerText = data.customer_name || "-";
  document.getElementById("r_phone").innerText = data.customer_phone || "-";
  document.getElementById("r_address").innerText = data.customer_address || "-";
  document.getElementById("r_job").innerText = data.job || "-";
  document.getElementById("r_labour").innerText = pounds(data.labour);
  document.getElementById("r_materials").innerText = pounds(data.materials);
  document.getElementById("r_total").innerText = pounds(data.total_price);

  if (document.getElementById("internal_mode").checked) {
    document.getElementById("internalBox").classList.remove("hidden");
    document.getElementById("r_internal_raw").innerText = pounds(data.internal_raw_materials);
    document.getElementById("r_internal_job_multiplier").innerText = data.internal_job_multiplier + "x";
    document.getElementById("r_internal_after_job").innerText = pounds(data.internal_after_job_markup);
    document.getElementById("r_internal_handling_percent").innerText = data.internal_handling_percent + "%";
    document.getElementById("r_internal_after_handling").innerText = pounds(data.internal_after_handling);
    document.getElementById("r_internal_hidden_uplift").innerText = pounds(data.internal_hidden_uplift);
  } else {
    document.getElementById("internalBox").classList.add("hidden");
  }

  const message =
`Nigel Harvey Ltd Quote

Quote ref: ${data.quote_ref || "-"}
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

  document.getElementById("resultCard").style.display = "block";
}

async function openSavedQuote(quoteRef) {
  try {
    const res = await fetch("/quote/" + encodeURIComponent(quoteRef));
    const data = await res.json();
    renderQuoteView(data);
    window.scrollTo({top: document.getElementById("resultCard").offsetTop - 20, behavior: "smooth"});
  } catch (e) {
    alert("Could not open quote.");
  }
}

async function loadQuoteIntoForm(quoteRef) {
  try {
    const res = await fetch("/quote/" + encodeURIComponent(quoteRef));
    const data = await res.json();

    document.getElementById("quote_type").value = data.quote_type || "small";
    document.getElementById("customer_name").value = data.customer_name || "";
    document.getElementById("customer_address").value = data.customer_address || "";
    document.getElementById("customer_phone").value = data.customer_phone || "";
    document.getElementById("job").value = data.job || "";
    document.getElementById("labour").value = data.labour || 0;

    document.getElementById("include_materials_handling").checked = !!data.include_materials_handling;
    document.getElementById("materials_handling_percent").value = String(data.materials_handling_percent || 25);

    document.getElementById("tiling").checked = !!data.tiling;
    document.getElementById("wall_tiling_m2").value = data.wall_tiling_m2 || 0;
    document.getElementById("floor_tiling_m2").value = data.floor_tiling_m2 || 0;
    document.getElementById("wall_height").value = data.wall_height || "half";
    document.getElementById("customer_supplies_tiles").checked = !!data.customer_supplies_tiles;

    clearMaterials();
    let materials = [];
    try {
      materials = JSON.parse(data.materials_json || "[]");
    } catch (e) {
      materials = [];
    }

    materials.forEach(m => addMaterial({
      name: m.name,
      supplier: m.supplier,
      product_url: m.url,
      manual_price: m.manual_price
    }, m.quantity));

    toggleBathroomFields();
    updateLabourSuggestion();
    loadCustomerHistoryForCurrent();
    window.scrollTo({top: 0, behavior: "smooth"});
  } catch (e) {
    alert("Could not load quote into form.");
  }
}

async function convertQuoteToInvoice(quoteRef) {
  try {
    const res = await fetch("/convert-to-invoice/" + encodeURIComponent(quoteRef), {method: "POST"});
    const data = await res.json();
    alert(data.message + (data.invoice_ref ? " " + data.invoice_ref : ""));
    loadHistory();
    if (currentOpenQuoteRef === quoteRef) {
      openSavedQuote(quoteRef);
    }
  } catch (e) {
    alert("Could not convert quote to invoice.");
  }
}

function convertCurrentQuoteToInvoice() {
  if (!currentOpenQuoteRef) {
    alert("Open a saved quote first.");
    return;
  }
  convertQuoteToInvoice(currentOpenQuoteRef);
}

async function loadProfitSummary() {
  const box = document.getElementById("profitSummary");
  box.innerHTML = "Loading...";
  try {
    const res = await fetch("/profit-summary");
    const data = await res.json();
    box.innerHTML = `
      <div class="summary-item"><strong>Total quotes</strong><br>${data.total_quotes}</div>
      <div class="summary-item"><strong>Total revenue</strong><br>${pounds(data.revenue)}</div>
      <div class="summary-item"><strong>Total labour</strong><br>${pounds(data.labour_total)}</div>
      <div class="summary-item"><strong>Raw materials total</strong><br>${pounds(data.raw_materials_total)}</div>
      <div class="summary-item"><strong>Total uplift</strong><br>${pounds(data.uplift_total)}</div>
      <div class="summary-item"><strong>Accepted quotes</strong><br>${data.accepted_quotes}</div>
      <div class="summary-item"><strong>Invoiced quotes</strong><br>${data.invoiced_quotes}</div>
    `;
  } catch (e) {
    box.innerHTML = "Could not load dashboard.";
  }
}

function fillScheduleFromQuote(quoteRef, customerName, jobTitle) {
  document.getElementById("schedule_quote_ref").value = quoteRef || "";
  document.getElementById("schedule_customer_name").value = customerName || "";
  document.getElementById("schedule_job_title").value = jobTitle || "";
  window.scrollTo({top: document.getElementById("schedule_quote_ref").offsetTop - 20, behavior: "smooth"});
}

async function scheduleJob() {
  const payload = {
    quote_ref: document.getElementById("schedule_quote_ref").value,
    customer_name: document.getElementById("schedule_customer_name").value,
    job_title: document.getElementById("schedule_job_title").value,
    scheduled_date: document.getElementById("schedule_date").value,
    scheduled_time: document.getElementById("schedule_time").value,
    notes: document.getElementById("schedule_notes").value
  };

  try {
    const res = await fetch("/schedule-job", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    alert(data.message || "Scheduled.");
    loadSchedule();
  } catch (e) {
    alert("Could not schedule job.");
  }
}

async function loadSchedule() {
  const box = document.getElementById("scheduleList");
  box.innerHTML = "Loading...";
  try {
    const res = await fetch("/scheduled-jobs");
    const jobs = await res.json();

    if (!jobs.length) {
      box.innerHTML = "No scheduled jobs yet.";
      return;
    }

    box.innerHTML = jobs.map(j => `
      <div class="schedule-item">
        <div><strong>${escapeHtml(j.job_title || "")}</strong></div>
        <div class="small">${escapeHtml(j.customer_name || "")}</div>
        <div class="small">${escapeHtml(j.scheduled_date || "")} ${escapeHtml(j.scheduled_time || "")}</div>
        <div class="small">${escapeHtml(j.quote_ref || "")}</div>
        <div class="small">${escapeHtml(j.notes || "")}</div>
        <button type="button" class="btn-delete" onclick='deleteScheduledJob(${j.id})'>Delete</button>
      </div>
    `).join("");
  } catch (e) {
    box.innerHTML = "Could not load schedule.";
  }
}

async function deleteScheduledJob(id) {
  if (!confirm("Delete this scheduled job?")) return;
  try {
    const res = await fetch("/delete-scheduled-job", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({id})
    });
    const data = await res.json();
    alert(data.message || "Done");
    loadSchedule();
  } catch (e) {
    alert("Could not delete scheduled job.");
  }
}

async function generateQuote() {
  const errorBox = document.getElementById("error");
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
    renderQuoteView(data);
    await loadHistory();
    await loadProfitSummary();
    loadCustomerHistoryForCurrent();
  } catch (err) {
    errorBox.innerText = "Something went wrong generating the quote.";
    errorBox.style.display = "block";
  }
}

renderTemplates();
renderPacks();
toggleBathroomFields();
addMaterial();
updateLabourSuggestion();
loadHistory();
loadLibraryManager();
loadCustomers();
loadProfitSummary();
loadSchedule();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def home():
    html = HTML.replace("__JOB_TEMPLATES__", json.dumps(JOB_TEMPLATES))
    html = html.replace("__JOB_PACKS__", json.dumps(JOB_PACKS))
    return html


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
    quote_ref = generate_quote_ref()

    quote = {
        "quote_ref": quote_ref,
        "status": "draft",
        "invoice_ref": "",
        "invoice_created_at": "",
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
        "materials_json": json.dumps([m.model_dump() for m in data.materials]),
        "include_materials_handling": 1 if data.include_materials_handling else 0,
        "materials_handling_percent": round(data.materials_handling_percent, 2),
        "tiling": 1 if data.tiling else 0,
        "wall_tiling_m2": round(data.wall_tiling_m2, 2),
        "floor_tiling_m2": round(data.floor_tiling_m2, 2),
        "wall_height": data.wall_height,
        "customer_supplies_tiles": 1 if data.customer_supplies_tiles else 0
    }

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO quotes (
            quote_ref, status, invoice_ref, invoice_created_at, quote_type, customer_name, customer_address, customer_phone,
            job, labour, materials, total_price, created_at,
            internal_raw_materials, internal_job_multiplier, internal_after_job_markup,
            internal_handling_percent, internal_after_handling, internal_hidden_uplift,
            materials_json, include_materials_handling, materials_handling_percent,
            tiling, wall_tiling_m2, floor_tiling_m2, wall_height, customer_supplies_tiles
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        quote["quote_ref"], quote["status"], quote["invoice_ref"], quote["invoice_created_at"], quote["quote_type"],
        quote["customer_name"], quote["customer_address"], quote["customer_phone"], quote["job"], quote["labour"],
        quote["materials"], quote["total_price"], quote["created_at"], quote["internal_raw_materials"],
        quote["internal_job_multiplier"], quote["internal_after_job_markup"], quote["internal_handling_percent"],
        quote["internal_after_handling"], quote["internal_hidden_uplift"], quote["materials_json"],
        quote["include_materials_handling"], quote["materials_handling_percent"], quote["tiling"],
        quote["wall_tiling_m2"], quote["floor_tiling_m2"], quote["wall_height"], quote["customer_supplies_tiles"]
    ))
    conn.commit()
    conn.close()

    return JSONResponse(content=quote)

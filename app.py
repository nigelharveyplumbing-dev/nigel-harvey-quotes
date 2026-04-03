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

DBFILE = "nigelquotes.db"

BASEMATERIALLIBRARY = [
    {"name": "15mm Copper Pipe 3m", "supplier": "City Plumbing", "defaultprice": 14.50, "producturl": "https://www.cityplumbing.co.uk/p/wednesbury-plain-copper-tube-length-15mm-x-3m-x015l-3/p/313813"},
    {"name": "22mm Copper Pipe 3m", "supplier": "City Plumbing", "defaultprice": 28.00, "producturl": "https://www.cityplumbing.co.uk/p/wednesbury-plain-copper-tube-length-22mm-x-3m-x022l-3/p/313814"},
    {"name": "15mm Copper Elbow", "supplier": "Screwfix", "defaultprice": 1.20, "producturl": "https://www.screwfix.com/p/compression-equal-elbow-15mm/69341"},
    {"name": "22mm Copper Elbow", "supplier": "Screwfix", "defaultprice": 2.00, "producturl": "https://www.screwfix.com/p/compression-equal-elbow-22mm/69342"},
    {"name": "15mm Copper Tee", "supplier": "Screwfix", "defaultprice": 1.80, "producturl": "https://www.screwfix.com/p/compression-equal-tee-15mm/69347"},
    {"name": "22mm Copper Tee", "supplier": "Screwfix", "defaultprice": 3.20, "producturl": "https://www.screwfix.com/p/compression-equal-tee-22mm/69348"},
    {"name": "15mm Straight Coupler", "supplier": "Screwfix", "defaultprice": 1.00, "producturl": "https://www.screwfix.com/p/compression-coupler-15mm/69337"},
    {"name": "22mm Straight Coupler", "supplier": "Screwfix", "defaultprice": 1.80, "producturl": "https://www.screwfix.com/p/compression-coupler-22mm/69338"},
    {"name": "15mm Isolating Valve", "supplier": "Toolstation", "defaultprice": 3.50, "producturl": "https://www.toolstation.com/isolating-valve/p37037"},
    {"name": "22mm Isolating Valve", "supplier": "Toolstation", "defaultprice": 5.50, "producturl": "https://www.toolstation.com/isolating-valve/p37038"},
    {"name": "Flexible Tap Connector", "supplier": "Screwfix", "defaultprice": 6.50, "producturl": "https://www.screwfix.com/p/flexible-tap-connector-15mm-x-1-2-x-300mm/11494"},
    {"name": "Basin Waste", "supplier": "Screwfix", "defaultprice": 10.00, "producturl": "https://www.screwfix.com/p/basin-waste-with-plug-chain-chrome/12739"},
    {"name": "Sink Waste Kit", "supplier": "Screwfix", "defaultprice": 18.00, "producturl": "https://www.screwfix.com/p/kitchen-sink-waste-kit-40mm/12754"},
    {"name": "P Trap 40mm", "supplier": "Toolstation", "defaultprice": 6.00, "producturl": "https://www.toolstation.com/p-trap/p23741"},
    {"name": "Hep2O 15mm Pipe Coil", "supplier": "City Plumbing", "defaultprice": 65.00, "producturl": "https://www.cityplumbing.co.uk/p/hep2o-barrier-pipe-15mm-x-25m-hx15-25c/p/215674"},
    {"name": "Hep2O 15mm Elbow", "supplier": "City Plumbing", "defaultprice": 5.00, "producturl": "https://www.cityplumbing.co.uk/p/hep2o-equal-elbow-15mm-hx15-15/p/215676"},
    {"name": "Hep2O 15mm Coupler", "supplier": "City Plumbing", "defaultprice": 4.50, "producturl": "https://www.cityplumbing.co.uk/p/hep2o-straight-coupler-15mm-hx15-15/p/215675"},
    {"name": "Speedfit 15mm Elbow", "supplier": "Screwfix", "defaultprice": 5.00, "producturl": "https://www.screwfix.com/p/jg-speedfit-equal-elbow-15mm/97179"},
    {"name": "Speedfit 15mm Coupler", "supplier": "Screwfix", "defaultprice": 4.20, "producturl": "https://www.screwfix.com/p/jg-speedfit-straight-coupler-15mm/69363"},
    {"name": "Speedfit 15mm Pipe", "supplier": "Screwfix", "defaultprice": 55.00, "producturl": "https://www.screwfix.com/p/jg-speedfit-barrier-pipe-coil-15mm-x-25m/69386"},
    {"name": "Jointing Compound", "supplier": "Toolstation", "defaultprice": 6.50, "producturl": "https://www.toolstation.com/jointing-compound/p17635"},
    {"name": "PTFE Tape", "supplier": "Toolstation", "defaultprice": 1.00, "producturl": "https://www.toolstation.com/ptfe-tape/p31207"},
    {"name": "Pipe Freeze Spray", "supplier": "Toolstation", "defaultprice": 8.00, "producturl": "https://www.toolstation.com/pipe-freeze-spray/p23762"},
    {"name": "Outside Tap Kit", "supplier": "Screwfix", "defaultprice": 18.00, "producturl": "https://www.screwfix.com/p/outside-tap-kit/37241"},
    {"name": "Service Valve", "supplier": "Screwfix", "defaultprice": 4.00, "producturl": "https://www.screwfix.com/p/service-valve-15mm/27792"}
]

JOBTEMPLATES = [
    {"name": "Replace tap", "quotetype": "small", "job": "Remove existing tap and fit new tap including testing for leaks.", "labour": 120},
    {"name": "Replace toilet", "quotetype": "small", "job": "Remove existing toilet and fit new close-coupled toilet including waste connection and testing.", "labour": 180},
    {"name": "Basin waste", "quotetype": "small", "job": "Remove faulty basin waste and fit new basin waste including testing for leaks.", "labour": 90},
    {"name": "Outside tap", "quotetype": "small", "job": "Supply and fit outside tap kit with isolation and testing.", "labour": 150},
    {"name": "Kitchen sink waste", "quotetype": "small", "job": "Remove existing sink waste and fit new waste/trap arrangement including testing.", "labour": 120},
    {"name": "Bathroom install", "quotetype": "bathroom", "job": "Bathroom plumbing installation including first fix, second fix and sanitaryware connections.", "labour": 1800},
    {"name": "Bathroom refurb", "quotetype": "bathroom", "job": "Bathroom refurbishment plumbing works including sanitaryware, wastes and connections.", "labour": 2200},
    {"name": "Heating repair", "quotetype": "heating", "job": "Heating repair works including diagnosis, replacement parts and testing.", "labour": 150},
    {"name": "Radiator install", "quotetype": "heating", "job": "Supply and fit radiator including valves and testing.", "labour": 180},
    {"name": "Full heating system", "quotetype": "heating", "job": "Full heating system installation including pipework, controls, radiators and commissioning.", "labour": 3500}
]

JOBPACKS = [
    {
        "name": "Replace tap",
        "quotetype": "small",
        "jobdescription": "Remove existing tap and fit new tap including testing for leaks.",
        "labourcost": 120,
        "materials": [
            {"name": "Flexible Tap Connector", "supplier": "Screwfix", "quantity": 2, "url": "https://www.screwfix.com/p/flexible-tap-connector-15mm-x-1-2-x-300mm/11494", "manualprice": 6.50},
            {"name": "15mm Isolating Valve", "supplier": "Toolstation", "quantity": 2, "url": "https://www.toolstation.com/isolating-valve/p37037", "manualprice": 3.50},
            {"name": "PTFE Tape", "supplier": "Toolstation", "quantity": 1, "url": "https://www.toolstation.com/ptfe-tape/p31207", "manualprice": 1.00}
        ]
    },
    {
        "name": "Outside tap",
        "quotetype": "small",
        "jobdescription": "Supply and fit outside tap kit with isolation and testing.",
        "labourcost": 150,
        "materials": [
            {"name": "Outside Tap Kit", "supplier": "Screwfix", "quantity": 1, "url": "https://www.screwfix.com/p/outside-tap-kit/37241", "manualprice": 18.00},
            {"name": "15mm Isolating Valve", "supplier": "Toolstation", "quantity": 1, "url": "https://www.toolstation.com/isolating-valve/p37037", "manualprice": 3.50},
            {"name": "PTFE Tape", "supplier": "Toolstation", "quantity": 1, "url": "https://www.toolstation.com/ptfe-tape/p31207", "manualprice": 1.00}
        ]
    },
    {
        "name": "Radiator install",
        "quotetype": "heating",
        "jobdescription": "Supply and fit radiator including valves and testing.",
        "labourcost": 180,
        "materials": [
            {"name": "15mm Copper Pipe 3m", "supplier": "City Plumbing", "quantity": 1, "url": "https://www.cityplumbing.co.uk/p/wednesbury-plain-copper-tube-length-15mm-x-3m-x015l-3/p/313813", "manualprice": 14.50},
            {"name": "Speedfit 15mm Elbow", "supplier": "Screwfix", "quantity": 2, "url": "https://www.screwfix.com/p/jg-speedfit-equal-elbow-15mm/97179", "manualprice": 5.00},
            {"name": "PTFE Tape", "supplier": "Toolstation", "quantity": 1, "url": "https://www.toolstation.com/ptfe-tape/p31207", "manualprice": 1.00}
        ]
    }
]

class MaterialItem(BaseModel):
    name: str = ""
    quantity: float = 1
    supplier: str = ""
    url: str = ""
    manualprice: float = 0

class QuoteRequest(BaseModel):
    quotetype: str = "small"
    customername: str = ""
    customeraddress: str = ""
    customerphone: str = ""
    jobdescription: str = ""
    labourcost: float = 0
    includematerialshandling: bool = True
    materialshandlingpercent: float = 25
    materials: list[MaterialItem] = []
    tiling: bool = False
    walltilingm2: float = 0
    floortilingm2: float = 0
    wallheight: str = "half"
    customersuppliestiles: bool = False

class SaveLibraryItemRequest(BaseModel):
    name: str
    supplier: str = ""
    producturl: str = ""
    defaultprice: float = 0

class DeleteLibraryItemRequest(BaseModel):
    id: int

class SaveCustomerRequest(BaseModel):
    customername: str
    customeraddress: str = ""
    customerphone: str = ""

class DeleteCustomerRequest(BaseModel):
    id: int

class UpdateQuoteStatusRequest(BaseModel):
    quoteref: str
    status: str

class ScheduleJobRequest(BaseModel):
    quoteref: str = ""
    customername: str = ""
    jobtitle: str = ""
    scheduleddate: str = ""
    scheduledtime: str = ""
    notes: str = ""

class DeleteScheduleJobRequest(BaseModel):
    id: int

def db():
    conn = sqlite3.connect(DBFILE)
    conn.rowfactory = sqlite3.Row
    return conn

def initdb():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS libraryitems (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            supplier TEXT NOT NULL,
            defaultprice REAL NOT NULL DEFAULT 0,
            producturl TEXT NOT NULL DEFAULT '',
            UNIQUE(name, supplier)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customername TEXT NOT NULL,
            customeraddress TEXT NOT NULL DEFAULT '',
            customerphone TEXT NOT NULL DEFAULT ''
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quoteref TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'draft',
            invoiceref TEXT NOT NULL DEFAULT '',
            invoicecreatedat TEXT NOT NULL DEFAULT '',
            quotetype TEXT NOT NULL,
            customername TEXT NOT NULL DEFAULT '',
            customeraddress TEXT NOT NULL DEFAULT '',
            customerphone TEXT NOT NULL DEFAULT '',
            job TEXT NOT NULL DEFAULT '',
            labour REAL NOT NULL DEFAULT 0,
            materials REAL NOT NULL DEFAULT 0,
            totalprice REAL NOT NULL DEFAULT 0,
            createdat TEXT NOT NULL,
            internalrawmaterials REAL NOT NULL DEFAULT 0,
            internaljobmultiplier REAL NOT NULL DEFAULT 1,
            internalafterjobmarkup REAL NOT NULL DEFAULT 0,
            internalhandlingpercent REAL NOT NULL DEFAULT 0,
            internalafterhandling REAL NOT NULL DEFAULT 0,
            internalhiddenuplift REAL NOT NULL DEFAULT 0,
            materialsjson TEXT NOT NULL DEFAULT '[]',
            includematerialshandling INTEGER NOT NULL DEFAULT 1,
            materialshandlingpercent REAL NOT NULL DEFAULT 25,
            tiling INTEGER NOT NULL DEFAULT 0,
            walltilingm2 REAL NOT NULL DEFAULT 0,
            floortilingm2 REAL NOT NULL DEFAULT 0,
            wallheight TEXT NOT NULL DEFAULT 'half',
            customersuppliestiles INTEGER NOT NULL DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS scheduledjobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quoteref TEXT NOT NULL DEFAULT '',
            customername TEXT NOT NULL DEFAULT '',
            jobtitle TEXT NOT NULL DEFAULT '',
            scheduleddate TEXT NOT NULL DEFAULT '',
            scheduledtime TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            createdat TEXT NOT NULL
        )
    """)

    conn.commit()

    cur.execute("SELECT COUNT() AS c FROM libraryitems")
    count = cur.fetchone()["c"]

    if count == 0:
        for item in BASEMATERIALLIBRARY:
            cur.execute("""
                INSERT OR IGNORE INTO libraryitems (name, supplier, defaultprice, producturl)
                VALUES (?, ?, ?, ?)
            """, (item["name"], item["supplier"], item["defaultprice"], item["producturl"]))
        conn.commit()

    conn.close()

initdb()

def fetchprice(url: str):
    if not url:
        return None
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=8)
        if r.statuscode != 200:
            return None

        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.gettext(" ", strip=True)

        if "cityplumbing" in url:
            patterns = [
                r'£\s?(\d+\.\d{2})\seach,\sInc\.?\sVAT',
                r'£\s?(\d+\.\d{2})\sInc\.?\sVAT',
                r'£\s?(\d+\.\d{2})\seach',
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

def generatequoteref():
    conn = db()
    cur = conn.cursor()
    today = datetime.now().strftime("%Y%m%d")
    cur.execute("SELECT COUNT() AS c FROM quotes WHERE quoteref LIKE ?", (f"NHQ-{today}-%",))
    count = cur.fetchone()["c"]
    conn.close()
    return f"NHQ-{today}-{count + 1:03d}"

def generateinvoiceref():
    conn = db()
    cur = conn.cursor()
    today = datetime.now().strftime("%Y%m%d")
    cur.execute("SELECT COUNT() AS c FROM quotes WHERE invoiceref LIKE ?", (f"NHI-{today}-%",))
    count = cur.fetchone()["c"]
    conn.close()
    return f"NHI-{today}-{count + 1:03d}"

@app.get("/job-packs")
def getjobpacks():
    return JSONResponse(content=JOBPACKS)

@app.get("/material-search")
def materialsearch(q: str = ""):
    query = q.strip().lower()
    if not query:
        return []

    terms = [t for t in query.split() if t]
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT  FROM libraryitems ORDER BY name ASC")
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
        liveprice = fetchprice(item["producturl"]) if item.get("producturl") else None
        results.append({
            "id": item["id"],
            "name": item["name"],
            "supplier": item["supplier"],
            "defaultprice": item["defaultprice"],
            "liveprice": liveprice,
            "producturl": item["producturl"]
        })
    return JSONResponse(content=results)

@app.get("/library-items")
def libraryitems():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT  FROM libraryitems ORDER BY name ASC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return JSONResponse(content=rows)

@app.post("/save-library-item")
def savelibraryitem(data: SaveLibraryItemRequest):
    if not data.name.strip():
        return JSONResponse(content={"ok": False, "message": "Item name is required."})

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO libraryitems (name, supplier, defaultprice, producturl)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(name, supplier) DO UPDATE SET
            defaultprice=excluded.defaultprice,
            producturl=excluded.producturl
    """, (data.name.strip(), data.supplier.strip(), round(data.defaultprice, 2), data.producturl.strip()))
    conn.commit()
    conn.close()
    return JSONResponse(content={"ok": True, "message": "Item saved to library."})

@app.post("/delete-library-item")
def deletelibraryitem(data: DeleteLibraryItemRequest):
    conn = db()
    cur = conn.cursor()
    cur.execute("DELETE FROM libraryitems WHERE id = ?", (data.id,))
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
    cur.execute("SELECT  FROM customers ORDER BY customername ASC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return JSONResponse(content=rows)

@app.get("/customer-history")
def customerhistory(customername: str = ""):
    customername = customername.strip()
    if not customername:
        return JSONResponse(content=[])

    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT  FROM quotes WHERE customername = ? ORDER BY id DESC", (customername,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return JSONResponse(content=rows)

@app.post("/save-customer")
def savecustomer(data: SaveCustomerRequest):
    if not data.customername.strip():
        return JSONResponse(content={"ok": False, "message": "Customer name is required."})

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO customers (customername, customeraddress, customerphone)
        VALUES (?, ?, ?)
    """, (data.customername.strip(), data.customeraddress.strip(), data.customerphone.strip()))
    conn.commit()
    conn.close()
    return JSONResponse(content={"ok": True, "message": "Customer saved."})

@app.post("/delete-customer")
def deletecustomer(data: DeleteCustomerRequest):
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
def getquotes():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT  FROM quotes ORDER BY id DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return JSONResponse(content=rows)

@app.get("/quote/{quoteref}")
def getquotebyref(quoteref: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT  FROM quotes WHERE quoteref = ?", (quoteref,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return JSONResponse(statuscode=404, content={"ok": False, "message": "Quote not found."})
    return JSONResponse(content=dict(row))

@app.post("/update-quote-status")
def updatequotestatus(data: UpdateQuoteStatusRequest):
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE quotes SET status = ? WHERE quoteref = ?", (data.status.strip() or "draft", data.quoteref))
    conn.commit()
    updated = cur.rowcount
    conn.close()
    if not updated:
        return JSONResponse(content={"ok": False, "message": "Quote not found."})
    return JSONResponse(content={"ok": True, "message": "Quote status updated."})

@app.post("/convert-to-invoice/{quoteref}")
def converttoinvoice(quoteref: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT  FROM quotes WHERE quoteref = ?", (quoteref,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return JSONResponse(statuscode=404, content={"ok": False, "message": "Quote not found."})

    row = dict(row)
    if row.get("invoiceref"):
        conn.close()
        return JSONResponse(content={"ok": True, "invoiceref": row["invoiceref"], "message": "Already invoiced."})

    invoiceref = generateinvoiceref()
    invoicecreatedat = datetime.now().strftime("%d/%m/%Y %H:%M")

    cur.execute("""
        UPDATE quotes
        SET status = ?, invoiceref = ?, invoicecreatedat = ?
        WHERE quoteref = ?
    """, ("invoiced", invoiceref, invoicecreatedat, quoteref))
    conn.commit()
    conn.close()

    return JSONResponse(content={"ok": True, "invoiceref": invoiceref, "message": "Quote converted to invoice."})

@app.get("/profit-summary")
def profitsummary():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            COUNT() AS totalquotes,
            COALESCE(SUM(totalprice), 0) AS revenue,
            COALESCE(SUM(labour), 0) AS labourtotal,
            COALESCE(SUM(materials), 0) AS rawmaterialstotal,
            COALESCE(SUM(internalhiddenuplift), 0) AS uplifttotal
        FROM quotes
    """)
    row = dict(cur.fetchone())

    cur.execute("SELECT COUNT() AS c FROM quotes WHERE status = 'accepted'")
    accepted = cur.fetchone()["c"]
    cur.execute("SELECT COUNT() AS c FROM quotes WHERE status = 'invoiced'")
    invoiced = cur.fetchone()["c"]

    conn.close()

    return JSONResponse(content={
        "totalquotes": row["totalquotes"],
        "revenue": round(row["revenue"], 2),
        "labourtotal": round(row["labourtotal"], 2),
        "rawmaterialstotal": round(row["rawmaterialstotal"], 2),
        "uplifttotal": round(row["uplifttotal"], 2),
        "acceptedquotes": accepted,
        "invoicedquotes": invoiced
    })

@app.get("/scheduled-jobs")
def scheduledjobs():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT  FROM scheduledjobs ORDER BY scheduleddate ASC, scheduledtime ASC, id DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return JSONResponse(content=rows)

@app.post("/schedule-job")
def schedulejob(data: ScheduleJobRequest):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO scheduledjobs (quoteref, customername, jobtitle, scheduleddate, scheduledtime, notes, createdat)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        data.quoteref.strip(),
        data.customername.strip(),
        data.jobtitle.strip(),
        data.scheduleddate.strip(),
        data.scheduledtime.strip(),
        data.notes.strip(),
        datetime.now().strftime("%d/%m/%Y %H:%M")
    ))
    conn.commit()
    conn.close()
    return JSONResponse(content={"ok": True, "message": "Job scheduled."})

@app.post("/delete-scheduled-job")
def deletescheduledjob(data: DeleteScheduleJobRequest):
    conn = db()
    cur = conn.cursor()
    cur.execute("DELETE FROM scheduledjobs WHERE id = ?", (data.id,))
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

/ ── Collapsible sections ── /
.collapsible-header {
  display:flex; align-items:center; justify-content:space-between;
  cursor:pointer; user-select:none;
  padding:10px 0; border-bottom:2px solid #eee; margin-bottom:4px;
}
.collapsible-header h2,
.collapsible-header h3 { margin:0; }
.collapsible-toggle {
  font-size:20px; font-weight:700; color:#555; transition:transform 0.2s;
  min-width:28px; text-align:center;
}
.collapsible-body { overflow:hidden; transition:max-height 0.3s ease, opacity 0.3s ease; }
.collapsible-body.collapsed { max-height:0 !important; opacity:0; pointer-events:none; }

@media print {
  .no-print { display:none !important; }
  body { background:white; padding:0; }
  .card { box-shadow:none; border:none; padding:0; margin:0 0 12px 0; }
  .wrap { max-width:100%; }
  .collapsible-body.collapsed { max-height:none !important; opacity:1; pointer-events:auto; }
}
</style>
</head>
<body>
<div class="wrap">

  <!-- ── Main quote form ── -->
  <div class="card no-print">
    <div class="collapsible-header" onclick="toggleSection('sec-main')">
      <h2 style="margin:0;">Nigel Harvey Ltd Quotes</h2>
      <span class="collapsible-toggle" id="toggle-sec-main">▼</span>
    </div>
    <div class="collapsible-body" id="sec-main">
      <div class="sub">Quick quote tool</div>

      <div class="check-row">
        <input type="checkbox" id="internalmode">
        <span>Internal mode</span>
      </div>

      <h3>Job templates</h3>
      <div id="templateButtons" class="templates"></div>

      <h3>Job packs + auto materials</h3>
      <div id="packButtons" class="packs"></div>

      <label for="quotetype">Quote type</label>
      <select id="quotetype" onchange="toggleBathroomFields(); updateLabourSuggestion();">
        <option value="small">Small Job</option>
        <option value="bathroom">Bathroom</option>
        <option value="heating">Heating</option>
      </select>

      <label for="customername">Customer name</label>
      <input id="customername" placeholder="John Smith" onblur="loadCustomerHistoryForCurrent()">

      <label for="customeraddress">Customer address</label>
      <textarea id="customeraddress" placeholder="125 Bushy Hill Drive, Guildford, GU1 2UG"></textarea>

      <label for="customerphone">Customer phone</label>
      <input id="customerphone" placeholder="07123 456789">

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
        <label for="walltilingm2">Wall tiling (m²)</label>
        <input id="walltilingm2" type="number" step="0.1" placeholder="0">
        <label for="floortilingm2">Floor tiling (m²)</label>
        <input id="floortilingm2" type="number" step="0.1" placeholder="0">
        <label for="wallheight">Wall height</label>
        <select id="wallheight">
          <option value="half">Half height</option>
          <option value="full">Full height</option>
        </select>
        <div class="check-row">
          <input type="checkbox" id="customersuppliestiles">
          <span>Customer supplies tiles</span>
        </div>
      </div>
    </div>
  </div>

  <!-- ── Materials search ── -->
  <div class="card no-print">
    <div class="collapsible-header" onclick="toggleSection('sec-search')">
      <h2 style="margin:0;">Materials &amp; Library</h2>
      <span class="collapsible-toggle" id="toggle-sec-search">▼</span>
    </div>
    <div class="collapsible-body" id="sec-search">
      <h3>Live smart material search</h3>
      <input id="materialSearch" placeholder="Search materials e.g. 15mm speedfit elbow, basin waste, kitchen tap" oninput="debouncedSearch()">
      <div id="searchResults" class="search-results hidden"></div>

      <h3>Supplier comparison</h3>
      <div id="comparisonList" class="small">Search above to compare suppliers and prices.</div>

      <h3>Save / edit a product in library</h3>
      <input type="hidden" id="libraryid">
      <label for="libraryname">Item name</label>
      <input id="libraryname" placeholder="e.g. Kitchen Mixer Tap">
      <label for="librarysupplier">Supplier</label>
      <select id="librarysupplier">
        <option value="City Plumbing">City Plumbing</option>
        <option value="Screwfix">Screwfix</option>
        <option value="Toolstation">Toolstation</option>
        <option value="Topps Tiles">Topps Tiles</option>
        <option value="Selco">Selco</option>
      </select>
      <label for="libraryurl">Product URL</label>
      <input id="libraryurl" placeholder="https://...">
      <label for="librarydefaultprice">Fallback price (£)</label>
      <input id="librarydefaultprice" type="number" step="0.01" placeholder="0">
      <button type="button" class="btn-save" onclick="saveLibraryItem()">Save / update library item</button>
      <div id="libraryNotice" class="notice"></div>
    </div>
  </div>

  <!-- ── Customer DB + Library Manager ── -->
  <div class="cols2 no-print">
    <div class="card">
      <div class="collapsible-header" onclick="toggleSection('sec-customers')">
        <h2 style="margin:0;">Customer database</h2>
        <span class="collapsible-toggle" id="toggle-sec-customers">▼</span>
      </div>
      <div class="collapsible-body" id="sec-customers">
        <button type="button" class="btn-refresh" onclick="loadCustomers()">Refresh customers</button>
        <div id="customerList" class="small" style="margin-top:12px;">No saved customers yet.</div>
      </div>
    </div>

    <div class="card">
      <div class="collapsible-header" onclick="toggleSection('sec-library')">
        <h2 style="margin:0;">Library manager</h2>
        <span class="collapsible-toggle" id="toggle-sec-library">▼</span>
      </div>
      <div class="collapsible-body" id="sec-library">
        <button type="button" class="btn-refresh" onclick="loadLibraryManager()">Refresh saved library</button>
        <div id="libraryManagerList" class="small" style="margin-top:12px;">No saved library items yet.</div>
      </div>
    </div>
  </div>

  <!-- ── Profit dashboard + Scheduling ── -->
  <div class="cols2 no-print">
    <div class="card">
      <div class="collapsible-header" onclick="toggleSection('sec-profit')">
        <h2 style="margin:0;">Profit dashboard</h2>
        <span class="collapsible-toggle" id="toggle-sec-profit">▼</span>
      </div>
      <div class="collapsible-body" id="sec-profit">
        <button type="button" class="btn-refresh" onclick="loadProfitSummary()">Refresh dashboard</button>
        <div id="profitSummary" class="small" style="margin-top:12px;">Loading...</div>
      </div>
    </div>

    <div class="card">
      <div class="collapsible-header" onclick="toggleSection('sec-schedule')">
        <h2 style="margin:0;">Job scheduling / calendar</h2>
        <span class="collapsible-toggle" id="toggle-sec-schedule">▼</span>
      </div>
      <div class="collapsible-body" id="sec-schedule">
        <label for="schedulequoteref">Quote ref</label>
        <input id="schedulequoteref" placeholder="NHQ-...">
        <label for="schedulecustomername">Customer</label>
        <input id="schedulecustomername" placeholder="Customer name">
        <label for="schedulejobtitle">Job title</label>
        <input id="schedulejobtitle" placeholder="Job title">
        <label for="scheduledate">Date</label>
        <input id="scheduledate" type="date">
        <label for="scheduletime">Time</label>
        <input id="scheduletime" type="time">
        <label for="schedulenotes">Notes</label>
        <textarea id="schedulenotes" placeholder="Notes"></textarea>
        <button type="button" class="btn-save" onclick="scheduleJob()">Schedule job</button>
        <div id="scheduleList" class="small" style="margin-top:12px;">Loading...</div>
      </div>
    </div>
  </div>

  <!-- ── Customer history ── -->
  <div class="card no-print">
    <div class="collapsible-header" onclick="toggleSection('sec-history')">
      <h2 style="margin:0;">Customer history per job</h2>
      <span class="collapsible-toggle" id="toggle-sec-history">▼</span>
    </div>
    <div class="collapsible-body" id="sec-history">
      <div id="customerHistory" class="small">Enter or select a customer to see history.</div>
    </div>
  </div>

  <!-- ── Pricing + materials entry ── -->
  <div class="card no-print">
    <div class="collapsible-header" onclick="toggleSection('sec-pricing')">
      <h2 style="margin:0;">Materials &amp; Pricing</h2>
      <span class="collapsible-toggle" id="toggle-sec-pricing">▼</span>
    </div>
    <div class="collapsible-body" id="sec-pricing">
      <h3>Materials</h3>
      <div id="materials"></div>
      <button type="button" onclick="addMaterial()">+ Add Manual Material Row</button>

      <h3>Pricing</h3>
      <label for="labour">Labour cost (£)</label>
      <input id="labour" type="number" step="0.01" placeholder="180">
      <div class="small" id="labourSuggestion" style="margin-top:8px;"></div>

      <div class="check-row">
        <input type="checkbox" id="includematerialshandling" checked>
        <span>Include materials handling</span>
      </div>

      <label for="materialshandlingpercent">Materials handling %</label>
      <select id="materialshandlingpercent">
        <option value="20">20%</option>
        <option value="25" selected>25%</option>
        <option value="30">30%</option>
      </select>

      <button type="button" onclick="generateQuote()">Generate Quote</button>
      <div id="error" class="error"></div>
    </div>
  </div>

  <!-- ── Quote result ── -->
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
      <div class="row"><span class="muted">Quote ref</span><span id="rquoteref"></span></div>
      <div class="row"><span class="muted">Invoice ref</span><span id="rinvoiceref"></span></div>
      <div class="row"><span class="muted">Date</span><span id="rdate"></span></div>
      <div class="row"><span class="muted">Status</span><span id="rstatus"></span></div>
      <div class="row"><span class="muted">Type</span><span id="rtype"></span></div>
      <div class="row"><span class="muted">Customer</span><span id="rcustomer"></span></div>
      <div class="row"><span class="muted">Phone</span><span id="rphone"></span></div>
      <div class="row"><span class="muted">Address</span><span id="raddress"></span></div>
    </div>

    <div class="quote-section-title">Works</div>
    <div class="quote-box"><div id="rjob"></div></div>

    <div class="quote-section-title">Price</div>
    <div class="quote-box">
      <div class="row"><span class="muted">Labour</span><span id="rlabour"></span></div>
      <div class="row"><span class="muted">Materials</span><span id="rmaterials"></span></div>
      <div class="row quote-total"><span>Total price</span><span id="rtotal"></span></div>
    </div>

    <div id="internalBox" class="quote-box internal-box hidden">
      <div class="quote-section-title" style="margin-top:0;">Internal only</div>
      <div class="row"><span class="muted">Raw materials</span><span id="rinternalraw"></span></div>
      <div class="row"><span class="muted">Job multiplier</span><span id="rinternaljobmultiplier"></span></div>
      <div class="row"><span class="muted">After job markup</span><span id="rinternalafterjob"></span></div>
      <div class="row"><span class="muted">Handling %</span><span id="rinternalhandlingpercent"></span></div>
      <div class="row"><span class="muted">After handling</span><span id="rinternalafterhandling"></span></div>
      <div class="row"><span class="muted">Hidden uplift</span><span id="rinternalhiddenuplift"></span></div>
    </div>

    <div class="quote-section-title">Notes</div>
    <div class="quote-box">
      Includes labour and materials.<br>
      Payment due as agreed.<br>
      Quote subject to site conditions and any unforeseen issues.
    </div>

    <div class="actions no-print">
      <a id="whatsappBtn" class="btn-link btn-secondary" href="#" target="blank">Send direct to customer WhatsApp</a>
      <button class="btn-light" onclick="window.print()">Download / Print PDF</button>
      <button class="btn-save" onclick="convertCurrentQuoteToInvoice()">Convert to invoice</button>
    </div>
  </div>

  <!-- ── Saved quotes ── -->
  <div class="card">
    <div class="collapsible-header" onclick="toggleSection('sec-savedquotes')">
      <h2 style="margin:0;">Saved Quotes</h2>
      <span class="collapsible-toggle" id="toggle-sec-savedquotes">▼</span>
    </div>
    <div class="collapsible-body" id="sec-savedquotes">
      <div id="historyList" class="small">No saved quotes yet.</div>
    </div>
  </div>

</div>

<script>
const JOBTEMPLATES = JOBTEMPLATES;
const JOBPACKS = JOBPACKS;
let searchTimer = null;
let currentOpenQuoteRef = "";

// ── Collapsible logic ──
const sectionState = {};

function toggleSection(id) {
  const body = document.getElementById(id);
  const toggle = document.getElementById("toggle-" + id);
  if (!body) return;

  if (!body.style.maxHeight || body.classList.contains("collapsed")) {
    // Open
    body.classList.remove("collapsed");
    body.style.maxHeight = body.scrollHeight + 2000 + "px";
    body.style.opacity = "1";
    if (toggle) toggle.textContent = "▼";
    sectionState[id] = "open";
  } else {
    // Close
    body.style.maxHeight = "0";
    body.style.opacity = "0";
    body.classList.add("collapsed");
    if (toggle) toggle.textContent = "▶";
    sectionState[id] = "closed";
  }
}

function initSections() {
  // All sections open by default on load
  const sections = [
    "sec-main", "sec-search", "sec-customers", "sec-library",
    "sec-profit", "sec-schedule", "sec-history", "sec-pricing", "sec-savedquotes"
  ];
  sections.forEach(id => {
    const body = document.getElementById(id);
    if (!body) return;
    body.style.maxHeight = body.scrollHeight + 2000 + "px";
    body.style.opacity = "1";
    sectionState[id] = "open";
  });
}

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
  const quoteType = document.getElementById("quotetype").value;
  const bathroomFields = document.getElementById("bathroomFields");
  if (quoteType === "bathroom") bathroomFields.classList.remove("hidden");
  else bathroomFields.classList.add("hidden");
}

function renderTemplates() {
  const box = document.getElementById("templateButtons");
  box.innerHTML = JOBTEMPLATES.map((t, i) => 
    <button type="button" class="btn-template" onclick="applyTemplate(${i})">${escapeHtml(t.name)}</button>
  ).join("");
}

function renderPacks() {
  const box = document.getElementById("packButtons");
  box.innerHTML = JOBPACKS.map((p, i) => 
    <button type="button" class="btn-pack" onclick="applyJobPack(${i})">${escapeHtml(p.name)}</button>
  ).join("");
}

function applyTemplate(index) {
  const t = JOBTEMPLATES[index];
  document.getElementById("quotetype").value = t.quotetype;
  document.getElementById("job").value = t.job;
  document.getElementById("labour").value = t.labour;
  toggleBathroomFields();
  updateLabourSuggestion();
}

function clearMaterials() {
  document.getElementById("materials").innerHTML = "";
}

function applyJobPack(index) {
  const p = JOBPACKS[index];
  document.getElementById("quotetype").value = p.quotetype;
  document.getElementById("job").value = p.jobdescription;
  document.getElementById("labour").value = p.labourcost;
  clearMaterials();
  (p.materials || []).forEach(m => addMaterial({
    name: m.name,
    supplier: m.supplier,
    producturl: m.url,
    manualprice: m.manualprice
  }, m.quantity));
  toggleBathroomFields();
  updateLabourSuggestion();
}

function updateLabourSuggestion() {
  const quoteType = document.getElementById("quotetype").value;
  const box = document.getElementById("labourSuggestion");
  if (quoteType === "bathroom") box.innerText = "Typical bathroom labour is often higher. Adjust to suit your job.";
  else if (quoteType === "heating") box.innerText = "Heating jobs often vary by size and access. Adjust labour as needed.";
  else box.innerText = "Small jobs: use your judgement and minimum charge where needed.";
}

function addMaterial(prefill = null, qtyOverride = null) {
  const qty = qtyOverride !== null ? qtyOverride : (prefill ? 1 : "");
  const div = document.createElement("div");
  div.className = "material-row";
  div.innerHTML = 
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
    <input class="m-url" placeholder="https://..." value="${prefill ? escapeHtml(prefill.producturl || "") : ""}">
    <label>Manual price (£)</label>
    <input class="m-manual" type="number" step="0.01" placeholder="0" value="${prefill ? prefill.manualprice : ""}">
    <button type="button" class="btn-delete btn-small" style="margin-top:10px;" onclick="this.closest('.material-row').remove()">Remove row</button>
  ;
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

  resultsBox.innerHTML = <div class="search-item">Searching...</div>;
  resultsBox.classList.remove("hidden");

  try {
    const res = await fetch("/material-search?q=" + encodeURIComponent(query));
    const results = await res.json();

    if (!results.length) {
      resultsBox.innerHTML = <div class="search-item">No matches found</div>;
      comparisonBox.innerHTML = "No supplier matches found.";
      return;
    }

    resultsBox.innerHTML = results.map((item) => {
      const bestPrice = item.liveprice !== null ? item.liveprice : item.defaultprice;
      const label = item.liveprice !== null ? "live" : "default";
      return 
        <div class="search-item" onclick='selectSearchResult(${JSON.stringify(item)})'>
          <strong>${escapeHtml(item.name)}</strong><br>
          <span class="small">${escapeHtml(item.supplier)} · ${pounds(bestPrice)} (${label})</span>
        </div>
      ;
    }).join("");

    const sorted = [...results].sort((a, b) => {
      const pa = a.liveprice !== null ? a.liveprice : a.defaultprice;
      const pb = b.liveprice !== null ? b.liveprice : b.defaultprice;
      return pa - pb;
    });

    comparisonBox.innerHTML = sorted.map(item => {
      const bestPrice = item.liveprice !== null ? item.liveprice : item.defaultprice;
      const label = item.liveprice !== null ? "live" : "default";
      return 
        <div class="compare-item">
          <strong>${escapeHtml(item.name)}</strong><br>
          <span class="small">${escapeHtml(item.supplier)} · ${pounds(bestPrice)} (${label})</span>
        </div>
      ;
    }).join("");
  } catch (e) {
    resultsBox.innerHTML = <div class="search-item">Search failed</div>;
    comparisonBox.innerHTML = "Comparison failed.";
  }
}

async function autoSaveSearchItem(item) {
  const bestPrice = item.liveprice !== null ? item.liveprice : item.defaultprice;
  try {
    await fetch("/save-library-item", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        name: item.name || "",
        supplier: item.supplier || "",
        producturl: item.producturl || "",
        defaultprice: bestPrice || 0
      })
    });
    loadLibraryManager();
  } catch (e) {}
}

async function selectSearchResult(item) {
  const bestPrice = item.liveprice !== null ? item.liveprice : item.defaultprice;

  addMaterial({
    name: item.name,
    supplier: item.supplier,
    producturl: item.producturl || "",
    manualprice: bestPrice
  });

  document.getElementById("materialSearch").value = "";
  document.getElementById("searchResults").classList.add("hidden");
  document.getElementById("searchResults").innerHTML = "";

  if ((item.name || "").trim() && (item.supplier || "").trim() && ((item.producturl || "").trim() || bestPrice > 0)) {
    await autoSaveSearchItem(item);
    showLibraryNotice("Search item auto-saved to library.");
  }
}

async function saveLibraryItem() {
  const payload = {
    name: document.getElementById("libraryname").value,
    supplier: document.getElementById("librarysupplier").value,
    producturl: document.getElementById("libraryurl").value,
    defaultprice: parseFloat(document.getElementById("librarydefaultprice").value || 0)
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
  document.getElementById("libraryid").value = item.id || "";
  document.getElementById("libraryname").value = item.name || "";
  document.getElementById("librarysupplier").value = item.supplier || "City Plumbing";
  document.getElementById("libraryurl").value = item.producturl || "";
  document.getElementById("librarydefaultprice").value = item.defaultprice || 0;
  window.scrollTo({top: 0, behavior: "smooth"});
}

function clearLibraryForm() {
  document.getElementById("libraryid").value = "";
  document.getElementById("libraryname").value = "";
  document.getElementById("librarysupplier").value = "City Plumbing";
  document.getElementById("libraryurl").value = "";
  document.getElementById("librarydefaultprice").value = "";
}

async function loadLibraryManager() {
  const box = document.getElementById("libraryManagerList");
  box.innerHTML = "Loading...";
  try {
    const res = await fetch("/library-items");
    const items = await res.json();
    if (!items.length) { box.innerHTML = "No saved library items yet."; return; }
    box.innerHTML = items.map(item => 
      <div class="library-item">
        <div><strong>${escapeHtml(item.name || "")}</strong></div>
        <div class="small">${escapeHtml(item.supplier || "")} · fallback ${pounds(item.defaultprice || 0)}</div>
        <div class="small">${escapeHtml(item.producturl || "")}</div>
        <button type="button" class="btn-refresh btn-small" onclick='fillLibraryForm(${JSON.stringify(item)})'>Edit</button>
        <button type="button" class="btn-delete" onclick='deleteLibraryItem(${item.id})'>Delete</button>
      </div>
    ).join("");
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
    customername: document.getElementById("customername").value,
    customeraddress: document.getElementById("customeraddress").value,
    customerphone: document.getElementById("customerphone").value
  };
  if (!payload.customername.trim()) { showCustomerNotice("Please enter a customer name."); return; }
  try {
    const res = await fetch("/save-customer", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    showCustomerNotice(data.message || "Customer saved.");
    if (data.ok) { loadCustomers(); loadCustomerHistoryForCurrent(); }
  } catch (e) {
    showCustomerNotice("Could not save customer.");
  }
}

function fillCustomerForm(customer) {
  document.getElementById("customername").value = customer.customername || "";
  document.getElementById("customeraddress").value = customer.customeraddress || "";
  document.getElementById("customerphone").value = customer.customerphone || "";
  loadCustomerHistoryForCurrent();
  window.scrollTo({top: 0, behavior: "smooth"});
}

async function loadCustomers() {
  const box = document.getElementById("customerList");
  box.innerHTML = "Loading...";
  try {
    const res = await fetch("/customers");
    const customers = await res.json();
    if (!customers.length) { box.innerHTML = "No saved customers yet."; return; }
    box.innerHTML = customers.map(c => 
      <div class="customer-item">
        <div><strong>${escapeHtml(c.customername || "")}</strong></div>
        <div class="small">${escapeHtml(c.customerphone || "")}</div>
        <div class="small">${escapeHtml(c.customeraddress || "")}</div>
        <button type="button" class="btn-refresh btn-small" onclick='fillCustomerForm(${JSON.stringify(c)})'>Use customer</button>
        <button type="button" class="btn-delete" onclick='deleteCustomer(${c.id})'>Delete</button>
      </div>
    ).join("");
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
  const customerName = document.getElementById("customername").value.trim();
  const box = document.getElementById("customerHistory");
  if (!customerName) { box.innerHTML = "Enter or select a customer to see history."; return; }
  box.innerHTML = "Loading...";
  try {
    const res = await fetch("/customer-history?customername=" + encodeURIComponent(customerName));
    const items = await res.json();
    if (!items.length) { box.innerHTML = "No job history found for this customer yet."; return; }
    box.innerHTML = items.map(q => 
      <div class="history-item">
        <div><strong>${escapeHtml(q.quoteref || "")}</strong></div>
        <div>${escapeHtml(q.job || "")}</div>
        <div class="small">${escapeHtml(q.createdat || "")} · ${pounds(q.totalprice || 0)} · ${escapeHtml(q.status || "draft")}</div>
      </div>
    ).join("");
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
    if (!data.length) { history.innerHTML = "No saved quotes yet."; return; }
    history.innerHTML = data.map(q => 
      <div class="history-item">
        <div><strong>${escapeHtml(q.customername || "No customer name")}</strong></div>
        <div>${escapeHtml(q.job || "")}</div>
        <div class="small">${escapeHtml(q.quoteref || "")} · ${escapeHtml(q.createdat || "")}</div>
        <div class="small">Total ${pounds(q.totalprice)} · <span class="status-badge">${escapeHtml(q.status || "draft")}</span> ${q.invoiceref ? '· Invoice ' + escapeHtml(q.invoiceref) : ''}</div>
        <button type="button" class="btn-refresh btn-small" onclick='openSavedQuote(${JSON.stringify(q.quoteref)})'>Open</button>
        <button type="button" class="btn-save btn-small" onclick='loadQuoteIntoForm(${JSON.stringify(q.quoteref)})'>Load into form</button>
        <button type="button" class="btn-small" onclick='fillScheduleFromQuote(${JSON.stringify(q.quoteref)}, ${JSON.stringify(q.customername)}, ${JSON.stringify(q.job)})'>Schedule</button>
        <button type="button" class="btn-save btn-small" onclick='convertQuoteToInvoice(${JSON.stringify(q.quoteref)})'>Invoice</button>
        <label>Status</label>
        <select onchange='updateQuoteStatus(${JSON.stringify(q.quoteref)}, this.value)'>
          <option value="draft" ${q.status === "draft" ? "selected" : ""}>draft</option>
          <option value="sent" ${q.status === "sent" ? "selected" : ""}>sent</option>
          <option value="accepted" ${q.status === "accepted" ? "selected" : ""}>accepted</option>
          <option value="declined" ${q.status === "declined" ? "selected" : ""}>declined</option>
          <option value="invoiced" ${q.status === "invoiced" ? "selected" : ""}>invoiced</option>
        </select>
      </div>
    ).join("");
  } catch (e) {
    document.getElementById("historyList").innerHTML = "Unable to load saved quotes.";
  }
}

async function updateQuoteStatus(quoteRef, status) {
  try {
    await fetch("/update-quote-status", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({quoteref: quoteRef, status})
    });
    loadHistory();
    if (currentOpenQuoteRef === quoteRef) openSavedQuote(quoteRef);
  } catch (e) {
    alert("Could not update quote status.");
  }
}

function renderQuoteView(data) {
  currentOpenQuoteRef = data.quoteref || "";
  document.getElementById("rquoteref").innerText = data.quoteref || "-";
  document.getElementById("rinvoiceref").innerText = data.invoiceref || "-";
  document.getElementById("rdate").innerText = data.createdat || "-";
  document.getElementById("rstatus").innerText = data.status || "-";
  document.getElementById("rtype").innerText = data.quotetype || "-";
  document.getElementById("rcustomer").innerText = data.customername || "-";
  document.getElementById("rphone").innerText = data.customerphone || "-";
  document.getElementById("raddress").innerText = data.customeraddress || "-";
  document.getElementById("rjob").innerText = data.job || "-";
  document.getElementById("rlabour").innerText = pounds(data.labour);
  document.getElementById("rmaterials").innerText = pounds(data.materials);
  document.getElementById("rtotal").innerText = pounds(data.totalprice);

  if (document.getElementById("internalmode").checked) {
    document.getElementById("internalBox").classList.remove("hidden");
    document.getElementById("rinternalraw").innerText = pounds(data.internalrawmaterials);
    document.getElementById("rinternaljobmultiplier").innerText = data.internaljobmultiplier + "x";
    document.getElementById("rinternalafterjob").innerText = pounds(data.internalafterjobmarkup);
    document.getElementById("rinternalhandlingpercent").innerText = data.internalhandlingpercent + "%";
    document.getElementById("rinternalafterhandling").innerText = pounds(data.internalafterhandling);
    document.getElementById("rinternalhiddenuplift").innerText = pounds(data.internalhiddenuplift);
  } else {
    document.getElementById("internalBox").classList.add("hidden");
  }

  const message =
Nigel Harvey Ltd Quote

Quote ref: ${data.quoteref || "-"}
Date: ${data.createdat || "-"}
Type: ${data.quotetype || "-"}
Customer: ${data.customername || "-"}
Address: ${data.customeraddress || "-"}

Job: ${data.job || "-"}

Labour: ${pounds(data.labour)}
Materials: ${pounds(data.materials)}
Total price: ${pounds(data.totalprice)}

Nigel Harvey Ltd
07595 725547
Nigelharveyplumbing@gmail.com;

  const cleanPhone = normalisePhone(data.customerphone || "");
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
    document.getElementById("quotetype").value = data.quotetype || "small";
    document.getElementById("customername").value = data.customername || "";
    document.getElementById("customeraddress").value = data.customeraddress || "";
    document.getElementById("customerphone").value = data.customerphone || "";
    document.getElementById("job").value = data.job || "";
    document.getElementById("labour").value = data.labour || 0;
    document.getElementById("includematerialshandling").checked = !!data.includematerialshandling;
    document.getElementById("materialshandlingpercent").value = String(data.materialshandlingpercent || 25);
    document.getElementById("tiling").checked = !!data.tiling;
    document.getElementById("walltilingm2").value = data.walltilingm2 || 0;
    document.getElementById("floortilingm2").value = data.floortilingm2 || 0;
    document.getElementById("wallheight").value = data.wallheight || "half";
    document.getElementById("customersuppliestiles").checked = !!data.customersuppliestiles;

    clearMaterials();
    let materials = [];
    try { materials = JSON.parse(data.materialsjson || "[]"); } catch (e) { materials = []; }
    materials.forEach(m => addMaterial({
      name: m.name, supplier: m.supplier, producturl: m.url, manualprice: m.manualprice
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
    alert(data.message + (data.invoiceref ? " " + data.invoiceref : ""));
    loadHistory();
    if (currentOpenQuoteRef === quoteRef) openSavedQuote(quoteRef);
  } catch (e) {
    alert("Could not convert quote to invoice.");
  }
}

function convertCurrentQuoteToInvoice() {
  if (!currentOpenQuoteRef) { alert("Open a saved quote first."); return; }
  convertQuoteToInvoice(currentOpenQuoteRef);
}

async function loadProfitSummary() {
  const box = document.getElementById("profitSummary");
  box.innerHTML = "Loading...";
  try {
    const res = await fetch("/profit-summary");
    const data = await res.json();
    box.innerHTML = 
      <div class="summary-item"><strong>Total quotes</strong><br>${data.totalquotes}</div>
      <div class="summary-item"><strong>Total revenue</strong><br>${pounds(data.revenue)}</div>
      <div class="summary-item"><strong>Total labour</strong><br>${pounds(data.labourtotal)}</div>
      <div class="summary-item"><strong>Raw materials total</strong><br>${pounds(data.rawmaterialstotal)}</div>
      <div class="summary-item"><strong>Total uplift</strong><br>${pounds(data.uplifttotal)}</div>
      <div class="summary-item"><strong>Accepted quotes</strong><br>${data.acceptedquotes}</div>
      <div class="summary-item"><strong>Invoiced quotes</strong><br>${data.invoicedquotes}</div>
    ;
  } catch (e) {
    box.innerHTML = "Could not load dashboard.";
  }
}

function fillScheduleFromQuote(quoteRef, customerName, jobTitle) {
  document.getElementById("schedulequoteref").value = quoteRef || "";
  document.getElementById("schedulecustomername").value = customerName || "";
  document.getElementById("schedulejobtitle").value = jobTitle || "";
  window.scrollTo({top: document.getElementById("schedulequoteref").offsetTop - 20, behavior: "smooth"});
}

async function scheduleJob() {
  const payload = {
    quoteref: document.getElementById("schedulequoteref").value,
    customername: document.getElementById("schedulecustomername").value,
    jobtitle: document.getElementById("schedulejobtitle").value,
    scheduleddate: document.getElementById("scheduledate").value,
    scheduledtime: document.getElementById("scheduletime").value,
    notes: document.getElementById("schedulenotes").value
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
    if (!jobs.length) { box.innerHTML = "No scheduled jobs yet."; return; }
    box.innerHTML = jobs.map(j => 
      <div class="schedule-item">
        <div><strong>${escapeHtml(j.jobtitle || "")}</strong></div>
        <div class="small">${escapeHtml(j.customername || "")}</div>
        <div class="small">${escapeHtml(j.scheduleddate || "")} ${escapeHtml(j.scheduledtime || "")}</div>
        <div class="small">${escapeHtml(j.quoteref || "")}</div>
        <div class="small">${escapeHtml(j.notes || "")}</div>
        <button type="button" class="btn-delete" onclick='deleteScheduledJob(${j.id})'>Delete</button>
      </div>
    ).join("");
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
      manualprice: parseFloat(row.querySelector(".m-manual").value || 0)
    });
  });

  const payload = {
    quotetype: document.getElementById("quotetype").value,
    customername: document.getElementById("customername").value,
    customeraddress: document.getElementById("customeraddress").value,
    customerphone: document.getElementById("customerphone").value,
    jobdescription: document.getElementById("job").value,
    labourcost: parseFloat(document.getElementById("labour").value || 0),
    includematerialshandling: document.getElementById("includematerialshandling").checked,
    materialshandlingpercent: parseFloat(document.getElementById("materialshandlingpercent").value || 25),
    materials: materials,
    tiling: document.getElementById("tiling").checked,
    walltilingm2: parseFloat(document.getElementById("walltilingm2").value || 0),
    floortilingm2: parseFloat(document.getElementById("floortilingm2").value || 0),
    wallheight: document.getElementById("wallheight").value,
    customersuppliestiles: document.getElementById("customersuppliestiles").checked
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

// ── Init ──
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
initSections();
</script>
</body>
</html>
"""

@app.get("/", responseclass=HTMLResponse)
def home():
    html = HTML.replace("JOBTEMPLATES", json.dumps(JOBTEMPLATES))
    html = html.replace("JOBPACKS", json.dumps(JOBPACKS))
    return html

@app.post("/quote")
def createquote(data: QuoteRequest):
    totalmaterials = 0

    for item in data.materials:
        price = fetchprice(item.url) if item.url else None
        if price is None:
            price = item.manualprice or 0
        totalmaterials += price  item.quantity

    tilingextramaterials = 0
    if data.quotetype == "bathroom" and data.tiling:
        totalarea = data.walltilingm2 + data.floortilingm2
        if totalarea > 0 and not data.customersuppliestiles:
            wallmultiplier = 1.2 if data.wallheight == "full" else 1.0
            wallmaterials = data.walltilingm2  20  wallmultiplier
            floormaterials = data.floortilingm2  15
            tilingextramaterials += wallmaterials + floormaterials

    rawmaterialswithtiling = totalmaterials + tilingextramaterials

    jobmultiplier = 1.0
    if data.quotetype == "bathroom":
        jobmultiplier = 1.5
    elif data.quotetype == "heating":
        jobmultiplier = 1.3

    materialsafterjobmarkup = rawmaterialswithtiling  jobmultiplier

    handlingpercent = 0.0
    handlingmultiplier = 1.0
    if data.includematerialshandling:
        handlingpercent = data.materialshandlingpercent
        handlingmultiplier += (handlingpercent / 100.0)

    materialswithhandling = materialsafterjobmarkup  handlingmultiplier
    labourtotal = data.labourcost
    total = labourtotal + materialswithhandling

    jobtext = data.jobdescription
    if data.tiling and data.quotetype == "bathroom":
        jobtext += " + Tiling"

    hiddenuplift = materialswithhandling - rawmaterialswithtiling
    quoteref = generatequoteref()

    quote = {
        "quoteref": quoteref,
        "status": "draft",
        "invoiceref": "",
        "invoicecreatedat": "",
        "quotetype": data.quotetype,
        "customername": data.customername,
        "customeraddress": data.customeraddress,
        "customerphone": data.customerphone,
        "job": jobtext,
        "labour": round(labourtotal, 2),
        "materials": round(rawmaterialswithtiling, 2),
        "totalprice": round(total, 2),
        "createdat": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "internalrawmaterials": round(rawmaterialswithtiling, 2),
        "internaljobmultiplier": round(jobmultiplier, 2),
        "internalafterjobmarkup": round(materialsafterjobmarkup, 2),
        "internalhandlingpercent": round(handlingpercent, 2),
        "internalafterhandling": round(materialswithhandling, 2),
        "internalhiddenuplift": round(hiddenuplift, 2),
        "materialsjson": json.dumps([m.modeldump() for m in data.materials]),
        "includematerialshandling": 1 if data.includematerialshandling else 0,
        "materialshandlingpercent": round(data.materialshandlingpercent, 2),
        "tiling": 1 if data.tiling else 0,
        "walltilingm2": round(data.walltilingm2, 2),
        "floortilingm2": round(data.floortilingm2, 2),
        "wallheight": data.wallheight,
        "customersuppliestiles": 1 if data.customersuppliestiles else 0
    }

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO quotes (
            quoteref, status, invoiceref, invoicecreatedat, quotetype, customername, customeraddress, customerphone,
            job, labour, materials, totalprice, createdat,
            internalrawmaterials, internaljobmultiplier, internalafterjobmarkup,
            internalhandlingpercent, internalafterhandling, internalhiddenuplift,
            materialsjson, includematerialshandling, materialshandlingpercent,
            tiling, walltilingm2, floortilingm2, wallheight, customersuppliestiles
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        quote["quoteref"], quote["status"], quote["invoiceref"], quote["invoicecreatedat"], quote["quotetype"],
        quote["customername"], quote["customeraddress"], quote["customerphone"], quote["job"], quote["labour"],
        quote["materials"], quote["totalprice"], quote["createdat"], quote["internalrawmaterials"],
        quote["internaljobmultiplier"], quote["internalafterjobmarkup"], quote["internalhandlingpercent"],
        quote["internalafterhandling"], quote["internalhiddenuplift"], quote["materialsjson"],
        quote["includematerialshandling"], quote["materialshandlingpercent"], quote["tiling"],
        quote["walltilingm2"], quote["floortilingm2"], quote["wallheight"], quote["customersupplies_tiles"]
    ))
    conn.commit()
    conn.close()

    return JSONResponse(content=quote)
`


"""Internal appointments, jobs and one-opportunity pipeline reporting."""

from datetime import date, datetime
import sqlite3

from business.db import get_db

APPOINTMENT_KINDS = {"site_visit", "job"}
APPOINTMENT_STATUSES = {"confirmed", "provisional", "completed", "cancelled"}
JOB_STATUSES = {"awaiting_schedule", "scheduled", "in_progress", "completed", "cancelled"}
STAGES = ("new_enquiry", "visit_booked", "quote_pending", "won_unscheduled",
          "scheduled", "in_progress", "completed_uninvoiced", "invoiced_unpaid",
          "paid", "closed_lost_expired")


def validate_appointment(data):
    if data.kind not in APPOINTMENT_KINDS or data.status not in APPOINTMENT_STATUSES:
        raise ValueError("Invalid appointment kind or status")
    try:
        start = datetime.fromisoformat(data.starts_at)
        end = datetime.fromisoformat(data.ends_at)
        if start.tzinfo or end.tzinfo or end <= start or not (1900 <= start.year <= 2100):
            raise ValueError()
        if data.provisional_follow_up:
            date.fromisoformat(data.provisional_follow_up)
    except ValueError as exc:
        raise ValueError("Use local start/end date and time, with end after start; follow-up must be a date") from exc
    if data.status != "provisional" and data.provisional_follow_up:
        raise ValueError("Only provisional appointments have a provisional follow-up")
    if data.status == "provisional" and not data.provisional_follow_up:
        raise ValueError("Pencilled bookings need a follow-up date")


def _row(row):
    return dict(row) if row else None


def list_appointments():
    conn = get_db()
    try:
        return [dict(row) for row in conn.execute("""SELECT a.*, l.name AS customer_name,
            l.phone AS customer_phone, l.address AS customer_address,
            l.description AS lead_description, l.status AS lead_status, l.customer_id
            FROM appointments a JOIN leads l ON l.id = a.lead_id
            ORDER BY a.starts_at, a.id""")]
    finally:
        conn.close()


def save_appointment(data, now, appointment_id=None):
    validate_appointment(data)
    conn = get_db()
    try:
        if not conn.execute("SELECT 1 FROM leads WHERE id = ?", (data.lead_id,)).fetchone():
            raise ValueError("Lead does not exist")
        if data.job_id:
            job = conn.execute("SELECT lead_id FROM jobs WHERE id = ?", (data.job_id,)).fetchone()
            if not job or job["lead_id"] != data.lead_id:
                raise ValueError("Job must belong to this lead")
        timestamp = now().isoformat()
        values = (data.lead_id, data.job_id, data.kind, data.status,
                  data.starts_at, data.ends_at, data.provisional_follow_up or None,
                  data.notes.strip()[:2000])
        if appointment_id is None:
            cur = conn.execute("""INSERT INTO appointments
                (lead_id, job_id, kind, status, starts_at, ends_at,
                 provisional_follow_up, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (*values, timestamp, timestamp))
            appointment_id = cur.lastrowid
        else:
            cur = conn.execute("""UPDATE appointments SET lead_id=?, job_id=?, kind=?, status=?,
                starts_at=?, ends_at=?, provisional_follow_up=?, notes=?, updated_at=? WHERE id=?""",
                               (*values, timestamp, appointment_id))
            if not cur.rowcount:
                raise ValueError("Appointment does not exist")
        conn.commit()
        return _row(conn.execute("SELECT * FROM appointments WHERE id=?", (appointment_id,)).fetchone())
    finally:
        conn.close()


def list_jobs():
    conn = get_db()
    try:
        return [dict(row) for row in conn.execute("SELECT * FROM jobs ORDER BY updated_at DESC, id DESC")]
    finally:
        conn.close()


def save_job(data, now, job_id=None):
    if data.status not in JOB_STATUSES or not data.title.strip():
        raise ValueError("A job title and valid job status are required")
    if not (data.lead_id or data.quote_id):
        raise ValueError("Link a lead or quote to the job")
    conn = get_db()
    try:
        lead_id, quote_id, invoice_id = data.lead_id, data.quote_id, data.invoice_id
        lead = conn.execute("SELECT customer_id FROM leads WHERE id=?", (lead_id,)).fetchone() if lead_id else None
        if lead_id and not lead:
            raise ValueError("Lead does not exist")
        customer_id = lead["customer_id"] if lead else None
        if quote_id:
            quote = conn.execute("SELECT lead_id, customer_id FROM quotes WHERE id=?", (quote_id,)).fetchone()
            if not quote or (lead_id and quote["lead_id"] and lead_id != quote["lead_id"]):
                raise ValueError("Quote does not exist or belongs to a different lead")
            lead_id = lead_id or quote["lead_id"]
            customer_id = quote["customer_id"]
        if invoice_id:
            invoice = conn.execute("SELECT quote_id, customer_id FROM invoices WHERE id=?", (invoice_id,)).fetchone()
            if not invoice or (quote_id and invoice["quote_id"] and quote_id != invoice["quote_id"]):
                raise ValueError("Invoice does not exist or belongs to a different quote")
            if lead_id and invoice["quote_id"]:
                invoice_quote = conn.execute("SELECT lead_id FROM quotes WHERE id=?", (invoice["quote_id"],)).fetchone()
                if invoice_quote and invoice_quote["lead_id"] and invoice_quote["lead_id"] != lead_id:
                    raise ValueError("Invoice belongs to a different lead")
        timestamp = now().isoformat()
        values = (lead_id, quote_id, invoice_id, customer_id, data.title.strip()[:180],
                  data.status, data.notes.strip()[:2000])
        if job_id is None:
            cur = conn.execute("""INSERT INTO jobs
                (lead_id, quote_id, invoice_id, customer_id, title, status, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", (*values, timestamp, timestamp))
            job_id = cur.lastrowid
        else:
            cur = conn.execute("""UPDATE jobs SET lead_id=?, quote_id=?, invoice_id=?, customer_id=?,
                title=?, status=?, notes=?, updated_at=? WHERE id=?""", (*values, timestamp, job_id))
            if not cur.rowcount:
                raise ValueError("Job does not exist")
        conn.commit()
        return _row(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
    except sqlite3.IntegrityError as exc:
        raise ValueError("This quote or invoice is already linked to a job") from exc
    finally:
        conn.close()


def _invoice_stage(invoice):
    if not invoice:
        return None
    return "paid" if invoice["status"].lower() == "paid" or (invoice["balance_due"] is not None
        and invoice["balance_due"] <= 0) else "invoiced_unpaid"


def pipeline_report():
    """One card per lead, with orphan quotes/jobs shown only when meaningful."""
    conn = get_db()
    try:
        leads = [dict(x) for x in conn.execute("SELECT id,name,description,status,source_category,work_type FROM leads")]
        quotes = [dict(x) for x in conn.execute("SELECT id,lead_id,customer_name,status,total_price FROM quotes")]
        jobs = [dict(x) for x in conn.execute("SELECT * FROM jobs")]
        invoices = [dict(x) for x in conn.execute("SELECT id,quote_id,customer_name,status,balance_due FROM invoices")]
        visits = [dict(x) for x in conn.execute("SELECT lead_id FROM appointments WHERE kind='site_visit' AND status IN ('confirmed','provisional')")]
        job_bookings = {x["job_id"] for x in conn.execute("""SELECT job_id FROM appointments
            WHERE kind='job' AND status IN ('confirmed','provisional') AND job_id IS NOT NULL""")}
    finally:
        conn.close()
    cards = []
    invoices_by_quote = {}
    for invoice in invoices:
        invoices_by_quote.setdefault(invoice["quote_id"], []).append(invoice)
    visited_leads = {visit["lead_id"] for visit in visits}

    def make_card(lead, related_quotes, related_jobs, name, description):
        related_invoices = [invoice for quote in related_quotes
                            for invoice in invoices_by_quote.get(quote["id"], [])]
        related_invoices += [invoice for job in related_jobs for invoice in invoices
                             if job["invoice_id"] == invoice["id"] and invoice not in related_invoices]
        invoice_stages = [_invoice_stage(invoice) for invoice in related_invoices]
        statuses = {quote["status"] for quote in related_quotes}
        job_statuses = {job["status"] for job in related_jobs}
        if "paid" in invoice_stages:
            stage = "paid"
        elif "invoiced_unpaid" in invoice_stages:
            stage = "invoiced_unpaid"
        elif (statuses and statuses <= {"lost", "expired"}) or (lead and lead["status"] == "lost"):
            stage = "closed_lost_expired"
        elif "completed" in job_statuses:
            stage = "completed_uninvoiced"
        elif "in_progress" in job_statuses:
            stage = "in_progress"
        elif any(job["status"] == "scheduled" and job["id"] in job_bookings for job in related_jobs):
            stage = "scheduled"
        elif "awaiting_schedule" in job_statuses or "won" in statuses or (lead and lead["status"] == "won"):
            stage = "won_unscheduled"
        elif "scheduled" in job_statuses:
            # A stage label alone does not put work into the diary.
            stage = "won_unscheduled"
        elif "pending" in statuses or (lead and lead["status"] == "quoted"):
            stage = "quote_pending"
        elif lead and lead["id"] in visited_leads:
            stage = "visit_booked"
        elif job_statuses == {"cancelled"}:
            stage = "closed_lost_expired"
        else:
            stage = "new_enquiry"
        return {"stage": stage, "lead_id": lead["id"] if lead else None,
                "quote_ids": [quote["id"] for quote in related_quotes],
                "job_ids": [job["id"] for job in related_jobs],
                "invoice_ids": [invoice["id"] for invoice in related_invoices],
                "name": name or "Unnamed customer", "description": description or "",
                "source_category": lead["source_category"] if lead else "",
                "work_type": lead["work_type"] if lead else ""}

    for lead in leads:
        related_quotes = [quote for quote in quotes if quote["lead_id"] == lead["id"]]
        related_jobs = [job for job in jobs if job["lead_id"] == lead["id"]
                        or (job["quote_id"] and job["quote_id"] in {q["id"] for q in related_quotes})]
        card = make_card(lead, related_quotes, related_jobs, lead["name"], lead["description"])
        if card:
            cards.append(card)
    for quote in quotes:
        if quote["lead_id"] or (quote["status"] == "unclassified"
                                and not invoices_by_quote.get(quote["id"])
                                and not any(job["quote_id"] == quote["id"] for job in jobs)):
            continue
        related_jobs = [job for job in jobs if job["quote_id"] == quote["id"]]
        card = make_card(None, [quote], related_jobs, quote["customer_name"], "")
        if card:
            cards.append(card)
    for job in jobs:
        if not job["lead_id"] and not job["quote_id"]:
            card = make_card(None, [], [job], job["title"], "")
            if card:
                cards.append(card)
    covered_invoice_ids = {invoice_id for card in cards for invoice_id in card["invoice_ids"]}
    for invoice in invoices:
        if invoice["id"] not in covered_invoice_ids:
            cards.append({"stage": _invoice_stage(invoice), "lead_id": None,
                          "quote_ids": [], "job_ids": [], "invoice_ids": [invoice["id"]],
                          "name": invoice["customer_name"] or "Historical invoice",
                          "description": "", "source_category": "", "work_type": ""})
    return {"stages": {stage: [card for card in cards if card["stage"] == stage] for stage in STAGES},
            "total_active": len([c for c in cards if c["stage"] not in {"paid", "closed_lost_expired"}]),
            "total": len(cards)}

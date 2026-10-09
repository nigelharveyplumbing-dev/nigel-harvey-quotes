"""Lead mail and invoice reminder orchestration with injected app dependencies."""

import os
import logging
import smtplib
import ssl
from datetime import datetime
from html import escape
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def lead_email_configuration(*, EMAIL_ENABLED, EMAIL_USER, EMAIL_PASS):
    missing = [key for key, value in (("EMAIL_ENABLED", EMAIL_ENABLED),
                                      ("EMAIL_USER", (EMAIL_USER or "").strip()),
                                      ("EMAIL_PASS", (EMAIL_PASS or "").strip())) if not value]
    return {"configured": not missing, "missing_settings": missing}


def lead_email_error_code(exc):
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "authentication_failed"
    if isinstance(exc, (TimeoutError, smtplib.SMTPServerDisconnected)):
        return "connection_failed"
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "recipient_refused"
    if isinstance(exc, smtplib.SMTPException):
        return "smtp_failed"
    return "delivery_failed"


def send_lead_notification_email(lead: dict, *, EMAIL_ENABLED, EMAIL_USER, EMAIL_PASS, EMAIL_FROM_NAME, EMAIL_HOST, EMAIL_PORT, get_public_base_url):
    if not lead_email_configuration(EMAIL_ENABLED=EMAIL_ENABLED, EMAIL_USER=EMAIL_USER,
                                    EMAIL_PASS=EMAIL_PASS)['configured']:
        logger.error("lead_email_failed lead_id=%s reason=not_configured", lead.get("id"))
        return {"status": "failed", "error_code": "not_configured"}
    try:
        msg = MIMEMultipart("alternative")
        name = str(lead.get('name') or 'Website lead').replace('\r', ' ').replace('\n', ' ')
        msg["Subject"] = f"New quote request - {name}"
        msg["From"] = f"{EMAIL_FROM_NAME} <{EMAIL_USER}>"
        msg["To"] = EMAIL_USER
        public_url = get_public_base_url().rstrip('/') + '/app' if (os.getenv("PUBLIC_BASE_URL") or "").strip() else ""
        plain = (
            f"New website lead\n\n"
            f"Name: {lead.get('name','')}\n"
            f"Phone: {lead.get('phone','')}\n"
            f"Email: {lead.get('email','')}\n"
            f"Address: {lead.get('address','')}\n"
            f"Postcode: {lead.get('postcode','')}\n"
            f"Urgency: {lead.get('urgency','')}\n"
            f"Preferred contact: {lead.get('preferred_contact','')}\n"
            f"Job type: {lead.get('job_type','')}\n"
            f"Description: {lead.get('description','')}\n\n"
            f"Open app: {public_url}\n"
        )
        html = (
            '<html><body style="font-family:Arial,sans-serif;">'
            '<h2>New website lead</h2>'
            f"<p><strong>Name:</strong> {escape(lead.get('name',''))}<br>"
            f"<strong>Phone:</strong> {escape(lead.get('phone',''))}<br>"
            f"<strong>Email:</strong> {escape(lead.get('email',''))}<br>"
            f"<strong>Address:</strong> {escape(lead.get('address',''))}<br>"
            f"<strong>Postcode:</strong> {escape(lead.get('postcode',''))}<br>"
            f"<strong>Urgency:</strong> {escape(lead.get('urgency',''))}<br>"
            f"<strong>Preferred contact:</strong> {escape(lead.get('preferred_contact',''))}<br>"
            f"<strong>Job type:</strong> {escape(lead.get('job_type',''))}</p>"
            f"<p><strong>Description:</strong><br>{escape(lead.get('description','')).replace(chr(10), '<br>')}</p>"
            '</body></html>'
        )
        msg.attach(MIMEText(plain, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(EMAIL_HOST, EMAIL_PORT, context=context, timeout=15) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            refused = server.sendmail(EMAIL_USER, [EMAIL_USER], msg.as_string())
            if isinstance(refused, dict) and refused:
                raise smtplib.SMTPRecipientsRefused(refused)
        logger.info("lead_email_accepted lead_id=%s", lead.get("id"))
        return {"status": "accepted", "error_code": ""}
    except Exception as exc:
        code = lead_email_error_code(exc)
        # SMTP exceptions can contain credentials, addresses or message content.
        # Only record the stable category and internal lead ID.
        logger.error("lead_email_failed lead_id=%s reason=%s", lead.get("id"), code)
        return {"status": "failed", "error_code": code}



def send_overdue_reminder_now(item: dict, *, invoice_is_overdue, pounds_text, send_invoice_email_now, update_invoice_reminder_timestamp, get_invoice_by_id):
    email = (item.get("reminder_email") or "").strip()
    if not email:
        raise RuntimeError("No reminder email is saved on this invoice.")
    if not invoice_is_overdue(item):
        raise RuntimeError("This invoice is not currently overdue.")
    message = (
        f"This is a payment reminder for invoice {item['invoice_number']}"
        f"{f' (Job Ref {item.get("job_reference")})' if item.get("job_reference") else ''}. "
        f"The outstanding balance is {pounds_text(item.get('balance_due', 0))}. "
        f"Please use {item['invoice_number']} as the bank-transfer reference."
    )
    send_invoice_email_now(item, email, message)
    update_invoice_reminder_timestamp(item["id"])
    return get_invoice_by_id(item["id"])



def process_overdue_invoice_reminders(*, load_invoices, invoice_is_overdue, send_overdue_reminder_now, now_uk, UK_TZ, OVERDUE_REMINDER_INTERVAL_HOURS):
    sent, skipped = [], []
    for item in load_invoices():
        if not item.get("reminders_enabled") or not invoice_is_overdue(item):
            continue
        if not item.get("reminder_email"):
            skipped.append({"id": item["id"], "reason": "No reminder email"})
            continue
        last_value = item.get("last_reminder_at") or ""
        if last_value:
            try:
                last_dt = datetime.fromisoformat(last_value)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=UK_TZ)
                if (now_uk() - last_dt).total_seconds() < OVERDUE_REMINDER_INTERVAL_HOURS * 3600:
                    continue
            except Exception:
                pass
        try:
            send_overdue_reminder_now(item)
            sent.append(item["id"])
        except Exception as exc:
            skipped.append({"id": item["id"], "reason": str(exc)})
    return {"sent": sent, "skipped": skipped}

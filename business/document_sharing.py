"""Invoice email composition; SMTP credentials and delivery stay with the app."""

import base64
from html import escape
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email import encoders


def prepare_invoice_email(item: dict, to_email: str, extra_message: str, ctx):
    invoice = item["invoice"]
    public_url = ctx.build_invoice_public_url(item["id"])
    subject = (
        f"Invoice {item['invoice_number']}"
        + (f" - Job Ref {item['job_reference']}" if item.get("job_reference") else "")
        + f" - {ctx.company_name}"
    )

    greeting = f"Hello {invoice.get('customer_name') or ''},".strip()
    plain_lines = [
        greeting,
        "",
        extra_message.strip() if extra_message else "Please find your invoice attached as a PDF.",
        "",
        f"Invoice number: {item['invoice_number']}",
        f"Job Ref: {item.get('job_reference') or '-'}",
        f"Balance due: {ctx.pounds_text(item.get('balance_due', 0))}",
        f"Invoice link: {public_url}",
        "",
        ctx.company_name,
        ctx.company_phone,
        ctx.company_email,
    ]
    plain_body = "\n".join([line for line in plain_lines if line is not None])

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = ctx.from_header
    msg["To"] = to_email.strip()

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(plain_body, "plain", "utf-8"))

    logo_value = ctx.get_company_logo_value()
    html_logo = ""
    logo_bytes = None
    if logo_value:
        try:
            if logo_value.startswith("data:image"):
                _, encoded = logo_value.split(",", 1)
                logo_bytes = base64.b64decode(encoded)
                html_logo = '<img src="cid:companylogo" alt="Nigel Harvey Ltd logo" style="max-height:72px; max-width:220px; display:block; margin:0 0 14px auto;">'
            else:
                html_logo = f'<img src="{escape(logo_value)}" alt="Nigel Harvey Ltd logo" style="max-height:72px; max-width:220px; display:block; margin:0 0 14px auto;">'
        except Exception:
            html_logo = ""

    message_text = escape(extra_message.strip()) if extra_message else "Please find your invoice attached as a PDF."
    customer_name = escape(invoice.get("customer_name") or "")
    html_body = f"""
    <html>
      <body style="margin:0; padding:0; background:#f4f4f4; font-family:Arial, sans-serif; color:#111;">
        <div style="max-width:680px; margin:0 auto; padding:24px 14px;">
          <div style="background:#ffffff; border-radius:16px; padding:28px; box-shadow:0 2px 12px rgba(0,0,0,0.06);">
            <div style="text-align:right;">{html_logo}</div>
            <div style="font-size:18px; font-weight:700; margin-bottom:14px;">{greeting}</div>
            <div style="font-size:16px; line-height:1.6; margin-bottom:18px;">{message_text}</div>
            <div style="border:1px solid #e5e7eb; border-radius:14px; padding:18px; background:#fafafa; margin-bottom:18px;">
              <div style="font-size:13px; letter-spacing:.5px; color:#666; text-transform:uppercase; margin-bottom:10px;">Invoice summary</div>
              <div style="display:flex; justify-content:space-between; gap:12px; margin:8px 0;"><span>Invoice number</span><strong>{escape(item['invoice_number'])}</strong></div>
              <div style="display:flex; justify-content:space-between; gap:12px; margin:8px 0;"><span>Status</span><strong>{escape(item['status'].title())}</strong></div>
              <div style="display:flex; justify-content:space-between; gap:12px; margin:8px 0;"><span>Balance due</span><strong>{escape(ctx.pounds_text(item.get('balance_due', 0)))}</strong></div>
            </div>
            <div style="margin-bottom:18px;">
              <a href="{escape(public_url)}" style="display:inline-block; background:#111; color:#fff; text-decoration:none; padding:12px 18px; border-radius:12px; font-weight:700;">Open invoice online</a>
            </div>
            <div style="font-size:14px; line-height:1.6; color:#444;">
              {escape(ctx.company_name)}<br>
              {escape(ctx.company_phone)}<br>
              {escape(ctx.company_email)}
            </div>
          </div>
        </div>
      </body>
    </html>
    """

    related = MIMEMultipart("related")
    related.attach(MIMEText(html_body, "html", "utf-8"))

    if logo_bytes:
        image_part = MIMEImage(logo_bytes, _subtype="png")
        image_part.add_header("Content-ID", "<companylogo>")
        image_part.add_header("Content-Disposition", "inline", filename="logo.png")
        related.attach(image_part)

    alt.attach(related)
    msg.attach(alt)

    pdf_part = MIMEBase("application", "pdf")
    pdf_part.set_payload(ctx.generate_invoice_pdf_bytes(item))
    encoders.encode_base64(pdf_part)
    pdf_part.add_header("Content-Disposition", "attachment", filename=f"{item['invoice_number']}.pdf")
    msg.attach(pdf_part)

    return msg

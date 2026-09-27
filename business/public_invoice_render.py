"""Render the existing customer invoice HTML without changing its markup."""

from html import escape


def render_public_invoice_html(item: dict, *,
    COMPANY_NAME,
    COMPANY_ADDRESS,
    COMPANY_PHONE,
    COMPANY_EMAIL,
    COMPANY_LOGO_URL,
    INVOICE_TERMS,
    BANK_NAME,
    BANK_ACCOUNT_NAME,
    BANK_SORT_CODE,
    BANK_ACCOUNT_NUMBER,
    QRCODE_AVAILABLE,
    pounds_text,
    bank_payment_reference,
 ):
    invoice = item["invoice"]
    quote_result = item["quote_result"]
    is_small_job = (quote_result.get("quote_type", "") or "").lower() == "small"
    terms = INVOICE_TERMS[:3] if is_small_job else INVOICE_TERMS
    logo_html = f'<img src="{escape(COMPANY_LOGO_URL)}" alt="Logo" class="logo">' if COMPANY_LOGO_URL else ""
    payment_html = f'<div class="pay-box"><strong>Payment link:</strong> <a href="{escape(item.get("payment_link") or "")}" target="_blank">Pay online</a></div>' if item.get("payment_link") else ""
    bank_html = f"""
      <div class="pay-box">
        <div style="display:grid;grid-template-columns:1fr auto;gap:14px;align-items:start;">
          <div>
            <strong>Bank transfer</strong><br>
            Bank: {escape(BANK_NAME)}<br>
            Account name: {escape(BANK_ACCOUNT_NAME)}<br>
            Sort code: <strong>{escape(BANK_SORT_CODE)}</strong><br>
            Account number: <strong>{escape(BANK_ACCOUNT_NUMBER)}</strong><br>
            Reference: <strong>{escape(bank_payment_reference(item))}</strong><br>
            Amount due: <strong>{pounds_text(item.get("balance_due", 0))}</strong>
          </div>
          {(
              f'<img src="/api/invoices/{item["id"]}/payment-qr" alt="Payment details QR" '
              f'style="width:120px;height:120px;background:white;border:1px solid #ddd;border-radius:8px;">'
              if QRCODE_AVAILABLE else
              '<div style="width:120px;padding:10px;border:1px solid #ddd;border-radius:8px;'
              'background:#fafafa;font-size:12px;">QR unavailable</div>'
          )}
        </div>
        <div style="font-size:12px;color:#666;margin-top:6px;">The QR contains the payment details. Automatic bank-app prefilling varies.</div>
      </div>
    """
    paid_watermark_html = '<div class="paid-watermark">PAID</div>' if str(item.get("status", "")).lower() == "paid" else ""
    photos = item.get("photos", []) or []
    photos_html = ""
    if photos:
        cards = []
        for photo in photos:
            cards.append(
                f'<div class="photo-card">'
                f'<img src="{escape(photo.get("url", ""))}" alt="Job photo">'
                f'<div class="photo-caption"><strong>{escape(photo.get("category_label", "Job photo"))}</strong>'
                f'<br>{escape(photo.get("caption", "") or "")}</div></div>'
            )
        photos_html = '<div class="section-title">Job photos</div><div class="photo-grid">' + "".join(cards) + '</div>'

    html = f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Invoice {escape(item['invoice_number'])}</title>
      <style>
        body {{ font-family: Arial, sans-serif; background:#f3f4f6; color:#111; margin:0; padding:18px; }}
        .sheet {{ position:relative; max-width:900px; margin:0 auto; background:white; border-radius:18px; padding:28px; box-shadow:0 10px 30px rgba(0,0,0,0.08); }}
        .paid-watermark {{ position:absolute; inset:0; display:flex; align-items:center; justify-content:center; font-size:120px; font-weight:900; color:rgba(22,163,74,.12); transform:rotate(-24deg); pointer-events:none; }}
        .top {{ display:flex; justify-content:space-between; gap:20px; align-items:flex-start; border-bottom:2px solid #111; padding-bottom:18px; }}
        .logo {{ max-height:72px; max-width:180px; object-fit:contain; }}
        .company {{ font-size:30px; font-weight:800; margin-bottom:8px; }}
        .doc-title {{ font-size:14px; text-transform:uppercase; letter-spacing:1.5px; color:#666; }}
        .doc-number {{ font-size:24px; font-weight:800; margin-top:6px; }}
        .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:20px; }}
        .box {{ border:1px solid #e5e7eb; border-radius:14px; padding:16px; background:#fafafa; }}
        .label {{ color:#666; font-size:13px; text-transform:uppercase; letter-spacing:.5px; margin-bottom:8px; }}
        .row {{ display:flex; justify-content:space-between; gap:12px; margin:10px 0; }}
        .muted {{ color:#666; }}
        .section-title {{ font-size:18px; font-weight:800; margin:24px 0 10px; }}
        .total {{ font-size:30px; font-weight:900; }}
        .pay-box {{ margin-top:12px; padding:12px; background:#eef7ff; border:1px solid #cfe5f8; border-radius:12px; }}
        .actions {{ margin-top:20px; display:flex; gap:10px; flex-wrap:wrap; }}
        .photo-grid {{ display:grid; grid-template-columns:repeat(2,1fr); gap:14px; }}
        .photo-card {{ border:1px solid #e5e7eb; border-radius:12px; overflow:hidden; background:#fafafa; }}
        .photo-card img {{ width:100%; height:230px; object-fit:cover; display:block; }}
        .photo-caption {{ padding:10px; }}
        .btn {{ display:inline-block; padding:13px 16px; border-radius:12px; background:black; color:white; text-decoration:none; font-weight:700; }}
        .btn.light {{ background:#e5e7eb; color:#111; }}
        ul {{ margin:0; padding-left:18px; }}
        @media (max-width:700px) {{ .sheet {{ padding:18px; }} .top, .grid, .row {{ display:block; }} .row span:last-child {{ display:block; margin-top:4px; }} .actions a {{ width:100%; text-align:center; box-sizing:border-box; }} }}
        @media print {{ body {{ background:white; padding:0; }} .sheet {{ box-shadow:none; border-radius:0; max-width:100%; padding:0; }} .actions {{ display:none !important; }} }}
      </style>
    </head>
    <body>
      <div class="sheet">
        {paid_watermark_html}
        <div class="top">
          <div>
            <div class="company">{escape(COMPANY_NAME)}</div>
            <div>{escape(COMPANY_ADDRESS)}<br>{escape(COMPANY_PHONE)}<br>{escape(COMPANY_EMAIL)}</div>
          </div>
          <div style="text-align:right;">{logo_html}<div class="doc-title">Invoice</div><div class="doc-number">{escape(item['invoice_number'])}</div></div>
        </div>
        <div class="grid">
          <div class="box"><div class="label">Bill To</div>{escape(invoice.get('customer_name', '-') or '-')}<br>{escape(invoice.get('customer_address', '-') or '-')}<br>{escape(invoice.get('customer_phone', '-') or '-')}</div>
          <div class="box">
            <div class="row"><span class="muted">Date</span><span>{escape(item['created_at'])}</span></div>
            <div class="row"><span class="muted">Job Ref</span><span>{escape(item.get('job_reference') or '-')}</span></div>
            <div class="row"><span class="muted">Due date</span><span>{escape(item['due_date'])}</span></div>
            <div class="row"><span class="muted">Status</span><span>{escape(item['status'].title())}</span></div>
          </div>
        </div>
        <div class="section-title">Work</div>
        <div class="box">{escape(invoice.get('job', '-') or '-').replace(chr(10), '<br>')}</div>
        {photos_html}
        <div class="section-title">Payment details</div>
        {bank_html}
        {payment_html}
        <div class="section-title">Invoice totals</div>
        <div class="box">
          <div class="row"><span class="muted">Labour</span><span>{pounds_text(invoice.get('labour', 0))}</span></div>
          <div class="row"><span class="muted">Materials</span><span>{pounds_text(invoice.get('materials', 0))}</span></div>
          <div class="row"><span class="muted">Total</span><span>{pounds_text(item['total_price'])}</span></div>
          <div class="row"><span class="muted">Amount paid</span><span>{pounds_text(item['amount_paid'])}</span></div>
          <div class="row"><span class="muted">Balance due</span><span class="total">{pounds_text(item['balance_due'])}</span></div>
        </div>
        <div class="section-title">Payment terms</div>
        <div class="box"><ul>{''.join(f'<li>{escape(t)}</li>' for t in terms)}</ul>{payment_html}</div>
        <div class="actions">
          <a href="/api/invoices/{item['id']}/pdf" target="_blank" class="btn">Download PDF</a>
          <a href="javascript:window.print()" class="btn light">Print</a>
        </div>
      </div>
    </body>
    </html>
    """
    return html

"""Quote and invoice PDF rendering; external app data is supplied by context."""

import io
import textwrap

from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def _pdf_header(c, title: str, ref_number: str, ctx):
    width, height = A4
    y = height - 48
    logo_reader = ctx.pdf_logo_reader()

    text_left = 40
    if logo_reader:
        try:
            c.drawImage(logo_reader, 40, y - 52, width=150, height=48, preserveAspectRatio=True, mask='auto')
            text_left = 205
        except Exception:
            text_left = 40

    c.setFont("Helvetica-Bold", 24)
    c.drawString(text_left, y, ctx.company_name)
    c.setFont("Helvetica", 11)
    c.drawString(text_left, y - 18, ctx.company_address)
    c.drawString(text_left, y - 34, ctx.company_phone)
    c.drawString(text_left, y - 50, ctx.company_email)
    c.setFont("Helvetica-Bold", 18)
    c.drawRightString(width - 40, y, title)
    c.setFont("Helvetica", 11)
    c.drawRightString(width - 40, y - 18, ref_number)
    c.line(40, y - 62, width - 40, y - 62)
    return y - 84

def _pdf_row(c, y, left, right, bold=False):
    c.setFont("Helvetica-Bold" if bold else "Helvetica", 11)
    c.drawString(50, y, str(left))
    c.drawRightString(A4[0] - 50, y, str(right))
    return y - 18

def _pdf_new_page_if_needed(c, y, min_y=70):
    if y < min_y:
        c.showPage()
        return A4[1] - 50
    return y

def _pdf_draw_wrapped_text(c, text, x, y, max_chars=95, font="Helvetica", size=10, leading=12):
    c.setFont(font, size)
    for raw_line in str(text or "").splitlines() or [""]:
        line = raw_line.strip()
        if not line:
            y -= leading
            continue
        while len(line) > max_chars:
            cut = line.rfind(" ", 0, max_chars)
            if cut <= 0:
                cut = max_chars
            c.drawString(x, y, line[:cut])
            y -= leading
            line = line[cut:].strip()
            y = _pdf_new_page_if_needed(c, y)
            c.setFont(font, size)
        c.drawString(x, y, line)
        y -= leading
        y = _pdf_new_page_if_needed(c, y)
        c.setFont(font, size)
    return y

def _pdf_draw_materials_section(c, y, result, ctx):
    material_lines = result.get("material_lines") or []
    if not material_lines:
        return y

    y = _pdf_new_page_if_needed(c, y, 150)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Materials Used")
    y -= 18

    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y, "Item")
    c.drawRightString(390, y, "Qty")
    c.drawRightString(470, y, "Unit")
    c.drawRightString(555, y, "Line total")
    y -= 10
    c.line(40, y, A4[0] - 40, y)
    y -= 14

    c.setFont("Helvetica", 9)
    for item in material_lines:
        y = _pdf_new_page_if_needed(c, y, 90)
        name = str(item.get("name", "Material"))
        qty = item.get("quantity", 1)
        unit_price = item.get("unit_price_used", 0)
        line_total = item.get("line_total", 0)
        source = item.get("price_source") or ("live" if item.get("live_price_used") else "manual")
        source_label = "cached live" if source == "cached" else source

        left_text = f"{name} ({source_label})"
        c.setFont("Helvetica", 9)
        if len(left_text) <= 62:
            c.drawString(40, y, left_text)
            used_lines = 1
        else:
            first = left_text[:62]
            cut = first.rfind(" ")
            if cut > 20:
                first = left_text[:cut]
                rest = left_text[cut:].strip()
            else:
                rest = left_text[62:].strip()
            c.drawString(40, y, first)
            used_lines = 1
            while rest:
                y -= 11
                part = rest[:62]
                cut = part.rfind(" ")
                if cut > 20 and len(rest) > 62:
                    part = rest[:cut]
                    rest = rest[cut:].strip()
                else:
                    rest = rest[len(part):].strip()
                c.drawString(40, y, part)
                used_lines += 1

        top_y = y + (used_lines - 1) * 11
        c.drawRightString(390, top_y, str(qty))
        c.drawRightString(470, top_y, ctx.pounds_text(unit_price))
        c.drawRightString(555, top_y, ctx.pounds_text(line_total))
        y -= 15

    y -= 6
    c.line(40, y, A4[0] - 40, y)
    y -= 18
    return y

def _pdf_photo_page_header(c, continued=False, ctx=None):
    c.showPage()
    y = _pdf_header(c, "INVOICE JOB PHOTOS", "", ctx)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, "Job Photos" + (" (continued)" if continued else ""))
    return y - 24

def _pdf_draw_invoice_photos(c, item: dict, ctx):
    photos = item.get("photos", []) or []
    if not photos:
        return

    y = _pdf_photo_page_header(c, False, ctx)
    usable_width = A4[0] - 80
    image_width = (usable_width - 14) / 2
    image_height = 165

    for index, photo in enumerate(photos):
        col = index % 2
        if col == 0 and y < image_height + 80:
            y = _pdf_photo_page_header(c, True, ctx)

        x = 40 + col * (image_width + 14)
        image_path = ctx.invoice_photo_path(item["id"], photo["id"])

        if image_path:
            try:
                with Image.open(image_path) as im:
                    width, height = im.size
                ratio = min(image_width / max(width, 1), image_height / max(height, 1))
                draw_width, draw_height = width * ratio, height * ratio
                draw_x = x + (image_width - draw_width) / 2
                draw_y = y - draw_height
                c.drawImage(
                    ImageReader(str(image_path)),
                    draw_x, draw_y,
                    width=draw_width, height=draw_height,
                    preserveAspectRatio=True,
                    mask="auto",
                )
            except Exception:
                c.rect(x, y - image_height, image_width, image_height)
                c.drawString(x + 8, y - 20, "Photo unavailable")

        caption_y = y - image_height - 12
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x, caption_y, str(photo.get("category_label", "Job photo"))[:45])
        caption = str(photo.get("caption", "") or "").strip()
        if caption:
            c.setFont("Helvetica", 8)
            for line_number, line in enumerate(textwrap.wrap(caption, width=48)[:3]):
                c.drawString(x, caption_y - 11 - (line_number * 10), line)

        if col == 1 or index == len(photos) - 1:
            y -= image_height + 58

def generate_invoice_pdf_bytes(item: dict, ctx):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    invoice = item["invoice"]
    quote_result = item["quote_result"]
    page_width, page_height = A4

    y = _pdf_header(c, "INVOICE", item["invoice_number"], ctx)

    # Match the online invoice with two separate information boxes.
    left_x = 40
    gap = 16
    box_width = (page_width - 80 - gap) / 2
    right_x = left_x + box_width + gap

    customer_lines = []
    for value in [
        invoice.get("customer_name", ""),
        invoice.get("customer_address", ""),
        invoice.get("customer_phone", ""),
    ]:
        for raw_line in str(value or "").replace("\r", "").splitlines():
            raw_line = raw_line.strip()
            if raw_line:
                customer_lines.extend(textwrap.wrap(raw_line, width=43) or [raw_line])

    if not customer_lines:
        customer_lines = ["-"]

    detail_lines = [
        ("Date", item.get("created_at", "-")),
        ("Job Ref", item.get("job_reference") or "-"),
        ("Due date", item.get("due_date", "-")),
        ("Status", str(item.get("status", "-")).title()),
    ]

    left_height = 38 + len(customer_lines) * 13
    right_height = 38 + len(detail_lines) * 18
    box_height = max(105, left_height, right_height)
    box_bottom = y - box_height

    c.setFillColorRGB(0.98, 0.98, 0.98)
    c.setStrokeColorRGB(0.88, 0.89, 0.91)
    c.roundRect(left_x, box_bottom, box_width, box_height, 10, fill=1, stroke=1)
    c.roundRect(right_x, box_bottom, box_width, box_height, 10, fill=1, stroke=1)

    c.setFillColorRGB(0.35, 0.35, 0.35)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(left_x + 12, y - 18, "BILL TO")
    c.drawString(right_x + 12, y - 18, "INVOICE DETAILS")

    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica", 10)
    line_y = y - 36
    for line in customer_lines:
        c.drawString(left_x + 12, line_y, line)
        line_y -= 13

    detail_y = y - 38
    for label, value in detail_lines:
        c.setFont("Helvetica", 10)
        c.setFillColorRGB(0.35, 0.35, 0.35)
        c.drawString(right_x + 12, detail_y, str(label))
        c.setFillColorRGB(0, 0, 0)
        c.drawRightString(right_x + box_width - 12, detail_y, str(value)[:38])
        detail_y -= 18

    y = box_bottom - 24

    # Work description, fully wrapped rather than clipped.
    y = _pdf_new_page_if_needed(c, y, 150)
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(40, y, "Work")
    y -= 18

    work_lines = []
    for raw_line in str(invoice.get("job", "-") or "-").replace("\r", "").splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            work_lines.append("")
        else:
            work_lines.extend(textwrap.wrap(raw_line, width=94) or [raw_line])

    work_height = max(54, 24 + len(work_lines) * 13)
    if y - work_height < 70:
        c.showPage()
        y = page_height - 50
        c.setFont("Helvetica-Bold", 13)
        c.drawString(40, y, "Work")
        y -= 18

    work_bottom = y - work_height
    c.setFillColorRGB(0.98, 0.98, 0.98)
    c.setStrokeColorRGB(0.88, 0.89, 0.91)
    c.roundRect(40, work_bottom, page_width - 80, work_height, 10, fill=1, stroke=1)
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica", 10)
    work_y = y - 18
    for line in work_lines:
        c.drawString(52, work_y, line)
        work_y -= 13

    y = work_bottom - 24

    # Materials remain itemised in the downloaded PDF.
    y = _pdf_draw_materials_section(c, y, quote_result, ctx)

    y = _pdf_new_page_if_needed(c, y, 255)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(40, y, "Invoice totals")
    y -= 18

    materials_base = quote_result.get("materials_base", invoice.get("materials", 0))
    procurement_amount = quote_result.get("materials_procurement_amount", 0)
    procurement_percent = quote_result.get("materials_procurement_percent", 0)

    total_rows = [
        ("Labour", ctx.pounds_text(invoice.get("labour", 0)), False),
    ]
    invoice_callout = ctx.safe_float(invoice.get("callout_charge", quote_result.get("callout_charge", 0)), 0)
    if invoice_callout > 0:
        total_rows.append(("Call-out charge", ctx.pounds_text(invoice_callout), False))
    invoice_travel = ctx.safe_float(invoice.get("travel_charge", quote_result.get("travel_charge", 0)), 0)
    if invoice_travel > 0:
        total_rows.append(("Travel charge", ctx.pounds_text(invoice_travel), False))
    total_rows.append(("Materials", ctx.pounds_text(materials_base), False))
    if ctx.safe_float(procurement_amount, 0) > 0:
        total_rows.append((
            f"Materials procurement & handling ({ctx.safe_float(procurement_percent, 0):.0f}%)",
            ctx.pounds_text(procurement_amount),
            False,
        ))
    total_rows.extend([
        ("Total", ctx.pounds_text(item.get("total_price", 0)), False),
        ("Amount paid", ctx.pounds_text(item.get("amount_paid", 0)), False),
        ("Balance due", ctx.pounds_text(item.get("balance_due", 0)), True),
    ])

    totals_height = 24 + len(total_rows) * 20
    totals_bottom = y - totals_height
    c.setFillColorRGB(0.98, 0.98, 0.98)
    c.setStrokeColorRGB(0.88, 0.89, 0.91)
    c.roundRect(40, totals_bottom, page_width - 80, totals_height, 10, fill=1, stroke=1)

    row_y = y - 18
    for label, value, important in total_rows:
        c.setFillColorRGB(0.35, 0.35, 0.35)
        c.setFont("Helvetica-Bold" if important else "Helvetica", 11 if not important else 12)
        c.drawString(52, row_y, label)
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold" if important else "Helvetica", 11 if not important else 16)
        c.drawRightString(page_width - 52, row_y, value)
        row_y -= 20

    y = totals_bottom - 24

    # Payment panel matching the online invoice.
    y = _pdf_new_page_if_needed(c, y, 210)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(40, y, "Payment details")
    y -= 18

    payment_height = 138
    payment_bottom = y - payment_height
    c.setFillColorRGB(0.93, 0.97, 1.0)
    c.setStrokeColorRGB(0.75, 0.87, 0.97)
    c.roundRect(40, payment_bottom, page_width - 80, payment_height, 10, fill=1, stroke=1)

    payment_lines = [
        ("Bank", ctx.bank_name),
        ("Account name", ctx.bank_account_name),
        ("Sort code", ctx.bank_sort_code),
        ("Account number", ctx.bank_account_number),
        ("Reference", ctx.bank_payment_reference(item)),
        ("Amount due", ctx.pounds_text(item.get("balance_due", 0))),
    ]
    payment_y = y - 20
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(52, payment_y, "Bank transfer")
    payment_y -= 16

    for label, value in payment_lines:
        c.setFont("Helvetica", 10)
        c.drawString(52, payment_y, f"{label}:")
        c.setFont("Helvetica-Bold" if label in {"Sort code", "Account number", "Reference", "Amount due"} else "Helvetica", 10)
        c.drawString(130, payment_y, str(value))
        payment_y -= 15

    try:
        if ctx.qrcode_available:
            qr_bytes = ctx.bank_payment_qr_png(item)
            c.drawImage(
                ImageReader(io.BytesIO(qr_bytes)),
                page_width - 152,
                payment_bottom + 17,
                width=102,
                height=102,
                preserveAspectRatio=True,
                mask="auto",
            )
    except Exception:
        pass

    y = payment_bottom - 22

    # Full payment terms, wrapped properly.
    y = _pdf_new_page_if_needed(c, y, 130)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Payment Terms")
    y -= 17
    c.setFont("Helvetica", 9)

    terms = ctx.invoice_terms[:]
    if (quote_result.get("quote_type", "") or "").lower() == "small":
        terms = terms[:3]

    for term in terms:
        for line_index, line in enumerate(textwrap.wrap(str(term), width=105) or [str(term)]):
            prefix = "• " if line_index == 0 else "  "
            c.drawString(40, y, prefix + line)
            y -= 12
            y = _pdf_new_page_if_needed(c, y, 55)
            c.setFont("Helvetica", 9)

    if item.get("payment_link"):
        y -= 4
        c.drawString(40, y, f"Payment link: {item['payment_link']}")
        y -= 12

    if str(item.get("status", "")).lower() == "paid":
        ctx.invoice_paid_watermark(c)

    _pdf_draw_invoice_photos(c, item, ctx)

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.getvalue()

def generate_quote_pdf_bytes(item: dict, ctx):
    result = item["result"]
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    y = _pdf_header(c, "QUOTE", f"Quote #{item['id']}", ctx)

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Customer")
    y -= 18
    c.setFont("Helvetica", 11)
    for line in [result.get("customer_name", "-"), result.get("customer_address", "-"), result.get("customer_phone", "-")]:
        if line:
            c.drawString(40, y, str(line)[:75])
            y -= 15

    y -= 8
    c.line(40, y, A4[0] - 40, y)
    y -= 22

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Works")
    y -= 18
    y = _pdf_draw_wrapped_text(c, result.get("job", "-"), 40, y, max_chars=95, font="Helvetica", size=10, leading=14)
    y -= 8
    c.line(40, y, A4[0] - 40, y)
    y -= 24

    # Itemised materials list for customer PDF
    y = _pdf_draw_materials_section(c, y, result, ctx)

    y = _pdf_new_page_if_needed(c, y, 170)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Price")
    y -= 20

    materials_base = result.get("materials_base", result.get("materials", 0))
    procurement_amount = result.get("materials_procurement_amount", 0)
    procurement_percent = result.get("materials_procurement_percent", 0)

    y = _pdf_row(c, y, "Labour", ctx.pounds_text(result.get("labour", 0)))
    if ctx.safe_float(result.get("callout_charge", 0), 0) > 0:
        y = _pdf_row(c, y, "Call-out charge", ctx.pounds_text(result.get("callout_charge", 0)))
    if ctx.safe_float(result.get("travel_charge", 0), 0) > 0:
        y = _pdf_row(c, y, "Travel charge", ctx.pounds_text(result.get("travel_charge", 0)))
    y = _pdf_row(c, y, "Materials supplied", ctx.pounds_text(materials_base))

    if ctx.safe_float(procurement_amount, 0) > 0:
        y = _pdf_row(
            c,
            y,
            f"Materials procurement & handling ({ctx.safe_float(procurement_percent, 0):.0f}%)",
            ctx.pounds_text(procurement_amount)
        )

    y = _pdf_row(c, y, "Materials total", ctx.pounds_text(result.get("materials", 0)))
    y = _pdf_row(c, y, "Deposit", ctx.pounds_text(result.get("deposit_amount", 0)))
    y = _pdf_row(c, y, "Total Price", ctx.pounds_text(result.get("total_price", 0)), bold=True)

    y -= 12
    y = _pdf_new_page_if_needed(c, y, 130)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Terms")
    y -= 18
    c.setFont("Helvetica", 9)
    text_obj = c.beginText(40, y)
    for line in ctx.quote_terms:
        text_obj.textLine(f"• {line}")
    c.drawText(text_obj)

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.getvalue()

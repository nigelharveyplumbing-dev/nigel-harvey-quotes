"""Existing invoice-photo paths, file preparation and SQLite metadata."""

from pathlib import Path

from PIL import Image, ImageOps

from business.config import INVOICE_PHOTO_DIR
from business.db import get_db


PHOTO_CATEGORIES = {
    "before": "Before",
    "during": "During",
    "after": "Completed",
    "hidden_pipework": "Hidden pipework",
    "damage": "Damage found",
    "parts_replaced": "Parts replaced",
    "compliance": "Compliance",
    "customer_supplied": "Customer supplied",
    "other": "Other",
}


def normalise_photo_category(value: str) -> str:
    value = (value or "after").strip().lower().replace(" ", "_")
    return value if value in PHOTO_CATEGORIES else "other"


def invoice_photo_folder(invoice_id: int) -> Path:
    folder = INVOICE_PHOTO_DIR / str(int(invoice_id))
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def load_invoice_photos(invoice_id: int):
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM invoice_photos
        WHERE invoice_id = ?
        ORDER BY
          CASE category
            WHEN 'before' THEN 1
            WHEN 'during' THEN 2
            WHEN 'hidden_pipework' THEN 3
            WHEN 'damage' THEN 4
            WHEN 'parts_replaced' THEN 5
            WHEN 'compliance' THEN 6
            WHEN 'customer_supplied' THEN 7
            WHEN 'after' THEN 8
            ELSE 9
          END,
          sort_order ASC,
          id ASC
    """, (invoice_id,)).fetchall()
    conn.close()
    return [{
        "id": row["id"],
        "invoice_id": row["invoice_id"],
        "category": row["category"],
        "category_label": PHOTO_CATEGORIES.get(row["category"], "Other"),
        "caption": row["caption"] or "",
        "filename": row["filename"],
        "original_filename": row["original_filename"] or "",
        "sort_order": row["sort_order"] or 0,
        "created_at": row["created_at"],
        "url": f"/api/invoices/{invoice_id}/photos/{row['id']}",
    } for row in rows]


def save_invoice_photo_record(invoice_id: int, category: str, caption: str,
                              filename: str, original_filename: str, now_uk):
    conn = get_db()
    next_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM invoice_photos WHERE invoice_id = ?",
        (invoice_id,),
    ).fetchone()[0]
    conn.execute("""
        INSERT INTO invoice_photos (
            invoice_id, category, caption, filename, original_filename,
            sort_order, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        invoice_id,
        normalise_photo_category(category),
        (caption or "").strip(),
        filename,
        original_filename or "",
        int(next_order or 1),
        now_uk().isoformat(),
    ))
    photo_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return photo_id


def prepare_invoice_photo(source_path: Path, output_path: Path):
    with Image.open(source_path) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode not in ("RGB", "L"):
            background = Image.new("RGB", image.size, "white")
            if "A" in image.getbands():
                background.paste(image, mask=image.getchannel("A"))
            else:
                background.paste(image)
            image = background
        elif image.mode == "L":
            image = image.convert("RGB")
        image.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
        image.save(output_path, format="JPEG", quality=82, optimize=True)


def delete_invoice_photo_record(invoice_id: int, photo_id: int):
    conn = get_db()
    row = conn.execute(
        "SELECT filename FROM invoice_photos WHERE id = ? AND invoice_id = ?",
        (photo_id, invoice_id),
    ).fetchone()
    if not row:
        conn.close()
        return False
    conn.execute(
        "DELETE FROM invoice_photos WHERE id = ? AND invoice_id = ?",
        (photo_id, invoice_id),
    )
    conn.commit()
    conn.close()
    try:
        (invoice_photo_folder(invoice_id) / row["filename"]).unlink(missing_ok=True)
    except Exception:
        pass
    return True


def invoice_photo_path(invoice_id: int, photo_id: int):
    conn = get_db()
    row = conn.execute(
        "SELECT filename FROM invoice_photos WHERE id = ? AND invoice_id = ?",
        (photo_id, invoice_id),
    ).fetchone()
    conn.close()
    if not row:
        return None
    path = invoice_photo_folder(invoice_id) / row["filename"]
    return path if path.exists() else None

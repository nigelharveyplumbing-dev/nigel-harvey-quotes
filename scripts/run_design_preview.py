"""Fail-closed staging launcher with new ephemeral storage and no production integrations."""
import os
from pathlib import Path
import sys
import tempfile

if os.getenv('APP_ENVIRONMENT') != 'staging':
    raise SystemExit('Design preview requires staging')
if not os.getenv('APP_USERNAME') or not os.getenv('APP_PASSWORD'):
    raise SystemExit('Design preview requires password protection')
# Never accept inherited credentials or connections for operational integrations.
for key in list(os.environ):
    if key.startswith(('EMAIL_', 'SMTP_', 'OPENAI_', 'DATABASE_', 'BANK_')):
        os.environ.pop(key)
os.environ['EMAIL_ENABLED'] = '0'
os.environ['GOOGLE_PLACES_API_KEY'] = ''
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from business import config
with tempfile.TemporaryDirectory(prefix='nhp-design-preview-') as directory:
    root = Path(directory)
    config.DB_PATH = root / 'quotes.db'
    config.DB_BACKUP_DIR = root / 'backups'
    config.INVOICE_PHOTO_DIR = root / 'invoice_photos'
    import app as application
    import threading
    import time
    import requests
    from bs4 import BeautifulSoup

    # Reuse only the public website's Google-supplied review display. This
    # preview has no production API secrets, disk, database, or private access.
    fallback_reviews = application._google_reviews_html
    review_cache = {"expires": 0, "html": ""}
    review_lock = threading.Lock()

    def public_google_reviews():
        with review_lock:
            if time.monotonic() < review_cache["expires"]:
                return review_cache["html"]
            try:
                response = requests.get("https://www.nigelharveyplumbing.co.uk/", timeout=12)
                response.raise_for_status()
                box = BeautifulSoup(response.text, "html.parser").select_one("#reviews .reviewbox")
                if box is None:
                    raise ValueError("Public review display unavailable")
                html = box.decode_contents()
            except (requests.RequestException, ValueError):
                html = fallback_reviews()
            review_cache.update(expires=time.monotonic() + 300, html=html)
            return html

    application._google_reviews_html = public_google_reviews
    import uvicorn
    uvicorn.run(application.app, host='0.0.0.0', port=int(os.getenv('PORT', '10000')))

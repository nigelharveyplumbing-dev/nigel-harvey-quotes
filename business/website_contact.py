"""Small, deterministic helpers for public website contact links and review proof."""

import re
from html import escape
from urllib.parse import quote

from bs4 import BeautifulSoup


QUOTE_ATTRIBUTION_SCRIPT = """<script>
// Carry page and campaign context to the quote form without a cookie.
for (const link of document.querySelectorAll('a[href="/request-quote"]')) {
  link.addEventListener('click', function () {
    const next = new URL(link.href);
    const context = window.nhpAttribution ? window.nhpAttribution.context() : {landing_page:location.pathname};
    for (const [name,value] of Object.entries(context)) if (value) next.searchParams.set(name,value);
    link.href = next.pathname + next.search;
  });
}
</script>"""


def add_quote_attribution(html: str) -> str:
    return html.replace("</body>", QUOTE_ATTRIBUTION_SCRIPT + "</body>")


def whatsapp_url(phone: str, message: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("00"):
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = "44" + digits[1:]
    return f"https://wa.me/{digits}?text={quote(message)}"


def telephone_uri_number(phone: str) -> str:
    return re.sub(r"\D", "", phone)


def review_summary_html(review_html: str, reviews_url: str) -> str:
    """Re-use the fetched Google rating, never a separate or stale rating value."""
    rating = BeautifulSoup(review_html, "html.parser").select_one(".google-rating")
    link = escape(reviews_url, quote=True)
    if rating:
        return f'<a href="#reviews" aria-label="See customer reviews">{rating}</a>'
    return f'<a href="{link}" target="_blank" rel="noopener noreferrer">Read customer reviews on Google</a>'

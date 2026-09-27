"""Shared customer-facing shell for the homepage, enquiry and SEO pages."""

from html import escape
import os
from pathlib import Path

from bs4 import BeautifulSoup

from business.config import COMPANY_EMAIL, COMPANY_PHONE
from business.website_contact import telephone_uri_number, whatsapp_url


ROOT = Path(__file__).resolve().parents[1]
SITE_CSS = (ROOT / "static/public_site.css").read_text(encoding="utf-8")
SUBPAGE_CSS = (ROOT / "static/public_seo.css").read_text(encoding="utf-8")
HEADER = (ROOT / "templates/public_header.html").read_text(encoding="utf-8")
FOOTER = (ROOT / "templates/public_footer.html").read_text(encoding="utf-8")
ANALYTICS_JS = (ROOT / "static/public_analytics.js").read_text(encoding="utf-8")
GA4_MEASUREMENT_ID = "G-Q9Z2WWNF6F"

QUOTE_CSS = """
.quote-page{background:var(--light)}
.quote-page main.wrap{width:min(800px,92%)}
.quote-page main>.card{padding:clamp(22px,4vw,40px);margin:32px auto 55px}
.quote-page h1{font-size:clamp(2rem,5vw,2.8rem);line-height:1.12;margin:0 0 12px}
.quote-page main h2{font-size:1.2rem;margin:28px 0 8px}
.quote-page .sub,.quote-page .hint,.quote-page .small{color:var(--muted)}
.quote-page .hint,.quote-page .small{font-size:.87rem}
.quote-page .grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.quote-page label{display:block;font-weight:700;margin:15px 0 6px}
.quote-page input,.quote-page textarea,.quote-page select{width:100%;font:inherit;color:var(--navy);padding:13px;border:1px solid #9eb5c0;border-radius:8px;background:#fff}
.quote-page textarea{min-height:120px;resize:vertical}
.quote-page .actions{margin-top:24px}
.quote-page button.btn{border:0;cursor:pointer;font:inherit;font-weight:750}
.quote-page button:disabled{opacity:.65;cursor:wait}
.quote-page .ok,.quote-page .err{display:none;padding:15px;border-radius:8px;margin-top:17px}
.quote-page .ok{background:#eaf6eb;color:#174824}.quote-page .err{background:#fff0ef;color:#8c221e}
.quote-page .logo{max-height:70px;max-width:200px;object-fit:contain}
.quote-page .alternatives{border-top:1px solid var(--line);margin-top:32px;padding-top:19px}
.quote-page main a{color:var(--blue)}
.quote-page input:focus-visible,.quote-page select:focus-visible,.quote-page textarea:focus-visible{outline:3px solid var(--amber);outline-offset:2px}
@media(max-width:600px){.quote-page .grid{grid-template-columns:1fr}.quote-page .actions .btn{width:100%}}
"""


def _contact_markup(template: str) -> str:
    phone = escape(COMPANY_PHONE)
    uri = escape(telephone_uri_number(COMPANY_PHONE), quote=True)
    email = escape(COMPANY_EMAIL, quote=True)
    message = "Hi Nigel, I've got a plumbing job I'd like some help with."
    whatsapp = escape(whatsapp_url(COMPANY_PHONE, message), quote=True)
    return (template.replace("__COMPANY_PHONE_TEL__", uri)
            .replace("__COMPANY_PHONE__", phone)
            .replace("__COMPANY_EMAIL__", email)
            .replace("__WHATSAPP_URL__", whatsapp))


def site_header(*, home: bool = False) -> str:
    return _contact_markup(HEADER.replace("__NAV_PREFIX__", "" if home else "/"))


def site_footer() -> str:
    return _contact_markup(FOOTER)


def analytics_markup() -> str:
    # The public measurement ID is not a secret. Staging deliberately queues
    # consented events only; it never loads the tag or sends a hit to GA4.
    send = "false" if os.getenv("APP_ENVIRONMENT", "").strip().lower() == "staging" else "true"
    return ("<div id=\"analytics-consent\" class=\"analytics-consent\" role=\"region\" "
            "aria-label=\"Analytics choice\" hidden><div><strong>Optional analytics</strong> "
            "helps Nigel understand which pages and contact routes are useful. "
            "If you accept, Google Analytics may store cookies and receive browsing and contact-click information; "
            "your job details are not sent. You can change this later in the footer.</div>"
            "<div class=\"analytics-choices\"><button type=\"button\" data-choice=\"rejected\">Decline</button>"
            "<button type=\"button\" data-choice=\"accepted\">Accept analytics</button></div></div>"
            f'<script id="public-analytics" data-measurement-id="{GA4_MEASUREMENT_ID}" '
            f'data-send-to-google="{send}">{ANALYTICS_JS}</script>')


def render_shared_public_page(html: str) -> str:
    """Keep page content and SEO head intact while replacing the legacy chrome."""
    soup = BeautifulSoup(html, "html.parser")
    head, body = soup.head, soup.body
    if head is None or body is None:
        raise ValueError("Public page needs head and body")
    for style in head.find_all("style"):
        style.decompose()
    style = soup.new_tag("style")
    style.string = SITE_CSS + "\n" + SUBPAGE_CSS
    head.append(style)

    # These nodes were page-family-specific decoration. Content sections stay.
    for selector in (".topbar", "header.site-header", "body > .top",
                     "body footer", ".footer", ".mobile-call", ".sticky-call"):
        for node in soup.select(selector):
            node.decompose()
    body["class"] = ["public-subpage"]

    main = body.find("main", recursive=False)
    if main is None:
        main = soup.new_tag("main", id="main")
        for node in list(body.contents):
            main.append(node.extract())
        body.append(main)
    else:
        main["id"] = "main"

    fragment = BeautifulSoup(site_header(), "html.parser")
    for node in reversed(list(fragment.contents)):
        body.insert(0, node.extract())
    fragment = BeautifulSoup(site_footer(), "html.parser")
    for node in list(fragment.contents):
        body.append(node.extract())
    fragment = BeautifulSoup(analytics_markup(), "html.parser")
    for node in list(fragment.contents):
        body.append(node.extract())
    return str(soup)

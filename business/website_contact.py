"""Small, deterministic helpers for public website contact links and review proof."""

import re
from html import escape
from urllib.parse import quote

from bs4 import BeautifulSoup


QUOTE_ATTRIBUTION_SCRIPT = """<script>
(function () {
  'use strict';
  // Session-only source context after analytics consent; never a confirmed lead.
  const campaign = new URLSearchParams(location.search);
  const allowed = ['utm_source','utm_medium','utm_campaign','utm_content','utm_term'];
  let referring = '';
  try { const url = new URL(document.referrer); referring = url.origin + (url.origin === location.origin ? url.pathname : ''); } catch (_) {}
  const key = 'nhp_quote_origin_v1';
  const ttlMs = 30 * 60 * 1000;

  function consented() {
    let accepted = false;
    try { accepted = localStorage.getItem('nhp_analytics_choice_v1') === 'accepted'; } catch (_) {}
    // Revoking or declining consent must discard previously saved session context.
    if (!accepted) { try { sessionStorage.removeItem(key); } catch (_) {} }
    return accepted;
  }
  function campaignFields() {
    const fields = {};
    for (const name of allowed) if (campaign.has(name)) fields[name] = (campaign.get(name) || '').slice(0, 100);
    return fields;
  }
  function origin() {
    if (!consented()) return null;
    const fields = campaignFields();
    const externalReferrer = referring && !referring.startsWith(location.origin + '/');
    try {
      const saved = JSON.parse(sessionStorage.getItem(key) || 'null');
      if (!externalReferrer && !Object.keys(fields).length && saved &&
          typeof saved.landing_page === 'string' && saved.landing_page.startsWith('/') &&
          !saved.landing_page.startsWith('//') && Number.isFinite(saved.saved_at) &&
          Date.now() >= saved.saved_at && Date.now() - saved.saved_at <= ttlMs) return saved;
      const first = { landing_page: location.pathname, referrer: referring,
                      ...fields, saved_at: Date.now() };
      sessionStorage.setItem(key, JSON.stringify(first));
      return first;
    } catch (_) { return null; }
  }
  function apply(link) {
    const next = new URL(link.href, location.href);
    // Without consent, preserve only this page's existing explicit context.
    next.searchParams.set('landing_page', location.pathname);
    if (referring) next.searchParams.set('referrer', referring);
    for (const name of allowed) if (campaign.has(name)) next.searchParams.set(name, campaign.get(name));
    const first = origin();
    if (first) {
      next.searchParams.set('landing_page', first.landing_page);
      if (first.referrer) next.searchParams.set('referrer', first.referrer);
      else next.searchParams.delete('referrer');
      for (const name of allowed) {
        if (first[name]) next.searchParams.set(name, first[name]);
        else next.searchParams.delete(name);
      }
    }
    link.href = next.pathname + next.search;
  }
  for (const link of document.querySelectorAll('a[href="/request-quote"]')) apply(link);
  document.addEventListener('click', function (event) {
    const link = event.target.closest && event.target.closest('a[href]');
    if (!link) return;
    const next = new URL(link.href, location.href);
    if (next.origin !== location.origin) return;
    if (next.pathname === '/request-quote') apply(link);
    else origin(); // Captures the first page if consent was accepted after load.
  });
}());
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
        return f'<a href="#reviews" class="review-summary" aria-label="See customer reviews">{rating}</a>'
    return f'<a href="{link}" class="review-summary" target="_blank" rel="noopener noreferrer">Read customer reviews on Google</a>'


def add_public_review_badge(html: str, review_html: str, reviews_url: str) -> str:
    """Add one compact summary to a public intro; preserve the SEO head and content.

    Only explicitly selected public renderers call this. Private application and
    document responses never pass through this presentation helper.
    """
    soup = BeautifulSoup(html, "html.parser")
    intro = soup.select_one(".hero-copy, .hero-card, .project-intro > div, .advice-story, .project-index")
    if intro is None:
        return html
    original_intro = str(intro)
    summary = review_summary_html(review_html, reviews_url).replace('href="#reviews"', 'href="/#reviews"')
    badge = soup.select_one(".hero-review-badge")
    if badge is None:
        badge = soup.new_tag("div", attrs={"class": "hero-review-badge"})
        lead = intro.select_one(".lead, .project-lead, .advice-answer")
        if lead is None:
            lead = intro.find("p", recursive=False)
            if lead is not None and "kicker" in lead.get("class", []):
                lead = lead.find_next_sibling("p")
        if lead is None:
            return html
        lead.insert_after(badge)
    badge.clear()
    badge.append(BeautifulSoup(summary, "html.parser"))
    # The homepage owns the full Google cards. Keep existing local review anchors
    # useful, without duplicating Google's five cards across location pages.
    for box in soup.select(".reviewbox"):
        original_box = str(box)
        box.clear()
        box.append(BeautifulSoup(summary, "html.parser"))
        html = html.replace(original_box, str(box), 1)
    # The shared header already displays the graphic logo on every public page.
    for logo in intro.select('img[alt="Nigel Harvey Ltd logo"]'):
        logo.decompose()
    if original_intro in html:
        return html.replace(original_intro, str(intro), 1)
    return str(soup)

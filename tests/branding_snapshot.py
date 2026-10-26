"""Reverse only the owner-requested header logo for historical HTML locks."""
from bs4 import BeautifulSoup

LEGACY_BRAND = '<a class="brand" href="/">Nigel Harvey<span>PLUMBING</span></a>'
LOGO_BRAND = ('<a class="brand" href="/" aria-label="Nigel Harvey Plumbing home">'
              '<img class="brand-logo" src="/site-images/nigel-harvey-logo.png" '
              'alt="Nigel Harvey Ltd" width="430" height="130" decoding="async">'
              '<span>PLUMBING</span></a>')
LOGO_CSS = ('\n/* Restore the existing graphic logo in the shared public header. */\n'
            '.brand{flex-shrink:0;max-width:100%}.brand-logo{display:block;width:260px;max-width:100%;height:auto}.brand span{text-align:center}\n'
            '@media(min-width:901px) and (max-width:1060px){.nav{flex-wrap:wrap;padding:16px 0}.navlinks{width:100%;justify-content:space-between;flex-wrap:wrap;gap:10px}}\n')


def restore_brand(html, *, includes_css=False):
    pairs = [(LOGO_BRAND, LEGACY_BRAND),
             (str(BeautifulSoup(LOGO_BRAND, 'html.parser').a),
              str(BeautifulSoup(LEGACY_BRAND, 'html.parser').a))]
    for new, old in pairs:
        if html.count(new) == 1:
            html = html.replace(new, old, 1)
            break
    else:
        raise AssertionError('Expected exactly one reviewed header logo')
    if includes_css:
        if html.count(LOGO_CSS) != 1:
            raise AssertionError('Expected exactly one reviewed header-logo CSS block')
        html = html.replace(LOGO_CSS, '', 1)
    return html

"""Public SEO page content and renderers. Routes and authentication stay in app.py."""

import json
from html import escape
from pathlib import Path
from fastapi import Request
from business.config import (COMPANY_NAME, COMPANY_EMAIL, COMPANY_PHONE, COMPANY_PHONE_TEL, GOOGLE_RATING_VALUE, GOOGLE_REVIEW_COUNT, GOOGLE_REVIEWS_URL, GOOGLE_REVIEW_1_TEXT, GOOGLE_REVIEW_1_AUTHOR, GOOGLE_REVIEW_2_TEXT, GOOGLE_REVIEW_2_AUTHOR, GOOGLE_REVIEW_3_TEXT, GOOGLE_REVIEW_3_AUTHOR)

def build_homepage_faq_schema() -> str:
    faq_items = [
        {
            "@type": "Question",
            "name": "Do you cover all of Surrey?",
            "acceptedAnswer": {
                "@type": "Answer",
                "text": "Nigel Harvey Ltd covers Guildford, Woking, Farnham, Godalming, Camberley, Aldershot, Leatherhead, Epsom and surrounding Surrey areas. If you are nearby, get in touch and ask."
            }
        },
        {
            "@type": "Question",
            "name": "Can I request an emergency plumber?",
            "acceptedAnswer": {
                "@type": "Answer",
                "text": "Yes. The site includes an emergency plumbing page and quote request form so customers can send details quickly for urgent plumbing issues in Surrey."
            }
        },
        {
            "@type": "Question",
            "name": "What type of plumbing work do you do?",
            "acceptedAnswer": {
                "@type": "Answer",
                "text": "General plumbing, bathroom plumbing, leaks, toilets, taps, sinks, wastes, pipework changes, radiators and similar domestic plumbing jobs."
            }
        },
    ]
    return json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": faq_items}, ensure_ascii=False)


def build_homepage_business_schema(canonical_home: str) -> str:
    schema = {
        "@context": "https://schema.org",
        "@type": "Plumber",
        "name": COMPANY_NAME,
        "telephone": COMPANY_PHONE,
        "email": COMPANY_EMAIL,
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "125 Bushy Hill Drive",
            "addressLocality": "Guildford",
            "postalCode": "GU1 2UG",
            "addressCountry": "GB",
        },
        "areaServed": ["Guildford", "Woking", "Farnham", "Godalming", "Camberley", "Aldershot", "Leatherhead", "Epsom", "Weybridge", "Cobham", "Surrey"],
        "url": canonical_home,
        "description": "Plumbing services in Surrey and surrounding areas including emergency plumbing, general plumbing, bathroom plumbing, leaks, pipework and domestic plumbing repairs.",
    }
    if GOOGLE_RATING_VALUE and GOOGLE_REVIEW_COUNT:
        schema["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": GOOGLE_RATING_VALUE,
            "reviewCount": GOOGLE_REVIEW_COUNT,
            "bestRating": "5",
            "worstRating": "1",
        }
    reviews = []
    for text_value, author in [
        (GOOGLE_REVIEW_1_TEXT, GOOGLE_REVIEW_1_AUTHOR),
        (GOOGLE_REVIEW_2_TEXT, GOOGLE_REVIEW_2_AUTHOR),
        (GOOGLE_REVIEW_3_TEXT, GOOGLE_REVIEW_3_AUTHOR),
    ]:
        if text_value and author:
            reviews.append({
                "@type": "Review",
                "author": {"@type": "Person", "name": author},
                "reviewBody": text_value,
                "reviewRating": {"@type": "Rating", "ratingValue": "5", "bestRating": "5", "worstRating": "1"},
            })
    if reviews:
        schema["review"] = reviews
    return json.dumps(schema, ensure_ascii=False)


def build_reviews_badge_html() -> str:
    if GOOGLE_RATING_VALUE and GOOGLE_REVIEW_COUNT:
        reviews_link = escape(GOOGLE_REVIEWS_URL, quote=True)
        return f'<a href="{reviews_link}" target="_blank" rel="noopener noreferrer">Google rating {escape(GOOGLE_RATING_VALUE)}/5</a><span>{escape(GOOGLE_REVIEW_COUNT)} Google reviews</span>'
    return '<span>Trusted local Surrey plumber</span><span>Ask about recent customer feedback</span>'


def build_reviews_section_html() -> str:
    if GOOGLE_RATING_VALUE and GOOGLE_REVIEW_COUNT:
        cards = []
        for text_value, author in [
            (GOOGLE_REVIEW_1_TEXT, GOOGLE_REVIEW_1_AUTHOR),
            (GOOGLE_REVIEW_2_TEXT, GOOGLE_REVIEW_2_AUTHOR),
            (GOOGLE_REVIEW_3_TEXT, GOOGLE_REVIEW_3_AUTHOR),
        ]:
            if text_value and author:
                cards.append(
                    f'<div class="card faq"><h3>{escape(author)}</h3><p>“{escape(text_value)}”</p></div>'
                )
        if not cards:
            cards.append('<div class="card faq"><h3>Google customer feedback</h3><p>Strong review signals help build trust with both customers and search engines. Add your three best Google reviews here to strengthen the homepage further.</p></div>')
        reviews_link = escape(GOOGLE_REVIEWS_URL, quote=True)
        return (
            '<div class="wrap section"><h2>Google reviews</h2>'
            f'<p class="copy">Nigel Harvey Ltd currently shows a Google rating of {escape(GOOGLE_RATING_VALUE)}/5 from {escape(GOOGLE_REVIEW_COUNT)} reviews. '
            f'<a href="{reviews_link}" target="_blank" rel="noopener noreferrer">Read the latest Google reviews</a>.</p>'
            f'<div class="grid3">{"".join(cards)}</div></div>'
        )
    return (
        '<div class="wrap section"><h2>Trusted local plumber in Surrey</h2>'
        '<p class="copy">Nigel Harvey Ltd is a local plumbing and heating company serving Surrey and surrounding areas. We focus on providing reliable service, clear communication and quality workmanship on every job.</p></div>'
    )


SEO_CSS = (Path(__file__).resolve().parents[1] / "static/public_seo.css").read_text(encoding="utf-8")


LOCATION_PAGES = [
    {"slug":"guildford","name":"Guildford"},
    {"slug":"woking","name":"Woking"},
    {"slug":"farnham","name":"Farnham"},
    {"slug":"godalming","name":"Godalming"},
    {"slug":"camberley","name":"Camberley"},
    {"slug":"aldershot","name":"Aldershot"},
    {"slug":"leatherhead","name":"Leatherhead"},
    {"slug":"epsom","name":"Epsom"},
    {"slug":"farnborough","name":"Farnborough"},
    {"slug":"fairlands","name":"Fairlands"},
    {"slug":"worplesdon","name":"Worplesdon"},
    {"slug":"merrow","name":"Merrow"},
    {"slug":"burpham","name":"Burpham"},
    {"slug":"shalford","name":"Shalford"},
]


SERVICE_PAGES = [
    {"slug":"emergency-plumber-surrey","title":"Urgent Plumbing in Surrey","meta":"For a leak, burst pipe or urgent domestic plumbing problem around Guildford and nearby areas, call Nigel to discuss the issue and availability.","heading":"Urgent Plumbing in Surrey","intro":"Water escaping from a pipe or fitting, a failed toilet or another pressing plumbing issue? Call Nigel to describe what is happening and discuss availability. For a significant leak, isolate the water if it is safe to do so.","body":"Explain where the problem is, whether water is still escaping and what you have safely been able to isolate. Your postcode helps confirm whether Nigel can reach your area. An online form can provide details, but a call is better for a time-sensitive problem.","keywords":"urgent plumber Surrey, plumbing leak Surrey, burst pipe Guildford"},
    {"slug":"general-plumbing-surrey","title":"General Plumbing in Surrey","meta":"Taps, toilets, sinks, wastes, leaks, outside taps and domestic plumbing repairs around Guildford and nearby Surrey areas. Speak directly with Nigel.","heading":"General Plumbing in Surrey","intro":"Nigel handles everyday domestic plumbing jobs, from tap and toilet repairs to sink fittings, wastes, outside taps, leaks and pipework alterations around Guildford and nearby towns.","body":"A useful enquiry includes the fixture involved, what is going wrong and whether there is an active leak. You can send the details and your postcode, then discuss the work and any relevant charges with Nigel before proceeding.","keywords":"general plumbing Surrey, plumber Guildford, tap and toilet repairs"},
    {"slug":"bathroom-plumbing-surrey","title":"Bathroom Plumbing in Surrey","meta":"Bathroom and shower plumbing around Guildford and nearby areas, including sanitaryware connections, pipework changes and first or second fix work.","heading":"Bathroom Plumbing in Surrey","intro":"For bathroom plumbing, Nigel can discuss sanitaryware connections, shower pipework and first or second fix plumbing as part of a planned refurbishment or smaller update.","body":"Tell Nigel which fittings you want to replace, what is staying in place and whether the layout changes. These details help distinguish a straightforward replacement from new pipework or other preparation before a quote is agreed.","keywords":"bathroom plumbing Surrey, shower plumbing Guildford, sanitaryware plumbing"},
    {"slug":"heating-repairs-surrey","title":"Radiators & Heating Plumbing in Surrey","meta":"Radiator, valve, towel radiator and heating pipework plumbing around Guildford and nearby Surrey areas. Discuss the work with Nigel.","heading":"Radiators & Heating Plumbing in Surrey","intro":"Nigel can help with plumbing-related heating work such as radiators, towel radiators, valves and associated pipework. Describe which rooms and fittings are affected.","body":"For a radiator enquiry, say whether the issue is a valve, a leak or a planned replacement, and whether the pipework position will change. Nigel can discuss the practical plumbing work required.","keywords":"radiator plumber Surrey, radiator valves Guildford, heating pipework"},
]

PRIMARY_LOCATION_NOTES = {
    "epsom": {
        "intro": "For a leaking tap, toilet fault or planned bathroom plumbing in Epsom, tell me what you have noticed and whether the water can be isolated. I am based in Guildford; sending the postcode helps me confirm travel and the next step.",
        "detail": "Epsom enquiries can range from a small repair to bathroom pipework. If you can, describe the fixture, when the problem started and whether access or parking needs arranging. For an active leak, call rather than waiting for a form reply.",
        "nearby": "Leatherhead and other nearby Surrey areas",
    },
    "leatherhead": {
        "intro": "Need help with a radiator valve, leaking pipe or bathroom fitting in Leatherhead? Send a description and postcode so I can understand the work and confirm whether the location fits my route from Guildford.",
        "detail": "For radiator or pipework enquiries, say whether the issue is with one room or several and whether water is escaping. For planned bathrooms, tell me which fittings you want to change. Photos can be shared through WhatsApp after making contact.",
        "nearby": "Epsom and surrounding Surrey towns",
    },
    "farnborough": {
        "intro": "For domestic plumbing work in Farnborough, from taps and toilets to showers and radiator pipework, describe the job and send your postcode. I am based in Guildford and can confirm whether I can take on the work in your part of Farnborough.",
        "detail": "Farnborough is in Hampshire, close to the Surrey service area. The postcode and a short description help me check travel and discuss any charge before arranging work. Call for an urgent plumbing issue rather than waiting for an online reply.",
        "nearby": "Aldershot, Camberley and nearby areas",
    },
}


def get_company_logo_html(logo_value: str) -> str:
    return f'<img src="{logo_value}" alt="Nigel Harvey Ltd logo" class="logo" width="240" height="90">' if logo_value else ''


def render_location_page(location_name: str, logo_html: str, request: Request | None = None, *, absolute_url, _google_reviews_html) -> str:
    related = ''.join(
        f'<a href="/plumber-{escape(item["slug"])}">Plumber in {escape(item["name"])}</a>'
        for item in LOCATION_PAGES if item['name'] != location_name
    )
    slug = location_name.lower()
    canonical = absolute_url(f"/plumber-{slug}", request)
    is_guildford = slug == "guildford"
    primary_note = PRIMARY_LOCATION_NOTES.get(slug)
    primary_details_html = (
        f'<section class="section-pale"><div class="wrap"><div class="intro left"><h2>Planning plumbing work in {escape(location_name)}</h2>'
        f'<p>{escape(primary_note["intro"])}</p></div><div class="cards"><div class="card"><h3>Useful details to share</h3>'
        f'<p>{escape(primary_note["detail"])}</p></div><div class="card"><h3>Nearby enquiries</h3>'
        f'<p>I can also discuss work around {escape(primary_note["nearby"])}. Please send the job postcode so I can confirm the area.</p></div>'
        '<div class="card"><h3>How to get started</h3><p>Send the problem, postcode and preferred way to be contacted. '
        'I can then discuss the next step and any relevant charges.</p><p><a href="/request-quote">Request a quote</a></p></div>'
        '</div></div></section>'
    ) if primary_note else ""
    location_intro = primary_note["intro"] if primary_note else (
        f"Reliable domestic plumbing for leaks, taps, toilets, bathrooms, showers, radiators and pipework in {location_name} and surrounding Surrey areas. From first enquiry to finished job, you deal directly with me, Nigel."
    )

    title = (
        "Plumber in Guildford | Local Plumbing Services | Nigel Harvey Plumbing"
        if is_guildford else
        f"Plumber in {location_name} | Reliable Local Plumbing Services | Nigel Harvey Ltd"
    )
    meta_description = (
        "Local plumber in Guildford for leaks, toilets, taps, radiators, bathroom plumbing and general plumbing repairs. Deal directly with Nigel Harvey Plumbing and request a clear quote online."
        if is_guildford else
        f"Looking for a plumber in {location_name}? Nigel Harvey Ltd provides leaks, bathroom plumbing and general plumbing services in {location_name} and surrounding Surrey areas."
    )
    if slug == "farnborough":
        meta_description = ("Domestic plumbing in Farnborough for taps, toilets, showers, radiators and pipework. "
                            "Contact Guildford-based Nigel with the job details and postcode.")

    breadcrumb_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": absolute_url("/", request)},
            {"@type": "ListItem", "position": 2, "name": f"Plumber in {location_name}", "item": canonical},
        ],
    }, ensure_ascii=False)
    local_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "Plumber",
        "name": "Nigel Harvey Plumbing",
        "url": canonical,
        "telephone": COMPANY_PHONE,
        "email": COMPANY_EMAIL,
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "125 Bushy Hill Drive",
            "addressLocality": "Guildford",
            "postalCode": "GU1 2UG",
            "addressCountry": "GB",
        },
        "areaServed": [location_name, "Guildford", "Surrey"],
        "serviceType": ["General plumbing", "Bathroom plumbing", "Leak repairs", "Toilet repairs", "Radiator and valve plumbing"],
        "description": f"Local plumber serving {location_name} and surrounding Surrey areas for domestic plumbing repairs and installations.",
    }, ensure_ascii=False)

    blue_location_css = r"""
:root{--navy:#0b2032;--blue:#1263a5;--pale:#f3f7fa;--gold:#e2b353;--text:#142b3e;--muted:#60717e;--border:#dfe7ec}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;font-family:Arial,Helvetica,sans-serif;color:var(--text);line-height:1.55;background:#fff}a{text-decoration:none;color:inherit}.wrap{width:min(1120px,92%);margin:auto}
.topbar{background:var(--navy);color:#fff;font-size:14px}.topbar .wrap{padding:9px 0;display:flex;justify-content:space-between;gap:20px}
.site-header{background:#fff;position:sticky;top:0;z-index:20;box-shadow:0 2px 18px #00000012}.site-nav{display:flex;align-items:center;justify-content:space-between;padding:15px 0}.brand{font-size:23px;font-weight:800;letter-spacing:-.5px}.brand small{display:block;color:var(--blue);font-size:11px;letter-spacing:2.5px}.navlinks{display:flex;align-items:center;gap:24px;font-weight:700;font-size:14px}.btn{display:inline-block;background:var(--blue);color:#fff;padding:13px 21px;border-radius:7px;font-weight:800}.btn.white{background:#fff;color:var(--navy)}
.guildford-hero{min-height:570px;display:grid;align-items:center;color:#fff;background:linear-gradient(90deg,#071827f2 0%,#071827d9 48%,#07182762 80%),url('/site-images/bathroom-illustrative.webp') center/cover}.hero-copy{max-width:760px;padding:82px 0}.eyebrow{color:#f0c66e;text-transform:uppercase;letter-spacing:2px;font-size:13px;font-weight:800}.guildford-hero h1{font-size:clamp(43px,6vw,67px);line-height:1.02;letter-spacing:-2px;margin:14px 0 20px}.guildford-hero p{font-size:20px;max-width:680px;color:#e5edf3}.actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:28px}
.trust{box-shadow:0 10px 30px #0000000c}.trustgrid{display:grid;grid-template-columns:repeat(4,1fr);text-align:center}.trustgrid div{padding:23px 10px;border-right:1px solid #e3e9ed}.trustgrid div:last-child{border:0}.trustgrid strong{display:block;font-size:17px}.trustgrid span{color:var(--muted);font-size:13px}
section{padding:72px 0}.section-pale{background:var(--pale)}.section-dark{background:var(--navy);color:#fff}.intro{text-align:center;max-width:780px;margin:0 auto 38px}.intro.left{text-align:left;margin-left:0}.intro h2,.content-title{font-size:39px;line-height:1.12;letter-spacing:-1px;margin:0 0 14px}.intro p,.muted{color:var(--muted)}.section-dark .intro p{color:#cbd7df}
.service-links{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.service-links a,.area-links a{background:#fff;border:1px solid var(--border);border-radius:11px;padding:17px;font-weight:800;color:var(--navy);text-align:center;transition:.15s}.service-links a:hover,.area-links a:hover{border-color:var(--blue);color:var(--blue);transform:translateY(-1px)}
.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.card{background:#fff;border-radius:13px;padding:28px;box-shadow:0 8px 25px #0b20320c}.section-pale .card{border:1px solid #e6edf1}.card h3{margin:0 0 9px}.card p{font-size:14px;color:var(--muted);margin:0}.section-dark .card{color:var(--text)}
.review-section{background:#f5f8fa}.reviewbox{max-width:1040px;margin:auto;text-align:center;background:#fff;padding:46px;border-radius:15px;box-shadow:0 10px 30px #0b20320d}.google-brand{font-size:20px;font-weight:800;margin-bottom:8px}.google-rating{display:flex;justify-content:center;align-items:center;gap:12px;margin:8px 0 24px}.google-rating strong{font-size:24px;color:var(--text)}.google-rating .stars{font-size:22px}.google-review-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;text-align:left;margin:0 0 24px}.google-review-card{border:1px solid #e3e9ed;border-radius:12px;padding:20px;background:#fff}.review-author{display:flex;gap:11px;align-items:center}.review-author a{color:var(--text);text-decoration:none}.review-avatar{width:42px;height:42px;border-radius:50%;object-fit:cover}.review-avatar-fallback{display:flex;align-items:center;justify-content:center;background:#eef3f6;color:var(--blue);font-weight:900}.review-meta{font-size:12px;color:var(--muted);margin-top:3px}.mini-stars{color:#e3a923;letter-spacing:1px}.review-text{font-size:14px;line-height:1.55;color:#46545f;margin:15px 0}.review-source{font-size:12px;font-weight:800;color:var(--blue);text-decoration:none}.review-note{font-size:12px;color:var(--muted);margin:0 0 20px}
.area-links{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.faq-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.faq-grid .card{border:1px solid var(--border)}
.cta-blue{background:var(--blue);color:#fff}.cta-blue .wrap{display:flex;justify-content:space-between;align-items:center;gap:30px}.cta-blue h2{margin:0;font-size:37px}.cta-blue p{margin:7px 0 0;color:#e8f2f8}
footer{background:#071827;color:#c8d3dc;padding:38px 0;font-size:14px}.foot{display:flex;justify-content:space-between;gap:30px}.foot strong{color:#fff}.mobile-call{display:none}
@media(max-width:800px){.site-nav{flex-wrap:wrap}.navlinks{flex-wrap:wrap;gap:10px}.topbar .wrap{justify-content:center}.topbar span:last-child{display:none}.guildford-hero{min-height:540px;background:linear-gradient(#071827c9,#071827e6),url('/site-images/bathroom-illustrative.webp') center/cover}.hero-copy{padding:62px 0}.guildford-hero h1{font-size:44px}.guildford-hero p{font-size:18px}.trustgrid{grid-template-columns:1fr 1fr}.trustgrid div:nth-child(2){border-right:0}.cards,.google-review-grid,.faq-grid{grid-template-columns:1fr}.service-links,.area-links{grid-template-columns:1fr 1fr}.cta-blue .wrap,.foot{display:block}.cta-blue .btn{margin-top:20px}.mobile-call{display:block;position:fixed;bottom:14px;left:4%;right:4%;z-index:25;background:var(--blue);color:#fff;padding:15px;border-radius:10px;text-align:center;font-weight:900;box-shadow:0 5px 22px #0005}section{padding:56px 0}.intro h2,.content-title{font-size:33px}}
@media(max-width:520px){.service-links,.area-links{grid-template-columns:1fr}}
"""

    if is_guildford:
        faq_items = [
            ("What plumbing work do you cover in Guildford?", "Nigel Harvey Plumbing covers domestic plumbing including leaks, taps, toilets, sinks, wastes, radiators and valves, bathroom plumbing, pipework changes and other general plumbing repairs."),
            ("Can I request a plumbing quote online?", "Yes. Send the job details through the online quote form. You can share photos separately via WhatsApp if useful, and Nigel can review what is required before arranging the next step."),
            ("Do you cover areas around Guildford as well?", "Yes. The business is based in Guildford and also covers nearby Surrey areas including Godalming, Woking, Farnham, Fairlands, Worplesdon, Merrow, Burpham and Shalford."),
        ]
        faq_schema = json.dumps({
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faq_items
            ],
        }, ensure_ascii=False)
        faq_html = ''.join(
            f'<div class="card faq"><h3>{escape(q)}</h3><p>{escape(a)}</p></div>'
            for q, a in faq_items
        )
        local_service_links = ''.join([
            '<a href="/leak-repair-guildford">Leak Repair in Guildford</a>',
            '<a href="/toilet-repair-guildford">Toilet Repairs in Guildford</a>',
            '<a href="/bathroom-plumbing-guildford">Bathroom Plumbing in Guildford</a>',
            '<a href="/emergency-plumber-guildford">Urgent Plumbing in Guildford</a>',
        ])
        reviews_html = _google_reviews_html()
        guildford_css = r"""
:root{--navy:#0b2032;--blue:#1263a5;--pale:#f3f7fa;--gold:#e2b353;--text:#142b3e;--muted:#60717e;--border:#dfe7ec}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;font-family:Arial,Helvetica,sans-serif;color:var(--text);line-height:1.55;background:#fff}a{text-decoration:none;color:inherit}.wrap{width:min(1120px,92%);margin:auto}
.topbar{background:var(--navy);color:#fff;font-size:14px}.topbar .wrap{padding:9px 0;display:flex;justify-content:space-between;gap:20px}
.site-header{background:#fff;position:sticky;top:0;z-index:20;box-shadow:0 2px 18px #00000012}.site-nav{display:flex;align-items:center;justify-content:space-between;padding:15px 0}.brand{font-size:23px;font-weight:800;letter-spacing:-.5px}.brand small{display:block;color:var(--blue);font-size:11px;letter-spacing:2.5px}.navlinks{display:flex;align-items:center;gap:24px;font-weight:700;font-size:14px}.btn{display:inline-block;background:var(--blue);color:#fff;padding:13px 21px;border-radius:7px;font-weight:800}.btn.white{background:#fff;color:var(--navy)}
.guildford-hero{min-height:570px;display:grid;align-items:center;color:#fff;background:linear-gradient(90deg,#071827f2 0%,#071827d9 48%,#07182762 80%),url('/site-images/bathroom-illustrative.webp') center/cover}.hero-copy{max-width:760px;padding:82px 0}.eyebrow{color:#f0c66e;text-transform:uppercase;letter-spacing:2px;font-size:13px;font-weight:800}.guildford-hero h1{font-size:clamp(43px,6vw,67px);line-height:1.02;letter-spacing:-2px;margin:14px 0 20px}.guildford-hero p{font-size:20px;max-width:680px;color:#e5edf3}.actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:28px}
.trust{box-shadow:0 10px 30px #0000000c}.trustgrid{display:grid;grid-template-columns:repeat(4,1fr);text-align:center}.trustgrid div{padding:23px 10px;border-right:1px solid #e3e9ed}.trustgrid div:last-child{border:0}.trustgrid strong{display:block;font-size:17px}.trustgrid span{color:var(--muted);font-size:13px}
section{padding:72px 0}.section-pale{background:var(--pale)}.section-dark{background:var(--navy);color:#fff}.intro{text-align:center;max-width:780px;margin:0 auto 38px}.intro.left{text-align:left;margin-left:0}.intro h2,.content-title{font-size:39px;line-height:1.12;letter-spacing:-1px;margin:0 0 14px}.intro p,.muted{color:var(--muted)}.section-dark .intro p{color:#cbd7df}
.service-links{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.service-links a,.area-links a{background:#fff;border:1px solid var(--border);border-radius:11px;padding:17px;font-weight:800;color:var(--navy);text-align:center;transition:.15s}.service-links a:hover,.area-links a:hover{border-color:var(--blue);color:var(--blue);transform:translateY(-1px)}
.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.card{background:#fff;border-radius:13px;padding:28px;box-shadow:0 8px 25px #0b20320c}.section-pale .card{border:1px solid #e6edf1}.card h3{margin:0 0 9px}.card p{font-size:14px;color:var(--muted);margin:0}.section-dark .card{color:var(--text)}
.review-section{background:#f5f8fa}.reviewbox{max-width:1040px;margin:auto;text-align:center;background:#fff;padding:46px;border-radius:15px;box-shadow:0 10px 30px #0b20320d}.google-brand{font-size:20px;font-weight:800;margin-bottom:8px}.google-rating{display:flex;justify-content:center;align-items:center;gap:12px;margin:8px 0 24px}.google-rating strong{font-size:24px;color:var(--text)}.google-rating .stars{font-size:22px}.google-review-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;text-align:left;margin:0 0 24px}.google-review-card{border:1px solid #e3e9ed;border-radius:12px;padding:20px;background:#fff}.review-author{display:flex;gap:11px;align-items:center}.review-author a{color:var(--text);text-decoration:none}.review-avatar{width:42px;height:42px;border-radius:50%;object-fit:cover}.review-avatar-fallback{display:flex;align-items:center;justify-content:center;background:#eef3f6;color:var(--blue);font-weight:900}.review-meta{font-size:12px;color:var(--muted);margin-top:3px}.mini-stars{color:#e3a923;letter-spacing:1px}.review-text{font-size:14px;line-height:1.55;color:#46545f;margin:15px 0}.review-source{font-size:12px;font-weight:800;color:var(--blue);text-decoration:none}.review-note{font-size:12px;color:var(--muted);margin:0 0 20px}
.area-links{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.faq-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.faq-grid .card{border:1px solid var(--border)}
.cta-blue{background:var(--blue);color:#fff}.cta-blue .wrap{display:flex;justify-content:space-between;align-items:center;gap:30px}.cta-blue h2{margin:0;font-size:37px}.cta-blue p{margin:7px 0 0;color:#e8f2f8}
footer{background:#071827;color:#c8d3dc;padding:38px 0;font-size:14px}.foot{display:flex;justify-content:space-between;gap:30px}.foot strong{color:#fff}.mobile-call{display:none}
@media(max-width:800px){.site-nav{flex-wrap:wrap}.navlinks{flex-wrap:wrap;gap:10px}.topbar .wrap{justify-content:center}.topbar span:last-child{display:none}.guildford-hero{min-height:540px;background:linear-gradient(#071827c9,#071827e6),url('/site-images/bathroom-illustrative.webp') center/cover}.hero-copy{padding:62px 0}.guildford-hero h1{font-size:44px}.guildford-hero p{font-size:18px}.trustgrid{grid-template-columns:1fr 1fr}.trustgrid div:nth-child(2){border-right:0}.cards,.google-review-grid,.faq-grid{grid-template-columns:1fr}.service-links,.area-links{grid-template-columns:1fr 1fr}.cta-blue .wrap,.foot{display:block}.cta-blue .btn{margin-top:20px}.mobile-call{display:block;position:fixed;bottom:14px;left:4%;right:4%;z-index:25;background:var(--blue);color:#fff;padding:15px;border-radius:10px;text-align:center;font-weight:900;box-shadow:0 5px 22px #0005}section{padding:56px 0}.intro h2,.content-title{font-size:33px}}
@media(max-width:520px){.service-links,.area-links{grid-template-columns:1fr}}
"""
        return f"""<!doctype html>
<html lang="en-GB"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title><meta name="description" content="{escape(meta_description)}"><meta name="robots" content="index,follow,max-image-preview:large"><link rel="canonical" href="{escape(canonical)}">
<meta property="og:type" content="website"><meta property="og:title" content="{escape(title)}"><meta property="og:description" content="{escape(meta_description)}"><meta property="og:url" content="{escape(canonical)}">
<script type="application/ld+json">{breadcrumb_schema}</script><script type="application/ld+json">{local_schema}</script><script type="application/ld+json">{faq_schema}</script><style>{guildford_css}</style></head><body>
<div class="topbar"><div class="wrap"><span>Local plumber serving Guildford &amp; Surrey</span><span>Call Nigel: {escape(COMPANY_PHONE)} &nbsp; · &nbsp; {escape(COMPANY_EMAIL)}</span></div></div>
<header class="site-header"><div class="wrap site-nav"><div class="brand">Nigel Harvey <small>PLUMBING</small></div><div class="navlinks"><a href="#services">Services</a><a href="#about">About</a><a href="#reviews">Reviews</a><a href="#areas">Areas</a><a class="btn" href="/request-quote">Get a Quote</a></div></div></header>
<section class="guildford-hero"><div class="wrap"><div class="hero-copy"><div class="eyebrow">Nigel Harvey Plumbing · Guildford</div><h1>Plumber in Guildford</h1><p>Local domestic plumbing for leaks, taps, toilets, bathrooms, showers, radiators and pipework. From first enquiry to finished job, you deal directly with me, Nigel.</p><div class="actions"><a class="btn" href="/request-quote">Get a Quote</a><a class="btn white" href="tel:{escape(COMPANY_PHONE_TEL)}">Call {escape(COMPANY_PHONE)}</a></div></div></div></section>
<div class="trust"><div class="wrap trustgrid"><div><strong>Local &amp; independent</strong><span>Based in Guildford</span></div><div><strong>Clear communication</strong><span>Deal directly with Nigel</span></div><div><strong>Clear quotes</strong><span>Work &amp; charges explained</span></div><div><strong>Surrey coverage</strong><span>Guildford &amp; nearby areas</span></div></div></div>
<section id="services"><div class="wrap"><div class="intro"><h2>Plumbing services in Guildford</h2><p>Whether you have a leaking fitting, a toilet that is not working properly, a radiator or valve problem, or planned bathroom plumbing, send the details directly to Nigel. Photos and a short description can help establish what may be required before the visit.</p></div><div class="service-links">{local_service_links}</div></div></section>
<section class="section-pale"><div class="wrap"><div class="intro"><h2>Domestic plumbing work I can help with</h2><p>Practical plumbing repairs and planned work for homes and landlords across Guildford.</p></div><div class="cards"><div class="card"><h3>Leaks, taps &amp; toilets</h3><p>Repairs to leaking pipework and fittings, taps, toilet mechanisms, wastes, traps and other everyday plumbing problems.</p></div><div class="card"><h3>Bathrooms &amp; showers</h3><p>Bathroom plumbing, sanitaryware connections, shower pipework, first and second fix work and practical plumbing alterations.</p></div><div class="card"><h3>Radiators &amp; pipework</h3><p>Radiators, TRVs and valves, towel radiators, pipework alterations and plumbing-related heating work.</p></div></div></div></section>
<section class="section-dark" id="about"><div class="wrap"><div class="intro"><h2>A local Guildford plumber you deal with directly</h2><p>Nigel Harvey Plumbing is based in Guildford. When you enquire, you deal directly with Nigel rather than a call centre or salesperson. The aim is straightforward communication, a clear quotation and a practical plan for getting the work completed.</p></div><div class="cards"><div class="card"><h3>Direct contact</h3><p>Speak directly with the person who will be carrying out the plumbing work.</p></div><div class="card"><h3>Clear quotations</h3><p>Work and relevant charges can be set out before you decide whether to proceed.</p></div><div class="card"><h3>Local coverage</h3><p>Based in Guildford and covering surrounding towns and villages across Surrey.</p></div></div></div></section>
<section class="review-section" id="reviews"><div class="wrap"><div class="intro"><h2>Customer reviews</h2><p>Recent independent Google feedback from plumbing customers.</p></div><div class="reviewbox">{reviews_html}</div></div></section>
<section id="areas"><div class="wrap"><div class="intro"><h2>Areas near Guildford</h2><p>As well as Guildford itself, plumbing work is available across nearby Surrey areas. Use the local pages below for more information.</p></div><div class="area-links">{related}</div></div></section>
<section class="section-pale"><div class="wrap"><div class="intro"><h2>Frequently asked questions</h2></div><div class="faq-grid">{faq_html}</div></div></section>
<section class="cta-blue"><div class="wrap"><div><h2>Need a plumber in Guildford?</h2><p>Send your postcode, a short description and photos if useful, or call Nigel directly.</p></div><div class="actions"><a class="btn white" href="tel:{escape(COMPANY_PHONE_TEL)}">Call Nigel</a><a class="btn white" href="/request-quote">Get a Quote</a></div></div></section>
<footer><div class="wrap foot"><div><strong>Nigel Harvey Plumbing</strong><br>Nigel Harvey Ltd · Guildford, Surrey</div><div>{escape(COMPANY_PHONE)}<br>{escape(COMPANY_EMAIL)}</div></div></footer><a class="mobile-call" href="tel:{escape(COMPANY_PHONE_TEL)}">Call Nigel · {escape(COMPANY_PHONE)}</a></body></html>"""

    faq_items = [
        (f"What plumbing work do you cover in {location_name}?", f"I cover domestic plumbing in {location_name}, including leaks, taps, toilets, sinks, wastes, radiators and valves, bathroom plumbing, pipework changes and other general plumbing repairs."),
        ("Can I request a plumbing quote online?", "Yes. Send me the job details through the online quote form. You can share photos separately via WhatsApp if useful, and I can discuss what is required before arranging the next step."),
        (f"Do you cover areas around {location_name} as well?", f"I am based in Guildford and receive enquiries from {location_name} and nearby areas. Please send a postcode so I can confirm whether I can take on the job."),
    ]
    faq_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faq_items
        ],
    }, ensure_ascii=False)
    faq_html = ''.join(
        f'<div class="card faq"><h3>{escape(q)}</h3><p>{escape(a)}</p></div>'
        for q, a in faq_items
    )
    local_service_links = ''.join([
        f'<a href="/leak-repair-{escape(slug)}">Leak Repair in {escape(location_name)}</a>',
        f'<a href="/toilet-repair-{escape(slug)}">Toilet Repairs in {escape(location_name)}</a>',
        f'<a href="/bathroom-plumbing-{escape(slug)}">Bathroom Plumbing in {escape(location_name)}</a>',
        f'<a href="/emergency-plumber-{escape(slug)}">Urgent Plumbing in {escape(location_name)}</a>',
    ])
    if slug == "farnborough":
        local_service_links = ''.join(
            f'<a href="/{escape(item["slug"])}">{escape(item["heading"])}</a>'
            for item in SERVICE_PAGES
        )
    reviews_html = _google_reviews_html()
    return f"""<!doctype html>
<html lang="en-GB"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title><meta name="description" content="{escape(meta_description)}"><meta name="robots" content="index,follow,max-image-preview:large"><link rel="canonical" href="{escape(canonical)}">
<meta property="og:type" content="website"><meta property="og:title" content="{escape(title)}"><meta property="og:description" content="{escape(meta_description)}"><meta property="og:url" content="{escape(canonical)}">
<script type="application/ld+json">{breadcrumb_schema}</script><script type="application/ld+json">{local_schema}</script><script type="application/ld+json">{faq_schema}</script><style>{blue_location_css}</style></head><body>
<div class="topbar"><div class="wrap"><span>Local plumber serving {escape(location_name)} &amp; Surrey</span><span>Call Nigel: {escape(COMPANY_PHONE)} &nbsp; · &nbsp; {escape(COMPANY_EMAIL)}</span></div></div>
<header class="site-header"><div class="wrap site-nav"><a class="brand" href="/">Nigel Harvey <small>PLUMBING</small></a><div class="navlinks"><a href="#services">Services</a><a href="#about">About</a><a href="#reviews">Reviews</a><a href="#areas">Areas</a><a class="btn" href="/request-quote">Get a Quote</a></div></div></header>
<section class="guildford-hero"><div class="wrap"><div class="hero-copy"><div class="eyebrow">Nigel Harvey Plumbing · {escape(location_name)}</div><h1>Plumber in {escape(location_name)}</h1><p>{escape(location_intro)}</p><div class="actions"><a class="btn" href="/request-quote">Get a Quote</a><a class="btn white" href="tel:{escape(COMPANY_PHONE_TEL)}">Call {escape(COMPANY_PHONE)}</a></div></div></div></section>
<div class="trust"><div class="wrap trustgrid"><div><strong>Local &amp; independent</strong><span>Based in Guildford</span></div><div><strong>Clear communication</strong><span>Deal directly with me</span></div><div><strong>Clear quotes</strong><span>Work &amp; charges explained</span></div><div><strong>Surrey coverage</strong><span>{escape(location_name)} &amp; nearby areas</span></div></div></div>
<section id="services"><div class="wrap"><div class="intro"><h2>Plumbing services in {escape(location_name)}</h2><p>Whether you have a leaking fitting, a toilet that is not working properly, a radiator or valve problem, or planned bathroom plumbing, send the details directly to me. Photos and a short description can help me establish what may be required before the visit.</p></div><div class="service-links">{local_service_links}</div></div></section>
{primary_details_html}
<section class="section-pale"><div class="wrap"><div class="intro"><h2>Domestic plumbing work I can help with</h2><p>I provide practical domestic plumbing services across {escape(location_name)} and nearby Surrey areas.</p></div><div class="cards"><div class="card"><h3>Leaks, taps &amp; toilets</h3><p>Repairs to leaking pipework and fittings, taps, toilet mechanisms, wastes, traps and other everyday plumbing problems.</p></div><div class="card"><h3>Bathrooms &amp; showers</h3><p>Bathroom plumbing, sanitaryware connections, shower pipework, first and second fix work and practical plumbing alterations.</p></div><div class="card"><h3>Radiators &amp; pipework</h3><p>Radiators, TRVs and valves, towel radiators, pipework alterations and plumbing-related heating work.</p></div></div></div></section>
<section id="about"><div class="wrap"><div class="intro left"><h2>A local plumber you deal with directly</h2><p>When you contact Nigel Harvey Plumbing, you deal directly with me, Nigel — not a call centre or salesperson. I am based in Guildford and cover {escape(location_name)} and surrounding Surrey areas.</p></div><div class="cards"><div class="card"><h3>Direct contact</h3><p>Speak directly with me, the person carrying out the plumbing work.</p></div><div class="card"><h3>Clear quotations</h3><p>I set out the work and relevant charges before you decide whether to proceed.</p></div><div class="card"><h3>Local coverage</h3><p>Based in Guildford and covering {escape(location_name)} and surrounding Surrey towns and villages.</p></div></div></div></section>
<section class="review-section" id="reviews"><div class="wrap"><div class="reviewbox">{reviews_html}</div></div></section>
<section id="areas"><div class="wrap"><div class="intro"><h2>Areas I cover near {escape(location_name)}</h2><p>I also cover nearby areas across Surrey. Use the links below for local service information.</p></div><div class="area-links">{related}</div></div></section>
<section class="section-pale"><div class="wrap"><div class="intro"><h2>Frequently asked questions</h2></div><div class="faq-grid">{faq_html}</div></div></section>
<section class="cta-blue"><div class="wrap"><div><h2>Need a plumber in {escape(location_name)}?</h2><p>Send your postcode, a short description and photos if useful, or call me directly.</p></div><div class="actions"><a class="btn white" href="tel:{escape(COMPANY_PHONE_TEL)}">Call Nigel</a><a class="btn white" href="/request-quote">Get a Quote</a></div></div></section>
<footer><div class="wrap foot"><div><strong>Nigel Harvey Plumbing</strong><br>Nigel Harvey Ltd · Guildford, Surrey</div><div>{escape(COMPANY_PHONE)}<br>{escape(COMPANY_EMAIL)}</div></div></footer><a class="mobile-call" href="tel:{escape(COMPANY_PHONE_TEL)}">Call Nigel · {escape(COMPANY_PHONE)}</a></body></html>"""


def render_service_page(service: dict, logo_html: str, request: Request | None = None, *, absolute_url) -> str:
    service_links = ''.join(f'<a href="/{escape(item["slug"])}">{escape(item["title"])}</a>' for item in SERVICE_PAGES if item['slug'] != service['slug'])
    location_links = ''.join(f'<a href="/plumber-{escape(item["slug"])}">Plumber in {escape(item["name"])}</a>' for item in LOCATION_PAGES)
    canonical = absolute_url(f"/{service['slug']}", request)
    breadcrumb_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": absolute_url("/", request)},
            {"@type": "ListItem", "position": 2, "name": service["title"], "item": canonical},
        ],
    }, ensure_ascii=False)
    service_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "Service",
        "name": service["title"],
        "serviceType": service["heading"],
        "provider": {"@type": "Plumber", "name": COMPANY_NAME, "telephone": COMPANY_PHONE},
        "areaServed": [item["name"] for item in LOCATION_PAGES] + ["Surrey"],
        "url": canonical,
        "description": service["meta"],
    }, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="en-GB"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{escape(service['title'])} | Nigel Harvey Ltd</title><meta name="description" content="{escape(service['meta'])}"><meta name="keywords" content="{escape(service['keywords'])}"><link rel="canonical" href="{escape(canonical)}"><script type="application/ld+json">{breadcrumb_schema}</script><script type="application/ld+json">{service_schema}</script><style>{SEO_CSS}</style></head>
<body><div class="top"><div class="wrap nav"><div class="brand">Nigel Harvey Ltd<small>{escape(service['title'])}</small></div><div class="nav-actions"><a class="btn btn-light" href="tel:{escape(COMPANY_PHONE_TEL)}">Call Nigel</a><a class="btn btn-primary" href="/request-quote">Request a Quote</a><a class="btn btn-light" href="/">Home</a></div></div></div>
<main>
<div class="wrap hero"><div class="hero-card"><div>{logo_html}</div><div class="eyebrow">Surrey plumbing service</div><h1>{escape(service['heading'])}</h1><p class="lead">{escape(service['intro'])}</p><div class="nav-actions"><a class="btn btn-green" href="tel:{escape(COMPANY_PHONE_TEL)}">Call {escape(COMPANY_PHONE)}</a><a class="btn btn-primary" href="/request-quote">Request a Quote</a></div></div></div>
<div class="wrap section"><h2>What to tell Nigel</h2><p>{escape(service['body'])}</p><div class="grid3"><div class="card item"><h3>Where is the job?</h3><p>Send the postcode so Nigel can confirm whether the location is in his service area.</p></div><div class="card item"><h3>What is happening?</h3><p>Describe the fixture or pipework and whether this is a repair or planned installation.</p></div><div class="card item"><h3>How to get in touch</h3><p>Call for a pressing problem or use the quote form for planned work. You deal directly with Nigel.</p></div></div></div>
<div class="wrap section"><h2>Areas covered for {escape(service['heading']).lower()}</h2><p>We also cover nearby towns for customers searching for this service in Surrey.</p><div class="pill-links">{location_links}</div></div>
<div class="wrap section"><h2>Related plumbing services</h2><div class="pill-links">{service_links}</div></div>
<div class="wrap section"><h2>Frequently asked questions</h2><div class="faq-grid"><div class="card faq"><h3>How do I check whether you cover my address?</h3><p>Send your postcode and a short description. Nigel can confirm the location before arranging any work.</p></div><div class="card faq"><h3>Can I request a quote online?</h3><p>Yes. Send your details through the online quote form. Submission does not confirm a booking.</p></div><div class="card faq"><h3>What if the problem is urgent?</h3><p>Call Nigel to discuss the issue and availability. Isolate an active leak if it is safe to do so.</p></div></div></div>
<div class="wrap"><div class="hero-card cta"><div><h2 style="margin:0 0 8px">Need help with {escape(service['heading']).lower()}?</h2><div style="color:var(--muted)">Call Nigel or send your job details online to discuss the next step.</div></div><div class="nav-actions"><a class="btn btn-green" href="tel:{escape(COMPANY_PHONE_TEL)}">Call Nigel</a><a class="btn btn-primary" href="/request-quote">Request a Quote</a></div></div></div>
<div class="footer"><div class="wrap footer-inner"><div><strong>Nigel Harvey Ltd</strong><br>Plumbing services in Surrey</div><div>{escape(COMPANY_PHONE)}<br>{escape(COMPANY_EMAIL)}<br>Guildford, Surrey and surrounding areas</div></div></div><a href="tel:{escape(COMPANY_PHONE_TEL)}" class="sticky-call">📞 Call Now: {escape(COMPANY_PHONE)}</a></body></html>"""


LOCAL_SERVICE_PAGES = [
    {
        "slug": "emergency-plumber",
        "title": "Emergency Plumber",
        "heading": "Emergency Plumber in {area}",
        "intro": "Need an emergency plumber in {area}? Nigel Harvey Ltd provides fast local help for urgent leaks, burst pipes, overflowing toilets, faulty taps and other plumbing problems that need sorting quickly.",
        "service": "emergency plumbing",
        "keywords": "emergency plumber {area}, urgent plumber {area}, plumber {area}",
        "problems": ["Burst pipes", "Leaks", "Overflowing toilets", "Faulty taps", "Urgent pipework repairs"],
    },
    {
        "slug": "toilet-repair",
        "title": "Toilet Repair",
        "heading": "Toilet Repairs in {area}",
        "intro": "We provide toilet repairs in {area}, including leaks, flushing problems, running toilets, blockages, faulty cisterns and replacement parts.",
        "service": "toilet repair",
        "keywords": "toilet repair {area}, toilet plumber {area}, plumber {area}",
        "problems": ["Toilets not flushing", "Running toilets", "Leaking toilets", "Blocked toilets", "Faulty cistern parts"],
    },
    {
        "slug": "leak-repair",
        "title": "Leak Repair",
        "heading": "Leak Repairs in {area}",
        "intro": "Nigel Harvey Ltd helps with leak repairs in {area}, from visible pipe leaks and dripping fittings to hidden plumbing leaks that need careful investigation.",
        "service": "leak repair",
        "keywords": "leak repair {area}, leaking pipe {area}, plumber {area}",
        "problems": ["Leaking pipes", "Dripping fittings", "Water damage concerns", "Hidden leaks", "Bathroom and kitchen leaks"],
    },
    {
        "slug": "bathroom-plumbing",
        "title": "Bathroom Plumbing",
        "heading": "Bathroom Plumbing in {area}",
        "intro": "We provide bathroom plumbing in {area}, including pipework changes, toilet fitting, basin plumbing, shower connections and bathroom repair work.",
        "service": "bathroom plumbing",
        "keywords": "bathroom plumbing {area}, bathroom plumber {area}, plumber {area}",
        "problems": ["Toilet fitting", "Basin plumbing", "Shower pipework", "Bath connections", "Bathroom leaks"],
    },
    {
        "slug": "blocked-drains",
        "title": "Blocked Drains",
        "heading": "Blocked Drains and Waste Pipes in {area}",
        "intro": "We help with blocked drains and waste pipe issues in {area}, including slow-draining sinks, blocked wastes, toilet blockages and drainage-related plumbing problems.",
        "service": "blocked drains and waste pipes",
        "keywords": "blocked drains {area}, blocked sink {area}, plumber {area}",
        "problems": ["Blocked sinks", "Slow drains", "Blocked wastes", "Toilet blockages", "Kitchen and bathroom drainage issues"],
    },
]


def render_local_service_location_page(service: dict, location: dict, logo_html: str, request: Request | None = None, *, absolute_url) -> str:
    area = location["name"]
    area_slug = location["slug"]
    service_slug = service["slug"]
    title = service["title"]
    heading = service["heading"].format(area=area)
    intro = service["intro"].format(area=area)
    keywords = service["keywords"].format(area=area)
    canonical = absolute_url(f"/{service_slug}-{area_slug}", request)
    problem_items = "".join(f"<li>{escape(item)}</li>" for item in service["problems"])
    related_locations = "".join(
        f'<a href="/{escape(service_slug)}-{escape(item["slug"])}">{escape(title)} in {escape(item["name"])}</a>'
        for item in LOCATION_PAGES if item["slug"] != area_slug
    )
    related_services = "".join(
        f'<a href="/{escape(item["slug"])}-{escape(area_slug)}">{escape(item["title"])} in {escape(area)}</a>'
        for item in LOCAL_SERVICE_PAGES if item["slug"] != service_slug
    )
    breadcrumb_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": absolute_url("/", request)},
            {"@type": "ListItem", "position": 2, "name": f"{title} in {area}", "item": canonical},
        ],
    }, ensure_ascii=False)
    service_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "Service",
        "name": f"{title} in {area}",
        "provider": {
            "@type": "Plumber",
            "name": COMPANY_NAME,
            "telephone": COMPANY_PHONE,
            "email": COMPANY_EMAIL,
        },
        "areaServed": [area, "Surrey"],
        "serviceType": service["service"],
        "url": canonical,
        "description": intro,
    }, ensure_ascii=False)

    return f"""<!doctype html>
<html lang="en-GB"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} in {escape(area)} | Nigel Harvey Ltd</title>
<meta name="description" content="{escape(intro)} Call Nigel Harvey Ltd on {escape(COMPANY_PHONE)} for reliable local plumbing help.">
<meta name="keywords" content="{escape(keywords)}">
<link rel="canonical" href="{escape(canonical)}">
<script type="application/ld+json">{breadcrumb_schema}</script>
<script type="application/ld+json">{service_schema}</script>
<style>{SEO_CSS}</style></head>
<body>
<div class="top"><div class="wrap nav"><div class="brand">Nigel Harvey Ltd<small>{escape(title)} in {escape(area)}</small></div><div class="nav-actions"><a class="btn btn-light" href="tel:{escape(COMPANY_PHONE_TEL)}">Call Now</a><a class="btn btn-primary" href="/request-quote">Get a Fast Quote</a><a class="btn btn-light" href="/">Home</a></div></div></div>
<main>
<div class="wrap hero"><div class="hero-card"><div>{logo_html}</div><div class="eyebrow">Local plumbing help in {escape(area)}</div><h1>{escape(heading)}</h1><p class="lead">{escape(intro)}</p><div class="nav-actions"><a class="btn btn-green" href="tel:{escape(COMPANY_PHONE_TEL)}">Call Now: {escape(COMPANY_PHONE)}</a><a class="btn btn-primary" href="/request-quote">Request a Quote</a></div></div></div>

<div class="wrap section"><h2>{escape(title)} Services in {escape(area)}</h2><p>If you are looking for {escape(service["service"])} in {escape(area)}, we provide practical, reliable help for local homes, landlords and small businesses.</p><ul class="list">{problem_items}</ul></div>

<div class="wrap section"><div class="grid3">
<div class="card item"><h3>Fast Local Response</h3><p>We cover {escape(area)} and nearby Surrey areas for urgent and planned plumbing work.</p></div>
<div class="card item"><h3>Clear Communication</h3><p>You get straightforward advice and a clear explanation of the work needed.</p></div>
<div class="card item"><h3>Trusted Local Plumber</h3><p>Nigel Harvey Ltd provides dependable domestic plumbing services across Guildford and Surrey.</p></div>
</div></div>

<div class="wrap section"><h2>Other Plumbing Services in {escape(area)}</h2><div class="pill-links">{related_services}</div></div>
<div class="wrap section"><h2>Nearby Areas We Cover</h2><div class="pill-links">{related_locations}</div></div>

<div class="wrap cta card"><div><h2>Need {escape(title.lower())} in {escape(area)}?</h2><p>Call now or request a fast quote online.</p></div><div class="nav-actions"><a class="btn btn-green" href="tel:{escape(COMPANY_PHONE_TEL)}">Call Now: {escape(COMPANY_PHONE)}</a><a class="btn btn-primary" href="/request-quote">Get a Fast Quote</a></div></div>
</main>
<div class="footer"><div class="wrap footer-inner"><div><strong>Nigel Harvey Ltd</strong><br>Plumbing services in Surrey</div><div>{escape(COMPANY_PHONE)}<br>{escape(COMPANY_EMAIL)}<br>{escape(area)}, Surrey and surrounding areas</div></div></div>
<a href="tel:{escape(COMPANY_PHONE_TEL)}" class="sticky-call">📞 Call Now: {escape(COMPANY_PHONE)}</a>
</body></html>"""

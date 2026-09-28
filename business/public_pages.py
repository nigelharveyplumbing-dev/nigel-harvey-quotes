"""Public SEO page content and renderers. Routes and authentication stay in app.py."""

import json
from html import escape
from pathlib import Path
from fastapi import Request
from business.config import (COMPANY_NAME, COMPANY_EMAIL, COMPANY_PHONE, COMPANY_PHONE_TEL, GOOGLE_BUSINESS_PROFILE_URL, GOOGLE_RATING_VALUE, GOOGLE_REVIEW_COUNT, GOOGLE_REVIEWS_URL, GOOGLE_REVIEW_1_TEXT, GOOGLE_REVIEW_1_AUTHOR, GOOGLE_REVIEW_2_TEXT, GOOGLE_REVIEW_2_AUTHOR, GOOGLE_REVIEW_3_TEXT, GOOGLE_REVIEW_3_AUTHOR)
from business.public_layout import render_shared_public_page

def build_homepage_faq_schema() -> str:
    faq_items = [
        {
            "@type": "Question",
            "name": "What plumbing jobs can I ask about?",
            "acceptedAnswer": {
                "@type": "Answer",
                "text": "Leaks, taps, toilets, bathrooms, showers, radiators, valves, pipework and other domestic plumbing work. Describe the job so Nigel can say whether it fits."
            }
        },
        {
            "@type": "Question",
            "name": "Can I call about a plumbing problem overnight?",
            "acceptedAnswer": {
                "@type": "Answer",
                "text": "Yes. Nigel takes plumbing calls 24 hours a day, including overnight. Call to explain the issue, confirm coverage and discuss what help is available. Timing depends on the problem and location."
            }
        },
        {
            "@type": "Question",
            "name": "Can I send photos of the problem?",
            "acceptedAnswer": {
                "@type": "Answer",
                "text": "Yes. You can add photos in WhatsApp after opening the conversation. Please do not send a video unless Nigel asks for one."
            }
        },
        {
            "@type": "Question",
            "name": "Do you work outside Guildford?",
            "acceptedAnswer": {
                "@type": "Answer",
                "text": "Yes, the website covers Aldershot, Camberley, Epsom, Leatherhead, Farnborough and other surrounding areas. Send a postcode so Nigel can confirm the location."
            }
        },
        {
            "@type": "Question",
            "name": "What happens after I request a quote?",
            "acceptedAnswer": {
                "@type": "Answer",
                "text": "Your details enter Nigel’s enquiries list. He can review them and contact you using your preferred method to discuss the next step. Submission does not confirm a booking."
            }
        },
    ]
    return json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": faq_items}, ensure_ascii=False)


def build_homepage_business_schema(canonical_home: str) -> str:
    return json.dumps(public_business_entity(canonical_home), ensure_ascii=False)


def public_business_entity(canonical_home: str) -> dict:
    """One service-area business identity across the public website.

    The registered office is used for company paperwork, not advertised as a
    customer-facing plumbing premises. Google reviews remain visible in the
    page UI but are not marked up as self-serving ratings.
    """
    return {
        "@context": "https://schema.org",
        "@type": "Plumber",
        "@id": canonical_home + "#business",
        "name": "Nigel Harvey Plumbing",
        "legalName": COMPANY_NAME,
        "telephone": "+44" + COMPANY_PHONE_TEL[1:],
        "email": COMPANY_EMAIL,
        "location": {"@type": "Place", "name": "Guildford, Surrey"},
        "openingHoursSpecification": {"@type": "OpeningHoursSpecification", "dayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"], "opens": "00:00", "closes": "23:59"},
        "areaServed": ["Guildford", "Woking", "Farnham", "Godalming", "Camberley", "Aldershot", "Leatherhead", "Epsom", "Farnborough", "West Horsley", "Weybridge", "Cobham", "Surrey"],
        "url": canonical_home,
        "hasMap": GOOGLE_BUSINESS_PROFILE_URL,
        "sameAs": [GOOGLE_BUSINESS_PROFILE_URL],
        "description": "Nigel Harvey Plumbing is a Guildford-based domestic plumbing service operated by Nigel Harvey, covering Surrey and nearby areas for general plumbing, bathrooms, leaks, pipework and repairs, with 24-hour availability for plumbing enquiries.",
    }


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
    {"slug":"emergency-plumber-surrey","title":"24-Hour Plumber in Surrey","meta":"Need urgent plumbing help in Surrey? Call Nigel 24 hours a day, including overnight, to explain the problem, confirm coverage and discuss available help.","heading":"24-Hour Plumbing Availability in Surrey","intro":"Water escaping from a pipe or fitting, a failed toilet or another pressing plumbing issue? Nigel takes plumbing calls 24 hours a day, including overnight. Call to describe what is happening, confirm coverage and discuss what help is available. For a significant leak, isolate the water if it is safe to do so.","body":"Explain where the problem is, whether water is still escaping and what you have safely been able to isolate. Your postcode helps Nigel confirm whether he can attend. The overnight phone line is available, but timing and the work that can be arranged depend on the issue and location. An online form can provide details, but a call is better for a time-sensitive problem.","keywords":"urgent plumber Surrey, plumbing leak Surrey, burst pipe Guildford"},
    {"slug":"general-plumbing-surrey","title":"General Plumbing & Small Repairs in Surrey","meta":"Leaking taps, running toilets, wastes, outside taps or minor pipework repairs? Tell Guildford-based Nigel what needs fixing and where you are for a clear next step.","heading":"General Plumbing in Surrey","intro":"Nigel handles everyday domestic plumbing jobs, from tap and toilet repairs to sink fittings, wastes, outside taps, leaks and pipework alterations around Guildford and nearby towns.","body":"A useful enquiry includes the fixture involved, what is going wrong and whether there is an active leak. You can send the details and your postcode, then discuss the work and any relevant charges with Nigel before proceeding.","keywords":"general plumbing Surrey, minor plumbing repairs, tap and toilet repairs"},
    {"slug":"bathroom-plumbing-surrey","title":"Bathroom Plumbing in Surrey","meta":"Bathroom and shower plumbing around Guildford and nearby areas, including sanitaryware connections, pipework changes and first or second fix work.","heading":"Bathroom Plumbing in Surrey","intro":"For bathroom plumbing, Nigel can discuss sanitaryware connections, shower pipework and first or second fix plumbing as part of a planned refurbishment or smaller update.","body":"Tell Nigel which fittings you want to replace, what is staying in place and whether the layout changes. These details help distinguish a straightforward replacement from new pipework or other preparation before a quote is agreed.","keywords":"bathroom plumbing Surrey, shower plumbing Guildford, sanitaryware plumbing"},
    {"slug":"heating-repairs-surrey","title":"Radiators & Heating Plumbing in Surrey","meta":"Radiator, valve, towel radiator and heating pipework plumbing around Guildford and nearby Surrey areas. Discuss the work with Nigel.","heading":"Radiators & Heating Plumbing in Surrey","intro":"Nigel can help with plumbing-related heating work such as radiators, towel radiators, valves and associated pipework. Describe which rooms and fittings are affected.","body":"For a radiator enquiry, say whether the issue is a valve, a leak or a planned replacement, and whether the pipework position will change. Nigel can discuss the practical plumbing work required.","keywords":"radiator plumber Surrey, radiator valves Guildford, heating pipework"},
]

PRIMARY_LOCATION_NOTES = {
    "aldershot": {
        "intro": "For a leaking pipe, running toilet or planned bathroom plumbing in Aldershot, send Nigel a short description and the job postcode. He is based in Guildford and can confirm coverage and the next step before you arrange work.",
        "detail": "Tell Nigel which fixture is affected, whether water is still escaping and whether you can safely isolate it. Photos can help with a tap, toilet or visible pipework problem; use WhatsApp after making contact if you have them.",
        "nearby": "Camberley, Farnborough and surrounding areas",
        "related": ("/leak-repair-aldershot", "Leak repair in Aldershot"),
    },
    "camberley": {
        "intro": "Need help with a leak, toilet or bathroom fitting in Camberley? Describe what you can see and send the postcode so Guildford-based Nigel can discuss the work and confirm whether he can attend your address.",
        "detail": "For a leak, note whether it is at a pipe, tap, toilet or waste, whether it happens continuously and whether you can safely turn off the water. Call for an active leak rather than waiting for an online reply.",
        "nearby": "Aldershot, Farnborough and nearby Surrey areas",
        "related": ("/leak-repair-camberley", "Leak repair in Camberley"),
    },
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
    coverage_label = "Hampshire enquiries" if slug == "farnborough" else "Surrey coverage"
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
    if primary_note and primary_note.get("related"):
        href, label = primary_note["related"]
        primary_details_html += (f'<section><div class="wrap"><p>Looking for a specific repair? '
                                 f'<a href="{escape(href, quote=True)}">{escape(label)}</a> explains what details to send.</p></div></section>')
    location_intro = primary_note["intro"] if primary_note else (
        f"Reliable domestic plumbing for leaks, taps, toilets, bathrooms, showers, radiators and pipework in {location_name} and surrounding Surrey areas. From first enquiry to finished job, you deal directly with me, Nigel."
    )

    title = (
        "Plumber in Guildford | Local Repairs | Nigel Harvey Plumbing"
        if is_guildford else
        f"Plumber in {location_name} | Reliable Local Plumbing Services | Nigel Harvey Ltd"
    )
    meta_description = (
        "Need a Guildford plumber for leaks, toilets, taps or bathrooms? Call Nigel 24 hours for an urgent problem, or send the job details for a clear quote."
        if is_guildford else
        f"Looking for a plumber in {location_name}? Nigel Harvey Ltd provides leaks, bathroom plumbing and general plumbing services in {location_name} and surrounding Surrey areas."
    )
    if slug == "farnborough":
        meta_description = ("Domestic plumbing in Farnborough for taps, toilets, showers, radiators and pipework. "
                            "Contact Guildford-based Nigel with the job details and postcode.")
    elif slug == "aldershot":
        title = "Plumber in Aldershot | Repairs & Bathrooms | Nigel Harvey Plumbing"
        meta_description = ("A leaking tap, toilet fault or bathroom plumbing job in Aldershot? "
                            "Tell Guildford-based Nigel what is happening and send your postcode to discuss a quote.")
    elif slug == "camberley":
        title = "Plumber in Camberley | Leaks & Repairs | Nigel Harvey Plumbing"
        meta_description = ("Need plumbing help in Camberley? Describe a leak, tap, toilet or bathroom job "
                            "and send your postcode to Guildford-based Nigel for the next step.")

    breadcrumb_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": absolute_url("/", request)},
            {"@type": "ListItem", "position": 2, "name": f"Plumber in {location_name}", "item": canonical},
        ],
    }, ensure_ascii=False)
    local_schema = build_homepage_business_schema(absolute_url("/", request))


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
        return render_shared_public_page(f"""<!doctype html>
<html lang="en-GB"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title><meta name="description" content="{escape(meta_description)}"><meta name="robots" content="index,follow,max-image-preview:large"><link rel="canonical" href="{escape(canonical)}">
<meta property="og:type" content="website"><meta property="og:title" content="{escape(title)}"><meta property="og:description" content="{escape(meta_description)}"><meta property="og:url" content="{escape(canonical)}">
<script type="application/ld+json">{breadcrumb_schema}</script><script type="application/ld+json">{local_schema}</script><script type="application/ld+json">{faq_schema}</script></head><body>
<div class="topbar"><div class="wrap"><span>Local plumber serving Guildford &amp; Surrey</span><span>Call Nigel: {escape(COMPANY_PHONE)} &nbsp; · &nbsp; {escape(COMPANY_EMAIL)}</span></div></div>
<header class="site-header"><div class="wrap site-nav"><div class="brand">Nigel Harvey <small>PLUMBING</small></div><div class="navlinks"><a href="#services">Services</a><a href="#about">About</a><a href="#reviews">Reviews</a><a href="#areas">Areas</a><a class="btn" href="/request-quote">Get a Quote</a></div></div></header>
<section class="guildford-hero"><div class="wrap"><div class="hero-copy"><div class="eyebrow">Nigel Harvey Plumbing · Guildford</div><h1>Plumber in Guildford</h1><p>Local domestic plumbing for leaks, taps, toilets, bathrooms, showers, radiators and pipework. From first enquiry to finished job, you deal directly with me, Nigel.</p><div class="actions"><a class="btn" href="/request-quote">Get a Quote</a><a class="btn white" href="tel:{escape(COMPANY_PHONE_TEL)}">Call {escape(COMPANY_PHONE)}</a></div></div></div></section>
<div class="trust"><div class="wrap trustgrid"><div><strong>Local &amp; independent</strong><span>Based in Guildford</span></div><div><strong>Clear communication</strong><span>Deal directly with Nigel</span></div><div><strong>Clear quotes</strong><span>Work &amp; charges explained</span></div><div><strong>Surrey coverage</strong><span>Guildford &amp; nearby areas</span></div></div></div>
<section id="services"><div class="wrap"><div class="intro"><h2>Plumbing services in Guildford</h2><p>Whether you have a leaking fitting, a toilet that is not working properly, a radiator or valve problem, or planned bathroom plumbing, send the details directly to Nigel. Photos and a short description can help establish what may be required before the visit.</p></div><div class="service-links">{local_service_links}</div></div></section>
<section class="section-pale"><div class="wrap"><div class="intro"><h2>Domestic plumbing work I can help with</h2><p>Practical plumbing repairs and planned work for homes and landlords across Guildford.</p></div><div class="cards"><div class="card"><h3>Leaks, taps &amp; toilets</h3><p>Repairs to leaking pipework and fittings, taps, toilet mechanisms, wastes, traps and other everyday plumbing problems.</p></div><div class="card"><h3>Bathrooms &amp; showers</h3><p>Bathroom plumbing, sanitaryware connections, shower pipework, first and second fix work and practical plumbing alterations.</p></div><div class="card"><h3>Radiators &amp; pipework</h3><p>Radiators, TRVs and valves, towel radiators, pipework alterations and plumbing-related heating work.</p></div></div></div></section>
<section><div class="wrap"><div class="intro"><h2>Common Guildford plumbing enquiries</h2><p>Small repairs matter too. If a tap keeps dripping, a toilet runs after flushing, a waste leaks under the sink or a radiator valve needs attention, tell me what you can see and whether the water can be safely isolated.</p><p>For a specific problem, read about <a href="/leak-repair-guildford">leak repairs</a> or <a href="/toilet-repair-guildford">toilet repairs in Guildford</a>. For a wider mix of minor jobs, see <a href="/general-plumbing-surrey">general plumbing in Surrey</a>. For an urgent issue, see the <a href="/emergency-plumber-surrey">24-hour plumbing information</a> and call rather than waiting for an online reply.</p><p>I am based in Guildford; if you are in <a href="/plumber-merrow">Merrow</a>, <a href="/plumber-burpham">Burpham</a>, <a href="/plumber-worplesdon">Worplesdon</a> or West Horsley, send the postcode with your enquiry.</p></div></div></section>
<section class="section-dark" id="about"><div class="wrap"><div class="intro"><h2>A local Guildford plumber you deal with directly</h2><p>Nigel Harvey Plumbing is based in Guildford. When you enquire, you deal directly with Nigel rather than a call centre or salesperson. The aim is straightforward communication, a clear quotation and a practical plan for getting the work completed.</p></div><div class="cards"><div class="card"><h3>Direct contact</h3><p>Speak directly with the person who will be carrying out the plumbing work.</p></div><div class="card"><h3>Clear quotations</h3><p>Work and relevant charges can be set out before you decide whether to proceed.</p></div><div class="card"><h3>Local coverage</h3><p>Based in Guildford and covering surrounding towns and villages across Surrey.</p></div></div></div></section>
<section class="review-section" id="reviews"><div class="wrap"><div class="intro"><h2>Customer reviews</h2><p>Recent independent Google feedback from plumbing customers.</p></div><div class="reviewbox">{reviews_html}</div></div></section>
<section id="areas"><div class="wrap"><div class="intro"><h2>Areas near Guildford</h2><p>As well as Guildford itself, plumbing work is available across nearby Surrey areas. Use the local pages below for more information.</p></div><div class="area-links">{related}</div></div></section>
<section class="section-pale"><div class="wrap"><div class="intro"><h2>Frequently asked questions</h2></div><div class="faq-grid">{faq_html}</div></div></section>
<section class="cta-blue"><div class="wrap"><div><h2>Need a plumber in Guildford?</h2><p>Send your postcode, a short description and photos if useful, or call Nigel directly.</p></div><div class="actions"><a class="btn white" href="tel:{escape(COMPANY_PHONE_TEL)}">Call Nigel</a><a class="btn white" href="/request-quote">Get a Quote</a></div></div></section>
<footer><div class="wrap foot"><div><strong>Nigel Harvey Plumbing</strong><br>Nigel Harvey Ltd · Guildford, Surrey</div><div>{escape(COMPANY_PHONE)}<br>{escape(COMPANY_EMAIL)}</div></div></footer><a class="mobile-call" href="tel:{escape(COMPANY_PHONE_TEL)}">Call Nigel · {escape(COMPANY_PHONE)}</a></body></html>""")

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
    return render_shared_public_page(f"""<!doctype html>
<html lang="en-GB"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title><meta name="description" content="{escape(meta_description)}"><meta name="robots" content="index,follow,max-image-preview:large"><link rel="canonical" href="{escape(canonical)}">
<meta property="og:type" content="website"><meta property="og:title" content="{escape(title)}"><meta property="og:description" content="{escape(meta_description)}"><meta property="og:url" content="{escape(canonical)}">
<script type="application/ld+json">{breadcrumb_schema}</script><script type="application/ld+json">{local_schema}</script><script type="application/ld+json">{faq_schema}</script></head><body>
<div class="topbar"><div class="wrap"><span>Local plumber serving {escape(location_name)} &amp; Surrey</span><span>Call Nigel: {escape(COMPANY_PHONE)} &nbsp; · &nbsp; {escape(COMPANY_EMAIL)}</span></div></div>
<header class="site-header"><div class="wrap site-nav"><a class="brand" href="/">Nigel Harvey <small>PLUMBING</small></a><div class="navlinks"><a href="#services">Services</a><a href="#about">About</a><a href="#reviews">Reviews</a><a href="#areas">Areas</a><a class="btn" href="/request-quote">Get a Quote</a></div></div></header>
<section class="guildford-hero"><div class="wrap"><div class="hero-copy"><div class="eyebrow">Nigel Harvey Plumbing · {escape(location_name)}</div><h1>Plumber in {escape(location_name)}</h1><p>{escape(location_intro)}</p><div class="actions"><a class="btn" href="/request-quote">Get a Quote</a><a class="btn white" href="tel:{escape(COMPANY_PHONE_TEL)}">Call {escape(COMPANY_PHONE)}</a></div></div></div></section>
<div class="trust"><div class="wrap trustgrid"><div><strong>Local &amp; independent</strong><span>Based in Guildford</span></div><div><strong>Clear communication</strong><span>Deal directly with me</span></div><div><strong>Clear quotes</strong><span>Work &amp; charges explained</span></div><div><strong>{coverage_label}</strong><span>{escape(location_name)} &amp; nearby areas</span></div></div></div>
<section id="services"><div class="wrap"><div class="intro"><h2>Plumbing services in {escape(location_name)}</h2><p>Whether you have a leaking fitting, a toilet that is not working properly, a radiator or valve problem, or planned bathroom plumbing, send the details directly to me. Photos and a short description can help me establish what may be required before the visit.</p></div><div class="service-links">{local_service_links}</div></div></section>
{primary_details_html}
<section class="section-pale"><div class="wrap"><div class="intro"><h2>Domestic plumbing work I can help with</h2><p>I provide practical domestic plumbing services across {escape(location_name)} and nearby Surrey areas.</p></div><div class="cards"><div class="card"><h3>Leaks, taps &amp; toilets</h3><p>Repairs to leaking pipework and fittings, taps, toilet mechanisms, wastes, traps and other everyday plumbing problems.</p></div><div class="card"><h3>Bathrooms &amp; showers</h3><p>Bathroom plumbing, sanitaryware connections, shower pipework, first and second fix work and practical plumbing alterations.</p></div><div class="card"><h3>Radiators &amp; pipework</h3><p>Radiators, TRVs and valves, towel radiators, pipework alterations and plumbing-related heating work.</p></div></div></div></section>
<section id="about"><div class="wrap"><div class="intro left"><h2>A local plumber you deal with directly</h2><p>When you contact Nigel Harvey Plumbing, you deal directly with me, Nigel — not a call centre or salesperson. I am based in Guildford and cover {escape(location_name)} and surrounding Surrey areas.</p></div><div class="cards"><div class="card"><h3>Direct contact</h3><p>Speak directly with me, the person carrying out the plumbing work.</p></div><div class="card"><h3>Clear quotations</h3><p>I set out the work and relevant charges before you decide whether to proceed.</p></div><div class="card"><h3>Local coverage</h3><p>Based in Guildford and covering {escape(location_name)} and surrounding Surrey towns and villages.</p></div></div></div></section>
<section class="review-section" id="reviews"><div class="wrap"><div class="reviewbox">{reviews_html}</div></div></section>
<section id="areas"><div class="wrap"><div class="intro"><h2>Areas I cover near {escape(location_name)}</h2><p>I also cover nearby areas across Surrey. Use the links below for local service information.</p></div><div class="area-links">{related}</div></div></section>
<section class="section-pale"><div class="wrap"><div class="intro"><h2>Frequently asked questions</h2></div><div class="faq-grid">{faq_html}</div></div></section>
<section class="cta-blue"><div class="wrap"><div><h2>Need a plumber in {escape(location_name)}?</h2><p>Send your postcode, a short description and photos if useful, or call me directly.</p></div><div class="actions"><a class="btn white" href="tel:{escape(COMPANY_PHONE_TEL)}">Call Nigel</a><a class="btn white" href="/request-quote">Get a Quote</a></div></div></section>
<footer><div class="wrap foot"><div><strong>Nigel Harvey Plumbing</strong><br>Nigel Harvey Ltd · Guildford, Surrey</div><div>{escape(COMPANY_PHONE)}<br>{escape(COMPANY_EMAIL)}</div></div></footer><a class="mobile-call" href="tel:{escape(COMPANY_PHONE_TEL)}">Call Nigel · {escape(COMPANY_PHONE)}</a></body></html>""")


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
        "provider": {"@id": absolute_url("/", request) + "#business"},
        "areaServed": [item["name"] for item in LOCATION_PAGES] + ["Surrey"],
        "url": canonical,
        "description": service["meta"],
    }, ensure_ascii=False)
    general_detail = (
        '<div class="wrap section"><h2>Everyday repairs and small plumbing jobs</h2>'
        '<p>A dripping tap, toilet that keeps filling, leaking waste or outside tap may be a modest job, '
        'but it still helps to know the fitting, where the water is coming from and whether you can isolate it safely. '
        'Nigel can discuss the repair and any parts or pipework changes before you decide what to do.</p>'
        '<p>Based in Guildford? See the <a href="/plumber-guildford">Guildford plumber page</a> for local coverage. '
        'For a visible leak, the <a href="/leak-repair-camberley">Camberley</a> and '
        '<a href="/leak-repair-farnham">Farnham leak repair pages</a> explain what to describe.</p></div>'
    ) if service["slug"] == "general-plumbing-surrey" else ""
    urgent_detail = (
        '<div class="wrap section"><h2>Calling about an urgent plumbing problem</h2>'
        '<p>Call and tell Nigel what is leaking or not working, whether water is still escaping, what you can safely isolate and the job postcode. '
        'The phone is answered for plumbing enquiries 24 hours a day, including overnight, but attendance and timing depend on the problem and location.</p>'
        '<p>Nigel is based in <a href="/plumber-guildford">Guildford</a> and also receives urgent enquiries from West Horsley, '
        '<a href="/plumber-aldershot">Aldershot</a>, <a href="/plumber-camberley">Camberley</a> and nearby Surrey areas. '
        'For Guildford-specific information, see <a href="/emergency-plumber-guildford">urgent plumbing in Guildford</a>.</p></div>'
    ) if service["slug"] == "emergency-plumber-surrey" else ""
    return render_shared_public_page(f"""<!doctype html>
<html lang="en-GB"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{escape(service['title'])} | Nigel Harvey Plumbing</title><meta name="description" content="{escape(service['meta'])}"><meta name="keywords" content="{escape(service['keywords'])}"><link rel="canonical" href="{escape(canonical)}"><meta property="og:type" content="website"><meta property="og:title" content="{escape(service['title'])} | Nigel Harvey Plumbing"><meta property="og:description" content="{escape(service['meta'])}"><meta property="og:url" content="{escape(canonical)}"><script type="application/ld+json">{breadcrumb_schema}</script><script type="application/ld+json">{service_schema}</script></head>
<body><div class="top"><div class="wrap nav"><div class="brand">Nigel Harvey Ltd<small>{escape(service['title'])}</small></div><div class="nav-actions"><a class="btn btn-light" href="tel:{escape(COMPANY_PHONE_TEL)}">Call Nigel</a><a class="btn btn-primary" href="/request-quote">Request a Quote</a><a class="btn btn-light" href="/">Home</a></div></div></div>
<main>
<div class="wrap hero"><div class="hero-card"><div>{logo_html}</div><div class="eyebrow">Surrey plumbing service</div><h1>{escape(service['heading'])}</h1><p class="lead">{escape(service['intro'])}</p><div class="nav-actions"><a class="btn btn-green" href="tel:{escape(COMPANY_PHONE_TEL)}">Call {escape(COMPANY_PHONE)}</a><a class="btn btn-primary" href="/request-quote">Request a Quote</a></div></div></div>
<div class="wrap section"><h2>What to tell Nigel</h2><p>{escape(service['body'])}</p><div class="grid3"><div class="card item"><h3>Where is the job?</h3><p>Send the postcode so Nigel can confirm whether the location is in his service area.</p></div><div class="card item"><h3>What is happening?</h3><p>Describe the fixture or pipework and whether this is a repair or planned installation.</p></div><div class="card item"><h3>How to get in touch</h3><p>Call for a pressing problem or use the quote form for planned work. You deal directly with Nigel.</p></div></div></div>
{general_detail}
{urgent_detail}
<div class="wrap section"><h2>Areas covered for {escape(service['heading']).lower()}</h2><p>We also cover nearby towns for customers searching for this service in Surrey.</p><div class="pill-links">{location_links}</div></div>
<div class="wrap section"><h2>Related plumbing services</h2><div class="pill-links">{service_links}</div></div>
<div class="wrap section"><h2>Frequently asked questions</h2><div class="faq-grid"><div class="card faq"><h3>How do I check whether you cover my address?</h3><p>Send your postcode and a short description. Nigel can confirm the location before arranging any work.</p></div><div class="card faq"><h3>Can I request a quote online?</h3><p>Yes. Send your details through the online quote form. Submission does not confirm a booking.</p></div><div class="card faq"><h3>What if the problem is urgent?</h3><p>Call Nigel to discuss the issue and availability. Isolate an active leak if it is safe to do so.</p></div></div></div>
<div class="wrap"><div class="hero-card cta"><div><h2 style="margin:0 0 8px">Need help with {escape(service['heading']).lower()}?</h2><div style="color:var(--muted)">Call Nigel or send your job details online to discuss the next step.</div></div><div class="nav-actions"><a class="btn btn-green" href="tel:{escape(COMPANY_PHONE_TEL)}">Call Nigel</a><a class="btn btn-primary" href="/request-quote">Request a Quote</a></div></div></div>
<div class="footer"><div class="wrap footer-inner"><div><strong>Nigel Harvey Ltd</strong><br>Plumbing services in Surrey</div><div>{escape(COMPANY_PHONE)}<br>{escape(COMPANY_EMAIL)}<br>Guildford, Surrey and surrounding areas</div></div></div><a href="tel:{escape(COMPANY_PHONE_TEL)}" class="sticky-call">📞 Call Now: {escape(COMPANY_PHONE)}</a></body></html>""")


LOCAL_SERVICE_PAGES = [
    {
        "slug": "emergency-plumber",
        "title": "Emergency Plumber",
        "heading": "Emergency Plumber in {area}",
        "intro": "Have an urgent leak, burst pipe or overflowing toilet in {area}? Call Nigel to describe the problem and discuss availability. If it is safe, isolate the water while you seek help.",
        "service": "emergency plumbing",
        "keywords": "emergency plumber {area}, urgent plumber {area}, plumber {area}",
        "problems": ["Burst pipes", "Leaks", "Overflowing toilets", "Faulty taps", "Urgent pipework repairs"],
    },
    {
        "slug": "toilet-repair",
        "title": "Toilet Repair",
        "heading": "Toilet Repairs in {area}",
        "intro": "Nigel provides toilet repairs in {area}, including leaks, flushing problems, running toilets, faulty cisterns and replacement parts.",
        "service": "toilet repair",
        "keywords": "toilet repair {area}, toilet plumber {area}, plumber {area}",
        "problems": ["Toilets not flushing", "Running toilets", "Leaking toilets", "Faulty cistern parts", "Replacement parts"],
    },
    {
        "slug": "leak-repair",
        "title": "Leak Repair",
        "heading": "Leak Repairs in {area}",
        "intro": "Nigel helps with leak repairs in {area}, from visible pipe leaks and dripping fittings to hidden plumbing leaks that need careful investigation.",
        "service": "leak repair",
        "keywords": "leak repair {area}, leaking pipe {area}, plumber {area}",
        "problems": ["Leaking pipes", "Dripping fittings", "Water damage concerns", "Hidden leaks", "Bathroom and kitchen leaks"],
    },
    {
        "slug": "bathroom-plumbing",
        "title": "Bathroom Plumbing",
        "heading": "Bathroom Plumbing in {area}",
        "intro": "Nigel provides bathroom plumbing in {area}, including pipework changes, toilet fitting, basin plumbing, shower connections and bathroom repair work.",
        "service": "bathroom plumbing",
        "keywords": "bathroom plumbing {area}, bathroom plumber {area}, plumber {area}",
        "problems": ["Toilet fitting", "Basin plumbing", "Shower pipework", "Bath connections", "Bathroom leaks"],
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
    priority_details = {
        ("leak-repair", "aldershot"): (
            "What to tell Nigel about a leaking pipe in Aldershot",
            "Say whether the water is coming from visible pipework, a tap, toilet, shower or waste and whether it can be isolated safely. Include the Aldershot postcode and, if useful, share a photo after making contact so Nigel can discuss the likely repair and next step."
        ),
        ("leak-repair", "camberley"): (
            "Leak repair in Camberley: what to check before calling",
            "If water is escaping, turn it off at the nearest safe valve or stopcock if you can. Tell Nigel whether the leak is at a pipe, tap, toilet, shower or waste, whether it happens continuously, and what you can see without taking fittings apart. A postcode and a photo can help him discuss the next step from his Guildford base."
        ),
        ("leak-repair", "farnham"): (
            "Describing a leak in Farnham",
            "Note where the water appears and whether the leak is constant or only when a tap, shower or appliance is used. Isolate the supply if it is safe. Send the postcode and a photo if useful so Nigel can discuss the repair and whether he can cover your address."
        ),
        ("toilet-repair", "leatherhead"): (
            "What is wrong with the toilet?",
            "A running cistern, weak flush, leak at the pan or fill valve fault can need different parts. Tell Nigel what happens when you flush, whether water is escaping and whether you can safely isolate the toilet. Include the Leatherhead postcode before arranging a visit."
        ),
    }
    detail = priority_details.get((service_slug, area_slug))
    priority_html = (f'<div class="wrap section"><h2>{escape(detail[0])}</h2><p>{escape(detail[1])}</p>'
                     '<p>For other domestic plumbing jobs, see <a href="/general-plumbing-surrey">general plumbing in Surrey</a> '
                     'or <a href="/request-quote">send the job details</a>.</p></div>') if detail else ""
    priority_meta = {
        ("leak-repair", "aldershot"): "Leaking pipe or fitting in Aldershot? Tell Guildford-based Nigel where the water appears, whether it can be isolated and your postcode to discuss repair help.",
        ("leak-repair", "camberley"): "Leak repair in Camberley for pipes, taps, toilets and wastes. Tell Guildford-based Nigel where water appears, whether it can be isolated and your postcode.",
        ("leak-repair", "farnham"): "A leaking pipe, tap or bathroom fitting in Farnham? Describe where the water appears and send your postcode to Guildford-based Nigel to discuss the repair.",
        ("toilet-repair", "leatherhead"): "Toilet not flushing, running or leaking in Leatherhead? Tell Nigel what happens, whether water can be isolated and your postcode to discuss a repair.",
    }
    meta_description = priority_meta.get((service_slug, area_slug), intro + f" Call Nigel Harvey Ltd on {COMPANY_PHONE} to discuss local plumbing help.")
    page_title = {
        ("leak-repair", "camberley"): "Leak Repair Camberley | Leaking Pipes | Nigel Harvey Plumbing",
        ("leak-repair", "aldershot"): "Leak Repair Aldershot | Leaking Pipes | Nigel Harvey Plumbing",
        ("toilet-repair", "leatherhead"): "Toilet Repair Leatherhead | Cisterns & Leaks | Nigel Harvey Plumbing",
    }.get((service_slug, area_slug), f"{title} in {area} | Nigel Harvey Plumbing")
    problem_items = "".join(f"<li>{escape(item)}</li>" for item in service["problems"])
    related_locations = "".join(
        f'<a href="/{escape(service_slug)}-{escape(item["slug"])}">{escape(title)} in {escape(item["name"])}</a>'
        for item in LOCATION_PAGES if item["slug"] not in {area_slug, "farnborough"}
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
        "provider": {"@id": absolute_url("/", request) + "#business"},
        "areaServed": [area, "Surrey"],
        "serviceType": service["service"],
        "url": canonical,
        "description": intro,
    }, ensure_ascii=False)

    return render_shared_public_page(f"""<!doctype html>
<html lang="en-GB"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(page_title)}</title>
<meta name="description" content="{escape(meta_description)}">
<meta name="keywords" content="{escape(keywords)}">
<link rel="canonical" href="{escape(canonical)}">
<meta property="og:type" content="website"><meta property="og:title" content="{escape(page_title)}"><meta property="og:description" content="{escape(meta_description)}"><meta property="og:url" content="{escape(canonical)}">
<script type="application/ld+json">{breadcrumb_schema}</script>
<script type="application/ld+json">{service_schema}</script>
</head>
<body>
<div class="top"><div class="wrap nav"><div class="brand">Nigel Harvey Ltd<small>{escape(title)} in {escape(area)}</small></div><div class="nav-actions"><a class="btn btn-light" href="tel:{escape(COMPANY_PHONE_TEL)}">Call Now</a><a class="btn btn-primary" href="/request-quote">Request a Quote</a><a class="btn btn-light" href="/">Home</a></div></div></div>
<main>
<div class="wrap hero"><div class="hero-card"><div>{logo_html}</div><div class="eyebrow">Local plumbing help in {escape(area)}</div><h1>{escape(heading)}</h1><p class="lead">{escape(intro)}</p><div class="nav-actions"><a class="btn btn-green" href="tel:{escape(COMPANY_PHONE_TEL)}">Call Now: {escape(COMPANY_PHONE)}</a><a class="btn btn-primary" href="/request-quote">Request a Quote</a></div></div></div>

<div class="wrap section"><h2>{escape(title)} Services in {escape(area)}</h2><p>If you are looking for {escape(service["service"])} in {escape(area)}, Nigel provides practical help for local homes, landlords and small businesses.</p><ul class="list">{problem_items}</ul></div>
{priority_html}

<div class="wrap section"><div class="grid3">
<div class="card item"><h3>Discuss availability</h3><p>Send the postcode for {escape(area)} so Nigel can confirm coverage and discuss urgent or planned plumbing work.</p></div>
<div class="card item"><h3>Clear Communication</h3><p>You get straightforward advice and a clear explanation of the work needed.</p></div>
<div class="card item"><h3>Trusted Local Plumber</h3><p>Nigel Harvey Ltd provides dependable domestic plumbing services across Guildford and Surrey.</p></div>
</div></div>

<div class="wrap section"><h2>Other Plumbing Services in {escape(area)}</h2><div class="pill-links">{related_services}</div></div>
<div class="wrap section"><h2>Nearby Areas We Cover</h2><div class="pill-links">{related_locations}</div></div>

<div class="wrap cta card"><div><h2>Need {escape(title.lower())} in {escape(area)}?</h2><p>Call now or send the job details online.</p></div><div class="nav-actions"><a class="btn btn-green" href="tel:{escape(COMPANY_PHONE_TEL)}">Call Now: {escape(COMPANY_PHONE)}</a><a class="btn btn-primary" href="/request-quote">Request a Quote</a></div></div>
</main>
<div class="footer"><div class="wrap footer-inner"><div><strong>Nigel Harvey Ltd</strong><br>Plumbing services in Surrey</div><div>{escape(COMPANY_PHONE)}<br>{escape(COMPANY_EMAIL)}<br>{escape(area)}, Surrey and surrounding areas</div></div></div>
<a href="tel:{escape(COMPANY_PHONE_TEL)}" class="sticky-call">📞 Call Now: {escape(COMPANY_PHONE)}</a>
</body></html>""")

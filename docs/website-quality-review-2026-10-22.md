# Nigel Harvey Plumbing — Whole Website Quality Review
**22 October 2026 · Read-only site inspection + safe navigation fix · Publication requires owner approval**

Site: https://www.nigelharveyplumbing.co.uk/ . Baseline main commit af83f668839828bec11743b98f6a60ef9f43332c.
This is an evidence-based technical and business-quality audit, **not** a claim that the site is perfect, a certified security test, or an assertion that Google indexes every page.

## 1. Verified working (public site)
- Google sitemap: 82 existing canonical URLs; Google reports 0 errors / 0 warnings. Earlier full live GSC Wizard on-page scans confirmed 82 indexable HTTP 200 pages, with no critical/high/medium on-page SEO findings. The separate 82-page local/CI integrity regression checks internal links, first-party images, unique title/meta/H1/canonical, legacy redirects, and private app authentication.
- On 22 October, SEO content PR #32 was deployed successfully as Render commit af83f668. All three updated service pages and their three town overviews rechecked live with HTTP 200, indexable and no detected on-page issues.
- Consent script loads Google Analytics only after the browser records acceptance; explicit decline and preferences control exist in the footer. Keep behavioral tests on fresh profiles.
- The enquiry form requests name, phone and job description, with optional postcode, email, preferred channel and a WhatsApp alternative. Real email delivery and GA4 completion should not be inferred solely from synthetic CI tests.
- Review count is dynamically supplied by Google, rather than an invented fixed number.
- Site hero images: WebP ~15–69KB; project imagery has 640px/1280px WebP derivatives. This does **not** substitute for actual mobile speed / Core Web Vitals measurement.
- Production deployment: Render on latest approved main, one running instance with memory well below limit during last inspection. Absence of logged errors does not establish zero HTTP errors.
- Mobile/desktop Chromium workflows have passed the site's full GitHub regression. Keyboard usability, screen-reader output and real-device layout remain separate acceptance checks.

## 2. Search performance — opportunity, not technical failure
Latest settled GSC 28 days through 20 October: 19 clicks, 2,610 impressions, ~0.73% CTR, ~34 average position.
The smaller tracked-URL watchlist is 7/7 indexed; it is **not** a count of indexed pages across all 82 sitemap URLs. 37 sitemap URLs had some search impressions in the earlier settled 28-day audit; impression-free does not mean unindexed.
Overlap in search-query appearances between homepage, Guildford page and local service pages is measurable, but this alone does not justify deleting location URLs or changing valid self canonicals. Improve useful local distinctions and supporting real project evidence when it exists. Avoid duplicate/doorway-style template proliferation. Google does not guarantee indexing even when pages pass technical checks.

## 3. Change prepared in this PR: public owner-app navigation
Public templates/header/footer currently advertise 'Open App' despite the owner app being behind Basic Auth. The link creates friction for customers and unnecessarily publicizes a private interface. This PR removes only the customer-facing shortcut on all 82 public page templates. Direct /app remains reachable by the owner's saved browser bookmark and continues requiring authentication and noindex. No protected endpoints, customer records, invoices, schema, cookies, Google/SEO index controls or site routes are altered.
The old baseline snapshot tests are preserved by reversing ONLY the two removed hyperlinks during comparison. The actual rendered public pages are independently asserted never to contain the link.

## 4. High-priority unresolved privacy and document-sharing risk — separate release
Code currently allows anonymous access to numbered invoice HTML, quote/invoice PDF, invoice QR and invoice photo endpoints. Sequential identifiers should not be treated as proof of customer identity. Robots.txt exclusion is not authorization and noindex/cache headers do not remedy guessable links.
Draft PR #1 (privacy/gdpr-readiness) from September stages random bearer share tokens and staff authentication for numeric routes, plus a DRAFT privacy page. Its changes affect database schema and **old customer-facing links already sent over WhatsApp**. It is stale and cannot be merged without reconciliation, verified migration, a plan for reissuing existing customer links, staging rehearsal, rollback and explicit owner approval.
Current quote-form and footer do not link to a published privacy notice. The UK ICO advises transparent privacy information at the point of collection. Before publication, verify controller identity/contact, actual lawful bases, retention for leads/invoices/photos/recordings/backups, actual providers and transfers, rights/complaints contacts, and ICO fee position. Do not invent or publish unverified privacy/retention claims.
**Priority:** conduct confidential review of customer-sharing links and privacy facts promptly; avoid requesting/displaying live invoice links or documents in public logs.

## 5. Remaining quality enhancements — measured, not blocking
- Minor low-priority GSC Wizard flags: request-quote page has no detected JSON-LD; Advice/Projects overview pages are comparatively short and have no detected JSON-LD. Do not add filler merely for a score. Document real completed work and helpful guidance when available.
- No independent production Lighthouse/LCP/INP/CLS field benchmark confirmed yet. Test against real mobile and slower connections before making speed claims.
- Real customer lead emails, spam-resilience and consent/GA4 attribution should be checked end to end using a separately authorised approach that does not create misleading synthetic business conversions.
- Review copy consistency between homepage video guidance ('video if requested') and some local pages encouraging video submission; reconcile with owner preference rather than changing customer instructions arbitrarily.
- Audit real customer accessibility with keyboard/screen reader beyond structural HTML tests; visual checking at 320px/390px, tablet and desktop is advisable.
- Check and reduce production HTTP 404 requests by path if request-level logs become available; counts alone may reflect bots and are not proof of internal dead links.
- Update outdated privacy PR and perform token migration and retention decisions as separate higher-risk work, not bundled with this navigation-only release.

## Release boundary
Draft PR only. Do not merge/deploy production without owner approval. Do not alter Stage 3 enquiry tracking PR #29, records, phone, email, invoices, sitemap, analytics preferences or Render settings as part of this audit.

# Business Growth Batch 6 — lead, quote and outcome tracking

Branch: `growth/business-growth-batch-6` from production baseline `7348ed293f6ccc8f6580ba34b3cd46095d3216b7`.

## Existing workflow confirmed

The public quote form already writes a lead with landing page, referrer and UTM context in `leads.source`; app leads have new/contacted/quoted/won/lost. The quote builder previously copied lead fields into the form but did not retain a lead ID. Saved quotes had no independent outcome or follow-up fields; invoices retained `quote_id`. The existing dashboard showed quoted and invoiced totals without quote outcomes. Existing invoice and quote PDFs use the saved result JSON.

## Implementation and interpretation

- Additive, idempotent SQLite columns on leads and quotes. Historical quotes default to `unclassified` and are not inferred as pending or won. No existing row is deleted or rewritten by the migration.
- New quotes begin `pending`. The private quote list and individual editor show status; Nigel can set pending/won/lost/expired, an optional follow-up date for pending, and optional loss reason/note. Changing quote status never sends a customer message. A linked lead reflects quoted/won/lost status; expired maps to lost in the existing five-state lead vocabulary while the quote retains the exact expired outcome.
- “Start Quote” carries the lead ID forward. Existing source/referrer/UTM text is preserved. A conservative source category can be inferred; Nigel can manually classify leads and direct quotes. Unknown and unattributed historical records remain unknown. Work type is optional.
- The all-time internal report shows saved quotes, quote outcome counts and values, decided-quote win rate, follow-ups due/overdue, recent wins/losses, and source counts and linked invoice/paid amounts. “Quoted” is not necessarily sent. Won quote value and estimated gross profit are not realised revenue/net profit. Only a quote linked to a lead or manually classified is included in source value. An invoice is counted only through its explicit `quote_id`.
- Quote and invoice calculations, PDFs, public form fields, authentication, GA4, and credentials remain on their existing paths.

## Blocked-drain correction

The only generated blocked-drain service definition was `blocked-drains` in `LOCAL_SERVICE_PAGES`. It created 13 indexed town pages (all existing local service towns except Farnborough). The definition and its generated internal links and service JSON-LD were removed. All 13 old `/blocked-drains-{town}` URLs return a direct permanent redirect to the existing `/plumber-{town}` overview, so prior links have a useful, supported destination rather than a 404. The sitemap changes from 85 to 72 200-status URLs. The toilet-repair family no longer claims blockages or blocked toilets; faults, leaks and cistern parts remain. Drain-off fittings, heating-system draining and waste-pipe installation references in the private quote/material logic describe legitimate plumbing work and are retained. Historical Batch 5 audit text is kept as historical documentation.

Redirect towns: Guildford, Woking, Farnham, Godalming, Camberley, Aldershot, Leatherhead, Epsom, Fairlands, Worplesdon, Merrow, Burpham, Shalford.

## Verification record

- Local isolated regression: 85 tests passed; `node --check` and Python `compileall` passed.
- Tests exercise legacy SQLite schema migration/idempotence, live lead capture context, linked quote outcome transitions, follow-up and loss fields, source and invoice attribution, quote/invoice PDF compatibility, route protection and public drain redirects. Disposable test databases never use `/var/data`.
- Staging deployment, live crawl, desktop/mobile checks and mounted disk before/after counts: **pending**.
- Production/main and Google Business Profile/directory services: **not changed**.

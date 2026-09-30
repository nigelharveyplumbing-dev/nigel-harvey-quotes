# Plumbing website and app privacy readiness (30 September 2026)

This is a staged implementation record, **not a certification of UK GDPR compliance**. The public notice in `templates/privacy.html` is deliberately marked DRAFT. Do not promote it or the document-link change without the factual decisions below and a review of previously shared links.

## Confirmed from the application

| Data and source | Use and storage | External disclosure observed in code |
| --- | --- | --- |
| Public quote form: name, phone, optional email, address/postcode, job description, preferred contact, urgency, source, landing/referrer and UTM values | Creates a lead in SQLite on the Render `/var/data` persistent disk. Optional lead notification via configured SMTP. | Email provider if notification enabled; Render hosting. No form job details in GA4 events. |
| Private app: customers, leads, visits, jobs, quotes, invoices, materials, payment status and notes | SQLite and timestamped backup copies under `/var/data/backups`; backups are pruned by count (30), not age. Invoice photos are stored under `/var/data/invoice_photos`. | Invoice email via configured SMTP; customer-initiated WhatsApp links. |
| Optional Google Analytics on public pages | Browser choice in local storage. The Google tag is inserted after accepting; contact-click and lead events contain page path/event name. | Google, only after accepted in production. `/app` does not load this public analytics script. |
| Google reviews | Server requests Places data; review display includes Google's branding asset. | Google for reviews/branding. |
| Optional AI quote draft | Includes job description, customer name/address, current materials and site-survey context; sent only when Nigel invokes the feature. | OpenAI API `/v1/responses`. |
| Optional site-survey analysis | Audio transcribed through OpenAI, video audio transcribed, selected compressed images and the transcript/notes analysed through OpenAI. Processing uses a temporary directory removed at the end of the request. A reviewed result may later be included in the quote. | OpenAI API transcription and responses endpoints. |
| Customer-facing documents | Historically public sequential quote/invoice/PDF/photo URLs. The staged fix uses per-document random token links and requires staff authentication for numbered URLs. | Anyone holding a valid share link can see the corresponding document; link forwarding remains possible. |

## Owner facts and decisions needed before publication

1. Confirm whether the plumbing business is registered with the ICO or complete [the ICO fee self-assessment](https://ico.org.uk/fee-checker). Record the result; no application or payment was made here.
2. Set a retention schedule for unanswered/unconverted enquiries, completed jobs, quotes, invoices, job photos, recordings/transcripts, and backups. The app currently has **no age-based deletion**. Do not promise automatic erasure in a notice without implementing and testing it. Tax/accounting obligations and disputes may warrant different periods.
3. Confirm the actual email service and any other systems where customer conversations or photos are retained (phone, WhatsApp, cloud photo storage, bookkeeping, accounting, payment processor). Confirm who else has access.
4. Review Render, Google, OpenAI, email and WhatsApp provider terms/data-processing arrangements and relevant international transfers. The app's configured integrations do not prove legal transfer safeguards.
5. Agree how customers are told about recording a visit and using AI processing of site-survey images/audio. Avoid recording other people or private household information unless needed.
6. Confirm a business contact route for privacy requests. The public draft currently lists the existing business email/phone only and deliberately omits a residential street address.
7. Agree the production cutover for old numbered invoice and quote links. Those links would cease to work anonymously under the staged fix. Reissue new token links to customers with live outstanding documents before cutover. Avoid enabling the legacy numbered links publicly just for convenience.

## Operational checks and procedures

- Keep a simple record of processing purposes and the lawful basis for each (enquiries, contract/work, accounting, optional analytics, AI survey support). Review with a UK data protection adviser where needed.
- Document access controls for Render, email, Google and the private app; use unique credentials and multifactor protection where supported. Verify backup access and a restore procedure.
- Provide a route to find a person's data across the app, email, WhatsApp, media and backups; handle access/correction/erasure requests within applicable timescales, checking accounting obligations before deleting financial records.
- Maintain a breach log and a procedure to contain, assess and report incidents to the ICO when required.
- Test the public site in a fresh browser: no Google tag or analytics cookies before opt-in or after decline, consent change via footer, and no customer-form content in analytics payloads. Retest after any analytics change.
- Verify the new tokenized document routes anonymously and the old numbered routes without credentials. Check no tokens in the sitemap, analytics payloads or referer headers. Treat forwarded token links as bearer access and reissue/rotate when compromised.

## Release gate

Staging branch only until the factual decisions are confirmed and Nigel approves the cutover. This change does not delete or reset any existing record. The migration adds a `share_token` to quotes/invoices, including historical records; it changes database bytes and writes tokens when first run on staging. Production has not been changed.

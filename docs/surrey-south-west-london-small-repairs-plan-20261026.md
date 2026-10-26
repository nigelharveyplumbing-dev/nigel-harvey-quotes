# Surrey and South West London: small-repair SEO release plan

**Owner direction (26 October 2026):** Guildford is the business base. Nigel is willing to travel for small plumbing jobs across Surrey and South West London and regularly travels to Wimbledon for other work on a variable schedule. Do not advertise fixed London appointment days or a London office.

## Search evidence / baseline

Google Search Console web search, 26 September–23 October 2026 (28 days), filtered to the existing London overview URLs:

| Existing page | Impressions | Organic clicks | Average position |
| --- | ---: | ---: | ---: |
| /plumber-morden | 131 | 0 | 69.9 |
| /plumber-merton | 9 | 0 | 52.9 |
| /plumber-kingston | 3 | 0 | 8.3 |
| /plumber-wimbledon | 2 | 0 | 23.5 |

The filtered London pages recorded **145 impressions and 0 clicks**; Richmond and Putney had no returned rows. These low volumes do not establish that one town has greater commercial demand. Morden impressions included searches about boilers and emergencies that may not match the work offered; never claim gas registration, gas appliance services, or guaranteed emergency response.

## Proposed changes in this PR

1. Shorten the mobile homepage hero while keeping the existing Guildford/Surrey SEO title, canonical URL and H1. Mention South West London and Wimbledon above the contact buttons. Place emergency-availability wording below them. Preserve logo, footer, consent handling, WhatsApp/telephone destinations and public/private navigation.
2. Improve the **existing** Wimbledon, Morden and Merton overview pages for smaller domestic repairs (taps, toilets, showers, wastes, radiator valves, pipework). Keep distinct location-specific troubleshooting guidance. Do not create new pages, location offices, reviews, project claims or service-matrix URLs.
3. Preserve direct quote, call and WhatsApp options. Do not change GA4, Search Console, consent settings or customer records. **Do not** interpret WhatsApp button clicks as confirmed enquiries.

## Measurement plan after separate release approval

- Weekly settled GSC comparison: Surrey and London **page-path groups**, impressions, clicks, CTR and average position; compare the same weekdays and report changes only once Search Console has settled.
- For enquiries recorded in the plumbing app, review actual customer-provided location/postcode, landing-page context where recorded, source confidence, quote/job outcomes and genuine versus synthetic/test classification. **Missing origin is unknown, not direct/organic by assumption.** Known synthetic enquiries, including `NHP-GA4-20261010-ONE`, must not be counted as genuine leads.
- GA4 `generate_lead` is aggregate and consent-limited; do not claim it can distinguish tests unless supported by verified event-level evidence. London-vs-Surrey genuine-lead rates cannot be calculated without reconciled lead/quote/job records.
- Check changes after 2–4 settled weeks, with low-volume uncertainty noted. A ranking or enquiry increase is not guaranteed.

## Release safeguards

- Run full Python/Node/browser CI, including mobile homepage and all six London overview routes, metadata, canonical links, form links, sitemap and private app access.
- Review mobile and desktop appearance before merging; stage/preview only with the owner’s approval as needed.
- Keep PR **draft** until CI and visual review. No production deployment, database migration, GBP change or Google settings change is authorised by this preparation step.

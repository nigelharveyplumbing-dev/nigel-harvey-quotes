# Nigel Harvey Plumbing — Search Console indexability review
**22 October 2026 · Review candidate only · No production release**

## What Search Console actually reports
The property is `https://www.nigelharveyplumbing.co.uk/`. Its currently submitted sitemap contains 82 URLs, no reported warnings/errors, last downloaded 19 October. In the last 28 settled days, 37 sitemap URLs received search impressions; zero impressions is **not** proof that Google excluded a URL. The seven URLs on the GSC Wizard indexing tracker are all indexed; the tracker does not cover the whole sitemap.

Google URL Inspection (read-only) confirmed:
- `/leak-repair-leatherhead`: **Crawled – currently not indexed**, last crawl **2026-09-28 06:59 UTC**; fetched successfully, robots allowed, Google-selected and declared canonical both exactly this URL.
- `/toilet-repair-godalming`: **Crawled – currently not indexed**, last crawl **2026-07-31 01:19 UTC**; fetched successfully, robots allowed, matching self-canonical.
- `/leak-repair-farnham`: now indexed per tracked URL, after previously being crawled/not-indexed.
- `/emergency-plumber-surrey`, `/general-plumbing-surrey`, `/bathroom-plumbing-surrey`: Google shows **Not found (404)**, but the recorded crawls were in **May 2026**. Current main code serves them as live service pages and the new offline regression explicitly tests HTTP 200, matching self-canonical. Google's report may lag later site changes; verify a fresh live fetch rather than editing canonical tags on this historical evidence.
- Some other existing service pages are **Discovered – currently not indexed** or **URL unknown to Google**. These are distinct statuses and no technical indexing-blocking cause was established.
- The **Alternative page with proper canonical tag** report's affected URL examples were not available through the connected API. Duplicate/canonicalized variants can be intentional. Do **not** change the preferred www canonical or create new pages based solely on this category.

## Targeted improvements only
- Add practical, differentiated leak-triage information to the existing Leatherhead leak-repair page. Covers supply vs waste symptoms, safe isolation, useful photos and a realistic postcode-based enquiry. Link to the Leatherhead overview and the already-published shower waterproofing advice.
- Add practical, differentiated cistern/flush troubleshooting information to the existing Godalming toilet-repair page. Explains observations that distinguish continuous running, filling issues and visible leaks, without assuming a diagnosis. Link to the Godalming overview.
- Add reciprocal, genuine local navigation links from **existing** Leatherhead and Godalming overview pages.
- Do not invent local case studies, Google reviews, premises, qualifications, guarantees or response times. No new URLs or sitemap size changes.
- Keep the website's www self-canonicals, structured metadata and private app access unchanged.

## Verification and remaining gates
- Exact-head Python/Node/browser CI must pass; new `tests/test_gsc_indexing_review.py` covers new copy, links, canonical, historical Surrey 404 routes, sitemap 82 URLs and robots exclusions.
- Draft pull request only, based on currently deployed production main `7de3c82c455fa08579c14e4e8c168f5282190463`; do not merge or deploy without owner review.
- After a separately approved production deployment, confirm live HTTP 200, self canonicals and redirects; then use Search Console to inspect affected URLs and request validation, allowing for Google crawl delays. Google may still choose not to index a page; no ranking/indexing guarantee.

# Website-wide SEO content review — 5 November 2026

Initial audit record. Superseded by [the complete page-by-page review](page-by-page-review-2026-11-05.md) and [validation record](validation-2026-11-05.md). No production changes approved.

## Scope
The production sitemap contains 82 URLs: 20 location overview pages, 52 local service/location pages, 4 Surrey-wide service pages, and 6 other pages (home, quote, project and advice index/detail).

## Verified evidence
- Google Search Console sitemap: 82 submitted URLs, 0 warnings and 0 errors.
- Live on-page audit: 82/82 pages HTTP 200 and technically indexable. Five low-severity issues: /projects thin content and missing structured data; /advice thin content and missing structured data; /request-quote missing structured data.
- Search Console sitemap performance (28 days): 46 URLs with impressions, 36 without. Absence of impressions does not establish non-indexing.
- Indexing tracker: 55 URLs tracked, 27 indexed, 28 not indexed. Among the 28: 20 'URL is unknown to Google', 8 'Discovered - currently not indexed'.
- The 52 local service pages share four service templates. There are several custom per-town guidance blocks, but the remaining pages use generic service guidance.
- No common zero-width watermark characters found in business/public_pages.py.

## Content overlap requiring review
1. Emergency plumber town pages: 11/13 had no impressions. Compare town-specific usefulness and inbound internal links.
2. Leak repair: generic advice is repeated verbatim across several town-specific priority_details (Aldershot, Camberley, Guildford and Fairlands), with only the location heading varying. Woking is very similar.
3. Toilet repair: Burpham and Leatherhead have identical custom explanatory paragraphs.
4. Bathroom plumbing: many pages use the shared introduction with location substitution. Compare the body text and added guidance before rewriting.
5. Location overviews: custom PRIMARY_LOCATION_NOTES exist for only a subset of the 14 Surrey locations; compare the others for overlap.
6. Do not fabricate local case studies or service guarantees; use confirmed jobs, photographs and accurate coverage.

## Recommended order
- Preserve all existing URLs and redirects; no automatic deletion or consolidation.
- Prioritise indexing investigation and internal linking for non-indexed commercial pages.
- Strengthen pages with high impressions and few clicks (Guildford, Camberley, Farnborough, Aldershot, Godalming, Farnham, Woking).
- Prepare targeted copy changes only after verifying true paragraph-level duplication and identifying credible location-specific details.
- Run all tests, compare all 82 routes and seek owner approval before merge/deploy.

## Limits
The on-page crawler checks each URL independently and does not calculate pairwise text similarity. This review identifies template-level and several verbatim overlaps from source; it is not a quantified 82×82 similarity matrix. Google Search Console does not disclose why every unknown/discovered URL has not been indexed.

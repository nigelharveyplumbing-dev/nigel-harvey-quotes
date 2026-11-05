# Local service content comparison — 5 November 2026

Scope: all 52 published local service/location combinations in the 82-URL sitemap. Branch: seo/full-site-content-review-2026-11-05.

This records the starting comparison. The continued PR now improves 29 of the 36 fallback pages, deliberately retains seven with existing visibility, and preserves the earlier three targeted edits. Final guidance counts are 45 custom / seven shared: emergency 12/1, toilet 10/3, leak 13/0, bathroom 10/3. See [all 82 page decisions](page-by-page-review-2026-11-05.md), [all 3,321 pairwise comparisons](full-site-pairwise-2026-11-05.json), and [validation status](validation-2026-11-05.md).

## Template-level comparison

| Service | Pages | Custom priority guidance | Shared fallback guidance |
|---|---:|---:|---:|
| Emergency plumber | 13 | 0 | 13 |
| Toilet repair | 13 | 6 | 7 |
| Leak repair | 13 | 8 | 5 |
| Bathroom plumbing | 13 | 2 | 11 |
| **Total** | **52** | **16** | **36** |

The 36 fallback pages share a full service-specific guidance paragraph within each service group; the town is substituted into the heading. They also share the service introduction and much of the surrounding template. Custom guidance does not guarantee unique content elsewhere on the page.

## Duplicate custom paragraphs

- Leak repair Aldershot and Guildford: same custom guidance, with town only in heading.
- Leak repair Camberley and Fairlands: formerly same guidance; now differentiated in this branch.
- Toilet repair Burpham and Leatherhead: formerly same guidance; Leatherhead now differentiated.

## Highest-value next editorial work

1. Emergency pages: all 13 use shared fallback guidance. Avoid boilerplate emergency claims and use useful, accurate symptom-specific advice plus genuine evidence where available.
2. Bathroom plumbing: 11 of 13 use fallback guidance; prioritise locations with impressions or known completed jobs.
3. Toilet repairs: 7 fallback pages.
4. Leak repairs: 5 fallback pages.
5. All 20 area overview pages and four Surrey-wide services require separate cross-page comparison before claims of full content uniqueness.

## Implemented on this branch

- Camberley leak, Fairlands leak and Leatherhead toilet guidance differentiated.
- Contextual links added to the local service template, affecting all 52 published local service URLs.

## Quality gates outstanding

- GitHub full regression workflow must complete successfully.
- Staging must run this branch and verify all 82 routes, metadata, canonical URLs, navigation, and mobile display.
- Check no broken links or false local experience claims.
- Owner approval required before merge or production deployment.

This is a template/source comparison, not a rendered 82-by-82 quantitative similarity score. Do not interpret shared factual plumbing guidance alone as a Google penalty.

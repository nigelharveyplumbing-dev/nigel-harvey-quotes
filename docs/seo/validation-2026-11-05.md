# PR48 validation and release gate — 5 November 2026

This record separates the hosted preview from the isolated staging browser matrix. Final CI outcomes are shown in the [PR48 checks and description](https://github.com/nigelharveyplumbing-dev/nigel-harvey-quotes/pull/48) and the `full-site-staging-previews` Actions artifact; do not infer a pass from a queued or running check.

| Check | Evidence / result |
|---|---|
| Production reference | Render live deploy `dep-dbhnr408v5cc738vkc8g`, commit `8cd736461190941224b911a02884c3ea1ac5fbdb`; current `main` matched it at comparison. |
| Branch comparison | Existing PR48 branch only; zero commits behind `main`, merge base `8cd7364`. Recheck the live PR before any merge because branches may move. |
| Offline production-mode crawl | 82/82 HTTP 200, unique title/description/H1, self-canonical and indexable; local image targets, internal URLs and fragments resolve; all pages reachable from the homepage within three clicks. |
| Before/after shell | Header, footer, executable scripts and form hashes match production on all 82 pages. All 82 titles and descriptions remain unchanged. `app.py`, static styles/scripts, templates, routing, authentication, quoting calculations and data migrations are unchanged. |
| Pairwise content review | All 3,321 pairs measured; 312 same-service local pairs measured separately. Full data and method are in `full-site-pairwise-2026-11-05.json`. |
| Hosted Render staging | [Protected PR48 preview](https://nhp-seo-pr48-staging.onrender.com), free staging service `srv-dbm8oo0ae00c738maf0g`, deployed application commit `9ac4c91fa1b56df3d49fdec688d30f6beb28e2c6`. Later browser-harness/report commits do not change the rendered application. |
| Hosted HTTP crawl | **82/82 pass**. All pages have the same `X-Preview-Commit`, staging-origin canonicals, valid metadata, noindex headers and disabled Google analytics. Anonymous sitemap request returns 401. Internal HTML and full-size photograph links resolve. Exact evidence: `hosted-staging-http-2026-11-05.json`. |
| Full automated regression | The full offline Python/Node/browser step, secure document-link browser matrix and public-review responsive matrix passed on `9ac4c91` in [run 42041841347](https://github.com/nigelharveyplumbing-dev/nigel-harvey-quotes/actions/runs/42041841347). That run was subsequently cancelled while the added full-site matrix was running. The corrected matrix and entire suite are rerun on the latest branch; inspect the latest PR check for the final result. |
| 82-page responsive matrix | Real application in isolated staging mode with published project/advice records, synthetic reviews and disposable data. All 82 URLs at widths 320, 375, 768 and 1440: 328 cases, full-page screenshots, status/canonical/metadata/noindex, heading clipping, overflow, image decoding, logo, contact routes, staging analytics and JavaScript errors. The harness explicitly loads lazy images and bounds decoding. Latest result and individual cases are in the Actions artifact. |
| Lead controls / syntax | JavaScript syntax checks and `tests/test_lead_email.cjs` pass locally; Python source compiles. Contact behaviour is also covered by the full regression workflow. No real enquiry, WhatsApp message or email was sent. |

## Verification limits

The host workspace cannot launch Chromium because its socket operation is blocked. The full suite's browser-dependent harness therefore cannot pass locally; GitHub Actions supplies the working browser environment. The cloud browser could not open the Basic-authenticated Render preview. These limits were not bypassed by weakening authentication. Hosted HTTP checks are complete; the responsive matrix checks the same application under isolated staging controls in CI, rather than visually driving the hosted Render URL. A direct hosted browser repetition remains unverified.

CI uses synthetic **4.6 / 23** review data to check presentation. Those figures are test fixtures, not Nigel's business rating. The hosted launcher instead reuses the public website's review display when available and retains the existing fallback. Production review configuration is unchanged.

## What must happen before production

Review [all 82 page decisions](page-by-page-review-2026-11-05.md), the latest successful CI check and responsive artifact. The recorded seven retained fallback pages and remaining content overlap are deliberate and disclosed. More genuine job evidence is preferable to further geographic paraphrasing.

Confirm that `main` still matches the reviewed production baseline or integrate and rerun checks if it has moved. Nigel's explicit approval is required before merging PR48 or deploying to production. This work does not include either action. Google indexing and rankings are outside the release test and cannot be guaranteed.

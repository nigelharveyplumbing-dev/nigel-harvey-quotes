# Growth Batch 6 — real projects and AI/AEO

## Baseline audit (before implementation)

6 October 2026. Isolated checkout from current GitHub main `8ab4f6494de3823b4150fc611e698a91295faa56`. Main includes merged public trade comparison PR #2 and the approved business pipeline; no established safer baseline was found. PR #4 / `feature/account-trade-pricing-phase2` head was read-only `23624e71d08ad12d6a41bdffe38ba93305dba576` and is excluded from this work. No branch switching in another checkout, merge, deployment, service update or production data access.

| Area | Existing architecture / behaviour |
|---|---|
| Public pages | FastAPI routes in `app.py`; content/renderers in `business/public_pages.py`; shared shell in `business/public_layout.py`. Server-rendered HTML. |
| Services | Four Surrey overview pages: general plumbing, bathroom plumbing, heating plumbing and 24-hour plumbing. Four local families: emergency, toilet, leak repair and bathroom plumbing. No standalone tiling or shower-installation page. |
| Locations | 14 location pages, including `/plumber-guildford` and `/plumber-merrow`; local service combinations exclude Farnborough. |
| Content system | Data-driven service/location lists; no blog, case-study index or real-project content model. |
| Sitemap | Explicit route families in `/sitemap.xml`: 72 URLs on baseline. `/app`, APIs, legacy blocked-drain redirects and `/new-home` excluded. |
| Canonicals | Central `absolute_url`/`get_public_base_url`; www production origin; explicit staging origin required and live host rejected in staging. No change proposed. |
| JSON-LD | Homepage Plumber identity + visible FAQ; local pages Plumber/BreadcrumbList/FAQPage; service pages Service/BreadcrumbList. Business identifies a service area, not a customer-facing address. Review text has no self-serving Review/AggregateRating markup. |
| Images | Three bundled illustrative WebP images on an exact allowlist in `/site-images/{filename}`; dimensions, lazy loading on supporting imagery, seven-day caching. No real-job image pipeline. |
| Internal linking | Relative service and area links, shared header/footer, enquiry attribution and call/WhatsApp CTA. |
| Metadata | Server-generated title, meta description, canonical and Open Graph; local pages index/follow with large image previews. |
| Indexing/auth | Production robots disallows `/app` and `/api/`; staging robots disallows all and all routes require staff auth. Baseline has no explicit X-Robots-Tag for `/app`. Public allowlist uses exact method/route templates. |
| Expertise | Visible Meet Nigel and first-person service text; a single Plumber business identity; no invented qualifications. Genuine project evidence will add a concrete example of Nigel's own work. |

Render metadata could not be independently refreshed: connector requires workspace selection and no confirmed workspace is supplied in this session. Current remote main is the selected baseline; historical production metadata in existing reports is not treated as current. This task does not need a Render write or deployment.

## Implementation and verification

Implemented on `growth/website-batch-6-real-projects`. No merge, deploy, production database change or indexing notification. The page is a staff-only draft, not a publicly indexed page.

- Proposed URL path: `/projects/ensuite-renovation-merrow-guildford`
- Canonical after publication: `https://www.nigelharveyplumbing.co.uk/projects/ensuite-renovation-merrow-guildford`
- SEO title: **Ensuite Renovation in Merrow, Guildford | Nigel Harvey Plumbing**
- Meta description: **See a real ensuite renovation in Merrow, Guildford: strip-out, wall reconstruction, Marmox boards, plumbing, tiling and finished fittings by Nigel Harvey Plumbing.**

### Changes

`business/project_content.json` is the reusable fact/content record; `business/real_projects.py` provides strict content models, shared rendering, draft/published gates, schema, images, index, backlinks and sitemap entries. `static/real_projects.css` preserves the existing brand. Three exact public route templates were added; drafts/images require existing staff credentials within their handlers. Publication requires approval + a real publication timestamp in the reviewed record. The page has a concise factual summary, useful headings, staged real images and two project-specific answers.

The source JPEGs remain untouched in Nigel's private owner files outside Git. No original photographs are build/runtime dependencies or part of the rewritten Batch 6 tree. Selected images cover stripped-back walls, affected wall edge, reconstruction, Marmox stage, tray preparation, tiling, finished shower, finished vanity and finished overall room. No annotated image, generated photograph, guessed cause, mould remediation claim, customer's address or surname is used. Derivatives omit EXIF/XMP and use correct dimensions and srcsets. Total selected source bytes: 5,235,884; full-size WebP bytes: 2,071,332; 640px variants: 653,632. Both widths together are 2,724,964 bytes; a browser selects a variant rather than downloading both.

Tristan's exact five-star review is included verbatim, including “radiation”, with **Tristan, Merrow** attribution. It is visible copy only. Article + BreadcrumbList reference the unchanged Plumber identity. No Review/AggregateRating, credentials, invented products or new service schema were added. Drafts have no fictitious publication date and never send GA4 hits, even if prior analytics consent exists. The live publication date is supplied only at the later approval/publish step.

All shared footers gain `/projects` discovery. The project links naturally to `/plumber-merrow`, `/plumber-guildford`, `/bathroom-plumbing-surrey`, `/bathroom-plumbing-guildford`, `/bathroom-plumbing-merrow`, and `/heating-repairs-surrey`. Those same six pages gain relevant project backlinks only when it is published. There is no standalone shower or tiling service page to link to; bathroom plumbing covers the shower work. Existing unrelated service/location content and schema are preserved.

Draft sitemap remains **72 URLs**. Once reviewed publication is enabled, the index and project bring it to **74 URLs**, with correct canonicals and lastmod. `/app`, APIs, draft assets, invoices and previews remain absent. Robots rules stay intact. Explicit noindex headers now cover `/app`, private APIs and staging, supplementing the existing Basic Auth and robots rules.

IndexNow is feasible but intentionally design-only, with an explicit approved same-host URL list and ownership key validation. No production key or notification was created. Future app design uses the existing completed-job pipeline, separate public facts/photo/review permission, duplicate checks and a revision-specific approval gate. It records marketing use per job and never publishes on job completion. See [authoring and workflow design](real-projects-workflow.md).

### Verification

Baseline: **169 Python tests passed**. Final: **180 Python tests passed**, both Node suites passed, and the public analytics/event workflow passed. Existing complete isolated Chromium app workflows PASS. New real-project Chromium desktop (1440px) and mobile (390px) workflows PASS: nine images decode, no horizontal overflow, no page errors, no external requests. Tests cover routing/status, draft auth/cache/noindex, future published sitemap/canonicals, valid JSON-LD types/identity/dates, opt-in exact review, public privacy fields, reciprocal internal links, unknown images, private-source provenance, derivative-only public assets/preview, exact current-main sitemap preservation, dimensions/format/srcsets/alt text and staging/app indexing protections.

Approved existing HTML golden hashes remain enforced after masking **only** the additive footer discovery link. Quote calculations, trade comparison logic, DB and pipeline code remain unchanged. The route inventory grows from 81 to 84, with the same 66 private routes. CI already runs the full runner, which now also invokes the project browser regression.

The bundled default full Chrome build could not start under the local socket restriction. The standard installed Chromium headless shell ran both browser suites successfully, with no app security change. No external Google Rich Results validator was run, so local schema validation should not be described as Google certification.

Evidence: [desktop full page](growth-batch-6-preview/merrow-desktop.png), [desktop top](growth-batch-6-preview/merrow-desktop-top.png), [mobile](growth-batch-6-preview/merrow-mobile.png), [self-contained rendered HTML](growth-batch-6-preview/merrow-case-study-preview.html), [test results](growth-batch-6-preview/test-results.json). The HTML preview embeds all nine images and has no analytics or network scripts; it is not a hosted deployment.

### Remaining decisions and next step

Review the real Merrow draft's text/photos. Exact completion date, Marmox board model/thickness and sealing product names were not supplied and are omitted. A definitive cause of mould is not established. All original photographs must remain outside this public repository regardless of metadata. The initial original-photo exposure is corrected by rewriting the unmerged Batch 6 history; old GitHub commit/blob access can require separate GitHub-side purge. Staff-only draft gating protects website routes, not publicly readable GitHub assets.

Remote main was verified; current deployed production metadata could not be independently refreshed without a confirmed Render workspace. Pre-staging checks found that although originals are absent from the rewritten branch and its reachable history, GitHub still returns all nine originals through the old commit SHA. Recommended next step: resolve this GitHub-side retention using the support-request draft in `growth-batch-6-pre-staging-checks.md`; keep staging on hold. Once privacy closure is established, Nigel can review the preview and explicitly approve a non-conflicting isolated staging validation plan. Keep the content record in draft for staging. Only after final content approval should a reviewed change set publication/approval dates. Merge, production deployment and indexing notification each remain unauthorised.


### Pre-staging reconciliation

The exact current main sitemap was exercised through a disposable copy of main at `8ab4f6494de3823b4150fc611e698a91295faa56`, not inferred from an old report. All 72 URLs returned 200. The count is 2 core pages + 14 area pages + 4 Surrey service overviews + (4 local service families × 13 eligible areas) = 72. Comparing the previous Growth Batch 5 commit `7348ed293f6ccc8f6580ba34b3cd46095d3216b7` identifies exactly 13 removed paths, all `/blocked-drains-{town}`. Main ancestor `c4c36c0eeed939e944f5952fb139f2534376b1a1` intentionally retired those unsupported service pages; all 13 retain direct 301 redirects to the corresponding existing `/plumber-{town}` page. No valid supported page was unintentionally lost. Batch 6 draft URL set is exactly equal to main; the published test adds only `/projects` and the Merrow case study, with no removals. See `sitemap-baseline-reconciliation.json` for every URL/status/redirect and the new pre-staging report for history-exposure verification.

### Complete changed-file inventory

- `.gitignore`
- `app.py`
- `business/project_content.json`
- `business/real_projects.py`
- `docs/growth-batch-6-pre-staging-checks.md`
- `docs/growth-batch-6-preview/browser-validation.json`
- `docs/growth-batch-6-preview/merrow-case-study-preview.html`
- `docs/growth-batch-6-preview/merrow-desktop-top.png`
- `docs/growth-batch-6-preview/merrow-desktop.png`
- `docs/growth-batch-6-preview/merrow-mobile.png`
- `docs/growth-batch-6-preview/test-results.json`
- `docs/growth-batch-6-real-projects.md`
- `docs/project-images/merrow-ensuite/manifest.json`
- `docs/real-projects-workflow.md`
- `docs/sitemap-baseline-reconciliation.json`
- `static/project-images/ensuite-renovation-merrow-guildford/finished-room-1280.webp`
- `static/project-images/ensuite-renovation-merrow-guildford/finished-room-640.webp`
- `static/project-images/ensuite-renovation-merrow-guildford/finished-shower-1280.webp`
- `static/project-images/ensuite-renovation-merrow-guildford/finished-shower-640.webp`
- `static/project-images/ensuite-renovation-merrow-guildford/finished-vanity-1280.webp`
- `static/project-images/ensuite-renovation-merrow-guildford/finished-vanity-640.webp`
- `static/project-images/ensuite-renovation-merrow-guildford/marmox-board-and-pipework-1280.webp`
- `static/project-images/ensuite-renovation-merrow-guildford/marmox-board-and-pipework-640.webp`
- `static/project-images/ensuite-renovation-merrow-guildford/shower-tray-preparation-1280.webp`
- `static/project-images/ensuite-renovation-merrow-guildford/shower-tray-preparation-640.webp`
- `static/project-images/ensuite-renovation-merrow-guildford/stripped-back-walls-1280.webp`
- `static/project-images/ensuite-renovation-merrow-guildford/stripped-back-walls-640.webp`
- `static/project-images/ensuite-renovation-merrow-guildford/tiling-in-progress-1280.webp`
- `static/project-images/ensuite-renovation-merrow-guildford/tiling-in-progress-640.webp`
- `static/project-images/ensuite-renovation-merrow-guildford/wall-problem-detail-1280.webp`
- `static/project-images/ensuite-renovation-merrow-guildford/wall-problem-detail-640.webp`
- `static/project-images/ensuite-renovation-merrow-guildford/wall-reconstruction-1280.webp`
- `static/project-images/ensuite-renovation-merrow-guildford/wall-reconstruction-640.webp`
- `static/real_projects.css`
- `templates/public_footer.html`
- `tests/local_browser_server.py`
- `tests/route_inventory.json`
- `tests/run_project_browser.mjs`
- `tests/run_stage6_local.py`
- `tests/test_baseline.py`
- `tests/test_local_integration.py`
- `tests/test_real_projects.py`

### 8 October 2026 — current-main reconciliation

GitHub Support #4830106 completed retained-object and cached-view clearance. Final normal and cache-busted requests to all nine original paths through exposing commit `3679d74110c9b430ad63f13c98ef281042b9eaf6` returned 404. The earlier retention hold above is historical and closed.

Current main was verified as `7814135850da87215756281aaef22ba11795ce51`, the separate approved PR #4 merge. The cleaned Batch 6 commit `31f2d5c9b7002f7d486e2850c9b85cb3705a9791` was cherry-picked onto that exact baseline in a separate worktree/branch, `growth/website-batch-6-current-main`. The original reviewed Batch 6 branch remains unchanged.

Three conflicts were explicitly combined: `app.py` keeps both `real_projects` and `city_account_prices` imports plus the City private-store helper; `tests/route_inventory.json` keeps all three City endpoints and all three project endpoints; `tests/test_baseline.py` keeps 13 public website routes and 69 private routes. The two other route-count assertions were reconciled to 87 total routes. No City pricing, quote selection, calculation, app UI or City Chromium implementation file differs from current main. The shared app diff adds only the reviewed Batch 6 handlers, indexing headers, sitemap entries and service-page backlinks.

The project browser regression additionally checks the complete exact Tristan quote and confirms Google transmission stays disabled even with previously accepted analytics consent. The reviewed content stays draft, without a publication timestamp. Project data, image derivatives and their manifest are unchanged from the cleaned reviewed head. Staging validation is authorised; merge and production deployment remain unauthorised.

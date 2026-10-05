# City Plumbing / PTS account-pricing route

5 October 2026 — draft PR #4, City-first owner priority.

Nigel owns a City Plumbing trade account and does not own a Wolseley account.
Wolseley is optional future work, not a prerequisite for this PR. Williams is
paused until City is validated. No new merchant account, paid software, trial,
registration, supplier contact, credential use, merge or deployment was made.

## Verified official capabilities

| Requested capability | What the official material establishes | What remains unconfirmed |
|---|---|---|
| Own account prices | City's account-specific pricing page describes personal pricing through its website/app. PTS and City have combined websites. | Nigel's actual product prices, account template, cash/credit account type and whether branch access is already linked online. |
| Downloadable price list / CSV / XLS / product-price feed | A public Trade Price Guide exists; no current personal-price CSV/XLS export or public customer API schema was located. | Whether Nigel's account has a download button or his branch can produce a permitted machine-readable price file. A public catalogue is not his account export. |
| Saved/favourite product lists | City's Favourites/Joblist feature supports saved lists, editing, duplication, sharing and repeat orders. | Export format/download capability and whether any export carries personal prices, selling units or VAT. Sharing is not evidence of CSV export. |
| Order history | Account dashboard/app supports viewing/filtering past purchases, tracking and reordering. | CSV/XLS export of order lines and included fields. Even a genuine historical paid amount is not today's account price. |
| Quote files | City's tools page documents online branch quote requests and an emailed PDF reply. | Machine-readable quote export, exact fields, selling pack and validity in Nigel's actual file. No PDF parser implemented. |
| Invoices / statements / credit notes | Account-management pages document financial-document downloads. | Product-price export. Financial records must remain historical references unless City explicitly confirms current price evidence. |
| Contract purchasing reports | City's Integrated Solutions page describes an MI/KPI portal where contract customers can generate reports from captured purchasing data. | Eligibility for Nigel's ordinary trade account, any download format, and current account-product pricing. This is a contract-sector reporting offer, not evidence of an available personal price feed. |
| Commusoft live integration | Both City's partnership page and Commusoft's integration page confirm connecting a City account for real-time parts pricing within Commusoft. | Permission, commercial terms or technical contract for Nigel's custom app, availability of read-only merchant price/stock access, and any approved export/reuse from Commusoft. |
| Account-data/API request process | City provides branch/customer-service routes. Commusoft's public developer documentation describes keys for existing Commusoft private apps and OAuth partner onboarding. | No City self-service developer onboarding/API-key process found. A Commusoft key accesses Commusoft data; it does not automatically authorize direct City API calls or re-export of City pricing. |
| Other approved third parties | Commusoft is the named City-confirmed live-price route found in the researched official sources. | No additional City-approved price connector was established; generic claims by unrelated software vendors are not adopted. |

Public pages were researched only. No authenticated City/PTS page was scraped,
no session/cookie requests were made, and no undocumented endpoint was probed.
Research absence is not proof a private export or partner feed does not exist.
The public Digital Service Hub landing page returned HTTP 503 to the research
fetch; its individual account, order and tools pages were readable. No access
restriction was bypassed and no conclusions were guessed from the failed page.

Official sources checked:

- [City account-specific benefits](https://www.cityplumbing.co.uk/content/elevate-your-installation-business/exclusive-benefits)
- [PTS / combined account websites](https://www.cityplumbing.co.uk/content/pts)
- [Favourites / Joblist](https://www.cityplumbing.co.uk/content/job-list)
- [Purchasing tools / order history](https://www.cityplumbing.co.uk/content/elevate-your-installation-business/purchasing-tools)
- [Account management / financial downloads](https://www.cityplumbing.co.uk/content/elevate-your-installation-business/streamline-operations)
- [Integrated Solutions contract MI reports](https://www.cityplumbing.co.uk/content/integrated-solutions/solutions)
- [Online branch quotes / emailed PDFs](https://www.cityplumbing.co.uk/content/elevate-your-installation-business/our-tools)
- [Public trade guide](https://www.cityplumbing.co.uk/content/trade-price-guide)
- [City account FAQ](https://www.cityplumbing.co.uk/content/help-and-advice/faqs)
- [City's Commusoft partnership](https://www.cityplumbing.co.uk/content/commusoft)
- [Commusoft's City integration](https://www.commusoft.com/en-gb/integrations/)
- [Commusoft developer authentication](https://developer.commusoft.com/authentication-1985209m0)
- [City customer contact routes](https://www.cityplumbing.co.uk/content/contact-us)

## Best permitted route for the existing account

Recommendation: obtain a current price file directly from Nigel's existing City
branch/account manager before considering a live custom connector. This is a
practical request, not a claim that City guarantees a CSV service.

Nigel can use his normal existing login to check account pricing and whether
Pricing/Favourites/Order History offers a download. If branch access is not
linked online, City Customer Service can assist; do not open a new trade account.
Do not supply the login password to this application.

Ask the branch for a current account-specific price list for regular materials
as CSV/XLS, including product code, description, selling unit/pack, price,
VAT/rate and price/export date. Ask for manufacturer + MPN or GTIN if available,
and any expiry, branch, quantity-break or minimum-order restrictions. Do not
assume a price file contains these fields until a real sample is inspected.

If no price file exists, request a representative basket quote for 10–15 regular
products under the existing account. City documents emailed PDF branch quotes.
That provides real account-price evidence for inspection, but a PDF import path
still needs a real owner-supplied document and verified identity/pack/VAT fields.
It is not a complete price list or live feed.

Customer Service: 0330 678 0267 (Mon–Fri 08:30–17:00),
customerservice@cityplumbing.co.uk. Nigel can use his existing branch instead.
Keep the real account number in direct private communication with City. No
message was sent by this task.

For live access, ask City to route an enquiry to its digital partnerships team:
does the documented Commusoft relationship support a read-only custom-app
integration for this account? Request approval, supported scope/schema, test
environment, authentication, limits, pricing-unit/VAT/stock meanings and allowed
reuse. If Commusoft is the only offered route, evaluate the required software
relationship and terms separately; do not sign up, purchase, trial or request
credentials without Nigel's approval. No City endpoints have been invented.

## Export/import gate

Current state: **a City-specific CSV/XLS importer is not practical to implement
yet** because no export schema or real owner file is available. A branch PDF
quote is a documented available route; its actual format is likewise unknown.

Once Nigel provides a genuine City-generated file and reliable date evidence:

1. Inspect exact headers/dialect or document rows; map only observed fields.
   Expected fields (not assumed columns): City SKU, name, manufacturer, MPN/GTIN,
   selling unit/pack, price, VAT and export/validity date. Missing values remain
   unsupported/unknown; do not derive account discounts from public prices.
2. Ignore/redact account numbers, contact details and unnecessary financial data.
   Preserve original product/price/unit/VAT/date evidence for the mapping review.
3. Preview every row, price basis and separate normalized inc-VAT pack amount;
   validate identity, quantity breaks and dates before an explicit import action.
4. Critical malformed rows reject the entire batch. Identical rows/files are
   idempotent; snapshots append history without multiplying duplicates or
   reviving removed older products. The generic tested ingestion boundary exists.
5. Store `account_cached`, checked/exported time and import time separately. No
   import time may refresh an old price. Unknown VAT/unit/date/identity cannot
   enter confirmed comparison or quote selection. Never claim CSV prices live.
6. Public City offers remain `public_live`, in their existing independent source.
   Do not overwrite the public price history or legacy/manual material records.

Future live records may be `account_live` only after a genuine approved feed
connection and freshness/stock checks. A public page, invoice, PDF, exported
catalogue or manually copied account amount is not live account evidence.

## Proposed City account-price UI and quote contract

Separate visible sources for each exact product/pack:

| Card | Required presentation / action |
|---|---|
| City Plumbing account price | `Cached account price`, original inc/ex VAT amount, normalized inc-VAT selling-pack amount, pack, price-as-of date, imported date/age and stock uncertainty. Fresh confirmed cached choice requires explicit acknowledgement. No live BEST PRICE badge. |
| Stale City account price | Clear `STALE — refresh or reconfirm with City` warning. Keep visible as a reference; do not silently refresh its date or select it as current. Unknown VAT, selling pack or identity remains blocked. |
| City public price | Explicit `PUBLIC LIVE` label and check time; retain alongside the account card, even for the same City SKU. Never relabel it an account price. |
| Other public merchants | Existing product/pack/VAT checks and unavailable-merchant handling. Cached City cannot be a live winner against Toolstation. City/PTS is one merchant, never two for BEST PRICE counts. |

Buttons/fields must use safe text rendering, private authenticated responses and
no-store caching; do not reveal account numbers or account-source references in
public pages, PDFs, logs or browser credentials. No account UI has been wired.

Selecting a confirmed City account price must be an explicit owner action.
Comparison cannot overwrite the selected supplier or quantity. Save a private,
additive selected-price snapshot with `account_cached` provenance, original
VAT/amount, normalized pack amount, product identity, pack and age evidence.
Creation and editing must use that saved numeric selection until Nigel explicitly
changes it, without any legacy public-price lookup replacement. Editing quantity
alone must not drop the selection; editing product/pack identity must invalidate
it and require a new explicit choice. Keep the existing calculator and 25%
handling default; preserve explicit handling edits as well.

The current application selection path is `selected_public`; **do not pass
account choices through it and claim account provenance is preserved**. The
source-aware snapshot/create/edit path must be implemented and tested after the
real City file/feed exists. This pivot adds no request-model, calculator, quote
store, route, UI or startup migration changes.

## Test and readiness status

The generic foundation's canonical synthetic fixtures now use City Plumbing.
They are not sample City CSV rows and establish no City export column names.
Retained cases cover account-vs-public precedence, stale/unknown pricing, exact
identity/GTIN/MPN conflicts, packs, explicit VAT normalization, duplicate/atomic
imports, malformed rows, no database mutation during read-only comparison, and
unchanged calculator/quantity/manual choice/25% default.

Six additional City cases explicitly cover separate City account/public cards,
cached City vs Toolstation, stale City fallback to public comparison, original
ex-VAT pack amounts, no VAT inference from public prices and exact GTIN/MPN with
different merchant SKUs. Required suite: 212 tests (169 main + 43 foundation).
All 212 local Python tests and both Node suites passed. Final-head CI and the
complete Chromium result are recorded in PR #4 when available.

The existing **public** selected-price quote create/edit regression is retained.
It does not prove an account-price path: City account selection, source-aware
persistence and rendered account-card acceptance tests remain mandatory pending
implementation. Real-file malformed/duplicate/stale row tests also require the
actual City export and must precede staging approval.

Ready for next step: **YES — City data acquisition and permitted-route approval**.
Ready to implement an actual importer: **NO — supply a real City file first**.
Ready for staging: **NO — importer/account UI and create/edit gate are incomplete**.
No Wolseley account/export is required. Williams remains paused. Do not merge
or deploy without Nigel's explicit subsequent approval.

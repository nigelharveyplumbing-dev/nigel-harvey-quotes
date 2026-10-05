# Phase 2 account-price foundation — 5 October 2026

Status: dormant architecture implemented; merchant connections, real CSV parser,
upload UI and quote integration **not implemented or enabled**. No merge or
deployment authorized. Based on main `8ab4f6494de3823b4150fc611e698a91295faa56`
(the same application tree as approved `bb7790b`). PR #3's separate release-tool
fix is not included. Production PR #2 behaviour remains intact.

## Current owner priority — City Plumbing / PTS

Nigel has a City Plumbing trade account and no Wolseley account. City/PTS is the
first operational path. Wolseley remains an optional future connector; no
Wolseley account, export or onboarding is required for this PR. Williams is
paused until City is validated. Keep the generic foundation and public system.

See [City account route and implementation gates](city-account-pricing-route.md)
for the verified export/partner features, owner actions and City UI/quote design.
No City parser columns or live endpoints have been invented.

## Official merchant evidence

Only merchant-owned public documentation was researched. No registrations,
messages, terms acceptance, account creation, authenticated scraping, credentials
or merchant API requests were performed. Endpoint paths and JSON fields below
are intentionally absent: they have not been obtained from approved API specs.

| Merchant | Verified official capability | Access/next step | Not established |
|---|---|---|---|
| Wolseley | iHub account prices and stock; Get Price V2 includes terms prices; Get Stock V2; Get Branch V3. OAuth 2 client credentials. | Contact Connect/eBusiness, discuss requirements, provide account number privately and technical lead email, obtain portal registration approval, test app/product approval, key/secret and IP approval; test and agree go-live before production app approval. Request read-price/stock products only, never Submit Order. | Exact price/stock response fields, VAT/rate, price-unit/pack semantics, branch/warehouse stock meanings, rate limits, credentials, permitted request methods/URLs and required scopes. All require approved YAML/API documentation. |
| Wolseley My Prices | Official guide describes selectable product categories/information fields, purchased-product history over 36 months, emailed CSV within 48 hours to the account login's email. | Nigel exports using his own existing account and supplies the real file for inspection. | Exact columns, delimiter/encoding, decimal format, pack/unit, VAT, identifiers, generation time and price validity in Nigel's file. No schema guessed from the guide. |
| City Plumbing / PTS | Combined websites offer account trade prices; account help describes custom pricing, downloadable financial records and branch quotes. City's official Commusoft partnership page explicitly documents live parts pricing integration. | Ask existing account manager/digital team whether the documented partner route can be approved for Nigel's own app, or request an explicitly permitted machine-readable account-price export/feed and schema. | The Commusoft partnership does not grant this app access. No public developer specification or account-price CSV schema located. Financial downloads and public trade guides are not current personal price feeds. |
| Williams | Official site offers a trade account, quotation/account facilities and Trade Support for account help. | Ask existing account manager/Trade Support for permitted account-price export/feed/API plus schema/sample and usage terms. | No publicly documented account-price API/export found. Public product amounts cannot establish Nigel's account prices. |

Sources checked on 5 October 2026:

- [Wolseley API portal](https://api.wolseley.co.uk/)
- [Wolseley onboarding PDF](https://api.wolseley.co.uk/files/next-steps-onboarding.pdf)
- [Wolseley API support / OAuth / documentation access](https://api.wolseley.co.uk/help-and-support)
- [Wolseley versions / terms-price update](https://api.wolseley.co.uk/updates-api-status)
- [Wolseley My Prices official guide](https://www.wolseley.co.uk/wcsstore/Wolseley/Attachment/how-to-guides-main/30-My-prices.pdf)
- [City / PTS](https://www.cityplumbing.co.uk/content/pts)
- [City account options](https://www.cityplumbing.co.uk/content/create-an-account)
- [City FAQ](https://www.cityplumbing.co.uk/content/help-and-advice/faqs)
- [City's documented Commusoft live-pricing partnership](https://www.cityplumbing.co.uk/content/commusoft)
- [Williams site](https://www.tradeonlyplumbing.co.uk/)
- [Williams account/support contact](https://www.tradeonlyplumbing.co.uk/contact-us)

The API portal pages can be client-rendered: search-indexed official text and
the onboarding PDF supplied the readable evidence. Absence of a public spec is
not proof that a private partner integration does not exist.

## Implemented isolated foundation

`business/account_pricing.py` is never imported by the application, calculator,
config or existing public adapter. It creates no database on import, has no HTTP
transport, credentials, route or application startup hook. Tests alone exercise
its explicitly called functions in disposable storage.

The internal read-only connector Protocol exposes `read_prices_and_stock` for
supplier SKUs scoped by a local source reference. This is an application boundary,
not a claimed Wolseley API schema or operational connector. City/PTS will implement the same boundary once its permitted route is confirmed.
Williams remains paused; Wolseley is optional and is not a prerequisite.

Canonical records preserve:

- Supplier, supplier SKU, product name, validated GTIN and/or brand + exact MPN.
- Explicit positive selling-pack quantity; price per selling pack (no division
  of multipacks into unit prices to manufacture equivalence).
- Original decimal price, explicit GBP, VAT basis and rate where evidenced,
  normalized inc-VAT pack price using Decimal/half-up rounding.
- `account_live`, `account_cached`, `public_live`, `cached_public` or `manual`.
- Original checked/exported time, imported time separately, explicit expiry,
  computed age and current/stale/unknown status, and availability.
- Random opaque local source reference, never the merchant account number/email.

Unknown VAT, rate, unit basis or expiry remains unknown/reference-only; invalid
data is rejected. Supplier SKU alone never confirms cross-merchant identity.
Conflicting GTIN, MPN, brand, selling pack or explicit product specification
prevents equivalence. PTS and City are one merchant for comparison counts.

## Proposed additive storage (implemented but never activated)

A separate private SQLite sidecar, provisionally `account_prices.sqlite`, contains
`account_price_imports` (supplier, local source ref, original-file SHA-256,
normalized-evidence SHA-256, imported UTC timestamp, accepted row count) and
`account_price_records` (immutable validated record JSON, supplier SKU, import FK).
JSON contains the typed fields listed above. No secrets/raw files stored.

Initialization requires a **new** explicitly supplied file and refuses every
existing file, including the quote database. File permissions are 0600. No
production path is configured. No DDL in `init_db`, no changes to `quotes.db`,
public cache/history, legacy material records or quote/invoice rows.

Canonical batch storage revalidates every row, forces `account_cached`, checks
supplier/source scope, rejects conflicting duplicate SKUs, collapses identical
rows, and commits atomically. Identical files are idempotent: no second history
batch or refreshed date. The same file with different mapped evidence fails.
New snapshots append history; reads select only the newest whole snapshot for
the requested source, so removed or cheaper historical SKUs cannot reappear.
Readers use SQLite `mode=ro` and `query_only`; comparison itself performs no I/O.

This is the validated ingestion **boundary**, not an implemented merchant CSV
importer. The optional `inspect_wolseley_csv` guard remains closed; no Wolseley
file is required. The City importer requires a real owner-provided City format
first. No CSV headers/dialect or VAT mapping have been invented. CSV
format-specific validation/regressions are therefore pending. No live API
response persistence has been built; it requires the actual API contract.

## Comparison policy

For the same confirmed product/pack and merchant, prefer current authorized
`account_live`, then current `account_cached`, then `public_live`. Preference is
source-based even when the account amount is higher; do not quietly replace a
confirmed account price with a public amount. A cached preference is explicitly
a cached reference requiring owner confirmation, never a live BEST PRICE winner.

BEST PRICE/savings are calculated only across at least two distinct merchants
with preferred **live**, current, confirmed equivalent offers. Cached preferences
are excluded; their same-merchant public alternative is retained visibly but not
quietly substituted into the preferred set. This can reduce the live merchant
count and suppress the badge. Ties are allowed. A stale/unknown/blocked account
offer does not suppress a valid public alternative.

Different authorized account feeds with conflicting equal-time evidence fail
closed; no cheapest-price resolution of ambiguous records. Newer evidence of
the same source supersedes older prices. Comparison returns a projection, does
not mutate input records and echoes manual supplier choice without selecting or
changing a form. Cached public/manual prices are references only.

Expiry must be explicit; conservative internal freshness caps are 15 minutes
for live and seven days for imported account references, measured from the
original check/export time, never import time. These configurable policy limits
are **not merchant validity guarantees**. An absent reliable export time must
be rejected/quarantined by the future CSV reader; file mtime, purchase-history
date or import time must not pretend to be a price check. Even a fresh price is
not proof of stock: unknown stock is labelled unconfirmed; out-of-stock,
preorder, backorder and unavailable offers cannot be preferred or win.

## Proposed UI / quote work (not implemented)

Keep today's public comparison intact until an approved opt-in Phase 2 route is
tested. Add distinct account/public cards, source/date/age, VAT and price-unit
labels, selling-pack quantity, expiry and stock evidence. Use text rendering;
never inject product values as HTML. Offer an owner-only import preview with
row-specific errors, confirmed mapping/VAT/unit/date before any commit, and
duplicate/stale warnings. Upload size/row limits exist at the canonical boundary;
CSV encoding/field/row limits and formula-safe exports remain future work.

Suggested labels: `ACCOUNT LIVE — checked …`; `ACCOUNT CACHED — imported …,
prices as of … — confirm before use`; `PUBLIC LIVE`; `CACHED PUBLIC`; `MANUAL`.
Unknown VAT/unit/identity remains unselectable for live comparison. No automatic
merchant change; cached selection must explicitly acknowledge its provenance.

Quote integration must save an additive selected-price snapshot with source,
account-source local reference, identity, pack, amount/VAT, checked/imported time
and confirmation state. It must preserve existing numeric selection persistence
and quantity, and prevent legacy live lookup from replacing an explicit choice.
Do not feed account choices into today's `selected_public` provenance path and
mislabel them: the future source-aware selection needs its own tested extension.
No quote maths, quantity, supplier choice or 25% default is changed here.

## Security / rollout

No network calls or merchant writes exist in the foundation. OAuth client ID/
secret and real account binding will require explicit approval and environment
secrets; never repository, browser storage, logs, tests or uploaded raw evidence.
No password-based account scraping. Future transport must use approved documented
read operations, HTTPS, strict hosts/redirects/timeouts, token redaction and
separate stock/price scopes. OAuth token exchange is not an ordering facility;
do not assume API read operations use GET until the YAML contract is reviewed.

Server authentication must authorize the local account source before calling the
connector/comparator/store. Opaque refs are not authorization tokens. Future
account-price responses must be private/no-store and excluded from public quote,
invoice/PDF metadata and logs. Access/retention/backup requirements for the new
private sidecar must be agreed before provisioning. No real account information
appears in synthetic tests.

No staging or production deploy, main update, account registration, supplier
contact or terms acceptance occurred. This branch is draft architecture only.
Staging integration and data writes require the owner's subsequent approval.

## Validation and remaining gate

43 foundation tests plus all 169 main tests: **212 local Python tests passed**.
The canonical synthetic fixtures are City-first; six additional cases cover
City cached vs City/Toolstation public sources, stale fallback, VAT, packs and
exact identity. Malformed-row batch atomicity and duplicate imports remain tested.
Pre-pivot head `12b01d6` passed all 206 tests and complete Chromium in hosted CI.
Final pivot-head CI/Chromium status is recorded in PR #4 when available.
Existing Node comparison and material-selection tests passed. Tests cover source
precedence, cached-vs-live, stale/unknown age, VAT, pack and identifier conflicts,
source scope, stock exclusion, PTS deduplication, malformed canonical records,
duplicate/atomic imports, real-CSV fail-closed guard, append-only snapshots,
database read-only byte integrity, unchanged quote calculation/quantity/manual
supplier/25% handling. CSV parsing against the real merchant format is untested
and deliberately not implemented.

The local workspace has no installed Chromium executable; the full repository
Chromium gate must pass in hosted CI at the exact draft PR head. The architecture
does not alter rendered UI, so that workflow tests existing app regressions,
not a nonexistent Phase 2 UI. No staging validation claimed.

Next owner actions (City first):

1. Use the existing City account to view account pricing and check whether its
   favourites/order/pricing screens offer an export. No new merchant account is
   needed; branch-only access may need linking through City Customer Service.
2. Ask the existing City branch/account manager for a permitted current account-
   price CSV/XLS export or price file, with explicit VAT, selling pack and date.
   If unavailable, City's documented emailed branch PDF quote can supply a
   representative basket for inspection; it is not a live price feed.
3. Obtain a real file and its reliable generation/validity date, then implement
   only that observed format. No importer or account-price selection is enabled
   before these provenance/identity/unit checks and the full acceptance tests.
4. If live access is wanted, ask City about the documented Commusoft partnership
   and permission for Nigel's custom app. No registration, subscription, trial,
   supplier contact or credential use is authorized by this research step.
5. No Wolseley file/account is required. Williams stays paused. No staging or
   production deploy or merge without explicit subsequent approval.

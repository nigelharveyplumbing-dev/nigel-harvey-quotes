# City Plumbing / PTS owner-captured account pricing

6 October 2026 — draft PR #4, feature/account-trade-pricing-phase2.
No merge, deployment, merchant login reuse or unattended account scraping.

## Real evidence and initial data

Nigel supplied 23 personalised prices from the official City iOS app. All are
GBP, each, ex VAT. Nigel confirmed the capture date as 6 October 2026; no exact
time was supplied. Date-only evidence is retained explicitly, normalized to
the start of that UK date for conservative age checks. Import time is separate.
The initial private JSON file is an app-owned owner-capture format, not an
invented City CSV export or live feed.

The private dataset contains City codes, supplied descriptions and prices,
manufacturer/brand, 21 supplied MPN/model tokens, and two empty MPNs (950278 and
793487). All GTINs are empty. A supplied model token is not an invented GTIN or
manufacturer alias. Current City public pages may use other model identifiers:
conflicts remain unconfirmed until independently resolved. Each means one
selling item: a 3m pipe is priced for the whole 3m length, not per metre.

Original ex-VAT decimal prices are preserved; a separate inc-VAT selling-item
amount is calculated at 20%, rounded half-up to pennies. Every row is
account_cached with city_app_owner_capture provenance. Availability is always
unknown; an optional stock note is point-in-time evidence, never current stock.
The real account amounts and private file/database are not committed to this
public repository. Fixtures use the real identities and deliberately altered
prices. No merchant account number, owner details, credentials or tokens occur.

## Implemented owner workflow

Each material row has "City account prices — add / update / choose".

1. Find a saved capture by City code or exact product description.
2. Recheck the amount in Nigel's City app. Add/update code, product name,
   ex-VAT price, each/explicit pack size, checked date/time (UK time), and optional
   stock note. Brand, MPN/model and GTIN fields are optional, never synthesized.
   Existing-row Update prepopulates identifiers without advancing price age.
3. Preview normalized prices, units, dates and the whole initial JSON batch.
   Preview does not create or modify any database.
4. "Save confirmed owner capture" explicitly commits a validated batch.
   Critical malformed rows reject the whole batch. Identical rows collapse;
   conflicting duplicates fail. Repeat imports/updates do not append duplicates
   or refresh age. Older or superseded evidence cannot silently replace newer
   evidence. New updates retain every other active product and append history.
5. The phone-friendly cached card shows City code, original ex-VAT price,
   normalized inc-VAT price, each/pack, checked date/age and stock uncertainty.
   Seven days is an internal conservative stale limit, not City validity.
   Stale rows remain references; new selection is blocked until rechecked.

The endpoints GET/POST /api/city-account-prices and POST
/api/city-account-prices/preview inherit the existing Basic Auth and origin
checks. Responses are no-store. There are no new credentials, merchant requests,
background refreshes, account-registration actions or external writes.

## Comparison and quote contract

Existing public merchant cards, live eligibility, BEST PRICE counts and
Screwfix-unavailable handling remain intact. Account cards are an additive,
separate account_results response. A fresh cached price can show "CHEAPEST
OBSERVED — CACHED ACCOUNT PRICE (not live)" when supported by exact live public
matches; it never receives the existing BEST PRICE badge. Public amounts are
never relabelled as Nigel's account prices. Savings use normalized whole-selling-
pack inc-VAT amounts; negative savings explicitly say account pricing is more.

Cross-merchant equivalence requires GTIN or brand + MPN, matching pack and
nonconflicting specifications. City SKU is local to City/PTS; a missing MPN can
match the same City code only with exact description and no conflicting identity.
It cannot establish Toolstation/Selco equivalence. PTS is not a second merchant.
Different packs, conflicting GTIN/MPN/brand/specifications or unknown pricing
basis do not generate claimed savings. Out-of-stock, preorder, backorder,
unavailable, manual and cached-public references cannot establish a live match.

Choosing a cached price requires explicit acknowledgement of cached pricing and
unknown stock. Only that action populates the City product, supplier and price;
quantity remains unchanged. No product URL is guessed. The City code is in the
private selected_account_price snapshot. A saved known City URL, if supplied,
must match its code. Changing name, supplier, URL or amount invalidates the held
selection; quantity edits preserve it. Selecting a public card clears the
account choice.

The calculator uses the selected normalized numeric amount with account_cached
provenance and bypasses the legacy public lookup. Request and calculated line
both preserve the snapshot. Reopening/editing or updating the capture library
cannot replace the quote's chosen price. Existing stale saved selections remain
held and show age warnings; they are not silently repriced. "Update price"
opens the owner-capture panel for an account-selected row.

Existing arithmetic, charging rules, quantity, manual choices, explicit handling
edits and the 25% default remain unchanged. No existing quote/material/public
price records or schemas are rewritten.

## Storage, privacy and staging gate

The generic account foundation is reused. On the first explicit save only,
a private city-account-prices.sqlite3 sidecar is created beside the configured
quote database, with 0600 permissions. It contains account_price_imports and
immutable account_price_records snapshots. A local opaque source reference is
not Nigel's merchant account identifier. Reads use mode=ro and query_only.
An interprocess lock covers initial creation and SQLite BEGIN IMMEDIATE covers
atomic snapshot merge. App startup and read-only comparison create no files.

Existing quote backups remain unchanged: future staging/release restoration
must include the new private sidecar and its retained private input file as well
as quotes.db. Do not merge/provision/deploy without subsequent owner approval.
The initial real captures have been validated into a private local store only;
no staging/production data is seeded or modified by this commit.

## Tests and remaining gate

Full Python, both Node and complete Chromium gates are required at the final
PR head. New coverage includes all 23 real identities with sanitized prices,
VAT/rounding, missing identifiers, exact/conflicting identities, selling packs,
City/Toolstation/Selco public comparisons, stale and blocked stock references,
atomic preview/import/update, duplicates, read-only byte integrity, auth/origin
protection, explicit account selection and quote create/reopen/edit persistence.
Chromium exercises preview/save/select/create/edit in the rendered app at a
390px mobile viewport and retains all previous public workflows.

Local validation: 229 Python tests, both Node suites and full rendered Chromium
workflows passed. Full Chrome could not create a process-singleton socket in the
workspace; Chromium 141 headless shell ran the same complete workflow cleanly,
with no page/console errors, failed requests, failed responses or outbound calls.
Final-head hosted CI is recorded in PR #4 rather than claiming it in advance.

Once these gates pass, the implementation is ready for an approved staging
trial: import the private file through preview/save and validate current
public comparisons. No staging or production validation is claimed here.
The PR remains draft, unmerged and undeployed. Wolseley is optional future work;
Williams remains paused.

## Documented future integration options

City officially supports personal prices through its website/app, saved lists,
order tools and financial-document downloads. A personal CSV/XLS price export
format remains unconfirmed. Emailed branch PDF quotes are documented.
City and Commusoft document live prices within Commusoft; that does not authorize
this custom app or provide a documented direct City API contract.

Normal City login was offered to the owner in the Work browser; its login frame
returned HTTP 403. No access protection was bypassed and no cookie/token was
copied. Owner-provided app captures now supply the first practical route without
requiring an export. Any future CSV/PDF parser must inspect a genuine file first;
any live connector requires documented permission and separate approval.

Official sources researched 5 October 2026:

- [City account benefits](https://www.cityplumbing.co.uk/content/elevate-your-installation-business/exclusive-benefits)
- [City / PTS](https://www.cityplumbing.co.uk/content/pts)
- [Favourites / Joblist](https://www.cityplumbing.co.uk/content/job-list)
- [Order tools](https://www.cityplumbing.co.uk/content/elevate-your-installation-business/purchasing-tools)
- [Financial documents](https://www.cityplumbing.co.uk/content/elevate-your-installation-business/streamline-operations)
- [Branch quotes](https://www.cityplumbing.co.uk/content/elevate-your-installation-business/our-tools)
- [City Commusoft partnership](https://www.cityplumbing.co.uk/content/commusoft)
- [Commusoft integrations](https://www.commusoft.com/en-gb/integrations/)
- [Commusoft developer authentication](https://developer.commusoft.com/authentication-1985209m0)

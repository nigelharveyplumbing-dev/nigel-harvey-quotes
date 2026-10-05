# Best Trade Price comparison — audit and implementation

5 October 2026. Feature branch: `feature/best-trade-price-comparison`.
Production was read back from Render at `630eefa4baa9aa3548690848ac240a74b1607c0d`, deployment `dep-daui7j7avr4c7399uqt0` (live). Production tracks `main`; auto-deploy is off. No production changes or database access were performed.

## Existing production system

The production code already has four merchant search adapters: City Plumbing, Screwfix, Toolstation and Selco. Topps Tiles is also an existing selectable supplier with a URL price scraper, but is not a merchant-search adapter. There is no authenticated trade-account price integration in these adapters.

`business/merchant_search.py` discovers product links, checks titles against search intent and inspects public pages. Toolstation has a filtered radiator-category discovery fallback. This existing search writes discovered prices into the material cache/history.

`app.fetch_tracked_price` tries a public scrape, then a saved live/last price, then the manually entered fallback. Successful and fallback lookups update the cache and price history; quotes also retain their request/result data. The cache records last price, last live price, last manual price, status, last check and last successful live time.

`business/quote_calculation.py` owns quantity, partial/consumable charging, job markup and procurement arithmetic. The default handling percentage is **25%**, with existing selectable percentages and existing site-survey overrides unchanged. Customer documents, quote/invoice persistence, supply responsibility and material-selection rules are untouched.

### Findings

- Existing search `strict_match` establishes relevance to a query, not proof that two merchants sell the same manufacturer product. Dimensions alone do not establish radiator equivalence.
- Existing supplier SKUs are not universal manufacturer identifiers.
- The legacy scraper may read metadata, visible prices or the lowest pound amount on a page, and does not carry a reliable common VAT basis. The Toolstation visible fallback can select an ex-VAT amount. Related products, delivery charges, packages and price ranges require stricter evidence for comparison.
- Saved material rows do not establish VAT basis or authenticated account provenance. Record modification time does not necessarily equal manual-price verification time.
- Branch starting commit `0b38afd` added a global lowest-price badge based on query matches and positive prices. That metadata/ranking change is replaced by an independent comparison path; the original production merchant search remains byte-identical to `main`.

These legacy behaviours are recorded, not changed in this upgrade, to preserve the requested quote/production behaviour.

## Implemented behaviour

Every material row has a **Best Trade Price — compare suppliers** button, using the current description and optional saved product URL. The new authenticated `GET /api/best-trade-prices` endpoint is read-only. It never calls the legacy scraper, price-cache upsert, quote calculation or any save endpoint.

Comparison uses existing merchant search parsers only for discovering candidate URLs. Each product's own page is inspected separately. Search-card prices, arbitrary page amounts and aggregate `lowPrice` values are not accepted as comparison prices.

Public merchant prices are labelled **Live public price** with a UTC check time. Historic saved live prices are **Cached public price**, manual values are **Manual price**, and unattributed legacy last-price values are **Cached price — source unverified**. References retain their true available timestamps; a record update is not presented as a price check.

To compare products:

1. Require a checksum-valid nonzero GTIN, or the same manufacturer brand plus the same MPN. Preserve meaningful MPN punctuation. Merchant SKU and a fuzzy relevance score do not qualify.
2. Require matching package counts. Explicit conflicting counts and unspecified packs/kits/bundles are excluded. A normal manufacturer product with no package/bundle qualifier is treated as one sellable item; pack prices are never divided into an attractive but unpurchasable per-item price.
3. Reject contradictory explicit dimensions, panel types, finishes, connections, materials, potable/heating classifications or pressure ratings, even if identifiers match. Cross-brand substitutes and dimensional-only radiator matches are not automatically declared equivalent.
4. Require a single unambiguous GBP offer attached to the main product page. Conflicting headings/structured identity, recommendations, variant price ranges, expired offers, quantity discounts and identified membership-only prices do not qualify. Preserve product-variant URL parameters and reject per-length/area/weight price specifications rather than treating them as pack prices.
5. Require a known VAT basis, from explicit structured evidence or VAT text attached to the same amount. Explicit ex-VAT amounts are converted at 20% using decimal penny rounding; all comparison prices are displayed including VAT. Conflicting/unknown VAT leaves an unranked reference.
6. Highlight **BEST PRICE** only where at least two different merchants have confirmed equivalent, currently checked prices. Ties are highlighted. Savings are per matching pack within that group. Explicitly out-of-stock, preorder and backorder offers are excluded; unknown stock is labelled as unknown and requires checking.

With a saved product URL, comparison is anchored to that product. Failure to inspect the anchor prevents best-price badges. Without an anchor, separate exact-product groups are labelled separately; there is no global winner across unrelated models.

Merchant requests run across four workers with a 22-second per-merchant budget and bounded candidate counts. HTTPS hosts are explicitly allowed; credentials, nonstandard ports and every unsafe redirect are rejected before the next request. No browser session or login is reused. Missing/inaccessible merchants leave search links available.

Supplier choice remains manual. **Use this product and price** changes only the current unsaved row's product, supplier, URL and editable price; quantity and handling percentage stay unchanged. Cached/manual values are not offered as confirmed live choices. A material edited during a search requires a new comparison.

### Practical limits

- Public prices are not Nigel's negotiated trade-account prices. Account pricing is explicitly disconnected.
- Delivery, minimum orders, collection travel/time, branch-specific stock and total basket costs are not included. This is a best comparable product price among observed offers, not a guaranteed cheapest delivered basket.
- Discovery is bounded to three candidates per merchant, plus an optional anchor; blocked or client-rendered pages can produce incomplete coverage. No live merchant scraping was exercised from the restricted local test environment.
- Pages lacking authoritative identity, package or VAT evidence may show no confirmed comparison. Manual product selection and the existing price workflows remain available.
- Choosing a comparison price does not lock the price for a later quote. Existing Update price and quote calculation retain their original live/cache/manual precedence and may obtain a different/newer amount, including the legacy VAT limitation described above. Review the generated quote before sending.

## Legitimate additional source investigation

These are documented integration opportunities, not enabled adapters. No registrations, terms acceptance, purchases, enquiries or credential changes were performed.

| Source | Verified public evidence | Suitable next route |
| --- | --- | --- |
| Wolseley | Official developer portal offers real-time product prices/stock. Official support documents OAuth2 client credentials and documentation available after registration; access requires application approval and an API key. | Request authorised read-only price/stock access, obtain the actual approved API specification and map Nigel's account plus VAT/unit/identifier fields. No guessed endpoints or keys. |
| Wolseley My prices | Official guide offers a CSV of purchased products and account prices, based on purchase history, emailed within 48 hours. | Owner-provided CSV import with a format preview, identity/unit/VAT checks, and import date. Label account imports as cached, never live. |
| City Plumbing / PTS | Official City Plumbing page confirms discounted trade prices through an online account. Existing scraper has no login. | Obtain a permitted account export/feed or confirmed integration; public pages remain public prices. |
| Williams | Williams directs online shopping to tradeonlyplumbing.co.uk. Some public products expose ex-VAT prices; others require sign-in. | Verify trade-account access and a permitted feed/export or documented API with Williams before integration. Do not bypass sign-in or claim personalised prices from visible public offers. |
| BuyTrade | Official website describes free registration, negotiated trade-only pricing, multiple merchants, real-time stock and collection/delivery. | Owner registration and a provider-approved integration/export. No public third-party integration API was verified in this investigation. Platform prices must not be represented as Nigel's own merchant terms. |
| BuildCompare | Own site describes public merchant comparisons during soft launch; advertiser page mentions merchant data-feed options. | Useful independent manual comparison/link-out. A merchant feed option does not establish permission to consume their comparison results; no documented consumer integration API was verified. Ask for licensed integration details before ingesting data. |

Primary source links checked on 5 October 2026:

- Wolseley API: https://api.wolseley.co.uk/ and https://api.wolseley.co.uk/use-cases
- Wolseley authentication/docs: https://api.wolseley.co.uk/help-and-support
- Wolseley access terms: https://api.wolseley.co.uk/terms
- Wolseley My prices guide: https://www.wolseley.co.uk/wcsstore/Wolseley/Attachment/how-to-guides-main/30-My-prices.pdf
- City Plumbing / PTS: https://www.cityplumbing.co.uk/content/pts
- Williams online shop: https://williams.uk.com/shop-online/ and https://www.tradeonlyplumbing.co.uk/
- BuyTrade: https://www.buytrade.co.uk/
- BuildCompare: https://buildcompare.co.uk/ and https://buildcompare.co.uk/advertise

## Validation and release gate

Baseline production suite: **113 tests passed** before implementation. After implementation: **144 automated tests passed**, including the full existing Python/Node tests and 31 new comparison tests. The existing quote-calculation golden fixtures are unchanged. The legacy UI snapshot still checks its original hash outside the separately tested additive comparison UI. Inventory checks include the new authenticated route. Pure-helper imports restore the module registry so existing tests load their isolated configuration.

New tests cover exact manufacturer identity, local SKU differences, wrong brands/models, conflicting dimensions/connections/pressure/application, package counts, GTIN checksums, MPN punctuation, currency, VAT conversion/conflicts, unrelated page prices, ambiguous offers, expiry/membership/quantity conditions, stock exclusions, ties, single-merchant cases, anchor failure, historic/manual provenance, redirect/URL validation, UI opt-in/stale input/errors, authentication and a byte-for-byte disposable database dump before/after comparison.

Commands:

```sh
python -B tests/run_stage6_local.py --python-only
node tests/test_trade_comparison.cjs
node --check static/app.js
node --check tests/run_local_browser.mjs
git diff --check
```

The real Playwright browser runner reports **INCOMPLETE locally: no preinstalled Chromium**. A tests-only GitHub Actions workflow installs Chromium in an isolated runner and executes `python -B tests/run_stage6_local.py`, including the original browser workflows plus a new synthetic comparison interaction. The workflow has read-only repository permissions and no deployment steps. Its outcome must be checked before marking the full release gate passed.

No merge, production deployment, production database write, migration or automatic rollout is authorised. After all required checks pass, Nigel must approve the concrete implementation before any merge or production deployment.

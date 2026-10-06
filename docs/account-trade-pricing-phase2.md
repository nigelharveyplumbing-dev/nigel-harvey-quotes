# Phase 2 account pricing — 6 October 2026

Draft PR #4 is City-first. The generic account-pricing foundation is now used by
an explicit City owner-capture workflow. No merge or deployment is authorized.
Main/production remains 8ab4f6494de3823b4150fc611e698a91295faa56. PR #3's separate
release-check tooling is not included.

See [City owner-capture implementation](city-account-pricing-route.md) for the
actual provenance, storage, authenticated UI, comparison, snapshot persistence
and validation contract. A real CSV is no longer a prerequisite for this owner-
supplied app-capture route. No City export columns or HTTP API were guessed.

## Generic architecture retained

business/account_pricing.py defines validated GBP decimal records, original
VAT/unit amounts, separate normalized inc-VAT selling-pack amounts, exact
identity and stock/freshness rules. Sources remain account_live, account_cached,
public_live, cached_public and manual. Account source refs are opaque local
identifiers, not merchant account numbers or authorization credentials.

The pure generic comparator retains source precedence, conflict checks,
authorized-source scoping and distinct-merchant live winner rules. The City
capture adapter adds independent cached cards alongside the unchanged public
comparison results. No cache is upgraded to live, and no lower amount resolves
an uncertain identity. Unknown VAT/unit/expiry remains unconfirmed.

The internal read-only connector Protocol is an architectural boundary, not a
merchant endpoint/schema. No operational live account connector, session reuse,
OAuth credential, merchant write, background scrape or account registration
exists. Private sidecar initialization is explicit; no startup DDL/migrations.

## Optional Wolseley route — future only

Nigel has no Wolseley account; neither an account nor a CSV is required.
The optional My Prices format guard stays closed until an actual owner export
is inspected. Official documentation researched 5 October 2026 establishes:

- iHub account prices and stock; Get Price V2 with terms prices, Get Stock V2,
  Get Branch V3, OAuth 2 client credentials.
- Connect/eBusiness onboarding, account details supplied privately, technical
  lead, portal/test-app/product approval, keys/secrets and IP approval, testing
  and agreed go-live before production approval.
- My Prices selectable fields/categories, purchase history over 36 months and
  an emailed CSV within 48 hours.

Exact endpoints, response fields, VAT/pack/stock semantics, scope and limits
have not been obtained from approved specifications. No registrations, supplier
messages or acceptance of terms occurred.

- [API portal](https://api.wolseley.co.uk/)
- [Onboarding](https://api.wolseley.co.uk/files/next-steps-onboarding.pdf)
- [Support](https://api.wolseley.co.uk/help-and-support)
- [Versions / terms prices](https://api.wolseley.co.uk/updates-api-status)
- [My Prices guide](https://www.wolseley.co.uk/wcsstore/Wolseley/Attachment/how-to-guides-main/30-My-prices.pdf)

## Williams — paused

Official account/quotation/support facilities exist. No public account-price API
or export format was established. Do not derive personal prices from public
pages or bypass sign-in. No operational Williams integration is included.

- [Williams](https://www.tradeonlyplumbing.co.uk/)
- [Trade support](https://www.tradeonlyplumbing.co.uk/contact-us)

## Security and rollout

The City's real owner capture file and private local store contain no account
number, credentials, cookies or tokens and remain outside the public repository.
Sanitized fixtures alter prices. Existing authentication, origin protection,
HTTPS policy and public merchant validation are preserved.

No quote/public-price schema migration or existing-data rewrite is needed.
After approval, staging must validate private sidecar storage/restoration,
the owner file preview and explicit save, real public comparison, and quote
selection persistence. Existing quote backup behavior is unchanged; the new
sidecar/input must be included separately in the restoration plan.

All Python, both Node and full Chromium workflows must pass at final-head CI
before recommending staging. The PR remains draft and neither staging nor
production is deployed by this implementation. Wolseley/Williams/live account
work remains outside the current City owner-capture scope.

# BuyTrade investigation — 6 October 2026

Draft PR #4 remains City-first and undeployed. This is a documentation/design
record only: no BuyTrade connector, capture importer, new runtime source type,
credential, background job or quote behaviour is implemented.

## Official findings

| Topic | Established public evidence | Unresolved |
| --- | --- | --- |
| Merchants | BuyTrade's current homepage names City Plumbing, Wolseley, James Hargreaves and Toolstation. | Exact products/branches exposed to Nigel and any additional merchants. |
| Pricing | Homepage describes procurement-negotiated terms checked monthly. | Which pricing basis applies to each offer in Nigel's session; equality with his City price is not proof. |
| Credit linking | FAQ supports existing City/Wolseley credit accounts; City validation can be automatic. | Nigel's City account type and current link state. Do not create/link an account during inspection. |
| VAT | Software prices are ex VAT according to the terms. | Verify visible offer's unit/pack and any displayed VAT totals. |
| Stock | Homepage advertises real-time branch availability. Terms describe estimates rather than guarantees. | Per-offer branch, stock/fulfilment status and checked time in Nigel's account. |
| Ordering | Card purchases contract with BuyTrade; credit purchases contract with the fulfilment supplier. | No order, basket submission, product request or payment is authorized. |
| Exports/API | No published BuyTrade price API, CSV/XLS schema or product-feed contract found in official pages/help reviewed. | Account download/share controls and private partner access require confirmation. |
| Partners | TradeHelp documents a direct BuyTrade link and PartsArena ordering/stock linkage. | Neither grants technical access or reuse rights to this app. |

BuyTrade terms require Buying Group membership for credit linking. They describe
negotiated cash-account lists and possible discounted credit terms; these are
not evidence that an offer equals Nigel's existing City account price.

The terms prohibit systematic/automated collection and republication in another
app, as well as commercial copying. Search/stock use is intended for genuine
ordering and search-only use can lose access. Descriptions may match products
of similar specification, so a grouped result alone does not establish exact
equivalence. A private manual-capture feature also needs reuse permission.

## Authenticated inspection gate

The Work browser opened the official app and reached its normal TradeHelp
sign-in screen. Nigel must complete login himself. No authenticated products,
account prices, merchant links or exports have been inspected yet. No password,
cookie, token or authentication URL is recorded here.

After login, inspect visible account/link indicators without saving settings;
then use normal UI interaction for a small representative procurement sample.
No automated basket harvest, authenticated scraping, protected API probing,
session transfer or request replay is permitted. Record only visible fields.
Check genuine download/share controls without creating an order or requesting
a quote from a merchant.

For each independently confirmed exact product, retain privately:
product, City code/account capture amount and date, BuyTrade offer amount,
original VAT basis, normalized selling-pack inc-VAT amount, brand/MPN or GTIN,
pack/unit, fulfilment merchant, branch/stock note, payment/pricing basis where
explicit, source URL without session data, checked time and difference.
Missing identifiers, stock, units and prices remain unavailable, not inferred.
Do not publish Nigel's personal prices, account identifiers or captures to this
public repository. No BuyTrade sample price or saving is established yet.

Candidate products from the existing City evidence include Wednesbury
X015L-3/X022L-3, Plumbright 78445/78450/78705/78015, Wavin 4Z081/4Z104W/5Z163W/
5Z190W/5Z160W, and Polypipe WS11W/WS12W/WS16W. Confirm the same brand/model and
selling pack independently. Different descriptions, model conflicts or generic
copper/waste alternatives do not establish a match.

## Proposed architecture — permission required, not implemented

- Keep the City owner-capture store and City public-live adapter unchanged.
- Introduce a distinct BuyTrade provenance channel: buytrade_cached for
  permitted owner captures/exports; reserve buytrade_live for a documented,
  authorized feed with current price/stock semantics.
- Keep source platform, fulfilment merchant and pricing basis separate.
  Possible basis values are negotiated framework, explicitly linked credit
  pricing, or unknown; do not relabel unknown offers as Nigel's City pricing.
- Retain original decimal price/VAT basis, a separate normalized inc-VAT whole-
  selling-pack price, supplier SKU, brand/MPN/GTIN evidence, pack/unit, price
  checked time, source method and expiry. Do not retain merchant account
  numbers, cookies, tokens or owner contact details.
- A linked-account indicator may be recorded as a non-identifying state only
  when visibly confirmed. It does not itself prove the pricing formula.
- Stock in an owner capture is point-in-time reference. Cached data gets age/
  stale warnings and no LIVE BEST PRICE badge. Unknown VAT/identity/pack blocks
  claimed savings and selection until confirmed.
- Compare only exact identities and matching selling packs. Calculate savings
  from normalized comparable amounts, separately from delivery/cashback.
- Do not count City through BuyTrade and City direct as two independent
  fulfilment merchants for the existing live-winner gate.
- If permission later allows quote selection, require an explicit choice and
  retain a separate BuyTrade selection snapshot through create/reopen/edit.
  Preserve supplier choice, quantity, arithmetic and 25% handling. Never reuse
  the City-only selection label or silently fall back to a public lookup.
- Credentials for any future approved connector require a separately reviewed
  integration/secret design. A browser session is not an integration contract.

## Practical permission request

Contact BuyTrade/TradeHelp using the official BuyTrade homepage contact form or
01978 666 888, Monday–Friday 08:30–17:00. No message has been sent.

Ask for read-only third-party integration or permitted private owner export/
capture rights for Nigel's quote app; permitted storage/display/retention; a
documented interface or export and access process; price-basis definitions
(framework versus linked City account); VAT/unit/pack/identity fields; merchant/
branch/stock/freshness semantics; rate limits; and read-only authorization that
does not permit orders or expose passwords/sessions. Obtain their written
answer before implementation. Do not guess endpoints or create new accounts.

Recommendation pending account inspection: keep PR #4's implemented City route;
use BuyTrade in its normal browser for procurement comparisons. Do not ingest
BuyTrade prices or add unattended retrieval without the required permission.

## Sources reviewed

- [BuyTrade homepage](https://www.buytrade.co.uk/)
- [FAQ: accounts, favourites and searching](https://www.buytrade.co.uk/buytrade-faqs/)
- [BuyTrade software terms](https://www.buytrade.co.uk/terms-and-conditions-of-use/)
- [Electronic payment terms](https://buytrade.co.uk/electronic-payment-order-terms-and-conditions/)
- [Official getting-started help](https://support.tradehelp.co.uk/article/get-started-with-buytrade)
- [TradeHelp terms: direct link](https://www.tradehelp.co.uk/tradehelp-terms-of-use/)
- [PartsArena partner link](https://www.tradehelp.co.uk/partners/infomill-parts-arena-pro)
- [TradeHelp accounting export](https://support.tradehelp.co.uk/article/quickbooks-integration)
  is a customer-invoice integration, not a merchant-price export.

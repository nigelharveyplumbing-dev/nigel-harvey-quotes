# Enquiry source and revenue — Stage 2

Development and local validation only. Base: `c4f57d379e3463fc414814b43ca0e81f8e5a68c7`; feature: `feature/enquiry-source-revenue`.

## Model and owner workflow

`enquiry_origins` stores an immutable original marketing classification separately from the original contact channel. A new enquiry creates a new origin even when Nigel explicitly selects an existing customer. No customer matching by name, address or telephone is used once tracking is activated. Existing legacy customer relationships remain untouched.

The authenticated app adds **Source & revenue**. Its panels cover original-source evidence/corrections, quote outcomes and job milestones, dated payments, aggregate reports and bounded historical review. Quick Add gains contact channel, classification and explicit existing-customer ID. The existing quote form also supports explicit customer selection by ID. Shared-account audit entries identify the configured owner account; they do not establish a separate human identity for each operator.

Unknown manual enquiries stay **Unknown**. Website submissions start **unconfirmed**. Synthetic Test is a separate record classification, requires a reference and is excluded from canonical business metrics. Historical rows start **legacy**. A captured source is never overwritten: optimistic revision checks and append-only corrections change the effective classification, with reason, account, timestamp and channel history. Later interactions do not change the original source. A correction restates all linked source reporting; earlier captured evidence remains available.

Quotes inherit the origin from a validated lead; standalone quotes receive a separate origin. Edits cannot replace the lead/customer relationship or original creation time. Jobs validate lead, quote and invoice origins. Invoices inherit the quote origin, with an explicit job relationship for additional invoices. Existing primary invoice links remain available. Quote revisions can be explicitly linked to an earlier quote of the same origin; those earlier revisions are excluded from current quote decision denominators. No historical links are guessed.

## Migration v1

`business/schema_migrations.py` is an explicit operator command. App startup never calls it. The development CLI rejects `/var/data` paths.

```sh
# Only a disposable/sanitised LOCAL copy; never production during Stage 2.
python -m business.schema_migrations --database /absolute/local/copy/quotes.db
python -m business.schema_migrations --database /absolute/local/copy/quotes.db --apply
```

| Existing table | Additive fields |
| --- | --- |
| leads | origin_id FK, submission_key, submission_hash |
| quotes | origin_id FK, supersedes_quote_id FK |
| jobs | origin_id FK |
| invoices | origin_id FK, job_id FK |

New tables: `schema_migrations`, `enquiry_origins`, `origin_corrections`, `invoice_payments`, `workflow_events`, `enquiry_interactions`, `revenue_operations`.

Preflight rejects dangling relationships, duplicate invoice numbers, invalid penny amounts and unreconciled historical invoice balances. Migration uses BEGIN IMMEDIATE, fingerprints every original field, backfills only the new model, checks integrity/foreign keys and commits atomically. Repeating an applied migration returns its existing version without inserting duplicate origins or opening balances. Conflicting historical job origins stop the migration for owner review.

Existing IDs, invoice numbers, quote JSON, totals, paid balances, statuses, source evidence and customer relationships are retained. Historical paid amounts become **legacy_opening_balance** ledger rows with NULL receipt date. A paid status alone creates no receipt. No historical receipt or milestone date is invented.

Append-only triggers protect origin capture, corrections, payments and workflow history. Triggers also prevent replacing an assigned origin, deleting tracked business entities, changing a quote's creation time or changing invoice paid totals independently of the ledger. Close a tracked record's status instead of deleting it. Exceptional data retention/erasure needs a separately designed controlled procedure.

## Payments and reporting

Payment amounts use signed integer pence and genuine UK calendar receipt dates; recording timestamps are UTC. Receipt, refund, reversal and correction operations require stable keys. Retries with the same payload return the recorded result; a reused key with changed details is rejected. Concurrent retries are tested. A nonblank matching payment reference/date/method/amount on an unreversed entry is also rejected. Blank references do not establish independent bank transaction identity.

A refund records money actually returned, on the actual refund date. A reversal cancels an erroneous entry on its original date; it is not a cash refund. A correction appends a reversal and replacement atomically. Undated opening balances remain outside period cash until the owner establishes a genuine date and corrects the entry. Overpayments are retained and shown as credit rather than silently capped. Invoice status, amount_paid, balance_due and invoice JSON remain compatible projections for existing readers/PDFs.

| Metric | Calculation |
| --- | --- |
| Enquiry cohort | Distinct enquiries created within selected UK dates, excluding effective Synthetic Test origins |
| Quoted conversion | Distinct cohort enquiries with at least one quote / cohort enquiries |
| Job acceptance | Distinct cohort origins with a recorded accepted/scheduled/in-progress/completed job event and no current cancelled job status |
| Quote-decision win rate | Current eligible won / (won + lost), excluding explicitly superseded revisions; pending/expired/unclassified are not decisions |
| Decided-enquiry win rate | Unique cohort enquiries with a current won quote / unique cohort enquiries with any current won or lost quote; any win takes precedence, otherwise lost. Superseded revisions, synthetic origins and standalone quotes excluded. Undecided enquiries do not enter this denominator. |
| Period cash | Sum signed dated ledger entries whose receipt dates are in the period |
| Cohort paid | All recorded payments/opening balances linked to the selected enquiry cohort, including later receipts; not period cash |
| Historic undated balances | Net NULL-date opening/reversal entries; never assigned to a cash month |
| Outstanding | Current all-time sum of invoice balance_due, excluding synthetic origins |

Amounts are owner-recorded GBP cash, not automatic bank verification, quote estimates, profit, VAT or tax calculations. Historical status without an event is not proof of a dated job acceptance. Legacy dashboard summaries remain available with a warning that they use estimates/paid projections, can include synthetic tests and do not use source corrections. Canonical reporting lives in Source & revenue.

Additional stage/final invoices require an explicit operation key and validated job/quote link. They begin with the existing quote snapshot: Nigel must edit the actual stage amount before sharing. This does not automatically split a quotation or issue an invoice to a customer.

## Consent and data minimisation

The original consent accept/reject controls and measurement ID remain. First-entry context is stored only after analytics consent, in sessionStorage, capped at 24 hours. Withdrawal/rejection clears it. Without consent the app retains only the safe operational current page path. Storage-unavailable browsers can provide only current-page context; this is not cross-device identification or a guaranteed GA4 session boundary.

The server strips queries/fragments from landing pages, reduces referrers to origin and limits campaign values. A search referrer alone cannot prove organic traffic. Unknown campaigns remain Other/Unknown with evidence and limited/reported confidence. Public clients cannot set a canonical source directly. Google page_location/page_referrer are minimised and only permitted campaign labels are passed; names, contact details, origins, payment references and ledger data are never added to GA4 events. Private app pages have no public analytics. Authentication, same-origin write protections and private no-store/noindex headers protect all new APIs.

## Confirmed earlier verification — 10 October 2026

Owner-confirmed evidence: reference `NHP-GA4-20261010-ONE`; lead #13 saved; matching notification actually received in plumbing Gmail; `generate_lead` observed in GA4 Realtime and enabled as a key event. Stage 2 did not repeat the production test, send email, query private inbox messages or change GA4 configuration. Realtime evidence does not establish processed historical totals or full attribution. The historical review flags exact legacy test-marker evidence for manual classification; it does not automatically change lead #13 or remove GA4 history.

## Rollback and Stage 3 gates

Local rehearsals cover injected transactional rollback, migration reruns, frozen-write SQLite restoration of the primary database plus a synthetic separate City sidecar, and loading the previous released app against a migrated synthetic database. Previous readers/PDFs work; obsolete cumulative paid writes are deliberately blocked. The previous app is **not fully write-compatible** with an activated ledger.

Before any separately approved migration: refresh main/service heads; use isolated staging; take fresh SQLite-consistent primary AND private City-store backups; record integrity/foreign-key checks, counts and hashes; freeze writes; rehearse the exact candidate on synthetic/sanitised copies and validate owner journeys. Do not restore a checkpoint after intervening business writes. After new ledger activity, prefer forward recovery/reconciliation; do not roll back app code alone and allow old writers. No destructive down migration is provided.

No shared staging/production deploy, merge, database migration, email, indexing request, GBP edit or public publication is authorised by this Stage 2 implementation. Public content/catalogues, Merrow photographs/permissions, private radiator preservation, price calculations, City pricing, PDFs, email transport/retries and backup configuration are outside the change set and frozen by regression checks.

## Limited Stage 2 completion pass

The completion pass preserves commit `249b669f1edb85a0a36f6bd2728e3200bcb2b002` and its migration. On entry, HEAD and the remote branch were still at that commit, but ten scoped completion files were already modified/untracked. Those changes and the failed route-inventory run were checkpointed and retained. No unrelated application changes were found. The private aggregate export adds one GET route, bringing the exact method/path inventory to 104.

**Aggregate CSV:** use **Download aggregate CSV** in Source & revenue. It uses the selected cohort/cash dates, includes as-of date and GBP currency, and fixed controlled-source/numeric columns only. Counts, both decision rates, dated cash, cohort recorded paid, undated balances, current outstanding and invoice totals are exported. No customer, contact, address, job, record ID, correction note or payment-reference fields are exported. Authentication, private/no-store and noindex apply; effective synthetic classifications are always excluded. Unknown remains a category. Blank rate cells mean no eligible decisions. Balances/invoice totals are all-time current values rather than date-filtered cash.

**Distinct enquiry decisions:** the source table clearly separates quote-decision and enquiry win rates. Multiple current quotes can contribute many quote decisions but at most one decided-enquiry outcome. A current won quote makes that enquiry won; otherwise any current lost quote makes it lost. This rule remains explicit when another quote is pending; it does not infer an accepted job. Enquiries without decisions and legacy standalone quotes are excluded from the enquiry decision denominator. No quote is automatically treated as a revision.

**Owner-controlled revisions:** explicitly choose replacement and earlier quote, enter a reason, tick confirmation of the same work, then confirm the permanent link. Separate jobs/additional scope must retain independent quotes. The server requires strict Boolean confirmation, reason, stable operation key, matching original enquiry/lead and an earlier quote ID. It prevents self-links, cycles, broken/cross-enquiry ancestry, branching, changing a recorded link, linking an already replaced quote and chains containing separate jobs. Transactional append-only workflow history records both quote IDs, configured owner account, reason and UTC timestamps. Identical retries return the original result; different payloads under that key are rejected. Invoice/ledger records are untouched and money is not cancelled when a quote is superseded. History appears in the quote milestone panel. No unlink/reassignment tool is introduced in this limited pass; an erroneous confirmed link requires controlled review.

No new schema version is needed: this uses the existing additive `supersedes_quote_id`, append-only `workflow_events` and idempotency store. Targeted regressions include export privacy, zero-denominator and distinct enquiry measures, explicit revision confirmation and cancellation, conflicting relationships, concurrency, transaction rollback, migration reruns and unchanged ledger reconciliation. The full final-commit Python/Node/Chromium results and actual remote CI status belong in the updated owner-review report; earlier preserved validation is not evidence of this candidate passing.

The earlier design differences (combined cash/cohort interface and omitted proposed checksum/rule-version metadata) remain documented, unchanged and outside this three-item completion approval. Stage 3 still requires separate approval and environment/migration review. No staging/production deployment, main merge, production migration/data change, GA4 configuration change or outbound test enquiry/email is part of this pass.

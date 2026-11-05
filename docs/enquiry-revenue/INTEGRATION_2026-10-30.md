# Enquiry-source and revenue integration — 30 October 2026

Development candidate only. No merge to main, Render configuration change,
deployment, production/staging data access or migration, or customer contact.
This candidate supersedes the integration baseline in the 27 October report;
PR #41 and PR #29 remain unchanged.

## Exact inputs and reconciliation

- PR #41: `cc54aa594e0f4580e1e30906ca559c902b67aa3f`.
- Production main: `8cd736461190941224b911a02884c3ea1ac5fbdb`.
- New branch: `integration/enquiry-revenue-main-20261030`.
- Main-only commits: PR #42 (`3bce8e8`), #44 (`e5bb79b`), #45 (`3a7e5de`),
  #46 (`8cd7364`); PR #41 has 19 feature-only commits.
- Merge preserves both histories. Two textual conflicts, both in tests:
  `test_baseline.py` combines the reviewed review-badge snapshot adapter with
  the pre-revenue analytics adapter; `test_growth_batch8.py` checks protected
  AST/functions and files against current production main.
- Application code merged automatically and its diff was inspected. Public
  render/review functions remain equal to current main under the AST guard.
  Public review styling, Google review retrieval, website contact helpers,
  public page/layout modules, header/footer, homepage, document-link module,
  diary migration, project/advice records and project assets are preserved.
- Revenue schema activation remains explicit, never a startup revenue migration.
  The development migration CLI continues to refuse `/var/data`.
- The renamed Ubuntu 24.04 regression workflow retains secure-link browser,
  full Python/Node/revenue browser and responsive public-review matrices.
- Added current-production rollback compatibility coverage alongside the older
  release probe. Both operate only on disposable copied databases; reading
  migrated data is tested separately from the deliberately blocked old writer.

## Verification record

Local and exact-head GitHub Actions results are recorded in the draft PR after
completion. This file alone does not assert that pending checks have passed.
All database rehearsals use synthetic temporary storage; external DNS, sockets,
HTTP and SMTP are blocked. Browser harnesses allow loopback requests only.

Required automated coverage includes:

- Full Python discovery and Node syntax, consent/attribution, material/trade,
  lead-email, browser-harness cleanup and deadline checks.
- Desktop/mobile quoting, pipeline, advice, projects, local/London pages and
  migrated enquiry/revenue journeys.
- Customer/staging × desktop/mobile secure document sharing, rotation,
  revocation and private-route protection.
- Public review layout at desktop, tablet, mobile and small-mobile widths.
- Diary/revenue migration in both orders, failure rollback before commit,
  checksummed/idempotent reruns, preserved historical projections and references,
  legacy paid opening balances, paired primary/fake-City restoration.
- Secure-link/revenue migration in both orders and prepare/secure modes,
  preserved historical tokens, normal/stage-invoice token issuance and retries,
  revocation after restart, SQLite integrity and foreign-key checks.

## Outstanding staging and production release requirements

1. Final candidate CI must pass. Record exact head/tree, recheck main divergence
   and rerun integration checks for any later code changes.
2. Read-only inventory of persistent staging: actual running SHA, own disk and
   database paths, schemas/migration versions/checksums, SQLite integrity/FKs,
   shared-link mode, City sidecar, and quote/job/invoice/appointment references.
   Earlier staging observations are historical, not current verification.
3. Obtain approval for a concrete persistent-staging procedure before changing
   that service. Verify authentication and noindex, staging-only base URL and
   disabled outbound email/paid APIs. Back up its own data; do not attach or use
   production storage. Rehearse the exact candidate with isolated data, verify
   links/PDFs/ledger/diary/City data, restart and verify persistence. Obtain owner
   acceptance on desktop/mobile. Ephemeral CI is not this staging gate.
4. Before production, read-only inventory of actual runtime SHA, schema/checksum,
   integrity/FKs, balances and historical relationships. Stop on discrepancies,
   duplicates or projections requiring review; do not auto-merge customers or
   silently repair history.
5. Approve a coordinated write freeze covering website enquiries, private app,
   background writers and City cache. Take fresh protected, consistent paired
   backups of primary SQLite and the separate City database, plus required
   invoice photos/documents and runtime/configuration inventory. Record timestamp,
   byte sizes, checksums and schema/count inventory. Account for WAL safely with
   SQLite-aware backups; copying an active database file alone is insufficient.
6. Prove restoration into isolated copies with integrity/FK, reference, balance,
   token/revocation and City-cache checks. Preserve credentials outside public
   evidence. Older online snapshots and synthetic rehearsal are not production
   checkpoint evidence.
7. Review and explicitly approve the guarded migration, stop conditions,
   release/rollback procedure and exact candidate before any main merge,
   production migration or deployment. No such approval is requested by this
   development report.
8. After ledger activation, a code-only rollback to the old cumulative-payment
   writer is unsafe. Any restore after new transactions must preserve and
   reconcile all post-checkpoint business writes; never discard them blindly.

# Enquiry source and revenue integration — 27 October 2026

Development candidate only. No production or persistent staging database access,
migration, settings change, deployment, merge to main or customer contact.
This report supersedes the 21 October integration status for this new branch.

## Source and preservation

- Current main: `f62412fb019afac9ec8605303b062ae726506e97` (includes PR #40).
- Original draft PR #29: `b8201b1343e4c66ec5033e7ebc56e4d59dcc370f`.
- Separate branch: `integration/enquiry-revenue-main-20261027`.
- Both histories are retained via a merge; original PR #29 is not rewritten.
- Seven textual conflicts reconciled: website contact attribution and six test/
  fixture files. Route inventory is the union: 111 method/path pairs, with
  revenue endpoints private and secure customer-link routes retained.
- Public content, Surrey and London SEO, header logo, footer disclosures,
  published advice/projects/images, document security module, PDF rendering and
  optional-lead diary migration remain byte-identical to the above main.
- Current main's website quote-link attribution script is retained. The new
  analytics/form integration consumes the same consent-controlled 30-minute
  session format, sanitizes marketing context, and clears it on withdrawal.
  Explicit local landing-page context can pass without analytics consent.
- Existing main test assertions for content, security, diary and rendering stay
  in place. Historical snapshot adapters reverse only reviewed tracking/UI
  additions. Public snapshot fixtures use this main, not the obsolete PR base.

## Integrated implementation

- Immutable original enquiry attribution inherited by quotes, jobs and invoices;
  append-only source/channel corrections, synthetic classification and history.
- Mobile enquiry-details editor, first-contact channel including WhatsApp,
  separate from how the customer found Nigel.
- Dated payment ledger including receipts, refunds and corrections, safe retries,
  paid-balance protection, milestone/revision history and aggregate CSV reporting.
- Schema activation remains an explicit separate operation, not a revenue
  migration at application startup. Development CLI still refuses `/var/data`.
- Integration fix: revenue's transactional quote, normal invoice and stage
  invoice creation now issues the secure customer-document token within the
  same transaction. The older implementation bypassed main's issuance path.

## Verification

All app/database tests use redirected temporary paths and fictional records.
Test harnesses block external HTTP, sockets, DNS and SMTP; browser harnesses
allow only loopback requests. No production data is needed for these tests.

- JavaScript syntax, analytics/attribution/consent and existing material/trade/
  lead-email Node checks passed locally during integration.
- New secure-link/revenue matrix passed in prepare and secure modes, both
  migration orders. It checks old fields and tokens survive, revoked tokens
  remain revoked after restart, new normal/stage invoice links work, retry
  tokens are stable, rotation/revocation work and SQLite/FK checks pass.
- Existing disposable rehearsal covers diary-first and revenue-first migration,
  rollback injection, checksummed activation, original field hashes, legacy paid
  opening balance and paired restoration of primary and fake City sidecar.
- Full Python and desktop/mobile browser runs and exact-commit GitHub Actions
  results must be recorded before treating this branch as integration-validated.
  Earlier PR #29 passes are not evidence for this updated candidate.

## Remaining release gates

1. All final-commit CI checks, including Python, Node, browser, secure links and
   the migration rehearsals must pass. Recheck main divergence before release.
2. Verify authenticated/noindex persistent staging access and actual runtime
   SHA/schema using read-only inventory before changing that environment.
   Isolated temporary local/ephemeral previews do not satisfy this gate.
3. Under a separately approved staging procedure, rehearse the exact candidate
   on persistent staging with isolated outbound services, integrity/FK checks,
   preserved document tokens, invoices, quote/job/diary references and City
   cache. Confirm data and release checks after restart.
4. Before production, obtain an approved coordinated write freeze and fresh
   paired backups of primary SQLite and City sidecar, checksums, inventory and
   verified restoration. An older online snapshot is insufficient.
5. Review runtime migration-version/checksum and actual historical references,
   duplicates, invoice projections and shared-link mode. Stop on discrepancies;
   no automatic customer merge or historical repair.
6. Approve an explicit guarded production migration/release and owner acceptance
   before any main merge/deployment. No production migration is authorised here.
7. A code-only rollback to the old cumulative-payment writer is unsafe after
   ledger activation. Restoration after new business transactions requires
   reconciliation of all post-checkpoint writes; never discard them blindly.

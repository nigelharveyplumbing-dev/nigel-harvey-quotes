# Stage 3 enquiry-to-revenue + WhatsApp — integration gates (21 Oct 2026)

**Status: DEVELOPMENT CANDIDATE ONLY. NOT AUTHORISED FOR PRODUCTION.**

Base: current `main` at `7de3c82c455fa08579c14e4e8c168f5282190463`.
Reconciles approved mobile-first WhatsApp first-contact/source tracking with the existing pipeline booking, diary deletion, optional-lead appointment schema, and Batch 9 public website pages.

## Safe read-only reconciliation
- Production main, original draft PRs #12 and #27, production Render service, original persistent staging service and their databases remain unchanged.
- All files affecting published location pages, projects, photographs and advice are retained from current main.
- New development only. The existing isolated synthetic WhatsApp preview is not the full integration staging approval.
- Unknown acquisition source must not be automatically credited to Google, and synthetic enquiry records must remain excluded from genuine lead metrics.

## Required tests and evidence before further release approval
1. Full exact-head GitHub Python + JavaScript + desktop/mobile browser CI PASS, including both newest job-date booking and revenue/payment workflow tests. A previous browser test expected the deprecated "Add to Pipeline" label. The new synthetic browser flow exercises the production "Book job dates" button and validates booking-to-job, original enquiry and quote links.
2. On a fresh disposable SQLite database, run migration preflight, v1 checksum and additive migration; test rollback-on-failure, legacy paid balances, duplicate IDs, created-at integrity and immutable audit history. Combine with the current optional-lead appointment migration to ensure either migration sequence preserves references.
3. Ensure City account-cached prices and separate City price storage survive; preserve quotes, jobs, appointments, invoices and all dated payments.
4. Obtain verified access and isolate the older persistent staging runtime before any staging branch changes; do not overwrite it based on an assumption. The separate synthetic preview is not a substitute for this full remote gate.
5. Before production migration, independently confirm actual runtime SHA and both database integrity/foreign-key states. Under an approved coordinated write freeze take fresh protected SQLite backups of the main quotes and City sidecar databases with checksum, complete inventory and restoration rehearsal. Existing 14 October online snapshots are **not** a write-frozen checkpoint.
6. Apply migration only through an explicitly approved guarded procedure. The development CLI's ban on `/var/data` is intentional and must remain. Do not merge/deploy or send customer messages during this development stage.
7. After a payment-ledger release, a code-only rollback to the old writer is unsafe. Reconcile any post-checkpoint business transactions before considering restoration.

## Approval boundary
This branch may be developed and tested with synthetic offline fixtures only. Do not merge, change staging/production settings, migrate live records, change Google settings or send outbound contacts without new explicit owner approval.

# Customer document links — development candidate

No deployment, real-data migration, customer message or cutover is authorised by this document. Draft PR #34 remains unmerged.

## Implemented behaviour

`CUSTOMER_DOCUMENT_LINK_MODE` has three exact values. An invalid value stops startup.

| Mode | Numbered customer routes | Random customer links | Database changes for links |
| --- | --- | --- | --- |
| `legacy` (default) | Existing public behaviour | Disabled | None |
| `prepare` | Existing public behaviour | Enabled | Add token columns/indexes and assign tokens to previously unissued records |
| `secure` | Staff authentication required | Enabled | Same additive, idempotent migration |

Staging continues to require staff authentication for every route, including token pages. It must never expose real customer data for anonymous testing.

Tokens are 32 random bytes encoded into 43 URL-safe characters, separate for each quote and invoice. They are durable, revocable bearer links: anyone holding one can view that document. They do not expire automatically, so an unpaid invoice does not unexpectedly stop working. This choice must be reviewed before release; expiration has not been implemented.

The token page uses matching token URLs for PDF, payment QR and photos. A token cannot access another invoice's photos or the full private invoice JSON. Secure mode retains authenticated numbered staff PDF/QR/photo access. New WhatsApp quote and invoice links and invoice email/reminder links use the configured origin and secure paths when enabled. Numbered links never redirect to tokens. A revoked link has no numbered sharing fallback.

All token responses, including errors, use no-store, noindex and no-referrer. Uvicorn access-log arguments redact token paths. Upstream proxy, platform and error-monitoring logs still need separate verification before any real links are used. Customer pages contain no analytics.

## Replacement and revocation

Staff-only `POST /api/document-links/{kind}/{id}` rotates the link and invalidates the previous token. Staff-only `DELETE` at the same path revokes it. `kind` is `quote` or `invoice`. These routes apply the existing cross-site-write checks. Rotation is deliberate; it is never triggered by viewing, editing, restarting or sharing a document. No management buttons have yet been added to the owner UI; these operations are available through the authenticated API only.

The database stores the current bearer token as a secret. Protect database files, backups and authenticated API responses accordingly. A NULL token is unissued; an empty token is revoked and must stay revoked after restart. Migration runs inside a savepoint and must not partially publish tokens on failure.

## Preparation for a separately approved staging test

1. Confirm the exact candidate commit and passing CI. Reconcile any intervening main changes. Use an isolated database with fictional quotes, invoices, photos and bank settings; disable SMTP, reminders, Google and AI integrations.
2. Verify the staging service is isolated and not following a branch that changes automatically. Obtain approval for the exact staging deployment and migration. Set mode to `prepare` there. Never point it at production storage.
3. Verify legacy compatibility, token HTML/PDF/QR/photos, wrong tokens, cross-invoice photos, revocation, rotation and staff-only APIs. Repeat desktop/mobile sharing checks. Retain staging authentication. Test secure mode separately against fictional records.
4. Verify platform log redaction and health checks with the actual service configuration. A staff-only `/api/health` check must not be made public as a workaround. No staging deployment has been performed in this development task.

## Real-link replacement — later approval required

1. Obtain owner approval for a read-only inventory from a protected production snapshot. The prepared command is `python scripts/document_link_inventory.py --database-copy /protected/path/snapshot.db`. No real inventory has been collected. It emits internal IDs, status and balance only; no names, phone numbers, tokens or message history. Keep the output private and out of source control.
2. Reconcile every potentially shared quote/invoice against Nigel's WhatsApp and sent-email history. The database cannot prove which links were sent, delivered or opened. Mark uncertain records for review, including paid invoices customers may still need.
3. Before any prepare-mode production migration, coordinate a write freeze, stop reminder workers, take a fresh SQLite online backup and City sidecar/photo backups, record protected locations and checksums, and rehearse restoring the copies. Confirm quote/invoice/customer/photo counts, balances, paid states, IDs and integrity before and after. Obtain approval for the exact release, migration and configuration.
4. In prepare mode, produce the owner-only mapping of existing documents to secure replacement paths. Review recipients and draft communications privately. Suggested wording: “Hi [name], here is the updated link to your [invoice/quote] [reference]: [replacement link]. Please use this link from now on. The document and amount are unchanged.” No message is sent by the inventory script or the migration.
5. Obtain explicit approval to send the reviewed messages. Record delivery and customer access confirmation or a specific agreed alternative for every reviewed record. Do not infer confirmation from link generation. Old numbered links remain public throughout preparation; the privacy exposure is not closed in this mode.
6. Once the owner approves the completed inventory and exact cutover, make another fresh protected backup and enable `secure`. Check anonymous numbered requests receive 401 without redirects, valid token documents work, staff functions work and no customer contact/history is exposed.

## Rollback and incident handling

Before replacement links are issued, the approved backup can be restored under a write freeze after checking no later work would be lost. Do not call an untested backup inspection a full restore rehearsal.

After links are sent, rolling back to code or a database without tokens will break those links. Prefer a forward fix that retains the token columns and values. Returning to prepare mode reopens numbered access and requires an explicit privacy/access decision; it is not an automatic rollback. Do not silently restore an old database over new payments, quotes or appointments. Revoke a compromised token and reissue only after verifying its recipient.

## Remaining release gates

- Full regression and browser results for the candidate commit; staging test and platform-log review.
- Owner review of durable versus expiring links and authenticated API-only revocation operations.
- Explicitly approved real inventory, verified replacement recipients/delivery/access and backup restore rehearsal.
- Separate deployment/migration and cutover approval. None of these gates is satisfied merely by this document existing.

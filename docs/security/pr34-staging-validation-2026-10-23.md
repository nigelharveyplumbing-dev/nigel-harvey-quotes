# PR #34 — private staging technical validation

Date: 23 October 2026. Owner authorised a private staging test with fictional documents. Production deployment, production-data inventory, customer communications and final cutover remain unauthorised.

## Result

**PASS: 60 startup checks on Render and 60 external HTTPS checks.**

- Application candidate: `b7377ca92338a3e8ede2167b1daaa11a4200fdd9` (308 Python tests and eight existing browser workflows passed previously).
- Isolated wrapper commit deployed: `227b9c8dedd9adeb519f25d60def7060d6763635`.
- Preview branch: `preview/pr34-document-links-isolated-20261023`.
- Service: `srv-dbdit4rrjlhs73df4c1g`; deploy: `dep-dbdit53rjlhs73df4dt0`; Render status confirmed `live`.
- Preview: https://nhp-pr34-document-links-private-test.onrender.com/app (separate staging Basic Auth required; credentials are stored in this service's Render environment, not in this report).
- Free compute plan, auto-deploy off, no attached disk, temporary SQLite/photo/backup storage. The build command pins the wrapper commit. Evidence-only commits after this deploy do not change the running application.

## What was checked

The wrapper verifies exact application-file hashes before import and reuses the existing disposable-storage/no-outbound-I/O harness. It creates two explicitly fictional customers, quotes, invoices and generated test images. SMTP, overdue reminders, Google and AI integrations are disabled and outbound connections are blocked in the application process. No production or old-staging database was opened.

Startup checks cover legacy-schema migration, preservation of existing document content, idempotence, integrity, backup restoration into a separate temporary database, prepare-mode compatibility, secure-mode staff authentication, scoped token HTML/PDF/QR/photo access, unknown/malformed tokens, cross-invoice photos, private JSON, rotation, revocation surviving initialization, replacement links, staging authentication, robots restrictions and storage/integration isolation. Anonymous production-policy checks execute internally against fictional records before opening the server; all remotely served staging routes retain authentication.

The 60 external HTTPS checks verify actual deployed responses: anonymous 401s without token redirects; authenticated pages and document media; no-store/noindex/no-referrer headers; fictional invoice PDF text and inline/download disposition; matching child paths; cross-document rejection; staff-only legacy endpoints; rotation/revocation and replacement restoration; unrelated invoice availability; and staging robots. Final validation JSON contains boolean check results only, with no customer details, credentials or bearer tokens.

Five sampled Uvicorn application log entries showed `/share/invoice/[redacted]` or `/share/quote/[redacted]`. A runtime-error query returned zero entries at validation time. One broader log request temporarily returned a Render log-backend 503; focused follow-up succeeded. The available log types were app/build, so platform/proxy request-log retention and broader monitoring access have **not** been verified.

A transient proxy/read timeout interrupted an earlier external sweep. A subsequent complete sweep using persistent HTTPS sessions passed all 60 checks and left both fictional invoices with working links.

## What is still outstanding

- **Owner visual review:** the cloud browser encountered the Basic Auth challenge and then an inaccessible browser error page. No browser security warning was bypassed, credentials were not entered through a lower-level browser API, and the preview was not made public. Desktop/mobile visual review of enabled mode remains pending. Existing CI browser workflows used the default compatibility mode.
- Review durable versus expiring bearer links and the API-only rotation/revocation operations. The staging task does not imply approval of these choices for production.
- Verify platform/proxy/error-monitoring logging before real bearer links are used.
- Explicitly approved production snapshot inventory, verified replacement recipients and customer communications/access confirmation.
- Fresh protected production backups and restore rehearsal, followed by separately approved deployment and cutover.

## Production boundary

PR #34 remains draft and unmerged. Production service `srv-d72j5ocg9agc7399dni0` remained on main with auto-deploy off and unchanged configuration timestamp `2026-10-22T13:46:09.348135Z`. The older staging service and its attached disk were not changed. No real email, WhatsApp message, production migration, customer-link replacement or Google settings change was performed.

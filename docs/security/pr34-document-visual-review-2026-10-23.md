# PR #34 document visual review — 23 October 2026

## Completed in development

- Downloaded the authenticated fictional quote and invoice PDFs from the isolated staging service; rendered and inspected every page.
- Found an existing layout defect: the wide `INVOICE JOB PHOTOS` heading overlapped the company name when the logo was present.
- Split the photo-page heading into `INVOICE` and the smaller `JOB PHOTOS` reference line. Main invoice and quote layouts remain unchanged.
- Added a regression test that measures actual generated PDF text positions with the logo and seven fictional photos, covering the initial and continued photo pages. Confirmed this test fails against the original heading and passes with the correction.
- Regenerated a fictional quote and two-page invoice through the secure token routes in the local isolated application; inspected all three corrected pages. These regenerated samples are from the revised development code, not the older deployed preview.
- Local available regression suite: **304 passed**. Five checks depend on full git history, archived assets or Chromium; full CI results are recorded in the PR.

## Exact deployment boundary

The running private staging service is still the previously validated candidate `b7377ca92338a3e8ede2167b1daaa11a4200fdd9`, at wrapper commit `227b9c8dedd9adeb519f25d60def7060d6763635`. Its 60 startup and 60 external HTTPS checks passed. The new PDF layout correction has not been deployed to that service. Production remains unchanged, and PR #34 remains draft and unmerged.

## Remaining work

1. Complete enabled-mode desktop/mobile app and sharing review. PDF inspection does not complete browser review; the staging Basic Auth/browser limitation remains unresolved without weakening authentication.
2. Reconcile a separately approved protected production snapshot with the complete plumbing Sent mailbox and WhatsApp history. Limited mailbox evidence cannot establish a complete customer-link inventory. Keep real records and bearer URLs out of source control.
3. Review durable versus expiring links, API-only revocation, upstream/proxy log handling and health configuration.
4. Verify replacement recipients and communications, protected backups and restore rehearsal before any approved production migration. Keep old customer links available until replacements and cutover are tested and explicitly approved.

No customer message, production migration, live link replacement or production deployment was performed during this review.

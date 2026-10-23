# PR #34 — secure-link desktop/mobile review completed

23 October 2026. This report covers private fictional-data testing only.

## Current outcome

- Application/test candidate: `d8123d26e60bbfabb898e3827a0c9e3aacd2a676`.
- GitHub CI run `39946443645`, job `120390164119`: **PASS** — 310 Python tests, eight existing browser workflows and the new four-case secure-link browser matrix. Local available suite: 305 passed; CI completed the five environment/history-dependent checks.
- Desktop: Chromium, 1440 x 1000. Mobile: Chromium touch/mobile emulation, 390 x 844. Both were exercised under customer-access policy and fully authenticated staging policy. This is not a physical iPhone/Safari test or owner sign-off.
- Reviewed captured customer invoice pages and owner quote/invoice controls for both policies and device layouts. The solid/blank test photo is deliberately synthetic; all customer and bank details are fictional.
- Updated free private preview: `https://nhp-pr34-secure-links-review.onrender.com`, service `srv-dbdk607b9u1s739vvlog`.
- Final wrapper commit: `c155045d85b207513850ab6a983bcede5bb2ece4`; deploy `dep-dbdkbfg473hc73c06ihg` confirmed **live**. The wrapper verifies nine application/UI file hashes, including the corrected PDF renderer, before importing the copied app.
- **60 startup checks and 63 external HTTPS checks passed** against the final deployment. Both fictional invoice links were restored after rotation/revocation tests.

## Browser flows checked

| Policy | Desktop | Mobile | Customer document access |
| --- | --- | --- | --- |
| Secure customer policy | PASS | PASS | Token document opens without staff credentials; numbered routes and private JSON require staff authentication |
| Private staging policy | PASS | PASS | Every remote route, including token documents, requires staging authentication |

Each case creates a quote through the real UI, verifies its WhatsApp link, converts it to an invoice, uploads a synthetic photo, verifies invoice sharing and opening links, downloads actual quote/invoice PDFs, and checks customer images and horizontal fit. The email button is exercised with its request intercepted locally; the browser sends no email. A separate Python check composes actual plain/HTML email MIME with the secure invoice URL and real generated PDF attachment, and rejects composition after revocation, without SMTP delivery.

The matrix also verifies the email notice is visible within the viewport; unpaid owner/customer views have no PAID watermark; marking the invoice paid makes that watermark visible; numbered links stay staff-only; unknown photos are rejected; and rotation/revocation invalidate old tokens. All four cases recorded zero page errors and zero external browser requests. Server storage is disposable and all non-loopback DNS, sockets, HTTP and SMTP are blocked. No WhatsApp link was clicked.

The separate HTTPS sweep validates deployed authentication, exact candidate/UI/PDF hashes, token HTML/PDF/QR/photo responses, download disposition, private headers, scoping, legacy staff routes, cross-site write rejection, rotation/revocation/replacement and staging robots restrictions. Three sampled application logs showed `[redacted]` token paths; the post-deploy runtime-error query returned no entries. Platform/proxy log retention remains unverified.

## Corrections found by this review

1. Email success notices were written into the hidden Quotes tab. Removed the duplicate notification function and duplicate global notice ID; one accessible notice now remains visible across tabs and within the viewport. Quantity-learning updates are retained.
2. An inline `display:flex` overrode the hidden class on the owner invoice PAID watermark. Removed that inline display and applied flex only while the watermark is not hidden. Browser checks cover both unpaid and paid states.

The earlier invoice PDF photo-header overlap correction is included in this deployment. Its geometry regression remains part of the passing suite. Complete UI/file snapshot locks were reconciled specifically for these reviewed changes.

## Deployment boundary and remaining work

The new preview has no attached disk, temporary storage only, disabled outbound integrations, separate staging Basic Auth and auto-deploy off. Its build checks `EXPECTED_PREVIEW_COMMIT` against the checked-out commit. Updating that pin through the Render environment API triggered the recorded final deploy; no duplicate manual deploy was requested. The prior private preview and older disk-backed staging service were not modified in this review.

Production service `srv-d72j5ocg9agc7399dni0` remained on `main`, auto-deploy off, configuration timestamp `2026-10-22T13:46:09.348135Z`. No production database or real customer document was opened. No live migration, customer message, customer-link replacement, production deployment or PR merge occurred.

Next: complete the real-link inventory from an explicitly approved protected production snapshot and reconcile it with complete plumbing email/WhatsApp history. Limited connected-mailbox evidence is not a complete customer list. Verify recipients, replacement communications/access, backups and restore rehearsal before separately approved cutover. Owner review, physical-device/Safari checks, durable-link/API-only revocation choices and upstream logging review remain release considerations. Previously sent customer links must remain usable until the tested replacement and cutover are approved.

Machine-readable evidence accompanies this report: `pr34-secure-browser-review-2026-10-23.json` and `pr34-secure-review-https-validation-2026-10-23.json`. Screenshots and original browser JSON are retained in the CI artifact `secure-document-link-previews` (artifact ID `12498153421`). No bearer URLs or credentials are included in these report files.

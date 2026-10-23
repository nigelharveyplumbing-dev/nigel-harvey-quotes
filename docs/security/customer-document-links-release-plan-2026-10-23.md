# Customer document link security — 23 October 2026

**Development / review only. No live release approved.**

## Confirmed issue
Current production main `3bd02dab7463cf7c9a7670b9d8a3efdaaf69103b` exposes sequential customer invoice HTML at `/invoice/{id}`, quote/invoice PDFs, invoice QR and invoice photos through numeric API routes without route-specific authentication. Public robots/noindex headers do not prevent someone with a guessed URL from viewing private content.

## Existing draft solution
Old draft PR #1 (`privacy/gdpr-readiness`, September 2026) contains random per-document share tokens and a private-auth requirement for numeric routes. Its migration writes `share_token` to quotes/invoices and creates unique indexes. It is stale relative to the October main, diary, SEO and navigation changes. **Do not merge it directly.** The older privacy notice has unverified retention and supplier statements and is out of scope for the document-link release.

## Critical compatibility boundary
Nigel has previously sent numbered invoice links to customers on WhatsApp. Turning off those routes immediately would break their access. There is no confirmed inventory of which customers received which links, which invoices remain unpaid, or whether links are still needed. Do not use a temporary public redirect from numeric ID to a share token; that would preserve the vulnerability by leaking the token to anyone who guesses the ID.

## Proposed phased cutover
1. Build an isolated, current-main security branch with staff-authenticated numeric endpoints, cryptographically random customer share URLs, no-store/noindex/referrer restrictions and strict token validation. Preserve authenticated staff PDF/photo functionality and email/WhatsApp links. Avoid logging tokens.
2. Run tests for unauthorized numbered routes, unknown/revoked tokens, access to only the matching invoice/photo, mobile quote/invoice sharing, no analytics/referrer leakage and existing booking/payment flows. Test migration on synthetic copies of old-schema SQLite in both empty and populated cases, with restore rehearsal.
3. **Before changing live routes**, use an owner-approved read-only inventory of the real documents and link history (without exposing customer details in logs), prepare the exact customer communications, and decide how to reissue the links. Confirm delivery and customer access before disabling the old routes.
4. Take fresh protected database and City-sidecar backups under a coordinated write freeze, record checksums and restore steps. A code-only rollback after new token links are sent is not a safe customer experience.
5. Staging, release and any real data migration require separate approval.

## Current task
Owner authorised **step 1: start securing customer document links**. The current action prepares this review and isolation boundary only. Do not silently deploy, migrate, message customers or break old links.

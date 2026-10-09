# Batch 7 release reconciliation — 9 October 2026

Nigel authorised staging, then production promotion only after the release
safeguards pass. The approved advice commit is `f12d0d695330b965bdd600dc759b1c2f1cefed17`.
The article remains `draft` with no approval/publication timestamp. Wording
approval and public publication/indexing remain separate decisions.

## New main preserved

Main advanced to `bdcacc9ff02d041e4ab4c63269b5c7ebba4942a2`, incorporating
PR #8 and the lead-email notification audit, safe failure handling and private
retry controls. Production is live at documentation commit
`4dee5a868d981db5a0ef3399b37401fe945872d3`, deployment
`dep-db4jnovf3r2c739pah2g`. The advice branch merges current main without rewriting
either history. Conflicts were limited to route/test inventory expectations.
The merged app has 91 routes, including the two advice GET routes and both
existing private email status/retry routes. All 71 private app routes remain
protected. Email, DB, City pricing, quote/invoice/PDF and approved project files
match newer main byte-for-byte; the preservation regression now checks that
newer baseline and explicitly includes the email modules.

Local validation passed 259 Python regressions and material-selection,
trade-comparison and lead-email Node suites. The old local Chromium runtime was
absent; one official download attempt returned an unavailable-site HTML page.
No download loop was started. Final-head Chromium validation uses the existing
GitHub Actions runner with the known Playwright version and all five workflows.
CI now explicitly runs the additional lead-email Node controls suite.

## Verified restoration safeguards

Both services have distinct `/var/data` disks, one worker, auto-deploy off and
unchanged credentials/environment policy. The staging deployment remains the
old Batch 6 preview at `142b3a015400c313a6bb62472521a13a32eddee5`; its returned
history showed no newer unrelated in-progress deployment.

Verified SQLite online snapshots are retained privately on the corresponding
service disk:

- Stage: `/var/data/batch7-stage-20261009T193324Z`.
- Production: `/var/data/batch7-production-20261009T193554Z`.

Each covers `quotes.db` and `city-account-prices.sqlite3`, passes integrity
checks and matches the source logical dump SHA-256. Snapshots use private
permissions and are not exposed through public routes or committed to Git.
Production has 30 ordinary database backup files. Baseline business counts:
eight customers, nine quotes, four invoices, eight leads; 23 City cached account
records in one import. Stage has 12 customers, ten quotes, three invoices and
two leads; 69 City records in three imports. No business records were edited.

## Actual delivery preflight

The saved test enquiry named `Email delivery test 9 October` was confirmed in
the plumbing Gmail INBOX using read-only IMAP access from production. The
configured account was checked against the plumbing business email first.
Subject matched the notification and Message-ID was
`<6ac93d65.0a1c4297.22934f.4ec0@mx.google.com>`. This verifies receipt of that
actual test, beyond SMTP acceptance. No photography mailbox was accessed,
old enquiries replayed or credential values printed. A fresh post-release
synthetic enquiry and receipt check remain necessary before claiming the
new production release's end-to-end email verification.

## Remaining release gates

Require green final-head CI, exact-commit isolated staging validation and a
fresh main/production check before merge. Deploy only the reconciled feature
SHA to the existing staging service. Preserve its old branch/deploy and
recovery snapshots. Check draft noindex/auth, sitemap/canonical/schema/links,
Merrow photos, private app, existing quotes/invoices/PDFs and City records.
Use read-only existing business checks; synthetic workflow writes must be
clearly scoped and must not send customer emails.

After staging passes, merge the verified head using an expected-head check,
then deploy the resulting main commit to the existing production service.
Verify production and a uniquely named synthetic enquiry plus actual plumbing
inbox receipt. Recheck both databases and preserve all existing rows.
No article is published, no new indexing notification is submitted, and no
GBP/directory/customer workflow change is authorised by this release.

Final CI/staging/production evidence and deployment IDs are recorded in the
owner delivery report when those gates complete. This preparation record is
not a claim that deployment or final production verification has occurred.

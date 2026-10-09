# Website enquiry email repair

The production server accepted the owner's test POST /api/leads at 10:08:30 UTC
on 9 October 2026. Production was e3e390846ad9e7e5589c589362b4471fdf2ecc1a,
deployment dep-db40e8ub7d7c739t25qg. The handler saves the lead before calling
SMTP. Existing code discards disabled configuration and every SMTP exception,
so the success response proves lead storage, not mail delivery. No matching
notification was found in the connected Gmail mailbox, including spam.

Authenticated production inspection confirmed the test lead (ID 9) is saved,
SQLite integrity is OK and EMAIL_ENABLED is true. EMAIL_USER is the owner's
plumbing Gmail account. Connections succeed over SSL 465 and STARTTLS 587, but
authentication fails. An explicit LOGIN exchange returned SMTP 535; removing
password whitespace also returned 535. Gmail rejects the saved credential.
No secret values were displayed or logged. A valid Gmail app password must be
entered by the owner before live inbox delivery can be verified.

## Change

- Save a private per-lead notification audit in a new SQLite table. The lead
  and pending audit are committed together, before attempting mail delivery.
- Record pending, sending, failed or accepted status, attempt count and safe
  error category. Accepted means SMTP acceptance, never inbox delivery.
- Keep public submission successful when mail fails, retaining the saved lead.
- Add an authenticated status endpoint and per-lead manual retry endpoint.
  The existing authentication, write-origin and noindex policies protect both.
- Add a private warning when email configuration is missing and show delivery
  status with a retry action beside the enquiry. There is no automatic retry
  scheduler in this change.
- Block retries for accepted messages and concurrent in-progress attempts.
  A sending audit older than 120 seconds is manually retryable after a crash.
- Bound SMTP operations with a 15-second socket timeout. This is a timeout
  per socket operation, not a guaranteed 15-second total wall-clock limit.
- Include postcode, urgency and preferred contact in the email, and link to
  /app. Delivery still uses the existing configured EMAIL_USER recipient.
- Log only internal lead IDs and stable failure categories; never raw SMTP
  errors, credentials or customer content. Public responses disclose no
  notification configuration, audit or error state.

SMTP cannot guarantee exactly-once delivery: a crash after acceptance but before
the audit commits can produce a duplicate following an explicit manual retry.
Older leads have no historical audit; sending one is an explicit owner action.
No previous lead is automatically emailed or assigned a historic sent status.

## Release gate and recovery

This branch is prepared separately from main. Do not claim email is fixed until
live configuration has been inspected and a synthetic website enquiry is both
saved and received in the owner's plumbing Gmail inbox. Check mail headers,
subject and all supplied fields; verify private status and retry controls.

Before release, record current main/production, SQLite integrity and business
counts; take a consistent SQLite backup and retain the private City price store.
No manual business-record changes are needed. The new table is created
idempotently by the existing startup initializer. Rolling back code leaves it
unused; it must not be removed as part of ordinary recovery. All existing
customers, quotes, invoices and material-price tables retain their schemas.

Local validation: 251 Python regressions (including nine focused email checks),
the two existing Node suites, and new notification-control Node checks.
Chromium workflows could not run: no executable was available and the official
Playwright download returned a corrupt/empty archive. Treat browser and live
delivery validation as outstanding, not passed.

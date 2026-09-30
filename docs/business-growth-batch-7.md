# Business Growth Batch 7 — pipeline, diary, Quick Add Lead

Branch: `growth/business-growth-batch-7` from production/main
`587f397120adc2f2cc6054446f45ab03bdc3a4c5`. Staging only until Nigel
explicitly approves production promotion.

## Existing record relationships

- A lead can exist before a customer, visit or quote. Batch 6 already links a
  quote to a lead and an invoice to a quote, while preserving independent quote
  outcomes, follow-up dates, source and work type.
- New `appointments` link to a lead. A site visit does not require a quote or
  job. Confirmed, provisional, completed and cancelled visits are explicit;
  provisional appointments require a follow-up date. A start/end range can
  span several days for a scheduled job.
- New `jobs` link a lead or quote and, optionally, an existing invoice. They
  have awaiting schedule, scheduled, in progress and completed statuses.
  Invoiced/paid stages are derived from existing linked invoice data.
- Pipeline cards aggregate multiple quotes under one lead. A won quote cannot
  be downgraded by another pending/lost quote. A job marked scheduled without
  booked dates remains in the awaiting-schedule stage. Historical unclassified
  quotes remain unclassified; closed lost/expired work remains visible
  separately and does not appear as an active visit merely because an older
  booking exists.
- The weekly diary groups every day, including free days. A multi-day job
  appears on each overlapping day. Closed-lead bookings are called out for
  review instead of occupying the active workload. Cards open the lead or
  load it directly into the existing quote builder, which already supports
  site notes/media and quote/PDF generation.

## Quick Add

Paste a message into the private app, request a conservative preview, correct
name/phone/address/job/source/work type and optionally confirm a site visit.
Common address wording and signed customer names can be suggested, but uncertain
fields remain blank. After save, a persistent panel links directly to the lead,
visit booking or booked Diary visit, and the linked quote builder. A booked
visit's Calendar action remains a separate reviewable draft in its Diary card.
Only explicit full UK dates with a time are suggested. When a confirmed name
and phone/address identify a customer, the confirmation links an existing
customer or creates one before a quote exists. It writes the customer, lead
and optional appointment in a single SQLite transaction; a unique
submission key returns the same lead after a repeated click/request. It never
sends the customer a message. Public enquiry capture remains unchanged.

### Multi-task enquiry and quote survey review

The existing `work_type` remains the **primary** reporting classification.
Additive `additional_work_types` JSON columns on leads and quotes contain only
other controlled categories; old rows get `[]`. Headline lead/quote/outcome/
value counts still use each record once. Quick Add suggests clear tap, toilet/
cistern and radiator/TRV wording only, then Nigel edits the preview and confirms
before any write. The original message remains the job description. The mobile
form keeps the primary selector visible and puts additional checkboxes in a
compact expandable control. Lead classification can be edited later; Start
Quote carries primary/additional types, source, email, address and description
to the quote builder. Saved quotes retain both types. A site visit is a short
quote survey, not a job booking. The Diary labels these separately; a completed
visit still appears in the quote-next pipeline stage. New plumbing job diary
bookings require a linked won quote/job. Existing appointments remain valid.
Google Calendar still opens only a reviewable draft from the Diary card.

## Calendar boundary

The diary shows a week at a time and marks provisional follow-ups. “Add to
Google Calendar” opens a pre-filled event draft for Nigel to review and save.
There is **no automatic two-way Google Calendar sync or conflict check**:
the deployed app has no authorised Google Calendar OAuth integration. This
prevents silent external calendar writes or inferred availability. Full sync
would need a separate account authorisation and safe token/storage design.
Booksy/unified external availability is benched as a future idea; Batch 7 has
no Booksy connection, import or availability check.
The safe follow-up path is to obtain Nigel's explicit Calendar account
authorisation and exact calendar choice, use minimum read/write permissions,
store revocable tokens securely outside source control, attach Calendar event
IDs to appointments, reconcile edits and cancellations in both directions,
check existing calendar commitments before confirming a date, and handle
Europe/London daylight-saving boundaries. Provisional holds need an explicit
expiry/review policy. Test this first against an isolated calendar and staging
data; no OAuth credentials or Calendar permissions are added in Batch 7.

## Release verification

Run `python scripts/verify_release.py --environment staging` inside the
existing staging service Shell, or `python scripts/verify_release.py
--environment production --read-only` inside the production service Shell
after a separately approved future release. The script checks service identity
where Render exposes it, environment, origin and mounted disk; opens SQLite
`mode=ro`; checks counts, backup files, integrity, required schema, protected
GET APIs, existing documents, anonymous auth boundaries, all 72 sitemap URLs,
metadata/canonicals, robots, 13 redirects and apex redirect on production.
It produces JSON and PASS/FAIL. It never writes records or contacts customers.
Render deploy SHA, runtime logs and HTTP 5xx outside its own requests are
verified separately through Render's deployment/log API. The Shell environment
must expose the existing APP_USERNAME/APP_PASSWORD to access private GET APIs;
the script never prints them.

## Verification record

- Local Batch 6 baseline: 89/89 Python tests passed, production verified.
- Batch 7 initial isolated tests: 96/96 Python tests passed, plus JavaScript
  syntax and Python import/compile checks. Re-run after the focused staging
  corrections described above.
- Staging service: `srv-das0vrflk1mc73dtb2cg`; initial Batch 7 deployment
  `dep-dau5lpmk1f9s73af59d0` ran approved commit
  `a498666e9fb3d67041db85a099bfd966c8f9fd2a`. Final correction deployment
  and live verification remain to record.
- Production/main, GBP, directories, credentials, analytics and Render
  environment/disk/build/start settings: unchanged by Batch 7.

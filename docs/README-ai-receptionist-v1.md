# AI receptionist V1 — Phase 2, Steps 1–3

Private synthetic foundation only. Base: freshly verified `main` at
`630eefa4baa9aa3548690848ac240a74b1607c0d`. Work belongs on
`feature/ai-receptionist-v1`. Step 4 requires Nigel's approval.

## Boundaries

No number, subscription, paid service, provider account, chargeable API call,
real telephone connection, production deployment or merge is part of this
implementation. No production customer database is opened. Public pages,
templates, JavaScript, company telephone details, SEO, quoting and invoicing
behavior are unchanged. There are no deployment workflows in this checkout.

The integration is disabled by default. Enabling it requires `APP_ENVIRONMENT`
to be exactly `test` or `development`, an explicit sandbox root, and a database
inside that root and outside `/var/data`. Startup rejects unsafe settings.
The supplied runners copy the app and rewrite storage paths **before import**,
create a disposable database, neutralize email/Google/OpenAI settings and block
all outbound HTTP, DNS, SMTP and non-loopback socket connections.

Do not run `uvicorn app:app` from the unmodified checkout for this project:
its existing database configuration still targets `/var/data/quotes.db`.
Use the disposable runner below. No hosting or database environment was changed.

## Exact changes

| File | Change |
|---|---|
| `.gitignore` | Exclude Python caches, local credentials, virtual environments, logs and SQLite files. |
| `app.py` | Exact HMAC machine-route exception to Basic Auth; seven private routes registered only when the sandbox feature is enabled. Existing public route allowlist unchanged. |
| `business/db.py` | Initialize additive voice tables only when the private feature is enabled, after the existing schema. |
| `business/lead_store.py` | Redact linked call content/transcripts/outbox atomically when an existing deletable lead is deleted. Preserve replay tombstones and existing financial deletion guards. |
| `business/phone_numbers.py` | Normalise UK full numbers to E.164 for comparison; retain display input. Reject extensions, foreign numbers, local-only numbers and ambiguous strings. Possible format does not prove allocation or ownership. |
| `business/voice_security.py` | Feature/environment/storage guards, bounded HMAC authentication with timestamp and nonce, authenticated Fernet encryption. |
| `business/voice_models.py` | Bounded, versioned, synthetic-only full-snapshot contract; timezone-aware timestamps; separate presented caller ID and confirmed callback details. |
| `business/voice_policy.py` | Identification, priority classification and limited emergency guidance. Gas/CO directs to emergency services rather than Nigel. |
| `business/voice_store.py` | Atomic call/event/lead/outbox handling, conservative customer matching, staff-edit preservation, expiry/deletion and leased notification retries. |
| `business/voice_api.py` | Signed machine intake; staff call list/detail, transcript deletion, expiry maintenance and notification status/retry controls. Responses use `Cache-Control: no-store`. |
| `business/voice_simulator.py` | Deterministic dialogue policy with explicitly annotated synthetic extraction fixtures; ten scenarios. No language model or speech service. |
| `requirements-test.txt`, `requirements-voice-test.txt` | Pinned cryptography and phonenumbers in test dependencies, plus a named private-test entry point. Production requirements unchanged. |
| `tests/local_browser_server.py` | Neutralise inherited voice settings; allow explicitly supplied synthetic credentials; verify the 80 original routes plus seven optional voice routes. |
| `tests/voice_support.py` | Generate ephemeral keys and sign local test requests. No saved credentials. |
| `tests/test_voice_receptionist.py` | 39 automated tests, including API/DB/security/retention/outbox/concurrency and emergency policy. |
| `tests/run_voice_simulations.py` | Run all ten conversations through the signed API and export fictional call/lead/notification records. |
| `tests/run_voice_private.py` | Optional loopback-only API inspection with disposable seeded records and temporary staff login. |
| `docs/ai-receptionist-v1-simulations.json` | Full fictional conversations and resulting records from the local signed-API simulation run. |
| This document | Scope, behavior, reproduction, results and remaining decisions. |

## Integration and idempotency

`POST /integrations/voice/v1/enquiries` is the only machine-authenticated route.
It is hidden from the schema and requires a signed raw body, including version,
HTTP method, exact path, timestamp and nonce. The replay window is five minutes;
nonces are unique and retained for ten minutes. Bodies are limited to 64 KiB;
validation errors never echo submitted content. Staff Basic Auth cannot substitute
for the HMAC. All other voice routes keep existing Basic Auth and cross-site
write protection. There is no broad public integration prefix.

The provider/account pair is pinned to `simulation` / `synthetic-v1`. Root IDs
must start `sim-`, event IDs `evt-`, and `synthetic` must be boolean `true`.
No real provider adapter is present.

One SQLite `BEGIN IMMEDIATE` transaction handles the authenticated nonce, event,
root call, optional existing lead and durable notification. Root uniqueness is
`(provider, account, root_call_id)`; event uniqueness is
`(provider, account, event_id)`. A newly signed retry of the same event returns
the stored IDs. Conflicting event reuse and same-sequence conflicts return 409.
Older snapshots are acknowledged without overwriting newer data. Final calls
cannot reopen; start times cannot change. Child leg IDs are metadata on the same
root rather than new enquiries. No raw event payload is retained in the event table.

Useful work details create an ordinary `new` lead in the existing workflow.
The contact channel is `phone/AI`; acquisition category starts as `Other` rather
than falsely attributing it to website traffic. Postcode and urgency use the
existing structured lead context. Appointment preferences go into the enquiry,
clearly labelled **not booked**. No visits, quotes, jobs or invoices are created.
Summary, photos-useful flag and provenance remain on the private call record.

Silent calls produce call records only. Incomplete calls with known work still
produce enquiries. A callback-only incomplete call can queue a call summary
without inventing a plumbing job. Snapshots retain known fields when later input
is blank; urgency cannot be downgraded. Updates preserve staff edits and never
reset workflow status or overwrite customer details.

Customer matching requires a confirmed name and callback number, a single
normalised-number candidate and a matching name. Shared numbers and mismatched
or unconfirmed names stay unlinked for review. Presented caller ID is stored
separately and never treated as identity proof. New callers remain leads until
the existing workflow needs a customer; no parallel customer database is added.
V1 matching scans the small existing customer table; indexing/verified identity
can be designed later without changing current customer behavior.

## Privacy and durable notifications

Provisional private defaults, subject to approval before real caller data:

| Data | Control |
|---|---|
| Transcript | Encrypted; hidden at expiry even before maintenance; 30 days from first receipt. Explicit staff deletion sets a tombstone preventing restoration by later events. |
| Call facts/summary/presented number | Encrypted; 90-day expiry from first receipt. Expired calls cannot recreate content. |
| Notification payload | Encrypted pending delivery; removed immediately after successful delivery; seven-day expiry otherwise. |
| Event/root replay metadata | IDs, hashes, sequence and receipt times only; retained as tombstones. Final metadata retention policy remains to be approved. |
| Existing enquiry/customer fields | Existing app storage; no new blanket deletion or financial retention rule. |

Maintenance is explicit (`expire()` / staff-only maintenance endpoint). No
scheduled service is created. SQLite secure deletion is enabled on voice writes
and lead redaction. This does **not** erase old backups, exported files, WAL copies
or recipient inboxes; backup/export retention and the real scheduler must be
settled before production. Fernet keys are external environment configuration,
not database content. Runners generate ephemeral keys and discard them on exit.
Production key storage, rotation and recovery are still future work.

The outbox is committed with the enquiry. Pending snapshots coalesce into the
latest summary. A later update after delivery can create a new revision. Workers
claim a two-minute lease atomically, send outside the database transaction,
retry with exponential backoff and stop visibly after five failures. Expired
leases recover after crashes. Error records contain exception types, not
customer content. Staff can inspect failed items and retry unexpired failures.
Successful payloads are removed. Stable message IDs support recipient/provider
deduplication.

Delivery is **at least once**, not an exactly-once promise: a crash after an
external delivery but before acknowledgement can repeat a message. Only an
injected fake sender is used here; no SMTP, SMS or real notification worker is
included or started. No email is sent.

## Reproduce privately

Use Python 3.12+ and an isolated virtual environment. Installing these ordinary
open-source packages does not create a provider account or chargeable service.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-voice-test.txt
.venv/bin/python tests/run_stage6_local.py --python-only
.venv/bin/python tests/run_voice_simulations.py --output /tmp/voice-simulations.json
# Optional local inspection. Ctrl+C discards storage and credentials.
.venv/bin/python tests/run_voice_private.py --port 8765
```

The inspector prints a temporary staff login and serves only `127.0.0.1`.
Open `/api/voice/calls`, then `/api/voice/calls/1` for a transcript and facts.
`/api/leads` contains the resulting ordinary enquiries. This is JSON API
inspection, not a finished receptionist dashboard. Its seed data does not
include the saved returning customer; the exported simulation report does.

## Verification

- Full Python suite: **152 passed**, comprising 113 existing tests and 39 voice
  tests, with outbound connections blocked.
- Ten signed-API plumbing simulations: **passed**.
- Replaying the final simulated event returned `duplicate`, preserving call 10
  and lead 9. No additional call, enquiry or notification was created.
- Twelve concurrent duplicate event deliveries created one enquiry and one
  notification; concurrent outbox workers sent one item while its lease was valid.
- Synthetic protected quote and invoice records remained byte-for-field unchanged
  after intake and lead deletion. Existing route inventory stayed at 80 with the
  feature disabled; 87 with it enabled.
- Syntax compilation and `git diff --check`: passed.
- Existing browser runner: **incomplete**, because its preinstalled Chromium
  executable is unavailable. No browser was downloaded. No templates or browser
  JavaScript changed. Actual voice, audio latency and model extraction are untested.
- Framework warnings: existing `on_event` startup handlers and the installed
  Starlette/httpx test adapter emit deprecation warnings; no test failed from them.

## Simulation results

All names, addresses and numbers in the example output are fictional. `TE1 1ST`
is a deliberate test placeholder, not a verified service address. The phone
numbers use the UK `07700 900xxx` fictional range. Call/lead IDs below refer only
to the disposable simulation run. One pre-seeded synthetic customer remains one.

| Scenario | Call | Lead | Outcome | Priority | Transfer request |
|---|---:|---:|---|---|---|
| Dripping kitchen tap | 1 | 1 | completed | routine | no |
| No details before hangup | 2 | — | incomplete | routine | no |
| Running toilet, partial address | 3 | 2 | incomplete | routine | no |
| Returning Alex Example | 4 | 3 | completed | routine | no |
| Uncontrolled burst pipe | 5 | 4 | completed | urgent | simulated |
| Water onto light fitting | 6 | 5 | completed | electrical_water | simulated |
| Smell of gas | 7 | 6 | emergency_redirect | gas_co | no |
| CO alarm and unwell occupant | 8 | 7 | emergency_redirect | gas_co | no |
| Outside tap, relative appointment preference | 9 | 8 | completed | routine | no |
| Toilet repair, details over several turns | 10 | 9 | completed | routine | no |

Final counts: **10 calls, 9 leads, 15 distinct events, 9 fake notification
deliveries, 1 pre-existing synthetic customer**. Quotes, invoices, jobs and
appointments: zero. Every call remains marked for staff review.

For the normal enquiry, the caller supplies name, callback, address, postcode,
problem, appointment preference and willingness to send a photograph in one
utterance. The receptionist acknowledges these details without asking for them
again. The stored lead has status `new`, channel `phone/AI`, category `Other`,
postcode, routine urgency and the unbooked Tuesday afternoon preference. The call
retains the summary and photos-useful flag. The returning enquiry links to the
same synthetic customer and leaves its saved address untouched.

For a multi-turn repair, the receptionist asks for the missing name, callback
number and address in turn. Once the final caller utterance includes both address
and postcode, it asks no separate postcode question.

For water near electrics, it advises keeping away, avoiding switches/equipment
when standing in water, and isolating the supply only if safely possible. It
flags urgency and records a simulated transfer request. No mobile is dialled.

For gas/CO, it gives emergency guidance immediately, points to **0800 111 999**
and **999** for immediate danger/serious illness, and says not to wait for Nigel.
It does not delay this with contact/address questions or attempt a Nigel transfer.

Safety sources checked during implementation:
- [National Gas emergency contacts](https://www.nationalgas.com/en/node/256)
- [HSE carbon monoxide guidance](https://www.hse.gov.uk/gas/domestic/co.htm)
- [Electrical Safety First flood guidance](https://www.electricalsafetyfirst.org.uk/safety-advice/home-and-people/house-maintenance/electrical-safety-after-a-flood/)
- [GOV.UK flood precautions](https://www.gov.uk/help-during-flood)

## Decisions still needed before real caller use

1. Explicit approval and budget for Step 4 private voice/API testing; select the
   adapter/provider, without buying or publishing a public number.
2. Real caller disclosure and privacy-policy wording, lawful basis, retention
   defaults, metadata lifetime, processor contracts and international transfers.
3. Encryption key storage/rotation/recovery, backup/export expiry and scheduled
   retention maintenance in an isolated service.
4. Real summary delivery channel and recipient; delivery/provider deduplication
   and operational alerts for failed/expired queue items.
5. Nigel's urgent transfer rules, working hours, fallback when unavailable and
   human review of emergency wording. No availability or response is guaranteed.
6. Voice quality, UK accents, interruptions, background noise, number/address
   confirmation and adversarial caller testing with an actual model. These
   annotated fixtures cannot establish real-world extraction accuracy or safety.

No Step 4 voice/provider testing has started. No deployment, merge or purchase
is requested by these files.

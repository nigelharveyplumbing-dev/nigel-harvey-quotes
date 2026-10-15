# Private telephone provider adapter — offline development

Status: local implementation for review. No publication, deployment, number,
customer access, provider connection, credential setup or paid testing authorised.

## Implemented path

`business.voice_provider.create_pilot_app` creates a **separate ASGI service**.
It is not mounted into the public website or `/app` and does not import the
production database. The existing pilot controller and speech policies remain
unchanged; the historical simulation API still rejects provider/real-call events.

1. `/pilot/incoming` validates the Twilio SDK signature over the configured public
   origin, exact path/query and all posted fields; checks account, destination and
   caller allowlist; then gathers a private six-digit test PIN. Caller ID is
   presented information, not proof of identity. PIN digests use an HMAC pepper.
2. `/pilot/pin` durably throttles attempts, enforces one active root call and
   calls the existing `PilotState.start` and `ring_twiml`. Nigel's mobile rings
   first. Recording is disabled. Child whisper requires a timely DTMF 1.
3. `/pilot/screen`, `/pilot/accept`, `/pilot/dial-finished` correlate signed
   account/root/child legs. Acceptance only grants `bridge_pending`. A signed
   correlated `DialBridged=true` completion confirms a human bridge. A voicemail
   answer without acceptance falls back to the AI disclosure.
4. `/pilot/ai-choice` offers DTMF 0 for a non-AI callback. Callback details can be
   entered by keypad without AI. No stream starts before the disclosure/choice.
5. `/pilot/media` authenticates the WebSocket upgrade using the SDK and fixed
   origin; checks start-event context, account, root/stream SIDs and 8 kHz mono
   G.711 mu-law codec. One transactional stream claim prevents reconnect/replay.
6. The media bridge speaks the pinned Realtime event protocol using an injected
   connected socket. It sends session configuration and waits for acknowledgement;
   forwards ordered caller PCMU; requests each response explicitly; enforces 12
   response requests / 768 output tokens and bounded input/output/idle/deadline
   limits. No arbitrary tool, appointment, gas job or direct transfer is exposed.
7. Spoken and DTMF non-AI requests stop the AI transport. Caller-only transcript
   triage uses existing policy functions. Gas/CO, electrical/water emergencies,
   uncontrolled water and ordinary gas-work requests stop model speech and use
   the existing fixed TwiML safety/refusal message after Stream ends.
8. Ordinary assistant audio is held in memory until the response is complete and
   a transcript is available for bounded speech/promise checks, then sent as PCMU
   plus playback marks. This adds latency deliberately. These checks and prompts
   are **not a semantic safety proof** or a substitute for human listening.
9. On interruption, clear buffered audio and truncate model conversation history
   only to the last acknowledged audio-chunk boundary. Marks returned by `clear`
   are discarded rather than treated as proof that audio was heard.
10. Capture uses the established `VoiceFacts` contract; normalises full phone and
    postcode without guessing; downgrades model identity confirmations to false;
    refuses booking confirmation and derives urgency from caller hazards only.
    Enquiry + notification commit together in an encrypted private staging store.
    No notification is sent and no production lead/customer is created.

## Persistence and failure handling

`PilotStore` requires an explicitly supplied new/empty private directory outside
the repository and `/var/data`. It uses a namespaced SQLite database, 0700
directory, 0600 file, encrypted state/enquiries/notification bodies and SQLite
immediate transactions. It refuses symlink destinations and unrelated databases.
No audio files or plaintext transcripts are written. Call IDs, token hashes and
minimal state/correlation indexes remain available for replay protection.

Provider retries return the durably cached result; conflicting retries are
rejected. A response intent commits before each `response.create`; response IDs
and complete/incomplete/cancelled usage receipts are associated durably. Missing
usage, unsolicited responses, errors, disconnects or failed closure stop without
automatic reconnect/retry. These **synthetic protocol receipts are not billing
ledgers**, do not calculate a live allowance, and never replace historical files.
`PilotStore.recover_interrupted` explicitly queues expired interrupted sessions
for review after a crash; it never resumes the model session. Uncertain usage is
not represented as zero. No automatic notification sender is installed.

## Activation and remaining work

The ordinary factory defaults to disabled and returns HTTP 503 / rejects media
WebSockets before calling any model factory. Existing environment flags or an API
key cannot change that. The only admitted mode is an explicit **offline harness**:
fictional `.example.invalid` origin, Ofcom drama-range mobile numbers and an
injected synthetic transport. The `synthetic_only` transport declaration is a
trusted test seam, not a live accounting authorisation mechanism.

This implements telephone routing, the bidirectional provider protocol and a
credential-injected `RealtimeProviderFactory` with the pinned model endpoint,
bounded WebSocket settings, sanitised errors and disabled payload/debug logging.
Its default `ClosedPilotAdmission` always refuses **before credential access or
network I/O**. No credential is read or configured by importing or constructing it.
It is **not a live private-number pilot yet**: no live admission/accounting path
has been approved or enabled, and no deployment/server instance is started.

Before a controlled paid test can be considered:

- Original-journal reconciliation or a separately reviewed/approved exception
  under PR #23 must resolve the accounting gate. Its aggregate export agreement
  is not journal recovery. Historical spend stays counted; £4.85 working and £5
  hard cumulative limits are unchanged. Never load a derived ledger as original.
- Review and validate the provider/network factory, runtime admission, private credentials,
  durable monetary reservation/settlement, ASR-specific and Twilio billing, stop
  conditions and an exact prospective cumulative spending limit. The new response
  intent table is not a substitute for monetary admission or original journals.
- Recheck current prices and propose an exact, separately approved test scope and
  ceiling. ASR in this protocol uses `gpt-4o-mini-transcribe` in addition to the
  existing `gpt-realtime-2.1`; do not silently omit transcription/telephony costs.
- Approve publication separately, run exact-head CI, review staging-only hosting,
  access/PIN/key setup and deployment. Keep access logs off for token-bearing
  URLs, and configure bounded server WS frame/queue settings (e.g. max queue 16,
  max message 20,000 bytes). Choose and verify a number only after separate scope.
- Verify real provider handshake/codec/DTMF/dial semantics and live listening on
  an allowlisted test number. Synthetic tests establish no live audio quality,
  model recognition, actual call routing, provider compatibility or billing.
- Define staging record expiry/redaction and staff review/delivery before any
  real personal data. Current storage is only exercised with temporary fictional
  records. No production data access or customer enablement is included.

## Offline verification

Install `requirements-voice-provider-test.txt` into an isolated test environment.
It adds the official Twilio SDK for signature validation; production requirements
are unchanged. Tests inject a deterministic model socket and disposable storage.

```sh
PYTHONPATH=tests/voice_lab/offline_guard:.:tests PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p 'test_voice_provider_adapter.py' -v
PYTHONPATH=tests/voice_lab/offline_guard:.:tests PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
PYTHONPATH=tests/voice_lab/offline_guard:.:tests PYTHONDONTWRITEBYTECODE=1 python tests/run_voice_recovery_preflight.py
```

No command above starts a telephone service or makes a model request. Existing
paid runners must not be used. No credentials are needed for these tests.

Local validation completed on 15 October 2026:
- **279 Python tests passed**, including **166 voice tests** and **32 new
  provider-adapter/transport tests**. Final full run: 33.841 seconds.
- Signed HTTP and WebSocket fixtures exercised the complete fictional call path,
  concurrent single-call admission, callback idempotency, child-leg correlation,
  human acceptance, AI disclosure/opt-out, speech safety holds, gas/water/electrical
  guidance, interruption marks, receipt failures and crash recovery.
- The network guard was enabled and the test environment contained no real
  provider credentials. The SDK was used only for local signature operations;
  the network connector was mocked.
- Frozen-plan preflight passed and still reported no live authority. All 50
  retained evidence files matched their preserved SHA-256 snapshot. No original
  journals, prompts, policy, production route or spending limits changed.
- No GitHub CI, publication, deployment or live provider compatibility result is
  claimed for this local implementation. Publication requires owner approval.

Protocol references reviewed during development:
- https://www.twilio.com/docs/usage/webhooks/webhooks-security
- https://www.twilio.com/docs/voice/media-streams/websocket-messages
- https://www.twilio.com/docs/voice/twiml/number
- https://developers.openai.com/api/docs/guides/voice-websockets?voice-api=realtime
- https://developers.openai.com/api/reference/resources/realtime/client-events

Use the Realtime `gpt-realtime-2.1` contract, not the distinct GPT-Live session
protocol shown alongside it in current docs. These links are protocol references,
not a claim of a current pricing check or access to a provider account.

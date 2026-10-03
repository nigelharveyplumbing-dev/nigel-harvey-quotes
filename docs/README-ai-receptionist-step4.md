# Step 4: private voice benchmark — prepared, live testing blocked

Status on 3 October 2026: **no authenticated voice API trials have run**.
Secure OpenAI API credentials are absent. The OpenAI Developers plugin was
declined; the standalone runner works without that plugin. Do not put an API
key in chat, source code, a report or GitHub.

This work continues `feature/ai-receptionist-v1` from Steps 1–3 commit
`00c11eca0c0d098320171b92336cc09c3b13a7bb`. The application feature remains
disabled by default. This step adds a test lab only: no production application,
database, route, migration, public assets or runtime requirements changed.
No numbers, services, telephony, deployments or main merge were created.
No Step 5 work is authorized or started.

## Changes

| File | Purpose |
| --- | --- |
| `tests/run_voice_api_benchmark.py` | No-network default preflight; explicitly opted-in, sequential paired API trials; safe reports and immediate stop on failure. |
| `tests/voice_lab/__init__.py` | Standalone private test package. |
| `tests/voice_lab/cases.py` | Fourteen fixed fictional scenarios, hidden expected answers, receptionist instructions and bounded capture tool. |
| `tests/voice_lab/audio.py` | Free local British English caller synthesis; PCM validation and script/audio hash verification. |
| `tests/voice_lab/budget.py` | Exclusive, persistent spending journal; reserve before each response, settle reported token usage, block unresolved usage and stale pricing. |
| `tests/voice_lab/realtime.py` | WebSocket audio transport, manual response control, virtual talk-over/truncation, response audio and capture output. Live protocol compatibility is unverified. |
| `tests/voice_lab/scoring.py` | Exact extraction checks; separate provided phone/postcode accuracy and unknown-field abstention; explicit listening/safety review gates. |
| `tests/test_voice_api_lab.py` | Offline accounting, isolation, audio tampering, protocol control and reporting tests. |
| `requirements-voice-api-test.txt` | Optional pinned WebSocket and free local speech dependencies; production requirements unchanged. |
| `docs/ai-receptionist-step4-preflight.json` | Actual no-network preflight output, not model results. |
| This document | Execution instructions, limitations and blocked comparison. |

## Paired experiment

Current official model pair: `gpt-realtime-2.1-mini` and `gpt-realtime-2.1`.
Both use the same Marin voice, instructions, tools, 24 kHz mono PCM input,
768 output-token cap and prerecorded caller clips. Model order alternates by
scenario. Record the server-resolved model and returned configuration; aliases
may change. The reasoning setting is low; server acceptance remains untested.

Fourteen scenarios cover normal enquiries, caller talk-over, a spelled UK name,
Guildford/Woking postcodes, local and international spoken numbers, an incomplete
caller, returning-customer language without history access, a burst pipe,
water beside electrics, gas smell, a CO alarm with serious illness, appointment
preferences, corrected digits during an interruption, and an unsafe gas request.
Sixteen local audio clips are hash-verified. Twenty-eight live trials are planned,
with sixty explicitly budgeted responses including extraction. No separate
input transcription service is enabled.

The scripts are fictional; callback numbers use the 07700 900xxx drama range.
Example addresses are invented; postcode strings are parsing fixtures and do
not identify actual customers. Expected answers are never sent to the model.
The capture function returns test facts; it cannot write enquiries, look up
customers, send messages, book visits or transfer calls.

## Budget and controls

Official prices checked 3 October 2026, USD per million tokens:

| Model | Text input / cached / output | Audio input / cached / output |
| --- | --- | --- |
| Mini | $0.60 / $0.06 / $2.40 | $10 / $0.30 / $20 |
| Larger | $4 / $0.40 / $24 | $32 / $0.40 / $64 |

The complete batch's conservative planning allocation is **£4.8115905**.
This is not a billed result. It assumes £1.25 per USD including conservative
VAT/fee loading; it is not a live exchange-rate quotation. It treats context
as uncached, bounds prompt tokens by UTF-8 bytes, counts previous output in both
input modalities, includes envelope overhead and prices all output at the most
expensive modality. Audio is bounded using the documented token rates.

The working ceiling is £4.85, leaving £0.15 below the user's £5 ceiling.
The full batch and any existing journal balance must fit before a live session
starts. Each paid response is reserved first; reported modality/cache usage
then replaces that reservation. Missing usage, unexpected autoresponses,
overrun, disconnect, timeout or API error stops the batch. There are no retries
or fallback models. Reservations survive interruption/restart; an unresolved
journal must be reconciled, never reset to circumvent the limit. Rates older
than three days must be rechecked before live use.

This is a conservative application spending guard, not a provider billing cap.
Provider accounting, token overhead and currency/tax changes are reasons to
stop and reconcile if reported costs exceed an allocation. A reduced batch or
fresh price review is needed if the full estimate no longer fits; approval is
required before an estimate above £5 can proceed.

**Actual paid API usage in this turn: zero requests, £0.** An unauthenticated
connectivity check returned HTTP 401; that is not a model trial.

## Verification and results

Full offline suite: **167 tests passed** (152 existing plus 15 new lab tests).
The new lab tests were rerun successfully after accounting refinements. The
sixteen generated caller clips passed format, duration and hash validation.
Existing FastAPI/Starlette deprecation warnings remain; they are not failures.

| Requested comparison | Mini | Larger |
| --- | --- | --- |
| Extraction, postcode and phone accuracy | Not measured | Not measured |
| Interruption handling | Not measured live | Not measured live |
| End-of-caller to first output-audio latency | Not measured | Not measured |
| Naturalness | Not assessed | Not assessed |
| Emergency handling / unsafe behavior | Not assessed | Not assessed |
| Reported tokens / usage cost | No live usage | No live usage |

No new voice-model conversation, lead or call record exists. The existing
Steps 1–3 simulation report remains annotated offline data; it is not reused as
evidence of model performance. The preflight report contains empty live results
and a null recommendation. **A pilot model cannot be recommended from measured
results yet.** Complete the comparison and safety listening review first.

## Running privately once secure credentials are available

Use a local virtual environment, ffmpeg and a private output directory outside
the repository and `/var/data`. The optional dependencies are free packages.

```sh
python -m pip install -r requirements-voice-api-test.txt
python tests/run_voice_api_benchmark.py --private-dir /tmp/nigel-voice-lab --generate-audio
python -m unittest discover -s tests -v
```

The first benchmark command generates only local caller audio and performs
preflight. It makes no network requests even if a key is already configured.
For an authorized local run, enter a key through the hidden local prompt:

```sh
VOICE_API_TEST_ENABLED=1 python tests/run_voice_api_benchmark.py --private-dir /tmp/nigel-voice-lab --live --prompt-key
```

Alternatively, supply `OPENAI_API_KEY` through the private environment's secure
secret configuration and omit `--prompt-key`. The lab switch is independent of
the app's feature switch and does not enable the app. Do not connect production
environment files, databases or other services. A funded API project with access
to both models is required; do not purchase credits without approval.

Reports are written after each completed trial. Audio is stored locally;
reports and the journal have private file permissions. The output folder is
synthetic-only scratch: delete it after reviewing or securely retain it outside
Git; no production transcript retention controls are exercised by this lab.

Listen to each generated response, and to the heard-prefix WAV for an interrupted
response. Generated transcripts include potentially unplayed words; keyword
screens cannot prove the caller received safe advice. Review emergency guidance
before routine questions, invented details/history, false bookings/transfers,
corrected digits, semantic extraction and whether advice was truncated.
Assign naturalness ratings consistently and document failures. Virtual playback
tests transport truncation, not actual browser speakers/microphone echo or
human conversational turn taking. One robotic caller voice and one trial per
model/scenario cannot establish reliability across human UK accents or a
statistical latency distribution. Further browser listening may be needed
within the remaining approved budget before selecting a pilot model.

## Sources

- [Mini model](https://developers.openai.com/api/docs/models/gpt-realtime-2.1-mini)
- [Larger model](https://developers.openai.com/api/docs/models/gpt-realtime-2.1)
- [OpenAI pricing](https://developers.openai.com/api/docs/pricing)
- [Realtime audio conversations](https://developers.openai.com/api/docs/guides/realtime-conversations)
- [WebSocket transport](https://developers.openai.com/api/docs/guides/voice-websockets)
- [VAD controls](https://developers.openai.com/api/docs/guides/realtime-vad)
- [National Gas emergency guidance](https://www.nationalgas.com/en/node/256)
- [NHS carbon monoxide guidance](https://www.nhs.uk/conditions/carbon-monoxide-poisoning/)
- [Electrical Safety First flooding guidance](https://www.electricalsafetyfirst.org.uk/safety-advice/home-and-people/house-maintenance/electrical-safety-after-a-flood/)

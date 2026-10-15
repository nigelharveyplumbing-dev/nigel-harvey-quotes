# Step 4.6 offline recovery — reconstructed validation safeguards

15 October 2026. This branch reconstructs **new offline-only checks** from the existing Step 4.6 validation plan. It is not the missing original `eb7fc53` commit and does not claim to reproduce its six files or 247-test result.

## What was reconstructed

- `tests/run_voice_recovery_preflight.py`: read-only synthetic-plan verifier that checks frozen prompt hashes, the eight required and two conditional scenarios, response reservations, prior reported spend and cumulative limits.
- `tests/test_voice_recovery_preflight.py`: negative tests that reject altered prompts, a changed spend cap, reset historical spend, optional-case escalation and missing journal gates.
- Existing prompts, production application, test audio, telephony, journals and evidence are unchanged.

The verifier intentionally reports `ready_for_live_validation: false`. Its output is a planning check only, not evidence that Mac paid journals/audio were reconciled. The existing Step 4.6 plan still requires the two original journals, exact paid Mac audio hash checks, independent price verification, explicit approval and a narrowly reviewed runner extension before any paid trials.

## Offline command (no API key, network calls or paid usage)

From the repository root, with the existing test environment:

```sh
PYTHONPATH=.:tests python tests/run_voice_recovery_preflight.py
PYTHONPATH=.:tests python -m unittest discover -s tests -p 'test_voice*.py'
```

This reconstruction does not request or modify API credentials, purchase a telephone number, call customers, change production, change spending limits or merge the feature branch.

## Remaining before considering publication of a functional Step 4.6 replacement

1. Obtain the original six changed files or accept that only a newly reconstructed version can be reviewed.
2. Run the offline test suite and inspect results against the exact new commit.
3. Verify no private audio, journal, personal information or secrets enter the diff.
4. If further work is required, add only reviewed, offline changes. Do not silently replace or force-update `feature/ai-receptionist-v1`.
5. Obtain a separate explicit approval for any publication to the original feature branch and separate approval for any paid validation or live telephony.

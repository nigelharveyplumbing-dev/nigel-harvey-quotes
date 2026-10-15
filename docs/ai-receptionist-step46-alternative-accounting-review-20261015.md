# Step 4 / 4.5 — alternative accounting exception: REVIEW ONLY

**Prepared:** 15 October 2026  
**Decision requested:** Review whether an alternative historical accounting pathway should be *investigated*. **No exception is granted by this document.**  
**Related:** draft PR #23 recovery plan; draft PR #22 offline safeguards (unchanged).

## Summary for reviewer

The original Step 4 and Step 4.5 spending journals were not found on the Mac. Owner-executed read-only checks did verify the Step 4 benchmark-report hash and all 21 Step 4.5 caller-input WAV hashes, found 17 Step 4.5 paid archives containing 35 response entries, and reconciled their saved `usage_usd` to **$0.68876960** (historical loaded planning **£0.86096200**). The archives include 31 completed, two incomplete and two cancelled responses. All 19 delivered audio references and two interruption heard-prefix references resolve to existing files, but independent historical generated-output hashes are unavailable.

The owner subsequently supplied two OpenAI Platform exports for 1–15 October 2026:
- **Cost:** 4 October 2026, organisation-grouped **$1.52736460**.
- **Activity:** 4 October 2026, project/model-grouped **31 `gpt-realtime-2.1`** and **14 `gpt-realtime-2.1-mini`** model requests, **45 total**.

Historical Step 4 report-derived USD **$0.83859500** plus Step 4.5 archive USD **$0.68876960** equals **$1.52736460**, with **$0.00000000 aggregate difference**. This is a meaningful corroboration of the **aggregate** historical planning cost, not a request-level audit, invoice settlement, or proof that the missing journals can be safely replaced.

**Do not commit or attach the source CSVs to GitHub.** They contain sensitive account and API-key identifiers; the aggregates above are sufficient for this review.

## Why the existing gate remains blocked

The current `tests/voice_lab/hardening.py` `Baseline` requires an original `spending-ledger.json` with exact labels, valid settled states, unique entries, complete model/case coverage, reported planning spend, and matching audio/report identity. Its Step 4.5 candidate logic expects a separate extension journal. The missing journals prevent proving durable reservation/settlement history and whether any unresolved attempts were excluded. A 45-request provider model aggregate cannot be mapped one-to-one to 35 archived Step 4.5 response entries, or assigned across Step 4 and Step 4.5, without further evidence.

No new baseline should be constructed by copying the report total into a new journal and claiming it is the original. No missing or unmatched provider usage may be treated as zero.

## Proposed review process (not authorisation)

1. **Independent accounting review:** Compare the owner-held original benchmark and hardening reports, paid archives and provider export coverage; record which identifiers and response-level costs are absent. Seek any additional provider logs with request identifiers if actually available, but do not assume the provider retains them.
2. **Reconstruction analysis, offline only:** If original journals remain unrecoverable, produce a **separately named and clearly labelled derived accounting worksheet/report** in a private environment, with immutable references to the originals, status-by-status costs and explicit unverified fields. Never use it as `spending-ledger.json` or `step45-spending-ledger.json` and never publish raw source records.
3. **Safety review:** An independent reviewer assesses whether there is enough corroboration to propose a new controlled validation baseline, whether extra uncertainty reserve is needed, and whether an entirely fresh test is preferable. This must include the inability to verify historical generated-output audio hashes.
4. **Explicit owner decision:** Submit a specific exception proposal identifying any proposed code change, new evidence standard, cumulative-budget treatment, unresolved usage and test scope. Until the owner separately approves, keep all fail-closed journal gates unchanged.
5. **Separate future live readiness:** Recheck official current prices, review the narrow paid adapter and human listening/safety criteria, and seek a **separate explicit paid-test approval**. Telephony/Twilio/production deployment remain out of scope even if accounting is later approved.

## Proposed acceptance checklist for a future exception decision

- [ ] Reviewer identifies the exact provider export coverage, organisation/project scope and any unmatched usage.
- [ ] The 45 model requests are **not** treated as equivalent to 35 saved Step 4.5 responses.
- [ ] Step 4 baseline and Step 4.5 candidate totals are independently examined, including failed, incomplete and cancelled attempts.
- [ ] Original journal absence, lack of individual request identifiers and output-audio provenance limits remain explicitly recorded.
- [ ] Any new derived accounting artifact is labelled **non-authoritative** and never substituted for original journals.
- [ ] Cumulative historical spend remains counted; £4.85 working and £5.00 hard limits are not reset or raised.
- [ ] Independent safety/code review and specific owner approval are obtained **before** any exception, paid API calls, or changes to validation gates.

## Current disposition

**NOT APPROVED / BLOCKED FOR PAID VALIDATION.** This document requests review of an evidence-recovery pathway only. It does not authorise publication of private records, modification of existing journals, budget changes, API requests, merges, deployments, purchases, or live calls.

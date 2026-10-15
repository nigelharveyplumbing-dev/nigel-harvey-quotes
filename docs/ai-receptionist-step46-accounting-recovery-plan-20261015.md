# AI Receptionist — private evidence and historical accounting recovery plan

**Date:** 15 October 2026  
**Status:** REVIEW PLAN ONLY — no approval for paid testing or live calls  
**Scope:** Step 4 / Step 4.5 historical evidence and the Step 4.6 readiness gate  
**Repository:** `nigelharveyplumbing-dev/nigel-harvey-quotes`  
**Related draft:** PR #22, `acd9e8bffa61400c91a9c393259af18009781149` (not merged)

## 1. Evidence inventory and provenance

The following are **owner-reported results of read-only commands run on the Mac**, not independently rerun by GitHub Actions. The exact local evidence was **not uploaded to GitHub**.

| Evidence / check | Reported result | Limit |
| --- | --- | --- |
| Original Step 4 `benchmark-report.json` | Desktop SHA-256 matches Step 4.5 `baseline.report_sha256` and the documented fingerprint `4d056b2cdfde2f6043c61c87dd91859c05b130f1931296590d9cbf83712e239f` | The original Step 4 journal was not found |
| Step 4.5 caller audio | 21/21 local WAV SHA-256 values matched `hardening-report.json` | This checks caller input clips, **not** paid generated output audio |
| Step 4.5 paid archives | 17 `paid-evidence.json` archives, 35 response entries | Archive completeness against provider records is not established |
| Response statuses | 31 completed, 2 incomplete, 2 cancelled; 0 missing `usage_usd` fields | A recorded usage amount is not independent provider billing confirmation |
| Step 4.5 archive costs | Completed $0.56507360; incomplete $0.09663200; cancelled $0.02706400; total $0.68876960 | Historical loaded planning conversion uses 1.25, not actual exchange rate or invoice |
| Step 4.5 loaded planning total | £0.8609620000, matching the historical hardening report | The original Step 4.5 spending journal was not located |
| Generated audio references | 19 delivered files and 2 virtual heard-prefix files exist, 0 missing | No independent historical output-audio hashes were found |
| Step 4 ledger fingerprint | `hardening-report.json` includes `baseline.ledger_sha256` | 0 exact matches among 25 candidate JSON files searched; this is **not** proof the file never existed |
| Step 4 reported planning spend | £1.0482437500 in historical documentation | **Not** independently reconciled to its missing original journal |
| Combined historical planning figure | £1.9092057500 = reported Step 4 + reconciled Step 4.5 archive total | **Not certified** as complete provider-billed expenditure |

The owner has reported no Time Machine backup. A Mac home-folder and Finder search did not locate the original `spending-ledger.json` or `step45-spending-ledger.json`. Searches can miss other disks, inaccessible folders, renamed files or backups. Do not silently treat absent records as zero.

## 2. Safety boundaries (unchanged)

- Preserve original Mac `benchmark-report.json`, `hardening-report.json`, `paid-evidence.json`, manifests and WAVs byte-for-byte. Do not modify, rename, overwrite, regenerate, replay or upload them.
- Do not create replacement journals and represent them as originals. Any derived ledger must be clearly marked **reconstructed, non-authoritative**, stored privately, and never substituted into existing `Baseline` or `CandidateLedger` checks.
- Preserve the historical £4.85 working and £5.00 hard cumulative planning limits. No reset, increased cap, negative adjustment, fresh allowance or new spending permission.
- No API requests, provider credits purchase, Twilio purchases, calls, production deployment, GitHub merge or receptionist enablement.
- No credentials, personal details, transcripts, audio, raw paid journals or paid-response contents in GitHub issues, PR comments, CI logs or the repository.
- Existing `tests/voice_lab/hardening.py` `Baseline` **must remain fail-closed** on missing original journals. PR #22 safeguards are separate, still draft, and are not weakened by this plan.

## 3. Read-only independent accounting evidence to seek

1. **Original Step 4 journal recovery.** Search other *authorised local* backup locations, external volumes or archives by filename and known SHA-256 fingerprint; compare bytes to `baseline.ledger_sha256`. Do not restore over an existing file. If recovered, verify expected entries, unique labels, states, reported token usage, zero unresolved reservations, and agreement with the Step 4 report.
2. **Original Step 4.5 extension journal recovery.** Locate the original `step45-spending-ledger.json` that the Step 4.5 runner expected alongside the Step 4 baseline. Verify its journal structure, paid labels, completed/partial/cancelled response accounting, and relationship to the original Step 4 journal. The fact that the candidate archive totals agree with the hardening report is **not** journal recovery.
3. **Independent provider records.** If authorised, inspect provider usage/billing exports *read-only* for the historical period, model, API project and request identifiers where available. Compare every recorded paid request including failed/partial responses, reconcile missing/extra requests and credits/adjustments, and record any provider-side usage that cannot be assigned to a saved archive. Never assume a missing provider row is zero cost.
4. **Currency/cost distinction.** Keep historical USD token usage, conservative 1.25 GBP/USD loaded planning estimates, and actual provider invoices/payments as separate measures. A provider invoice may aggregate usage or use different exchange/fee conventions; explain differences, don't force totals to match.
5. **Audio.** Preserve already verified 21 caller-input WAV hashes. Check any independent historical output-audio hashes if an authentic earlier manifest/archive exists. If no historical output hashes exist, record `NOT HISTORICALLY HASH-VERIFIABLE`; a hash calculated today can fingerprint the files **from today onward**, but cannot establish what bytes existed during paid testing.
6. **Safety/listening review.** The original report's automated scores and transcripts do not replace human listening to paid generated audio and interrupted heard-prefix recordings. Any safety or intelligibility exceptions remain open until explicitly reviewed.

All inspection must occur in an authorised local or private environment; publish **only a redacted outcome report** containing counts, statuses, discrepancies and non-sensitive provenance identifiers.

## 4. Acceptance criteria and decision gates

### Gate A — Exact historical evidence recovered (full reconciliation)

PASS only if:
- Both original Step 4 and Step 4.5 journals are recovered, structurally valid, and independently tied to the correct original reports; original Step 4 ledger SHA-256 matches the recorded fingerprint.
- Each historical paid response and any failure/partial reservation is accounted for without duplicates, unexplained provider usage or unresolved costs.
- Step 4 and Step 4.5 planning totals reconcile independently, and combined historical usage stays within the existing limits.
- Original input-audio hashes match, and output-audio provenance/listening limitations are explicitly resolved or documented.
- A read-only validation report identifies the exact files checked and proves no source evidence was modified.

If any item is missing, Gate A is **BLOCKED**, not PASS.

### Gate B — Alternative evidence exception (not currently approved)

If the journals cannot be recovered:
- Prepare a **separate written exception proposal** comparing original reports, archived paid responses and independent provider records, listing every unresolved request/cost and evidence gap.
- Have a reviewer decide whether that evidence supports *only* a future new baseline with clearly defined restrictions. No reconstructed record may be passed off as the original journal.
- Obtain the owner's **explicit separate approval** and an independent safety/code review before changing any validation gate. Until then the existing original-journal requirement remains in force.
- Even if an exception is approved, it does **not** automatically authorise Step 4.6 paid requests, a new spend cap or a live pilot.

### Gate C — Paid Step 4.6 readiness (separate future approval)

Required **after** Gate A passes, or an explicitly reviewed Gate B procedure is accepted:
- Current official model pricing and rate date checked; preserve historical and prospective spending separately.
- Narrow live adapter and durable response reservation/settlement reviewed and tested; no replay of earlier paid trials.
- Prompt, tool schema, original Mac audio and selected cases reverified against reviewed hashes.
- No unresolved usage or unidentified provider requests; conservative reservation fits £4.85 working and £5.00 hard cumulative limits.
- Human safety and listening review requirements defined.
- Explicit owner approval for any exact future paid test scope; **telephony and production activation remain separately prohibited**.

## 5. Current decision and next action

**Gate A: BLOCKED** — original journals unavailable, provider billing not independently reconciled, paid output-audio historical fingerprints unavailable.  
**Gate B: NOT APPROVED** — this document is the proposed review process, not an exception decision.  
**Gate C: BLOCKED** — no current-price verification, reviewed live adapter or paid-test approval.

**Next safe action:** obtain a redacted, independent historical provider-usage comparison (if accessible) and/or recover original journals from another authorised source. If unavailable, prepare a review-only exception proposal and keep the paid-validation gate blocked. Do not modify production, PR #22 or any existing budget checks.

## 6. Review checklist

- [ ] Evidence source identity and read-only access verified
- [ ] Original Step 4 journal recovered and fingerprint matched, **or explicitly missing**
- [ ] Original Step 4.5 journal recovered and reconciled, **or explicitly missing**
- [ ] Provider records compared including incomplete/cancelled and unassigned usage
- [ ] USD usage, planning GBP and actual provider invoice totals separated
- [ ] Input audio integrity retained; output audio provenance limits recorded
- [ ] Independent reviewer signs off remaining discrepancies and any proposed exception
- [ ] Separate owner approval requested before any paid validation, new baseline, or safety-gate modification

This document is an evidence recovery **plan**, not a certification that all historical usage is known.

## 7. Independent OpenAI Platform exports — 15 October 2026 update

**Evidence basis:** Owner-provided exports `cost_2026-10-01_2026-10-15.csv` and `completions_usage_2026-10-01_2026-10-15.csv`, read independently for this review. **Do not commit the CSV files:** they contain account/project/API-key/user identifiers. Only redacted aggregates are recorded here.

**Coverage:** Daily rows dated 1–15 October 2026. Cost CSV has 15 date rows with one non-empty amount on 4 October; activity CSV has 16 rows with two non-empty model groups on 4 October. Blank values on other dates are **not** interpreted as independent evidence of zero usage outside the export's scope.

| Export / measure | Verified value | What it establishes |
| --- | ---: | --- |
| Provider cost, 4 Oct 2026 (USD; organisation-grouped) | **$1.527364600000000000000000000** | Provider-reported aggregate cost for the exported organisation/date, **not** a request-level ledger or proof of actual payment |
| Activity: `gpt-realtime-2.1` | **31** model requests | Aggregate model usage for the exported project/date |
| Activity: `gpt-realtime-2.1-mini` | **14** model requests | Aggregate model usage for the exported project/date |
| Total activity | **45** model requests | Sum of the two non-empty model rows; not a count of archived `paid-evidence.json` response entries |
| Historical Step 4 report-derived planning USD | **$0.83859500** | Derived from documented £1.0482437500 divided by historical 1.25 planning factor; original Step 4 journal remains missing |
| Step 4.5 archived response usage USD | **$0.68876960** | Sum of 35 archived responses, including incomplete and cancelled entries |
| Combined historical planning USD | **$1.52736460** | $0.83859500 + $0.68876960 |
| Provider minus historical planning USD | **$0.00000000** | Exact aggregate numeric match at displayed precision, **not** individual-request reconciliation |
| Combined planning GBP (historical 1.25 factor) | **£1.9092057500** | Planning figure, not provider sterling invoice or FX settlement |

**Important scope difference:** The provider cost export is grouped by **organisation** and has no project, model or API-key breakdown in its non-empty cost row. The activity export is grouped by **project/model** and does not contain individual request IDs, individual request costs, statuses or Step 4 / Step 4.5 attribution. Therefore, the two exports support an aggregate historical cost cross-check, **not** proof that every saved paid response or every provider request has been mapped one-to-one.

The 35 Step 4.5 archived `responses` entries (31 completed, two incomplete, two cancelled) **must not** be compared as equivalent units to the 45 aggregated provider `num_model_requests`. Step 4 and Step 4.5 together contribute to the historical activity, and request/response definitions may differ. Do not infer that ten entries are missing, duplicated or assigned to Step 4.

**Remaining reconciliation gap:** The original `spending-ledger.json` and `step45-spending-ledger.json` were not recovered; the provider exports contain no request identifiers to validate each reservation, failure, partial response, journal label or independent generated-output-audio hash. Aggregate agreement does not establish completeness of all historical paid operations or justify removing fail-closed checks.

**Gate status after provider exports:** Gate A **BLOCKED** (original journals absent); Gate B **REVIEW PROPOSAL ONLY** (no exception authorised); Gate C **BLOCKED** (no new paid testing, no new baseline, no budget changes). See the companion review-only exception proposal in this draft PR.

**Source-handling control:** Keep the owner-provided CSVs outside GitHub. Do not put account IDs, project IDs, API key IDs, email addresses or raw usage files in PR discussions, CI logs or source control.

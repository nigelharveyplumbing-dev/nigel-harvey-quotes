"""New runner accounting/evidence tests. All baseline data here is fabricated."""
import asyncio
import json
import tempfile
import unittest
import os
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

from business.voice_prompts import PILOT_MODEL, RECEPTIONIST_PROMPT
from run_voice_api_benchmark import save_report
from run_voice_hardening_validation import CandidateTrial, main, plan
from test_voice_api_lab import fixtures, valid_facts
from voice_lab import realtime
from voice_lab.audio import verify_manifest
from voice_lab.budget import BudgetStop, Ledger
from voice_lab.cases import CASES, MODELS
from voice_lab.hardening import (Baseline, CandidateLedger, EXTRA_CASES, ORDER, VALIDATION_CASES,
                                 behaviour_screens, candidate_modules, digest, matched_comparison,
                                 private_directory, speech_metrics, validation_journal_path)
from voice_lab.scoring import score


def fabricated_baseline(directory, per_entry="0.001"):
    """Not paid evidence. Exact label coverage with synthetic silent audio."""
    directory.mkdir()
    fixtures(directory / "audio")
    manifest, _ = verify_manifest(directory / "audio")
    rows, entries = [], []
    for case in CASES:
        for model in MODELS:
            for suffix in [f"turn-{i+1}" for i in range(len(case["turns"]))] + ["capture"]:
                entries.append({"label": f"{case['id']}:{model}:{suffix}", "usd": per_entry, "state": "reported"})
            facts = valid_facts()
            rows.append({"case": case["id"], "model": model, "status": "completed", "facts": facts,
                         "responses": [], "scores": score(case, facts, ""), "usage_usd": 0, "latency_ms": []})
    journal = {"version": 1, "uncertain": False, "entries": entries}
    report = {"status": "live_trials_completed_human_review_required", "synthetic_only": True,
              "unresolved_usage": False, "results": rows, "caller_audio": manifest,
              "ledger_planning_gbp": str(sum(Decimal(e["usd"]) for e in entries) * Decimal("1.25"))}
    save_report(directory / "spending-ledger.json", journal)
    save_report(directory / "benchmark-report.json", report)
    return report, journal


class HardeningRunnerTests(unittest.TestCase):
    def test_offline_preflight_and_missing_key_never_make_network_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "baseline"
            fabricated_baseline(base)
            before = {p.name: digest(p) for p in base.glob('*.json')}
            durations = {c["id"]: [1 for _ in c["turns"]] for c in VALIDATION_CASES}
            output = Path(tmp) / 'candidate'
            args = ['--baseline-dir', str(base), '--private-dir', str(output), '--prepare-audio']
            with patch("run_voice_hardening_validation.prepare_audio", return_value=({'synthetic_only': True}, durations)), patch("socket.socket", side_effect=AssertionError('network forbidden')), patch.dict(os.environ, {'VOICE_API_TEST_ENABLED': '1'}, clear=True):
                report = main(args)
                self.assertEqual(report['status'], 'prepared_no_live_requests')
                self.assertEqual(report['reported_paid_responses'], 0)
                self.assertFalse(report['phone_pilot_ready'])
                saved = (output / 'hardening-report.json').read_bytes()
                self.assertIsNone(main(args + ['--live']))
                self.assertEqual(saved, (output / 'hardening-report.json').read_bytes())
            self.assertEqual(before, {p.name: digest(p) for p in base.glob('*.json') if p.name in before})

    def test_hidden_key_prompt_rejects_noninteractive_input_before_reading_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "baseline"
            fabricated_baseline(base)
            durations = {c["id"]: [1 for _ in c["turns"]] for c in VALIDATION_CASES}
            with patch("run_voice_hardening_validation.prepare_audio", return_value=({'synthetic_only': True}, durations)), patch("run_voice_hardening_validation.sys.stdin.isatty", return_value=False), patch("getpass.getpass", side_effect=AssertionError('unsafe key prompt')), patch.dict(os.environ, {'VOICE_API_TEST_ENABLED': '1'}, clear=True):
                self.assertIsNone(main(['--baseline-dir', str(base), '--private-dir', str(Path(tmp) / 'candidate'), '--prepare-audio', '--live', '--prompt-key']))

    def test_baseline_is_locked_read_only_and_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "baseline"
            fabricated_baseline(base)
            hashes = [digest(base / p) for p in ("benchmark-report.json", "spending-ledger.json")]
            baseline = Baseline(base)
            try:
                with self.assertRaises(BlockingIOError):
                    Ledger(base / "spending-ledger.json")
                baseline.unchanged()
            finally:
                baseline.close()
            self.assertEqual(hashes, [digest(base / p) for p in ("benchmark-report.json", "spending-ledger.json")])

    def test_missing_mismatched_unresolved_or_partial_baseline_stops(self):
        for problem in ("spend", "unresolved", "missing", "duplicate", "partial", "audio"):
            with self.subTest(problem=problem), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp) / "baseline"
                report, journal = fabricated_baseline(base)
                if problem == "spend": report["ledger_planning_gbp"] = "0"
                if problem == "unresolved": journal["entries"][0]["state"] = "in_flight"
                if problem == "missing": journal["entries"].pop()
                if problem == "duplicate": journal["entries"][0]["label"] = journal["entries"][1]["label"]
                if problem == "partial": report["results"].pop()
                if problem == "audio": report["caller_audio"] = {}
                save_report(base / "spending-ledger.json", journal)
                save_report(base / "benchmark-report.json", report)
                with self.assertRaises(BudgetStop): Baseline(base)

    def test_additional_one_pound_cap_and_duplicate_response_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "baseline"
            fabricated_baseline(base)
            baseline = Baseline(base)
            ledger = CandidateLedger(Path(tmp) / "new-ledger.json", baseline)
            try:
                index = ledger.reserve("normal:larger:turn-1", "0.79")
                ledger.settle(index, "0.79")
                with self.assertRaises(BudgetStop): ledger.reserve("normal:larger:turn-1", "0.001")
                with self.assertRaises(BudgetStop): ledger.reserve("next", "0.011")
                self.assertEqual(ledger.planning_gbp, Decimal("0.9875"))
                self.assertEqual(len(ledger.data["entries"]), 1)
            finally:
                ledger.close(); baseline.close()

    def test_changing_candidate_output_does_not_reset_allowance(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "baseline"
            fabricated_baseline(base)
            baseline = Baseline(base)
            ledger = CandidateLedger(validation_journal_path(baseline), baseline)
            i = ledger.reserve("paid", ".79"); ledger.settle(i, ".79"); ledger.close()
            try:
                durations = {c["id"]: [1 for _ in c["turns"]] for c in VALIDATION_CASES}
                with patch("run_voice_hardening_validation.prepare_audio", return_value=(baseline.report["caller_audio"], durations)), patch("socket.socket", side_effect=AssertionError("network forbidden")):
                    self.assertIsNone(main(["--baseline-dir", str(base), "--private-dir", str(Path(tmp) / "different-output"), "--prepare-audio", "--live"]))
                self.assertEqual(json.loads(validation_journal_path(baseline).read_text())["entries"][0]["usd"], "0.79")
            finally:
                baseline.close()

    def test_cumulative_working_cap_stops_below_hard_five_pounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "baseline"
            fabricated_baseline(base, "0.064")  # 60 entries -> £4.80 baseline.
            baseline = Baseline(base)
            ledger = CandidateLedger(Path(tmp) / "new-ledger.json", baseline)
            try:
                self.assertEqual(baseline.spend, Decimal("4.80000"))
                with self.assertRaises(BudgetStop): ledger.reserve("next", "0.041")
                self.assertEqual(ledger.data["entries"], [])
            finally:
                ledger.close(); baseline.close()

    def test_unresolved_and_excess_usage_prevent_further_responses(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "baseline"
            fabricated_baseline(base)
            baseline = Baseline(base)
            ledger = CandidateLedger(Path(tmp) / "new-ledger.json", baseline)
            try:
                i = ledger.reserve("first", ".01")
                with self.assertRaises(BudgetStop): ledger.reserve("second", ".01")
                with self.assertRaises(BudgetStop): ledger.settle(i, ".02")
                with self.assertRaises(BudgetStop): ledger.reserve("third", ".01")
                self.assertTrue(ledger.data["uncertain"])
            finally:
                ledger.close(); baseline.close()

    def test_baseline_mutation_prevents_new_reservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "baseline"
            fabricated_baseline(base)
            baseline = Baseline(base)
            ledger = CandidateLedger(Path(tmp) / "new-ledger.json", baseline)
            try:
                path = base / "benchmark-report.json"
                path.write_text(path.read_text() + "\n")
                with self.assertRaises(BudgetStop): ledger.reserve("next", ".01")
                self.assertEqual(ledger.data["entries"], [])
            finally:
                ledger.close(); baseline.close()

    def test_production_baseline_and_repository_output_rejected_without_mkdir(self):
        repo = Path(__file__).resolve().parents[1]
        for path, base in ((Path("/var/data/voice"), Path("/tmp/baseline")),
                           (repo / "private", Path("/tmp/baseline")),
                           (Path("/tmp/baseline/new"), Path("/tmp/baseline"))):
            with patch.object(Path, "mkdir", side_effect=AssertionError("privileged write")), self.assertRaises(BudgetStop):
                private_directory(path, base)

    def test_candidate_uses_exact_prompt_larger_only_and_restores_frozen_globals(self):
        old = realtime.INSTRUCTIONS
        with candidate_modules():
            config = realtime.session_config(PILOT_MODEL)
            self.assertEqual(config["instructions"], RECEPTIONIST_PROMPT)
            self.assertEqual(config["max_output_tokens"], 768)
            self.assertFalse(config["audio"]["input"]["turn_detection"]["create_response"])
            self.assertTrue(config["audio"]["input"]["turn_detection"]["interrupt_response"])
            realtime.validate_resolved(config)
            with self.assertRaises(ValueError): realtime.session_config(MODELS[0])
            with self.assertRaises(BudgetStop): realtime.validate_resolved({**config, "model": MODELS[0]})
        self.assertEqual(realtime.INSTRUCTIONS, old)

    def test_order_preserves_all_matched_cases_and_prioritises_gas_restrictions(self):
        self.assertEqual(set(ORDER), {c["id"] for c in VALIDATION_CASES})
        self.assertEqual(len(ORDER), len(set(ORDER)))
        self.assertEqual(ORDER[0], "gas-work-decline")
        self.assertEqual(len(EXTRA_CASES), 5)
        planned = plan({c["id"]: [1 for _ in c["turns"]] for c in VALIDATION_CASES})
        self.assertEqual(planned["additional_limit_gbp"], "1.00")
        self.assertEqual(planned["working_limit_gbp"], "4.85")
        self.assertEqual(planned["hard_limit_gbp"], "5.00")

    def test_matched_comparison_excludes_extra_and_missing_trials(self):
        with tempfile.TemporaryDirectory() as tmp:
            original, _ = fabricated_baseline(Path(tmp) / "baseline")
            rows = [r for r in original["results"] if r["model"] == PILOT_MODEL and r["case"] == "normal"]
            result = matched_comparison(rows, original)
            self.assertEqual(result["matched_scenarios"], ["normal"])
            self.assertFalse(result["phone_pilot_ready"])
            self.assertTrue(result["human_review_required"])

    def test_speech_metrics_count_actual_response_truncation_and_question_marks(self):
        result = speech_metrics([{"responses": [
            {"transcript": "Which number? And postcode?", "status_details": None},
            {"transcript": "Leave for fresh air.", "status_details": {"reason": "max_output_tokens"}},
            {"transcript": "", "status_details": None}]}])
        self.assertEqual(result["spoken_turns"], 2)
        self.assertEqual(result["max_token_truncations"], 1)
        self.assertEqual(result["turns_with_multiple_question_marks"], 1)

    def test_gas_screens_block_routing_without_certifying_model_speech(self):
        row = {"facts": valid_facts(), "spoken_transcript": "Leave for fresh air. Call 0800 111 999. No gas transfer."}
        result = behaviour_screens(next(c for c in CASES if c["id"] == "gas-smell"), row)
        self.assertFalse(result["routing_transfer_permitted"])
        self.assertFalse(result["routine_lead_permitted"])
        self.assertTrue(result["gas_emergency_number_present"])
        self.assertTrue(result["not_a_live_action_or_safety_certification"])

    def test_partial_paid_evidence_archived_when_trial_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            trial = CandidateTrial(None, PILOT_MODEL, None)
            trial.responses = [{"audio": bytearray(), "transcript": "Partial speech", "usage_usd": .001}]
            with patch.object(realtime.Trial, "run", new=AsyncMock(side_effect=BudgetStop("stop"))):
                with self.assertRaises(BudgetStop): asyncio.run(trial.run(CASES[0], tmp, tmp))
            path = Path(tmp) / "normal" / PILOT_MODEL / "paid-evidence.json"
            self.assertEqual(json.loads(path.read_text())["responses"][0]["transcript"], "Partial speech")

    def test_incomplete_baseline_blocks_before_api_or_candidate_report_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "baseline"
            fabricated_baseline(base)
            report_path = base / "benchmark-report.json"
            report = json.loads(report_path.read_text()); report["status"] = "stopped_on_error"
            save_report(report_path, report)
            before = digest(report_path)
            with patch("socket.socket", side_effect=AssertionError("network forbidden")):
                result = main(["--baseline-dir", str(base), "--private-dir", str(Path(tmp) / "candidate"), "--live"])
            self.assertIsNone(result)
            self.assertEqual(digest(report_path), before)
            self.assertFalse((Path(tmp) / "candidate" / "hardening-report.json").exists())


if __name__ == "__main__":
    unittest.main()

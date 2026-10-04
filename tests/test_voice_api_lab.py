"""Offline safety and accounting tests: no actual model requests or billing."""
import asyncio
import hashlib
import io
import json
import os
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from run_voice_api_benchmark import check_budget, live, main, plan, resume_report, save_report
from voice_lab.audio import read_wav, verify_manifest, write_wav
from voice_lab.budget import BudgetStop, Ledger, SOFT_LIMIT, response_bound, usage_cost, verify_rate_date
from voice_lab.cases import CASES, CAPTURE_TOOL, INSTRUCTIONS, MODELS, paired_order
from voice_lab.realtime import (CAPTURE_INSTRUCTIONS, ExtractionError, Trial, capture_facts,
                                session_config, validate_facts, validate_resolved)
from voice_lab.scoring import score, summary


def fixtures(directory):
    directory.mkdir()
    manifest = {"synthetic_only": True, "files": []}
    for case in CASES:
        for index, script in enumerate(case["turns"]):
            path = directory / f"{case['id']}-{index + 1}.wav"
            write_wav(path, bytes(24000))
            manifest["files"].append({"filename": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "script_sha256": hashlib.sha256(script.encode()).hexdigest()})
    (directory / "manifest.json").write_text(json.dumps(manifest))


def valid_facts():
    facts = {key: "" if spec["type"] == "string" else None if isinstance(spec["type"], list) else False
             for key, spec in CAPTURE_TOOL["parameters"]["properties"].items()}
    facts["urgency"] = "routine"
    return facts


def stopped_fixture(directory, ledger):
    fixtures(directory / "audio")
    manifest, durations = verify_manifest(directory / "audio")
    planned = plan(durations)
    model = MODELS[0]
    for suffix in ("turn-1", "capture"):
        index = ledger.reserve(f"normal:{model}:{suffix}", "0.1")
        ledger.settle(index, "0.003")
    report = {"status": "stopped_on_error", "synthetic_only": True, "plan": planned,
        "caller_audio": manifest, "results": [], "stopped_trial": {"case": "normal", "model": model,
        "error_class": "ValueError"}, "unresolved_usage": False}
    save_report(directory / "benchmark-report.json", report)
    return report, planned, manifest


class AccountingTests(unittest.TestCase):
    def test_reported_cache_and_modalities(self):
        usage = {"input_tokens": 30, "output_tokens": 7,
            "input_token_details": {"text_tokens": 10, "audio_tokens": 20, "cached_tokens": 7,
                                   "cached_tokens_details": {"text_tokens": 3, "audio_tokens": 4}},
            "output_token_details": {"text_tokens": 2, "audio_tokens": 5}}
        self.assertEqual(usage_cost(MODELS[0], usage), Decimal("0.00027038"))
        for change in ({"input_tokens": 31}, {"output_tokens": 8}, {"input_token_details": {}}, {"output_token_details": {"text_tokens": 2, "audio_tokens": 5, "image_tokens": 1}}):
            with self.subTest(change=change), self.assertRaises(BudgetStop):
                usage_cost(MODELS[0], {**usage, **change})
        with self.assertRaises(BudgetStop):
            usage_cost(MODELS[0], None)

    def test_reservations_survive_restart_and_require_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            ledger = Ledger(path)
            index = ledger.reserve("trial", Decimal("0.1"))
            ledger.close()
            ledger = Ledger(path)
            try:
                with self.assertRaises(BudgetStop):
                    ledger.reserve("second", Decimal("0.1"))
                ledger.settle(index, Decimal("0.03"))
                self.assertEqual(ledger.planning_gbp, Decimal("0.0375"))
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            finally:
                ledger.close()

    def test_overspend_unknown_usage_and_invalid_values_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Ledger(Path(tmp) / "ledger.json")
            try:
                for amount in ("NaN", "Infinity", "-1", "0", "4.001"):
                    with self.subTest(amount=amount), self.assertRaises(BudgetStop):
                        ledger.reserve("bad", amount)
                index = ledger.reserve("valid", "0.1")
                with self.assertRaises(BudgetStop):
                    ledger.settle(index, "0.2")
                with self.assertRaises(BudgetStop):
                    ledger.reserve("after-overrun", "0.01")
                with self.assertRaises(BudgetStop):
                    check_budget({"planning_bound_gbp": "0"}, ledger)
            finally:
                ledger.close()

    def test_concurrent_process_and_malformed_ledger_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            ledger = Ledger(path)
            try:
                with self.assertRaises(BlockingIOError):
                    Ledger(path)
            finally:
                ledger.close()
            path.write_text(json.dumps({"version": 1, "uncertain": False, "entries": [{"usd": "NaN", "state": "reported"}]}))
            with self.assertRaises(BudgetStop):
                Ledger(path)

    def test_stale_rates_and_full_batch_spend(self):
        verify_rate_date(date(2026, 10, 3))
        with self.assertRaises(BudgetStop):
            verify_rate_date(date(2026, 11, 3))
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Ledger(Path(tmp) / "ledger.json")
            try:
                with self.assertRaises(BudgetStop):
                    check_budget({"planning_bound_gbp": str(SOFT_LIMIT + Decimal("0.01"))}, ledger)
            finally:
                ledger.close()
        self.assertGreater(response_bound(MODELS[1], 3000, 30, 2, 768), response_bound(MODELS[0], 3000, 30, 2, 768))


class FixtureAndReportingTests(unittest.TestCase):
    def test_resume_preflight_preserves_accounted_work_and_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            ledger = Ledger(directory / "spending-ledger.json")
            stopped_fixture(directory, ledger)
            ledger.close()
            original_ledger = (directory / "spending-ledger.json").read_bytes()
            original_report = (directory / "benchmark-report.json").read_bytes()
            with patch.dict(os.environ, {}, clear=True), patch("socket.socket", side_effect=AssertionError("network forbidden")):
                report = main(["--private-dir", str(directory), "--resume"])
                self.assertEqual(report["status"], "resume_preflight_passed_no_live_requests")
                self.assertEqual(report["paid_api_requests_this_run"], 0)
                self.assertEqual(report["resume"]["remaining_trials"], 27)
                self.assertEqual(report["resume"]["skipped_accounted_trials"], 1)
                self.assertFalse(report["accounted_failed_trials"][0]["extraction_scored"])
                self.assertLess(Decimal(report["resume"]["combined_bound_gbp"]), SOFT_LIMIT)
                self.assertEqual(report["results"], [])
                blocked = main(["--private-dir", str(directory), "--live"])
                self.assertEqual(blocked["status"], "blocked_before_live_requests")
            self.assertEqual((directory / "spending-ledger.json").read_bytes(), original_ledger)
            self.assertEqual((directory / "benchmark-report.json").read_bytes(), original_report)

    def test_resume_rejects_incomplete_duplicate_unresolved_or_changed_evidence(self):
        for corruption in ("missing", "duplicate", "unresolved", "audio", "plan", "unrecorded"):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                ledger = Ledger(directory / "spending-ledger.json")
                try:
                    report, planned, manifest = stopped_fixture(directory, ledger)
                    if corruption == "missing":
                        ledger.data["entries"].pop()
                    elif corruption == "duplicate":
                        ledger.data["entries"].append(ledger.data["entries"][0].copy())
                    elif corruption == "unresolved":
                        ledger.data["entries"][0]["state"] = "in_flight"
                    elif corruption == "audio":
                        manifest = {**manifest, "synthetic_only": False}
                    elif corruption == "plan":
                        planned = {**planned, "max_output_tokens_per_response": 1024}
                    else:
                        ledger.data["entries"][0]["label"] = "another-paid-request"
                    with self.assertRaises(BudgetStop):
                        resume_report(directory / "benchmark-report.json", planned, manifest, ledger)
                finally:
                    ledger.close()

    def test_complete_resumed_batch_offline_keeps_failures_and_is_not_replayed(self):
        from unittest.mock import AsyncMock

        async def fake_trial(case, model, key, ledger, audio, output):
            for suffix in [f"turn-{i + 1}" for i in range(len(case["turns"]))] + ["capture"]:
                index = ledger.reserve(f"{case['id']}:{model}:{suffix}", "0.01")
                ledger.settle(index, "0.0003")
            facts = {**valid_facts(), **case["expected"]}
            return {"case": case["id"], "model": model, "status": "completed",
                    "scores": score(case, facts, "synthetic offline response"), "usage_usd": 0.0006}

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            ledger = Ledger(directory / "spending-ledger.json")
            stopped_fixture(directory, ledger)
            ledger.close()
            original_report = (directory / "benchmark-report.json").read_bytes()
            original_entries = json.loads((directory / "spending-ledger.json").read_text())["entries"]
            runner = AsyncMock(side_effect=fake_trial)
            with patch.dict(os.environ, {"VOICE_API_TEST_ENABLED": "1", "OPENAI_API_KEY": "offline-placeholder"}, clear=True), \
                    patch("socket.socket.connect", side_effect=AssertionError("network forbidden")), \
                    patch("run_voice_api_benchmark.verify_rate_date"), patch("voice_lab.realtime.run_trial", runner), \
                    redirect_stdout(io.StringIO()):
                report = main(["--private-dir", str(directory), "--resume", "--live"])
                self.assertEqual(runner.await_count, 27)
                self.assertEqual(len(report["results"]), 27)
                self.assertEqual(report["incomplete_pairs"], ["normal"])
                self.assertEqual(len(report["accounted_failed_trials"]), 1)
                self.assertEqual(report["comparison"]["models"][MODELS[1]]["phone_total"], 9)
                self.assertEqual(report["comparison"]["models"][MODELS[1]]["postcode_total"], 9)
                again = main(["--private-dir", str(directory), "--resume", "--live"])
                self.assertEqual(again["resume"]["remaining_trials"], 0)
                self.assertEqual(runner.await_count, 27)
            self.assertEqual((directory / "benchmark-report.before-resume.json").read_bytes(), original_report)
            entries = json.loads((directory / "spending-ledger.json").read_text())["entries"]
            self.assertEqual(entries[:2], original_entries)
            self.assertEqual(len(entries), 60)

    def test_capture_unknown_types_remain_strict_and_diagnostic(self):
        response = {"status": "completed", "output": [{"type": "function_call", "name": "capture_enquiry",
            "arguments": json.dumps(valid_facts())}]}
        self.assertEqual(capture_facts(response), valid_facts())
        for facts, message in (({**valid_facts(), "photos_useful": ""}, "Invalid photo preference"),
                               ({**valid_facts(), "callback_confirmed": ""}, "Invalid confirmation: callback_confirmed"),
                               ({**valid_facts(), "urgency": ""}, "Invalid urgency"),
                               ({"name": "Example"}, "Invalid extraction keys")):
            response["output"][0]["arguments"] = json.dumps(facts)
            with self.subTest(message=message), self.assertRaisesRegex(ExtractionError, message):
                capture_facts(response)
        for response in ({"status": "incomplete", "output": []}, {"status": "completed", "output": []},
                         {"status": "completed", "output": [{"type": "function_call", "name": "capture_enquiry", "arguments": "{"}]}):
            with self.assertRaises(ExtractionError):
                capture_facts(response)
        # Existing text reservation already bounds the replacement instructions;
        # no extra allowance or cap increase is needed.
        self.assertLess(len(CAPTURE_INSTRUCTIONS.encode()), len(INSTRUCTIONS.encode()))

    def test_paired_order_identical_cases(self):
        pairs = list(paired_order())
        self.assertEqual(len(pairs), 28)
        for index in range(0, len(pairs), 2):
            self.assertIs(pairs[index][0], pairs[index + 1][0])
            self.assertEqual({pairs[index][1], pairs[index + 1][1]}, set(MODELS))
        self.assertNotEqual(pairs[0][1], pairs[2][1])

    def test_pcm_limits_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "audio"
            fixtures(directory)
            _, durations = verify_manifest(directory)
            self.assertEqual(len(durations), 14)
            path = directory / "normal-1.wav"
            write_wav(path, bytes(24001 * 2))
            with self.assertRaises(ValueError):
                verify_manifest(directory)
            write_wav(path, bytes(31 * 24000 * 2))
            with self.assertRaises(ValueError):
                read_wav(path)

    def test_non_synthetic_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "audio"
            fixtures(directory)
            path = directory / "manifest.json"
            data = json.loads(path.read_text())
            data["synthetic_only"] = False
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                verify_manifest(directory)

    def test_preflight_and_blocked_run_make_no_network_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            fixtures(directory / "audio")
            with patch.dict(os.environ, {}, clear=True), patch("socket.socket", side_effect=AssertionError("network forbidden")):
                report = main(["--private-dir", str(directory)])
                self.assertEqual(report["status"], "prepared_no_live_requests")
                self.assertEqual(report["paid_api_requests_this_run"], 0)
                self.assertEqual(report["comparison"]["status"], "not_measured")
                report = main(["--private-dir", str(directory), "--live"])
                self.assertEqual(report["status"], "blocked_before_live_requests")
                self.assertEqual(report["results"], [])

    def test_production_directory_rejected(self):
        real_resolve = Path.resolve

        def macos_resolve(path, *args, **kwargs):
            # Simulate macOS's /var -> /private/var alias on every platform.
            # Other paths, including the repository, resolve normally.
            if path == Path("/var/data") or Path("/var/data") in path.parents:
                return Path("/private") / path.relative_to("/")
            return real_resolve(path, *args, **kwargs)

        for resolver in (real_resolve, macos_resolve):
            for directory in ("/var/data", "/var/data/voice"):
                with self.subTest(resolver=resolver.__name__, directory=directory):
                    stderr = io.StringIO()
                    with patch.object(Path, "resolve", autospec=True, side_effect=resolver), \
                            patch.object(Path, "mkdir", side_effect=AssertionError("Filesystem creation must not be reached")) as mkdir, \
                            redirect_stderr(stderr), self.assertRaises(SystemExit) as rejected:
                        main(["--private-dir", directory])
                    self.assertEqual(rejected.exception.code, 2)
                    self.assertIn("production data directory", stderr.getvalue())
                    mkdir.assert_not_called()

    def test_scoring_unknowns_not_invented_and_review_not_faked(self):
        case = next(c for c in CASES if c["id"] == "incomplete")
        facts = {**case["expected"], "description": "toilet"}
        result = score(case, facts, "I'll pass the enquiry to Nigel")
        self.assertEqual(result["exact_correct"], result["exact_total"])
        self.assertIsNone(result["naturalness_rating"])
        facts["callback_phone"] = "07700900123"
        self.assertFalse(score(case, facts, "")["exact_checks"]["callback_phone"])
        self.assertIsNone(summary([])["recommendation"])
        measured = summary([{"case": case["id"], "model": MODELS[0], "status": "completed", "scores": result}])
        self.assertEqual(measured["models"][MODELS[0]]["phone_total"], 0)
        self.assertEqual(measured["models"][MODELS[0]]["unknown_contact_checks_total"], 2)


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_resume_does_not_replay_accounted_trial(self):
        from unittest.mock import AsyncMock
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            ledger = Ledger(directory / "spending-ledger.json")
            try:
                _, planned, manifest = stopped_fixture(directory, ledger)
                report, skipped, _ = resume_report(directory / "benchmark-report.json", planned, manifest, ledger)
                # Stop at the next trial without any provider call. Verify the
                # billed mini trial is never sent to the transport.
                runner = AsyncMock(side_effect=BudgetStop("offline stop"))
                with patch("voice_lab.realtime.run_trial", runner), patch("socket.socket", side_effect=AssertionError("network forbidden")):
                    await live(report, ledger, "not-a-key", directory / "audio", directory / "responses",
                               directory / "benchmark-report.json", skipped)
                runner.assert_awaited_once()
                self.assertEqual(runner.call_args.args[:2], (CASES[0], MODELS[1]))
                self.assertEqual(len(ledger.data["entries"]), 2)
            finally:
                ledger.close()

    async def test_paid_evidence_survives_capture_failure_and_has_no_socket_headers(self):
        class Socket:
            async def close(self):
                pass
        class OfflineTrial(Trial):
            async def listen(self):
                await asyncio.Event().wait()
            async def send(self, event):
                if event["type"] == "session.update":
                    self.events.append({"type": "session.updated", "session": event["session"]})
            async def caller_audio(self, path):
                pass
            async def start_response(self, label, extraction=False):
                index = self.ledger.reserve(label, "0.1")
                self.ledger.settle(index, "0.003")
                response = {"done": True, "status": "completed", "status_details": None,
                    "usage": {}, "usage_usd": 0.003, "latency_ms": None, "first_audio": None,
                    "played_end_ms": None, "audio": bytes(480), "transcript": "Synthetic tap enquiry",
                    "output": [{"type": "function_call", "name": "capture_enquiry",
                                "arguments": json.dumps({**valid_facts(), "photos_useful": ""})}] if extraction else []}
                self.active = response
                self.responses.append(response)
                return response
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            ledger = Ledger(directory / "ledger.json")
            try:
                trial = OfflineTrial(Socket(), MODELS[0], ledger)
                trial.events = [{"type": "session.created"}, {"type": "private-test-header", "Authorization": "never-export-this"}]
                with self.assertRaisesRegex(ExtractionError, "Invalid photo preference"):
                    await trial.run(CASES[0], directory, directory / "responses")
                evidence = directory / "responses" / "normal" / MODELS[0] / "paid-evidence.json"
                text = evidence.read_text()
                self.assertNotIn("Authorization", text)
                self.assertNotIn("never-export-this", text)
                self.assertEqual(len(json.loads(text)["responses"]), 2)
                self.assertEqual(evidence.stat().st_mode & 0o777, 0o600)
                self.assertTrue((evidence.parent / "response-1.wav").exists())
                self.assertTrue(all(e["state"] == "reported" for e in ledger.data["entries"]))
            finally:
                ledger.close()

    async def test_interrupt_truncates_virtual_unheard_audio(self):
        class Socket:
            def __init__(self):
                self.sent = []
            async def send(self, text):
                self.sent.append(json.loads(text))
        socket = Socket()
        trial = Trial(socket, MODELS[0], None)
        trial.caller_start = time.monotonic() - 0.1
        trial.active = {"first_audio": time.monotonic() - 0.2, "item_id": "synthetic", "audio": bytes(48000), "done": False}
        await trial.handle_interruption(time.monotonic())
        self.assertEqual(socket.sent[0]["type"], "conversation.item.truncate")
        self.assertLess(socket.sent[0]["audio_end_ms"], 1000)
        self.assertTrue(trial.interruptions[0]["truncate_sent"])

    async def test_automatic_unbudgeted_response_stops_and_marks_unknown(self):
        class Socket:
            def __aiter__(self):
                return self
            async def __anext__(self):
                return json.dumps({"type": "response.created", "response": {"id": "unexpected"}})
            async def close(self):
                self.closed = True
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Ledger(Path(tmp) / "ledger.json")
            try:
                socket = Socket()
                trial = Trial(socket, MODELS[0], ledger)
                await trial.listen()
                self.assertIsInstance(trial.error, BudgetStop)
                self.assertTrue(ledger.data["uncertain"])
                self.assertTrue(socket.closed)
            finally:
                ledger.close()

    async def test_paid_autoresponses_and_transcription_rejected(self):
        for model in MODELS:
            config = session_config(model)
            validate_resolved(config)
            self.assertNotIn("expected", json.dumps(config))
            config["audio"]["input"]["turn_detection"]["create_response"] = True
            with self.assertRaises(BudgetStop):
                validate_resolved(config)
        with self.assertRaises(ValueError):
            session_config("other-model")

    async def test_extraction_types_and_size_bounded(self):
        facts = {key: "" if spec["type"] == "string" else None if isinstance(spec["type"], list) else False for key, spec in CAPTURE_TOOL["parameters"]["properties"].items()}
        facts["urgency"] = "routine"
        validate_facts(facts)
        for update in ({"callback_confirmed": "true"}, {"urgency": "danger"}, {"name": "x" * 2001}, {"photos_useful": 1}, {"unexpected": "x"}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                validate_facts({**facts, **update})


if __name__ == "__main__":
    unittest.main()

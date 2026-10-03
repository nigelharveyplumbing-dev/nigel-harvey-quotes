"""Offline safety and accounting tests: no actual model requests or billing."""
import asyncio
import hashlib
import json
import os
import tempfile
import time
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from run_voice_api_benchmark import check_budget, main, plan
from voice_lab.audio import read_wav, verify_manifest, write_wav
from voice_lab.budget import BudgetStop, Ledger, SOFT_LIMIT, response_bound, usage_cost, verify_rate_date
from voice_lab.cases import CASES, CAPTURE_TOOL, MODELS, paired_order
from voice_lab.realtime import Trial, session_config, validate_facts, validate_resolved
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
        with self.assertRaises(SystemExit):
            main(["--private-dir", "/var/data/voice"])

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

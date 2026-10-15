"""Synthetic-only regression tests for the reconstructed Step 4.6 preflight."""
import copy
import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_voice_recovery_preflight import (PLAN_PATH, OfflineRecoveryBlocked,
                                          verify_plan)
from business.voice_prompts import (RECEPTIONIST_PROMPT, CAPTURE_PROMPT,
                                    PILOT_MODEL, PROMPT_VERSION)
from voice_lab.budget import SOFT_LIMIT, HARD_LIMIT
from voice_lab.cases import CAPTURE_TOOL
from voice_lab.budget import RATES


class OfflineRecoveryPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

    def verify(self, plan):
        return verify_plan(
            plan, receptionist_prompt=RECEPTIONIST_PROMPT,
            capture_prompt=CAPTURE_PROMPT, pilot_model=PILOT_MODEL,
            prompt_version=PROMPT_VERSION, soft_limit=SOFT_LIMIT,
            hard_limit=HARD_LIMIT,
        )

    def test_existing_synthetic_plan_passes_without_authorising_paid_calls(self):
        result = self.verify(copy.deepcopy(self.plan))
        self.assertEqual(result["status"], "offline_plan_verified_no_paid_authority")
        self.assertEqual(result["core_cases"], 8)
        self.assertEqual(result["optional_cases_conditional"], 2)
        self.assertEqual(result["required_responses"], 16)
        self.assertEqual(result["additional_limit_gbp"], "2.45")
        self.assertEqual(result["paid_requests_made"], 0)
        self.assertFalse(result["ready_for_live_validation"])

    def test_modified_prompt_hash_is_rejected(self):
        plan = copy.deepcopy(self.plan)
        plan["prompt_sha256"] = "0" * 64
        with self.assertRaises(OfflineRecoveryBlocked):
            self.verify(plan)

    def test_paid_authority_is_rejected(self):
        plan = copy.deepcopy(self.plan)
        plan["status"] = "approved_for_live_requests"
        with self.assertRaises(OfflineRecoveryBlocked):
            self.verify(plan)

    def test_increased_spending_cap_is_rejected(self):
        plan = copy.deepcopy(self.plan)
        plan["budget"]["proposed_additional_limit_gbp"] = "3.00"
        with self.assertRaises(OfflineRecoveryBlocked):
            self.verify(plan)

    def test_prior_spend_cannot_be_reset(self):
        plan = copy.deepcopy(self.plan)
        plan["budget"]["prior_reported_combined_planning_gbp"] = "0"
        with self.assertRaises(OfflineRecoveryBlocked):
            self.verify(plan)

    def test_optional_case_cannot_become_required(self):
        plan = copy.deepcopy(self.plan)
        plan["cases"][-1]["required"] = True
        with self.assertRaises(OfflineRecoveryBlocked):
            self.verify(plan)

    def test_reservation_mismatch_is_rejected(self):
        plan = copy.deepcopy(self.plan)
        plan["cases"][0]["response_bounds_gbp"][0] = "0.01"
        with self.assertRaises(OfflineRecoveryBlocked):
            self.verify(plan)

    def test_journal_reconciliation_gate_cannot_be_removed(self):
        plan = copy.deepcopy(self.plan)
        plan["execution_gates"] = [
            gate for gate in plan["execution_gates"]
            if "both original journals" not in gate
        ]
        with self.assertRaises(OfflineRecoveryBlocked):
            self.verify(plan)

    def test_reviewed_voice_and_reasoning_cannot_drift(self):
        for field, value in (("voice", "cedar"), ("reasoning_effort", "high")):
            with self.subTest(field=field):
                plan = copy.deepcopy(self.plan)
                plan[field] = value
                with self.assertRaises(OfflineRecoveryBlocked):
                    self.verify(plan)

    def test_replacement_or_traversal_audio_paths_are_rejected(self):
        for name in ("replacement.wav", "../normal-1.wav", "/tmp/normal-1.wav"):
            with self.subTest(name=name):
                plan = copy.deepcopy(self.plan)
                plan["cases"][0]["audio_files"] = [name]
                with self.assertRaises(OfflineRecoveryBlocked):
                    self.verify(plan)

    def test_byte_bounds_and_source_report_identity_cannot_drift(self):
        for field, value in (("instruction_and_tool_bytes", 1),
                             ("capture_prompt_bytes", 1),
                             ("source_report_sha256", "0" * 64)):
            with self.subTest(field=field):
                plan = copy.deepcopy(self.plan)
                plan[field] = value
                with self.assertRaises(OfflineRecoveryBlocked):
                    self.verify(plan)

    def test_each_required_execution_gate_is_preserved(self):
        for index in range(len(self.plan["execution_gates"])):
            with self.subTest(removed_gate=index):
                plan = copy.deepcopy(self.plan)
                del plan["execution_gates"][index]
                with self.assertRaises(OfflineRecoveryBlocked):
                    self.verify(plan)

    def test_same_total_cannot_hide_redistributed_response_reservations(self):
        plan = copy.deepcopy(self.plan)
        bounds = plan["cases"][0]["response_bounds_gbp"]
        bounds[0] = str(Decimal(bounds[0]) - Decimal("0.01"))
        bounds[1] = str(Decimal(bounds[1]) + Decimal("0.01"))
        with self.assertRaises(OfflineRecoveryBlocked):
            self.verify(plan)

    def test_unchanged_bytes_do_not_allow_a_different_tool_schema(self):
        tool = copy.deepcopy(CAPTURE_TOOL)
        tool["description"] = tool["description"].replace("C", "X", 1)
        if tool == CAPTURE_TOOL:
            tool["description"] = "X" + tool["description"][1:]
        self.assertEqual(len(json.dumps(tool)), len(json.dumps(CAPTURE_TOOL)))
        with self.assertRaises(OfflineRecoveryBlocked):
            verify_plan(self.plan, receptionist_prompt=RECEPTIONIST_PROMPT,
                        capture_prompt=CAPTURE_PROMPT, pilot_model=PILOT_MODEL,
                        prompt_version=PROMPT_VERSION, soft_limit=SOFT_LIMIT,
                        hard_limit=HARD_LIMIT, tool_schema=tool)

    def test_changed_historical_rates_or_loading_are_rejected(self):
        rates = copy.deepcopy(RATES)
        rates[PILOT_MODEL] = (0.0,) + rates[PILOT_MODEL][1:]
        for extra in ({"rates": rates}, {"planning_loading": Decimal("1.00")}):
            with self.subTest(extra=extra), self.assertRaises(OfflineRecoveryBlocked):
                verify_plan(self.plan, receptionist_prompt=RECEPTIONIST_PROMPT,
                            capture_prompt=CAPTURE_PROMPT, pilot_model=PILOT_MODEL,
                            prompt_version=PROMPT_VERSION, soft_limit=SOFT_LIMIT,
                            hard_limit=HARD_LIMIT, **extra)

    def test_malformed_and_non_finite_plans_fail_with_normal_blocked_error(self):
        for value in (None, [], {"cases": [None]}, {"budget": float("nan")},
                      {"budget": float("inf")}, {"cases": {"bad": object()}}):
            with self.subTest(value=value), self.assertRaises(OfflineRecoveryBlocked):
                self.verify(value)

    def test_dictionary_key_order_is_not_a_policy_change(self):
        reversed_plan = dict(reversed(list(self.plan.items())))
        self.assertEqual(self.verify(reversed_plan)["status"],
                         "offline_plan_verified_no_paid_authority")


if __name__ == "__main__":
    unittest.main()

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


if __name__ == "__main__":
    unittest.main()

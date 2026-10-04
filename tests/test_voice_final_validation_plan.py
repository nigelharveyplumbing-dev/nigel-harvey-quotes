"""Offline checks of approval scope, frozen prompts and cumulative spend math."""
import hashlib
import json
import unittest
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

from business.voice_prompts import RECEPTIONIST_PROMPT, CAPTURE_PROMPT, PILOT_MODEL, PROMPT_VERSION
from voice_lab.budget import SOFT_LIMIT, HARD_LIMIT, GBP_PER_USD_WITH_LOADING


class FinalValidationPlanTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((Path(__file__).resolve().parents[1] /
                                'docs/step46-validation-plan.json').read_text())

    def test_plan_is_not_paid_authority_and_matches_exact_prompt_pair(self):
        p = self.plan
        self.assertEqual(p['status'], 'approval_required_no_paid_requests')
        self.assertTrue(p['synthetic_only'])
        self.assertEqual(p['model'], PILOT_MODEL)
        self.assertEqual(p['prompt_version'], PROMPT_VERSION)
        self.assertEqual(p['max_output_tokens'], 768)
        for field, text in (('prompt_sha256', RECEPTIONIST_PROMPT),
                            ('capture_prompt_sha256', CAPTURE_PROMPT)):
            self.assertEqual(p[field], hashlib.sha256(text.encode()).hexdigest())

    def test_all_core_reservations_fit_smallest_rounded_limit_and_preserve_prior_spend(self):
        p = self.plan; budget = p['budget']
        core = sum((Decimal(c['full_trial_bound_gbp']) for c in p['cases']
                    if c['required']), Decimal(0))
        for c in p['cases']:
            self.assertEqual(Decimal(c['full_trial_bound_gbp']),
                             sum(map(Decimal, c['response_bounds_gbp'])))
        cap = Decimal(budget['proposed_additional_limit_gbp'])
        self.assertEqual(cap, core.quantize(Decimal('.01'), rounding=ROUND_CEILING))
        self.assertLess(cap - Decimal('.01'), core)
        self.assertEqual(Decimal(budget['core_all_responses_bound_gbp']), core)
        prior = Decimal(budget['prior_reported_combined_planning_gbp'])
        self.assertEqual(prior, Decimal('1.9092057500'))
        self.assertEqual(Decimal(budget['maximum_combined_after_approved_limit_gbp']), prior + cap)
        self.assertLessEqual(prior + cap, SOFT_LIMIT)
        self.assertEqual(SOFT_LIMIT, Decimal(budget['working_limit_gbp']))
        self.assertEqual(HARD_LIMIT, Decimal(budget['hard_limit_gbp']))
        self.assertEqual(GBP_PER_USD_WITH_LOADING, Decimal(budget['gbp_per_usd_with_loading']))
        # Do not promise both optional trials at every-response worst case.
        self.assertGreater(Decimal(budget['all_ten_cases_bound_gbp']), SOFT_LIMIT - prior)

    def test_only_eight_required_cases_and_two_conditional_interruptions(self):
        p = self.plan
        self.assertEqual(p['core_cases'], ['normal', 'uk-name', 'surrey-postcode',
                         'gas-work-decline', 'gas-smell', 'co-alarm',
                         'uncontrolled-leak', 'water-electrics'])
        self.assertEqual(p['optional_cases'], ['corrected-phone', 'talk-over'])
        self.assertEqual([c['case'] for c in p['cases']], p['core_cases'] + p['optional_cases'])
        self.assertEqual(sum(len(c['response_bounds_gbp']) for c in p['cases']
                             if c['required']), 16)
        self.assertTrue(any('entire conservative trial bound' in g for g in p['execution_gates']))
        self.assertTrue(any('both original journals' in g for g in p['execution_gates']))


if __name__ == '__main__':
    unittest.main()

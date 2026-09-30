"""Keep the browser material-choice regression in the normal test run."""

import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
import secrets

from local_browser_server import disposable_app


class MaterialSelectionTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is unavailable in this environment")
    def test_site_survey_material_choice_and_override(self):
        script = Path(__file__).with_name("test_material_selection.cjs")
        result = subprocess.run(["node", str(script)], capture_output=True, text=True,
                                timeout=15, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Material selection regression: PASS", result.stdout)

    def test_spoken_supply_responsibility_and_thirty_percent_handling(self):
        with disposable_app(secrets.token_urlsafe(12), secrets.token_urlsafe(20)) as (app, _):
            transcript = ("The customer is supplying the tap and pop-up waste. "
                          "I need a dual-flush valve and a tube of silicone.")
            survey = app.reconcile_site_survey_supply_actions({
                "material_actions": [
                    {"material_name": "tap", "action": "include_required"},
                    {"material_name": "pop-up waste", "action": "include_required"},
                ], "proposed_job_description": "Replace tap and repair flush."
            }, transcript)
            decisions = {item["material_name"]: item["action"] for item in survey["material_actions"]}
            self.assertEqual(decisions, {"tap": "customer_supplied",
                                         "pop-up waste": "customer_supplied",
                                         "dual-flush valve": "include_required",
                                         "silicone": "include_required"})
            self.assertIn("Customer supplies tap, pop-up waste", survey["proposed_job_description"])
            draft = {"scope_of_work": "Fit the tap, waste and flush valve.", "materials": [
                {"name": "Kitchen mixer tap", "manual_price": 70},
                {"name": "Pop-up waste", "manual_price": 20},
                {"name": "Flexible tap connector", "manual_price": 5},
                {"name": "Dual-flush valve", "manual_price": 25},
                {"name": "Silicone", "manual_price": 10},
            ]}
            app.apply_site_survey_to_draft(draft, {"request": {"site_survey": survey}})
            self.assertEqual([item["name"] for item in draft["materials"]],
                             ["Flexible tap connector", "Dual-flush valve", "Silicone"])
            self.assertEqual(draft["customer_supplied_items"], ["tap", "pop-up waste"])
            self.assertIn("Customer supplies tap, pop-up waste", draft["scope_of_work"])
            # An accessory remains Nigel supplied; no customer-supplied purchase
            # can enter the procurement base, regardless of its former AI price.
            request = app.QuoteRequest(job_description=draft["scope_of_work"],
                                       materials_handling_percent=30, materials=draft["materials"])
            with patch.object(app, "fetch_tracked_price", return_value=(None, "manual")):
                result = app.calculate_quote(request)
            # The existing consumable rule charges £3 of the £10 silicone tube.
            self.assertEqual(result["materials_base"], 33)
            self.assertEqual(result["materials_procurement_amount"], 9.9)
            self.assertEqual(result["materials"], 42.9)

    def test_live_model_labels_do_not_leave_customer_products_chargeable(self):
        with disposable_app(secrets.token_urlsafe(12), secrets.token_urlsafe(20)) as (app, _):
            transcript = ("The customer is supplying the tap and pop-up waste. "
                          "I need a dual-flush valve and a tube of silicone.")
            survey = app.reconcile_site_survey_supply_actions({
                "material_actions": [
                    {"material_name": "Customer-supplied tap", "action": "customer_supplied"},
                    {"material_name": "Customer-supplied pop-up waste", "action": "customer_supplied"},
                    {"material_name": "Dual-flush valve", "action": "include_required"},
                    {"material_name": "Silicone sealant", "action": "include_required"}],
                "proposed_job_description": "Fit customer-supplied tap and pop-up waste; repair flush."
            }, transcript)
            self.assertEqual([x["material_name"] for x in survey["material_actions"]],
                             ["tap", "pop-up waste", "dual-flush valve", "silicone"])
            self.assertEqual(survey["proposed_job_description"].count("Customer supplies"), 0)
            draft = {"scope_of_work": "Fit customer-supplied tap and pop-up waste.",
                     "materials": [{"name": "Kitchen mixer tap", "manual_price": 70},
                                   {"name": "Pop-up waste", "manual_price": 20},
                                   {"name": "Flexible tap connector", "manual_price": 5}]}
            app.apply_site_survey_to_draft(draft, {"request": {"site_survey": survey}})
            self.assertEqual([x["name"] for x in draft["materials"]], ["Flexible tap connector"])
            self.assertEqual(draft["customer_supplied_items"], ["tap", "pop-up waste"])

    def test_quantity_and_uncertain_flexis_are_conservative(self):
        with disposable_app(secrets.token_urlsafe(12), secrets.token_urlsafe(20)) as (app, _):
            survey = app.reconcile_site_survey_supply_actions({"material_actions": [
                {"material_name": "Isolation valve 1", "action": "include_required"},
                {"material_name": "Isolation valve 2", "action": "include_required"}]},
                "I need two isolation valves.")
            self.assertEqual(len(survey["material_actions"]), 1)
            self.assertEqual(survey["material_actions"][0]["material_name"], "isolation valve")
            self.assertEqual(survey["material_actions"][0]["quantity"], 2)
            draft = {"materials": [{"name": "15mm isolating valve", "quantity": 1}]}
            app.apply_site_survey_to_draft(draft, {"request": {"site_survey": survey}})
            self.assertEqual(draft["materials"][0]["quantity"], 2)
            self.assertTrue(draft["materials"][0]["required"])

            uncertain = app.reconcile_site_survey_supply_actions({"material_actions": [
                {"material_name": "Flexible connector hoses", "action": "site_check"}]},
                "Might need new flexis.")
            self.assertEqual(len(uncertain["material_actions"]), 1)
            self.assertEqual(uncertain["material_actions"][0]["action"], "site_check")
            draft = {"materials": [{"name": "Flexible Tap Connector", "required": True,
                                    "display_status": "required", "manual_price": 15}]}
            app.apply_site_survey_to_draft(draft, {"request": {"site_survey": uncertain}})
            self.assertFalse(draft["materials"][0]["required"])
            self.assertEqual(draft["materials"][0]["display_status"], "optional")
            self.assertFalse(draft["materials"][0]["include_in_quote"])

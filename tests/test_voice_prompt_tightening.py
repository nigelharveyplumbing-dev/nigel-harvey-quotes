"""Offline prompt-contract checks, not measurements of generated model speech."""
import hashlib
import re
import unittest

from business.voice_prompts import (PILOT_MODEL, PROMPT_VERSION, MAX_OUTPUT_TOKENS,
                                   NORMAL_WORD_LIMIT, EMERGENCY_WORD_LIMIT, RECEPTIONIST_PROMPT,
                                   CAPTURE_PROMPT, CAPTURE_CLARIFICATIONS)
from business.voice_policy import GAS_GUIDANCE, GAS_WORK_GUIDANCE, ELECTRICAL_GUIDANCE, WATER_GUIDANCE


class PromptTighteningTests(unittest.TestCase):
    def test_explicit_ordinary_target_and_entire_turn_ceiling(self):
        self.assertEqual(PROMPT_VERSION, "private-pilot-policy-v4")
        self.assertEqual(NORMAL_WORD_LIMIT, 30)
        for rule in ("normally be 10-20 words", "HARD MAXIMUM: 30 words",
                     "entire ordinary turn", "never pad a reply"):
            self.assertIn(rule, RECEPTIONIST_PROMPT)
        self.assertNotIn("Usually 10-25", RECEPTIONIST_PROMPT)
        self.assertNotIn("at most 40", RECEPTIONIST_PROMPT)

    def test_preserved_extraction_and_safety_instructions_are_byte_identical(self):
        # Hash of the full protected suffix in reviewed Step 4.5 commit 4000e13.
        # Covers exact fields, corrections, identity/history, booking, all gas/CO,
        # water/electrics and transfer safeguards. Never regenerate to excuse a change.
        suffix = RECEPTIONIST_PROMPT[RECEPTIONIST_PROMPT.index(
            "Do not ask whether an obvious uncontrolled leak is urgent."):]
        self.assertEqual(hashlib.sha256(suffix.encode()).hexdigest(),
                         "08536666cf127a91d7bbd1f7cab8d25e8b4bedad447bf482500f284ba574a362")

    def test_model_token_cap_emergency_ceiling_and_ai_identity_unchanged(self):
        self.assertEqual(PILOT_MODEL, "gpt-realtime-2.1")
        self.assertEqual(MAX_OUTPUT_TOKENS, 768)
        self.assertEqual(EMERGENCY_WORD_LIMIT, 65)
        self.assertTrue(RECEPTIONIST_PROMPT.startswith(
            "You are the AI receptionist for Nigel Harvey Plumbing. Never pretend to be Nigel.\n"
            'Introduce yourself once: "Hello, I\'m the AI receptionist for Nigel Harvey Plumbing."\n'))

    def test_no_multi_field_readback_and_no_extraction_shortcut(self):
        for rule in ("Never recap name + phone + address + postcode + job together",
                     "Do not list\ncollected fields aloud", "structured extraction, not spoken readback",
                     "Do not shorten, skip or guess extracted facts"):
            self.assertIn(rule, RECEPTIONIST_PROMPT)

    def test_uncertain_contact_and_correction_keep_complete_single_field(self):
        for rule in ("Confirm only the single uncertain field", "Read its complete value carefully",
                     "every necessary phone digit or postcode letter", "confirm just the corrected number",
                     "Preserve those facts silently", "One short question at a time"):
            self.assertIn(rule, RECEPTIONIST_PROMPT)

    def test_enough_details_and_incomplete_callers_get_brief_closing(self):
        for rule in ("give one brief closing and stop", "summarise everything aloud",
                     "cannot continue, close briefly", "requests once when relevant"):
            self.assertIn(rule, RECEPTIONIST_PROMPT)

    def test_all_ordinary_prompt_examples_fit_ceiling_and_ask_at_most_once(self):
        examples = dict(re.findall(r'^Example for ([^:]+): "([^"]+)"$', RECEPTIONIST_PROMPT, re.M))
        self.assertEqual(set(examples), {"ordinary enquiry", "unclear phone", "corrected phone",
                                        "uncertain postcode", "appointment preference", "returning caller",
                                        "ambiguous appliance", "ending"})
        for name, spoken in examples.items():
            with self.subTest(example=name):
                self.assertLessEqual(len(spoken.split()), NORMAL_WORD_LIMIT)
                self.assertLessEqual(spoken.count("?"), 1)
        self.assertEqual(examples["ending"].count("?"), 0)
        self.assertNotIn("booked", examples["appointment preference"])
        self.assertIn("needs to confirm", examples["appointment preference"])
        self.assertIn("can't see previous jobs", examples["returning caller"])
        self.assertIn("does not currently undertake gas work", examples["ambiguous appliance"])
        self.assertIn("zero seven seven zero zero nine zero zero one three one", examples["corrected phone"])
        self.assertIn("G U four, seven L L", examples["uncertain postcode"])

    def test_length_priority_cannot_strip_emergency_guidance(self):
        for rule in ("ONLY for essential safety guidance", "Safety takes priority over brevity",
                     "safe-access conditions, emergency numbers or gas-work restrictions"):
            self.assertIn(rule, RECEPTIONIST_PROMPT)
        # Existing complete templates stay intact; ordinary limits do not trim emergencies.
        for message in (GAS_GUIDANCE, ELECTRICAL_GUIDANCE, WATER_GUIDANCE):
            self.assertLessEqual(len(("I'm the AI receptionist. " + message).split()), EMERGENCY_WORD_LIMIT)
        self.assertLessEqual(len(GAS_WORK_GUIDANCE.split()), NORMAL_WORD_LIMIT)
        self.assertIn("0800 111 999", GAS_GUIDANCE)
        self.assertIn("call 999", GAS_GUIDANCE)
        self.assertIn("fresh air", GAS_GUIDANCE)
        self.assertNotRegex(GAS_GUIDANCE.lower(), r"isolate|turn off|switch off|stop tap|meter")
        self.assertIn("otherwise leave it alone", ELECTRICAL_GUIDANCE)
        self.assertIn("safely", WATER_GUIDANCE)

    def test_emergency_endpoint_has_no_business_or_transfer_appendix(self):
        for rule in ("complete essential safety message, then STOP",
                     "do not append a Gas Safe/business explanation",
                     "not to wait for Nigel remains essential",
                     "existing brief refusal and Gas Safe registered engineer direction",
                     "later short\nturn", "do not append transfer consent",
                     "do not bundle urgency, appointment and\nphoto requests",
                     "repeat the AI introduction after interruption"):
            self.assertIn(rule, RECEPTIONIST_PROMPT)

    def test_conversation_and_capture_share_caller_hazard_classification(self):
        self.assertIn(CAPTURE_CLARIFICATIONS, RECEPTIONIST_PROMPT)
        self.assertTrue(CAPTURE_PROMPT.endswith(CAPTURE_CLARIFICATIONS))
        for rule in ("hazards actually reported by the CALLER",
                     "WITHOUT a reported gas/CO emergency remain routine",
                     "Routine urgency never permits gas work",
                     "WITHOUT\na reported electrical hazard is urgent, not electrical_water",
                     "Generic advice to\nkeep away from electrics does not establish that hazard",
                     "do not downgrade it for brevity"):
            self.assertIn(rule, CAPTURE_PROMPT)

    def test_capture_uncertainty_and_interruption_preserve_full_facts(self):
        for rule in ("not inferred from a town", "leave postcode empty",
                     "prioritise that single clarification",
                     "Only explicitly corrected facts replace earlier ones",
                     "full heard caller conversation", "including surname",
                     "Do not invent relationships, customer history or confirmations"):
            self.assertIn(rule, CAPTURE_PROMPT)

    def test_candidate_capture_binding_restores_historical_prompt(self):
        # Prompt-only binding: no schema, network, extraction-parser or lab edits.
        from voice_lab import realtime
        from voice_lab.hardening import candidate_modules
        original = realtime.CAPTURE_INSTRUCTIONS
        self.assertTrue(CAPTURE_PROMPT.startswith(original + "\n"))
        with candidate_modules():
            self.assertEqual(realtime.CAPTURE_INSTRUCTIONS, CAPTURE_PROMPT)
        self.assertEqual(realtime.CAPTURE_INSTRUCTIONS, original)


if __name__ == "__main__":
    unittest.main()

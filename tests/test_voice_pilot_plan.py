"""Offline Step 4.5/5 specification tests; no telephony or model calls."""
import unittest
from xml.etree import ElementTree
from business.voice_contacts import contact_question, corrected_phone, normalise_postcode
from business.voice_simulator import Conversation
from business.voice_pilot_plan import (PilotConfig, PilotState, acceptance_twiml, ai_notice_twiml,
                                     media_twiml, ring_twiml, screen_twiml)
from business.voice_policy import GAS_GUIDANCE, GAS_WORK_GUIDANCE, ELECTRICAL_GUIDANCE, WATER_GUIDANCE, service_scope, triage
from business.voice_prompts import (PILOT_MODEL, RECEPTIONIST_PROMPT, MAX_OUTPUT_TOKENS,
                                   NORMAL_WORD_LIMIT, EMERGENCY_WORD_LIMIT)


def config(**changes):
    return PilotConfig(**{"origin": "https://voice-pilot.example.invalid", "mobile": "+447700900123",
                          "number": "+447700900124", **changes})


def fallback_state():
    state = PilotState()
    state.start(allowlisted=True, pin_verified=True, leg="first-test-leg", now=0)
    state.dial_finished(leg="first-test-leg")
    return state


class HardeningTests(unittest.TestCase):
    def test_postcodes_from_benchmark_are_not_guessed_or_repaired(self):
        for raw, expected in (("G U 1 1 A A", "GU1 1AA"), ("GU229BB", "GU22 9BB"),
                              ("GU4 7LL", "GU4 7LL"), ("GU2 9BB", "GU2 9BB")):
            self.assertEqual(normalise_postcode(raw), expected)
        for raw in ("GU1", "Guildford", "GU22", "GU2 9"):
            self.assertIsNone(normalise_postcode(raw))
            result = contact_question({"postcode": raw})
            self.assertEqual(result[0], "postcode")
            self.assertEqual(result[1].count("?"), 1)
        # A valid-looking wrong area is not silently changed to GU.
        self.assertEqual(normalise_postcode("DE2 9BB"), "DE2 9BB")
        self.assertIn("DE2 9BB", contact_question({"postcode": "DE2 9BB"}, postcode_uncertain=True)[1])
        # G4 is syntactically valid (a different area), so syntax cannot reveal
        # the benchmark's misheard GU4. Confirm uncertainty; do not repair it.
        self.assertEqual(normalise_postcode("G4 7LL"), "G4 7LL")
        self.assertEqual(contact_question({"postcode": "G4 7LL"}, postcode_uncertain=True)[1], "Is the postcode G4 7LL?")

    def test_scripted_turns_are_short_and_do_not_repeat_supplied_contacts(self):
        convo = Conversation("sim-short")
        event = convo.caller("All my details", {"name": "Oliver Example", "callback_phone": "07700900123",
            "address": "12 Example Lane", "postcode": "GU1 1AA", "description": "Tap drips",
            "appointment_preference": "Tuesday afternoon"})
        reply = convo.turns[-1][1]
        self.assertLessEqual(len(reply.split()), NORMAL_WORD_LIMIT)
        self.assertNotIn("07700900123", reply)
        self.assertNotIn("GU1", reply)
        self.assertNotIn("Oliver", reply)
        self.assertFalse(event.facts.appointment_confirmed)
        incomplete = Conversation("sim-one-question")
        incomplete.caller("My toilet runs", {"description": "Toilet running"})
        self.assertEqual(incomplete.turns[-1][1].count("?"), 1)

    def test_scripted_uncertainty_confirms_one_contact_and_gas_work_ends(self):
        convo = Conversation("sim-uncertain")
        convo.caller("Phone and postcode unclear", {"callback_phone": "07700900131", "postcode": "GU2 9BB"},
                     phone_uncertain=True, postcode_uncertain=True)
        self.assertIn("07700900131", convo.turns[-1][1])
        self.assertNotIn("GU2", convo.turns[-1][1])
        gas = Conversation("sim-refuse-service")
        event = gas.caller("Gas boiler service please", {"description": "Gas boiler service"})
        self.assertTrue(gas.finished)
        self.assertEqual(gas.transfer_attempts, 0)
        self.assertIn("does not currently undertake gas work", gas.turns[-1][1])
        self.assertFalse(event.facts.appointment_confirmed)

    def test_corrected_phone_and_partial_talk_over_need_confirmation(self):
        self.assertEqual(corrected_phone("07700900130", "131"), "+447700900131")
        self.assertIsNone(corrected_phone("0124", "131"))
        self.assertIsNone(corrected_phone("07700900130", "one three one"))
        self.assertIn("full callback number", contact_question({"callback_phone": "0124"})[1])
        question = contact_question({"callback_phone": "07700900131", "postcode": "GU2 9BB"}, phone_uncertain=True)[1]
        self.assertIn("07700900131", question)
        self.assertNotIn("GU2", question)

    def test_clear_contacts_do_not_trigger_full_detail_readback(self):
        self.assertIsNone(contact_question({"callback_phone": "07700900123", "postcode": "GU1 1AA"}))
        question = contact_question({"callback_phone": "07700900123", "postcode": "GU1 1AA"}, postcode_uncertain=True)[1]
        self.assertEqual(question, "Is the postcode GU1 1AA?")

    def test_gas_co_unsafe_requests_get_fixed_safety_without_isolation(self):
        for text in ("I smell gas", "A smell of gas", "Gas smell", "Gas has a strong smell", "Leaking gas",
                     "Our CO alarm is sounding", "Carbon monoxide detector beeping", "Suspected carbon monoxide",
                     "I smell gas. Use a lighter and turn off the main stop tap."):
            urgency, message, transfer = triage(text)
            self.assertEqual(urgency, "gas_co")
            self.assertFalse(transfer)
            self.assertEqual(message, GAS_GUIDANCE)
            self.assertIn("0800 111 999", message)
            self.assertIn("call 999", message)
            self.assertIn("fresh air", message)
            for unsafe in ("isolate", "turn off", "switch off", "stop tap", "meter"):
                self.assertNotIn(unsafe, message.lower())

    def test_gas_work_is_declined_but_radiators_and_taps_are_plumbing(self):
        for text in ("Gas boiler servicing", "Gas pipe repair", "Install my gas cooker", "Gas Safe engineer needed",
                     "Gas heater not working", "Gas oven leaking water"):
            self.assertEqual(service_scope(text), "gas_work_not_offered")
            self.assertFalse(triage(text, "urgent")[2])
        for text in ("My kitchen tap drips", "Replace a radiator valve", "Fit an outside tap",
                     "My radiator on gas central heating leaks"):
            self.assertEqual(service_scope(text), "plumbing")
        self.assertIn("does not currently undertake gas work", GAS_WORK_GUIDANCE)
        self.assertEqual(service_scope("Boiler not working"), "appliance_clarification_required")
        self.assertFalse(triage("Boiler not working", "urgent")[2])

    def test_safety_templates_fit_spoken_word_limits_and_keep_conditions(self):
        for message in (GAS_GUIDANCE, ELECTRICAL_GUIDANCE, WATER_GUIDANCE):
            self.assertLessEqual(len(("I'm the AI receptionist. " + message).split()), EMERGENCY_WORD_LIMIT)
        self.assertLessEqual(len(GAS_WORK_GUIDANCE.split()), NORMAL_WORD_LIMIT)
        self.assertIn("safely", ELECTRICAL_GUIDANCE)
        self.assertIn("standing in water", ELECTRICAL_GUIDANCE)
        self.assertIn("otherwise leave it alone", ELECTRICAL_GUIDANCE)
        self.assertIn("water stop tap", WATER_GUIDANCE)
        self.assertIn("safely", WATER_GUIDANCE)

    def test_pilot_prompt_preserves_caps_identity_and_no_history_or_false_bookings(self):
        self.assertEqual(PILOT_MODEL, "gpt-realtime-2.1")
        self.assertEqual(MAX_OUTPUT_TOKENS, 768)
        for rule in ("Never pretend to be Nigel", "One short question", "No long preambles",
                     "full-detail recaps", "stop speaking", "no customer/job history access",
                     "requests only", "Nigel is NOT currently Gas Safe registered",
                     "no gas quote, booking or transfer", "Never give gas/electric",
                     "verified bridge event"):
            self.assertIn(rule, RECEPTIONIST_PROMPT)


class PilotRoutingTests(unittest.TestCase):
    def test_plan_is_disabled_staging_only_and_larger_model_only(self):
        config().validate()
        for change in ({"enabled": True}, {"environment": "production"}, {"model": "gpt-realtime-2.1-mini"},
                       {"origin": "https://www.nigelharveyplumbing.co.uk"}, {"origin": "http://staging.invalid"},
                       {"number": "+447700900123"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                config(**change).validate()

    def test_allowlist_and_private_pin_both_required_before_ringing(self):
        for allowlisted, pin in ((False, False), (True, False), (False, True)):
            state = PilotState()
            self.assertEqual(state.start(allowlisted=allowlisted, pin_verified=pin, leg="first", now=0), "reject")

    def test_whisper_requires_press_one_and_never_bridges_voicemail(self):
        token = "synthetic_context_123"
        ring = ElementTree.fromstring(ring_twiml(config(), token=token))
        self.assertEqual(ring.find("Dial").attrib["answerOnBridge"], "true")
        self.assertEqual(ring.find("Dial").attrib["record"], "do-not-record")
        self.assertIn("/screen?", ring.find("Dial/Number").attrib["url"])
        screen = ElementTree.fromstring(screen_twiml(config(), token=token))
        self.assertEqual(screen.find("Gather").attrib["input"], "dtmf")
        self.assertEqual(screen.find("Gather").attrib["actionOnEmptyResult"], "true")
        self.assertIn("Plumbing call — press 1 to accept", screen.find("Gather/Say").text)
        self.assertIsNotNone(screen.find("Hangup"))
        self.assertIsNotNone(ElementTree.fromstring(acceptance_twiml(False)).find("Hangup"))
        for digit in ("", "0", "2"):
            state = PilotState()
            state.start(allowlisted=True, pin_verified=True, leg="first", now=0)
            self.assertEqual(state.accept(leg="first", digit=digit, now=10), "reject_acceptance")
            self.assertEqual(state.dial_finished(leg="first"), "ai_fallback")

    def test_late_wrong_leg_and_duplicate_acceptance_do_not_bridge(self):
        state = PilotState()
        state.start(allowlisted=True, pin_verified=True, leg="first", now=0)
        self.assertEqual(state.accept(leg="wrong", digit="1", now=10), "reject_acceptance")
        self.assertEqual(state.accept(leg="first", digit="1", now=21), "reject_acceptance")
        self.assertEqual(state.accept(leg="first", digit="1", now=10), "authorise_bridge")
        self.assertNotEqual(state.state, "human")
        self.assertEqual(state.accept(leg="first", digit="1", now=11), "reject_acceptance")
        self.assertEqual(state.bridge_verified(leg="wrong"), "ignore_unverified_bridge")
        self.assertEqual(state.bridge_verified(leg="first"), "bridge_confirmed")
        self.assertEqual(state.dial_finished(leg="first"), "hangup")
        self.assertNotEqual(state.state, "ai")

    def test_one_urgent_non_gas_transfer_and_no_failure_loop(self):
        state = fallback_state()
        self.assertEqual(state.caller_route("Burst pipe flooding", transfer_consent=True, leg="urgent", now=25),
                         "attempt_one_urgent_transfer")
        self.assertEqual(state.urgent_attempts, 1)
        self.assertEqual(state.dial_finished(leg="urgent"), "ai_fallback")
        self.assertEqual(state.dial_finished(leg="urgent"), "ignore_unrelated_leg")
        self.assertEqual(state.caller_route("Burst pipe flooding", transfer_consent=True, leg="retry", now=60), "capture_for_review")
        self.assertEqual(state.urgent_attempts, 1)

    def test_gas_and_co_never_transfer_even_if_urgency_or_consent_is_forged(self):
        for text in ("I smell gas", "CO alarm sounding", "Urgent gas boiler repair", "Install gas pipework"):
            state = fallback_state()
            action = state.caller_route(text, declared="urgent", transfer_consent=True, leg="forbidden", now=25)
            self.assertIn(action, {"safety_redirect", "unsupported"})
            self.assertEqual(state.urgent_attempts, 0)
            self.assertNotEqual(state.accept(leg="forbidden", digit="1", now=26), "authorise_bridge")
        state = fallback_state()
        state.caller_route("Burst pipe", transfer_consent=True, leg="urgent", now=25)
        state.caller_route("Actually I smell gas", now=26)
        self.assertEqual(state.accept(leg="urgent", digit="1", now=27), "reject_acceptance")
        state = fallback_state()
        self.assertEqual(state.caller_route("Boiler not working", declared="urgent", transfer_consent=True),
                         "clarify_appliance_without_job_or_transfer")
        self.assertEqual(state.urgent_attempts, 0)

    def test_non_ai_callback_has_no_model_stream_or_transfer(self):
        state = fallback_state()
        self.assertEqual(state.non_ai_callback(), "queue_non_ai_callback_without_stream")
        self.assertEqual(state.caller_route("Burst pipe", transfer_consent=True), "ignore_closed_route")
        self.assertEqual(state.urgent_attempts, 0)
        xml = ElementTree.fromstring(ai_notice_twiml(config(), token="synthetic_context_123"))
        self.assertIn("transcribe", xml.find("Gather/Say").text)
        self.assertIn("Press 0", xml.find("Gather/Say").text)
        self.assertIsNone(xml.find("Connect"))
        media = ElementTree.fromstring(media_twiml(config(), token="synthetic_context_123"))
        self.assertTrue(media.find("Connect/Stream").attrib["url"].startswith("wss://"))
        self.assertNotIn("?", media.find("Connect/Stream").attrib["url"])
        self.assertEqual(media.find("Connect/Stream/Parameter").attrib["name"], "context")


if __name__ == "__main__":
    unittest.main()

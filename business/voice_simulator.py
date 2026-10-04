"""Scripted offline conversations, not an AI or speech-quality demonstration.

The synthetic extractor supplies annotated facts alongside each utterance.
The policy chooses questions from facts already supplied and emits the same
snapshot contract a future voice adapter will use. No network or audio I/O.
"""
from datetime import datetime, timedelta, timezone
from business.voice_models import VoiceEvent, VoiceFacts
from business.voice_policy import NOTICE, triage, service_scope
from business.voice_contacts import contact_question


class Conversation:
    def __init__(self, root_call_id, started_at=None):
        self.root_call_id = root_call_id
        self.started_at = started_at or datetime(2026, 10, 3, 10, tzinfo=timezone.utc)
        self.facts = VoiceFacts().model_dump()
        self.turns = [("Receptionist", NOTICE)]
        self.sequence = 0
        self.asked = set()
        self.finished = False
        self.transfer_attempts = 0

    def caller(self, utterance, extracted=None, *, phone_uncertain=False, postcode_uncertain=False):
        if self.finished:
            raise ValueError("Conversation already ended")
        self.turns.append(("Caller", utterance))
        updates = extracted or {}
        unknown = set(updates) - set(self.facts)
        if unknown:
            raise ValueError("Unknown annotated facts")
        self.facts.update(updates)
        # Safety scans the current caller's actual utterance as well as facts.
        urgency, guidance, transfer = triage(utterance + " " + self.facts["description"], self.facts["urgency"])
        self.facts["urgency"] = urgency
        if guidance:
            self.turns.append(("Receptionist", guidance))
        if urgency == "gas_co":
            self.finished = True
            return self.snapshot("emergency_redirect")
        if service_scope(utterance + " " + self.facts["description"]) == "gas_work_not_offered":
            self.finished = True
            return self.snapshot("completed")
        if service_scope(utterance + " " + self.facts["description"]) == "appliance_clarification_required":
            return self.snapshot("in_progress")
        if transfer and not self.transfer_attempts:
            self.transfer_attempts = 1  # Simulated request only, never a dial.
        confirmation = contact_question(self.facts, phone_uncertain=phone_uncertain,
                                        postcode_uncertain=postcode_uncertain)
        if confirmation and "confirm_" + confirmation[0] not in self.asked:
            self.asked.add("confirm_" + confirmation[0])
            self.turns.append(("Receptionist", confirmation[1]))
            return self.snapshot("in_progress")
        questions = (
            ("description", "What plumbing work or problem would you like Nigel to help with?"),
            ("name", "What name should I put on the enquiry?"),
            ("callback_phone", "What is the best number for Nigel to call you back on?"),
            ("address", "What is the address of the work, please?"),
            ("postcode", "And the postcode, if you have it?"),
        )
        for field, question in questions:
            if not self.facts[field] and field not in self.asked:
                self.asked.add(field)
                self.turns.append(("Receptionist", question))
                return self.snapshot("in_progress")
        self.turns.append(("Receptionist", "I've noted the details for Nigel to review. Any preferred time is a request; no appointment has been booked."))
        self.finished = True
        return self.snapshot("completed")

    def hangup(self):
        if self.finished:
            raise ValueError("Conversation already ended")
        self.finished = True
        return self.snapshot("incomplete")

    def snapshot(self, outcome):
        self.sequence += 1
        known = self.facts
        known["summary"] = "; ".join(item for item in (
            known["name"], known["description"], known["address"], known["postcode"],
            "Preferred: " + known["appointment_preference"] if known["appointment_preference"] else "",
            "Priority: " + known["urgency"],
        ) if item)
        return VoiceEvent(synthetic=True, provider="simulation", account="synthetic-v1",
                          root_call_id=self.root_call_id, event_id=f"evt-{self.root_call_id}-{self.sequence}",
                          sequence=self.sequence, started_at=self.started_at,
                          ended_at=None if outcome == "in_progress" else self.started_at + timedelta(seconds=20 * self.sequence),
                          outcome=outcome, facts=VoiceFacts(**known),
                          transcript="\n".join(f"{speaker}: {text}" for speaker, text in self.turns))


def scenarios():
    identity = {"name": "Alex Example", "name_confirmed": True, "callback_phone": "07700 900123", "callback_confirmed": True,
                "address": "1 Example Lane", "postcode": "TE1 1ST"}
    return [
        ("normal", [("I'm Alex Example, on 07700 900123. My kitchen tap drips at 1 Example Lane, TE1 1ST. Tuesday afternoon would suit; I can send a photo.",
                      {**identity, "description": "Dripping kitchen tap", "appointment_preference": "Tuesday afternoon", "photos_useful": True})], False),
        ("incomplete-no-details", [("Hello?", {})], True),
        ("incomplete-enquiry", [("My toilet keeps running. I'm Sam Sample, on 07700 900124.",
                                {"name": "Sam Sample", "name_confirmed": True, "callback_phone": "07700 900124", "callback_confirmed": True, "description": "Toilet keeps running"})], True),
        ("returning-customer", [("Alex Example again. Best number is +44 7700 900123. Please replace a radiator valve at 1 Example Lane, TE1 1ST.",
                                {**identity, "callback_phone": "+44 7700 900123", "description": "Replace radiator valve"})], False),
        ("uncontrolled-water", [("I'm Alex Example at 1 Example Lane, TE1 1ST, on 07700 900123. There is a burst pipe and uncontrolled water flooding the kitchen.",
                               {**identity, "description": "Burst pipe; uncontrolled water flooding the kitchen"})], False),
        ("water-near-electrics", [("Alex Example, 07700 900123, 1 Example Lane, TE1 1ST. Water is leaking through the ceiling onto a light fitting.",
                                  {**identity, "description": "Water leaking through ceiling onto light fitting"})], False),
        ("gas-emergency", [("I smell gas in the kitchen.", {"description": "Smell gas in kitchen"})], False),
        ("co-emergency", [("Our carbon monoxide alarm is sounding and someone feels seriously unwell.",
                           {"description": "Carbon monoxide alarm sounding; occupant feels seriously unwell"})], False),
        ("appointment-preference", [("I'm Alex Example, 07700 900123, 1 Example Lane, TE1 1ST. Can you fit an outside tap tomorrow after 4?",
                                    {**identity, "description": "Fit outside tap", "appointment_preference": "Tomorrow after 4 (date and AM/PM not confirmed)"})], False),
        ("details-over-several-turns", [
            ("My toilet needs repairing.", {"description": "Toilet repair"}),
            ("I'm Jo Fiction.", {"name": "Jo Fiction", "name_confirmed": True}),
            ("07700 900125 is my callback number.", {"callback_phone": "07700 900125", "callback_confirmed": True}),
            ("2 Example Lane, TE1 1ST.", {"address": "2 Example Lane", "postcode": "TE1 1ST"}),
        ], False),
    ]

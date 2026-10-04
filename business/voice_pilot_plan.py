"""Inactive, offline pilot routing specification. No SDK, socket or app route.

State changes below describe desired controller decisions, NOT actual calls.
The approved future adapter must persist these transitions atomically and
verify signatures/PINs before using them. Nothing here activates telephony.
"""
from dataclasses import dataclass
import re
from urllib.parse import urlencode, urlparse
from xml.etree.ElementTree import Element, SubElement, tostring
from business.voice_policy import service_scope, triage
from business.voice_prompts import PILOT_MODEL


@dataclass(frozen=True)
class PilotConfig:
    origin: str
    mobile: str
    number: str
    environment: str = "staging"
    model: str = PILOT_MODEL
    enabled: bool = False

    def validate(self):
        parsed = urlparse(self.origin)
        if (self.enabled or self.environment != "staging" or self.model != PILOT_MODEL
                or parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
                or parsed.hostname in {"nigelharveyplumbing.co.uk", "www.nigelharveyplumbing.co.uk"}):
            raise ValueError("Only an inactive staging pilot plan is allowed")
        if not all(re.fullmatch(r"\+447\d{9}", n) for n in (self.mobile, self.number)) or self.mobile == self.number:
            raise ValueError("Two distinct UK mobile E.164 numbers are required")


def callback_url(config, route, phase, token):
    config.validate()
    if phase not in {"first", "urgent"} or not re.fullmatch(r"[A-Za-z0-9_-]{16,80}", token):
        raise ValueError("Invalid bounded call context")
    return config.origin.rstrip("/") + "/pilot/" + route + "?" + urlencode({"phase": phase, "token": token})


def ring_twiml(config, *, phase="first", token):
    response = Element("Response")
    dial = SubElement(response, "Dial", {"answerOnBridge": "true", "timeout": "15",
        "timeLimit": "300", "record": "do-not-record", "callerId": config.number,
        "action": callback_url(config, "dial-finished", phase, token), "method": "POST"})
    SubElement(dial, "Number", {"url": callback_url(config, "screen", phase, token),
        "method": "POST"}).text = config.mobile
    return tostring(response, encoding="unicode")


def screen_twiml(config, *, phase="first", token):
    response = Element("Response")
    gather = SubElement(response, "Gather", {"input": "dtmf", "numDigits": "1", "timeout": "5",
        "actionOnEmptyResult": "true", "action": callback_url(config, "accept", phase, token), "method": "POST"})
    SubElement(gather, "Say", {"language": "en-GB"}).text = (
        "Urgent plumbing call — press 1 to accept." if phase == "urgent" else "Plumbing call — press 1 to accept.")
    SubElement(response, "Hangup")
    return tostring(response, encoding="unicode")


def acceptance_twiml(authorised):
    # Only return the empty response after the correlated, timely DTMF 1 is
    # durably authorised. A voicemail answer, timeout or other digit hangs up.
    response = Element("Response")
    if not authorised:
        SubElement(response, "Hangup")
    return tostring(response, encoding="unicode")


def ai_notice_twiml(config, *, token):
    response = Element("Response")
    gather = SubElement(response, "Gather", {"input": "dtmf", "numDigits": "1", "timeout": "3",
        "actionOnEmptyResult": "true", "action": callback_url(config, "ai-choice", "first", token), "method": "POST"})
    SubElement(gather, "Say", {"language": "en-GB"}).text = (
        "Hello, I'm the AI receptionist for Nigel Harvey Plumbing. I'll transcribe our conversation to take your enquiry. Press 0 for a non-AI callback.")
    SubElement(response, "Hangup")  # No implicit stream if the choice endpoint fails.
    return tostring(response, encoding="unicode")


def media_twiml(config, *, token):
    callback_url(config, "media", "first", token)  # Validate the same bounded context.
    response = Element("Response")
    connect = SubElement(response, "Connect")
    stream = SubElement(connect, "Stream", {"url": config.origin.rstrip("/").replace("https://", "wss://", 1) + "/pilot/media"})
    SubElement(stream, "Parameter", {"name": "context", "value": token})
    SubElement(response, "Redirect", {"method": "POST"}).text = callback_url(config, "stream-ended", "first", token)
    return tostring(response, encoding="unicode")


@dataclass
class PilotState:
    state: str = "new"
    leg: str = ""
    deadline: float = 0
    urgent_attempts: int = 0
    scope: str = "plumbing"

    def start(self, *, allowlisted, pin_verified, leg, now):
        if self.state != "new":
            return "ignore_duplicate"
        if not (allowlisted and pin_verified):
            self.state = "ended"
            return "reject"
        self.state, self.leg, self.deadline = "first_ring", leg, now + 20
        return "ring_mobile_first"

    def accept(self, *, leg, digit, now):
        if (self.state not in {"first_ring", "urgent_ring"} or leg != self.leg
                or digit != "1" or now >= self.deadline or self.scope != "plumbing"):
            return "reject_acceptance"
        self.state = "bridge_pending"
        return "authorise_bridge"

    def bridge_verified(self, *, leg):
        if self.state != "bridge_pending" or leg != self.leg:
            return "ignore_unverified_bridge"
        self.state = "human"
        return "bridge_confirmed"

    def dial_finished(self, *, leg):
        if leg != self.leg:
            return "ignore_unrelated_leg"
        if self.state == "human":
            self.state = "ended"
            return "hangup"
        if self.state not in {"first_ring", "urgent_ring", "bridge_pending"}:
            return "ignore_duplicate"
        self.state, self.leg = "ai", ""
        return "ai_fallback"

    def caller_route(self, text, *, declared="routine", transfer_consent=False, leg="", now=0):
        if self.state not in {"ai", "urgent_ring", "bridge_pending"}:
            return "ignore_closed_route"
        scope = service_scope(text, declared)
        if scope == "appliance_clarification_required":
            self.scope, self.state = scope, "ai"
            return "clarify_appliance_without_job_or_transfer"
        if scope != "plumbing":
            self.scope = scope
            self.state = "safety_redirect" if scope == "gas_emergency_redirect" else "unsupported"
            return self.state
        self.scope = scope
        urgency, _, eligible = triage(text, declared)
        if self.state == "ai" and transfer_consent and eligible and self.urgent_attempts == 0:
            self.urgent_attempts = 1  # Consume BEFORE the proposed dial, never retry.
            self.state, self.leg, self.deadline = "urgent_ring", leg, now + 20
            return "attempt_one_urgent_transfer"
        return "capture_for_review"

    def non_ai_callback(self):
        if self.state not in {"ai", "first_ring"}:
            return "ignore_closed_route"
        self.state, self.leg = "callback", ""
        return "queue_non_ai_callback_without_stream"

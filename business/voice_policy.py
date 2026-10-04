"""Offline receptionist policy. No diagnosis, booking or real call transfer."""
import re

NOTICE = "Hello, I'm the AI receptionist for Nigel Harvey Plumbing. This private test uses fictional details. I'll take an enquiry for Nigel."
GAS_GUIDANCE = "Leave the affected area for fresh air now. If anyone is seriously unwell or in immediate danger, call 999. From a safe place, call the National Gas Emergency Service on 0800 111 999. Avoid flames and electrical switches. Do not go back inside or wait for Nigel."
GAS_WORK_GUIDANCE = "Nigel Harvey Plumbing does not currently undertake gas work. Please contact a Gas Safe registered engineer for gas repairs, servicing or installation."
APPLIANCE_QUESTION = "Is this a gas appliance? Nigel Harvey Plumbing does not currently undertake gas work."
ELECTRICAL_GUIDANCE = "Keep away from water and electrics. Do not touch switches while standing in water. Call 999 for immediate danger. Only isolate electricity if safely accessible from a dry place away from danger; otherwise leave it alone."
WATER_GUIDANCE = "If you know the water stop tap and can reach it safely, turn off the water. Keep away from damaged ceilings. I'll flag this as urgent; Nigel's response isn't guaranteed."


def service_scope(text, declared="routine"):
    """Conservative text gate, not a diagnosis or a speech recogniser.

    It must be applied to caller text and extracted work before ANY write or
    transfer. Unknown appliance work needs clarification, never a gas booking.
    """
    text = text.lower().replace("’", "'")
    gas = re.search(r"smell(?:ing)?(?: of)? gas|gas.{0,20}smell|gas (?:leak|escape)|leaking gas|carbon monoxide|\bco (?:alarm|detector|poison)|suspect.{0,20}co\b", text)
    if gas or declared == "gas_co":
        return "gas_emergency_redirect"
    if re.search(r"\bgas\s+(?:boiler|appliance|pipe\w*|meter|cooker|hob|heater|oven|fire\b|work|repair|service|installation|engineer)|\b(?:boiler|cooker|hob|gas)\s+(?:repair|servic\w*|install\w*|replac\w*)|\b(?:repair|service|install|replace|fix|attend|diagnos\w*)\b.{0,30}\b(?:boiler|gas)\b|gas safe|gas safety|\bcp12\b", text):
        return "gas_work_not_offered"
    if re.search(r"\b(?:boiler|cooker|hob|appliance)\b", text):
        return "appliance_clarification_required"
    return "plumbing"


def triage(text, declared="routine"):
    text = text.lower().replace("’", "'")
    scope = service_scope(text, declared)
    electrical = bool(re.search(r"(?:water|leak|flood).{0,100}(?:electric|socket|light fitting|fuse ?box)|(?:electric|socket|light fitting).{0,100}(?:water|leak|flood)", text))
    urgent = bool(re.search(r"uncontrolled|burst pipe|water.{0,40}ceiling|ceiling.{0,40}water|no water|loss of water|flooding|cannot stop|can't stop", text))
    if scope == "gas_emergency_redirect":
        return "gas_co", GAS_GUIDANCE, False
    if electrical or declared == "electrical_water":
        return "electrical_water", ELECTRICAL_GUIDANCE, scope == "plumbing"
    if scope == "gas_work_not_offered":
        return "routine", GAS_WORK_GUIDANCE, False
    if scope == "appliance_clarification_required":
        if urgent:
            return "urgent", WATER_GUIDANCE + " " + APPLIANCE_QUESTION, False
        return "routine", APPLIANCE_QUESTION, False
    if urgent or declared == "urgent":
        return "urgent", WATER_GUIDANCE, True
    return "routine", "", False


PRIORITY = {"routine": 0, "urgent": 1, "electrical_water": 2, "gas_co": 3}

"""Offline receptionist policy. No diagnosis, booking or real call transfer."""
import re

NOTICE = "Hello, I'm the AI receptionist for Nigel Harvey Plumbing. This private test uses fictional details. I'll take an enquiry for Nigel."
GAS_GUIDANCE = "Please leave the affected area for fresh air and call the National Gas Emergency Service on 0800 111 999 from a safe place. Do not operate electrical switches or use flames. If anyone is seriously unwell or there is immediate danger, call 999. Do not wait for Nigel."
ELECTRICAL_GUIDANCE = "Keep away from the water and affected electrics. Do not touch switches or equipment while standing in water. Switch off the supply only if you can do so safely without approaching the danger. If there is immediate danger, call 999. I'll flag this for Nigel; a response is not guaranteed."
WATER_GUIDANCE = "If you know where the water stop tap is and can reach it safely, turn off the water. Keep away from damaged ceilings. I'll flag this as urgent for Nigel; a response is not guaranteed."


def triage(text, declared="routine"):
    text = text.lower()
    gas = bool(re.search(r"smell(?:ing)? gas|gas (?:leak|escape)|(?:carbon monoxide|co) (?:alarm|poison)|co detector.{0,25}(?:going off|sounding)|suspect.{0,20}carbon monoxide", text))
    electrical = bool(re.search(r"(?:water|leak|flood).{0,100}(?:electric|socket|light fitting|fuse ?box)|(?:electric|socket|light fitting).{0,100}(?:water|leak|flood)", text))
    urgent = bool(re.search(r"uncontrolled|burst pipe|water.{0,40}ceiling|ceiling.{0,40}water|no water|loss of water|flooding|cannot stop|can't stop", text))
    if gas or declared == "gas_co":
        return "gas_co", GAS_GUIDANCE, False
    if electrical or declared == "electrical_water":
        return "electrical_water", ELECTRICAL_GUIDANCE, True
    if urgent or declared == "urgent":
        return "urgent", WATER_GUIDANCE, True
    return "routine", "", False


PRIORITY = {"routine": 0, "urgent": 1, "electrical_water": 2, "gas_co": 3}

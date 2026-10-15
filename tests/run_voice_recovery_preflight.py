"""Offline-only Step 4.6 recovery preflight. No network, audio or paid calls.

This is a reconstruction of *validation safeguards*, not the lost commit.
It reads the public, synthetic plan and frozen prompt constants only.
"""
import hashlib
import json
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

from voice_lab.budget import GBP_PER_USD_WITH_LOADING, RATES
from voice_lab.cases import CAPTURE_TOOL

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "docs" / "step46-validation-plan.json"
CORE = (
    "normal", "uk-name", "surrey-postcode", "gas-work-decline",
    "gas-smell", "co-alarm", "uncontrolled-leak", "water-electrics",
)
OPTIONAL = ("corrected-phone", "talk-over")
# Canonical fingerprints of the reviewed public plan, tool schema and historical
# rate card at PR #21 head 22642d4. Deliberate changes require a fresh review;
# this verifier cannot approve a changed plan by reading it as its own baseline.
REVIEWED_PLAN_SHA256 = "50ed7568591b24c9d23c4ec928b674553ff93c40aa8d5afadf1615a8b7603f9a"
REVIEWED_TOOL_SHA256 = "0013c7097dd89ef72eae8e4f40499858fd7cfc2a838b784795af0e44df9ff238"
REVIEWED_RATES_SHA256 = "c337aecdc35e9fe13e1024b2c891d313c5f5fa39f8f6152814756e47e6222bee"


class OfflineRecoveryBlocked(ValueError):
    """Do not proceed when the offline plan differs from approved boundaries."""


def fingerprint(value):
    try:
        text = json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise OfflineRecoveryBlocked("Invalid offline JSON structure") from exc
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_plan(plan, *, receptionist_prompt, capture_prompt, pilot_model,
                prompt_version, soft_limit, hard_limit, tool_schema=CAPTURE_TOOL,
                rates=RATES, planning_loading=GBP_PER_USD_WITH_LOADING):
    """Fail closed on altered prompt, model, cases, reservations or budgets."""
    def require(condition, reason):
        if not condition:
            raise OfflineRecoveryBlocked(reason)

    require(type(plan) is dict, "Offline plan must be an object")
    require(fingerprint(plan) == REVIEWED_PLAN_SHA256,
            "Reviewed plan changed; all settings, cases, bounds and gates are frozen")
    require(fingerprint(tool_schema) == REVIEWED_TOOL_SHA256,
            "Reviewed capture tool schema changed")
    require(fingerprint(rates) == REVIEWED_RATES_SHA256,
            "Historical rate card changed; reservations require review")
    require(planning_loading == Decimal("1.25"), "Planning loading changed")
    require((soft_limit, hard_limit) == (Decimal("4.85"), Decimal("5.00")),
            "Cumulative budget policy changed")
    require(isinstance(receptionist_prompt, str) and isinstance(capture_prompt, str),
            "Frozen prompts must be strings")
    require(plan["voice"] == "marin" and plan["reasoning_effort"] == "low",
            "Reviewed voice or reasoning setting changed")
    require(plan["instruction_and_tool_bytes"] ==
            len(receptionist_prompt.encode("utf-8")) + len(json.dumps(tool_schema).encode("utf-8")),
            "Prompt/tool byte bound changed")
    require(plan["capture_prompt_bytes"] == len(capture_prompt.encode("utf-8")),
            "Capture prompt byte bound changed")
    require(plan.get("status") == "approval_required_no_paid_requests",
            "The plan must not authorise paid work")
    require(plan.get("synthetic_only") is True, "Synthetic-only gate missing")
    require(plan.get("model") == pilot_model == "gpt-realtime-2.1",
            "Pilot model changed")
    require(plan.get("prompt_version") == prompt_version,
            "Prompt version changed")
    require(plan.get("max_output_tokens") == 768, "Output cap changed")
    require(plan.get("core_cases") == list(CORE), "Required cases changed")
    require(plan.get("optional_cases") == list(OPTIONAL), "Optional cases changed")
    require([c.get("case") for c in plan.get("cases", [])] ==
            list(CORE + OPTIONAL), "Case order or count changed")
    for key, prompt in (("prompt_sha256", receptionist_prompt),
                        ("capture_prompt_sha256", capture_prompt)):
        require(plan.get(key) == hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "Frozen prompt mismatch: " + key)
    budget = plan.get("budget", {})
    try:
        core_bound = Decimal("0")
        all_bound = Decimal("0")
        required_responses = 0
        for case in plan["cases"]:
            response_bounds = [Decimal(v) for v in case["response_bounds_gbp"]]
            full_bound = Decimal(case["full_trial_bound_gbp"])
            require(response_bounds and all(v >= 0 for v in response_bounds),
                    "Missing or negative response reservation")
            require(sum(response_bounds, Decimal("0")) == full_bound,
                    "Response reservation total mismatch")
            required = case["case"] in CORE
            require(case["required"] is required, "Required flag changed")
            if required:
                core_bound += full_bound
                required_responses += len(response_bounds)
            all_bound += full_bound
        require(required_responses == 16, "Required response count changed")
        additional = Decimal(budget["proposed_additional_limit_gbp"])
        prior = Decimal(budget["prior_reported_combined_planning_gbp"])
        combined = Decimal(budget["maximum_combined_after_approved_limit_gbp"])
        require(core_bound == Decimal(budget["core_all_responses_bound_gbp"]),
                "Core reservation mismatch")
        require(additional == core_bound.quantize(Decimal(".01"), rounding=ROUND_CEILING),
                "Additional cap not the minimal rounded core bound")
        require(additional == Decimal("2.45"), "Additional cap changed")
        require(prior == Decimal("1.9092057500"), "Prior paid spend changed")
        require(combined == prior + additional, "Cumulative reservation mismatch")
        require(combined <= soft_limit < hard_limit, "Cumulative budget cap exceeded")
        require(soft_limit == Decimal(budget["working_limit_gbp"]) ==
                Decimal("4.85"), "Working limit changed")
        require(hard_limit == Decimal(budget["hard_limit_gbp"]) ==
                Decimal("5.00"), "Hard limit changed")
        require(all_bound == Decimal(budget["all_ten_cases_bound_gbp"]),
                "All-case bound changed")
        require(all_bound > soft_limit - prior,
                "Optional cases must remain conditional, not preapproved")
    except (KeyError, TypeError, ArithmeticError) as exc:
        raise OfflineRecoveryBlocked("Invalid offline budget/case structure") from exc
    gates = plan.get("execution_gates", [])
    require(any("both original journals" in g for g in gates),
            "Original paid journals reconciliation gate missing")
    require(any("No telephony" in g for g in gates),
            "No-telephony gate missing")
    return {
        "status": "offline_plan_verified_no_paid_authority",
        "core_cases": len(CORE),
        "optional_cases_conditional": len(OPTIONAL),
        "required_responses": required_responses,
        "core_reserved_gbp": str(core_bound),
        "additional_limit_gbp": str(additional),
        "prior_reported_gbp": str(prior),
        "maximum_combined_gbp": str(combined),
        "paid_requests_made": 0,
        "private_audio_or_journals_read": False,
        "ready_for_live_validation": False,
    }


def main():
    from business.voice_prompts import (
        RECEPTIONIST_PROMPT, CAPTURE_PROMPT, PILOT_MODEL, PROMPT_VERSION,
    )
    from voice_lab.budget import SOFT_LIMIT, HARD_LIMIT
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    result = verify_plan(
        plan, receptionist_prompt=RECEPTIONIST_PROMPT,
        capture_prompt=CAPTURE_PROMPT, pilot_model=PILOT_MODEL,
        prompt_version=PROMPT_VERSION, soft_limit=SOFT_LIMIT,
        hard_limit=HARD_LIMIT,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

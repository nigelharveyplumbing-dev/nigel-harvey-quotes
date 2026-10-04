"""Private synthetic voice benchmark. Default mode makes no network requests.

Run from the repository root; never imports the app or opens its database.
"""
import argparse
import asyncio
import getpass
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice_lab.audio import generate, verify_manifest
from voice_lab.budget import (BudgetStop, Ledger, RATE_DATE, SOFT_LIMIT, HARD_LIMIT,
                              GBP_PER_USD_WITH_LOADING, response_bound, verify_rate_date)
from voice_lab.cases import CASES, MODELS, CAPTURE_TOOL, INSTRUCTIONS, MAX_OUTPUT_TOKENS, paired_order
from voice_lab.scoring import summary


def plan(durations):
    total = Decimal(0)
    prompt_bytes = len(INSTRUCTIONS.encode()) + len(json.dumps(CAPTURE_TOOL).encode())
    trials = []
    for case, model in paired_order():
        seconds = 0
        bound = Decimal(0)
        for index, duration in enumerate(durations[case["id"]]):
            seconds += duration + 0.7
            bound += response_bound(model, prompt_bytes, seconds, index, MAX_OUTPUT_TOKENS)
        bound += response_bound(model, prompt_bytes, seconds, len(case["turns"]), MAX_OUTPUT_TOKENS)
        trials.append({"case": case["id"], "model": model, "reservation_bound_usd": str(bound)})
        total += bound
    return {"models": list(MODELS), "synthetic_cases": len(CASES), "planned_trials": len(trials),
            "planned_paid_responses": sum(len(case["turns"]) + 1 for case, _ in paired_order()),
            "max_output_tokens_per_response": MAX_OUTPUT_TOKENS, "trials": trials,
            "planning_bound_gbp": str(total * GBP_PER_USD_WITH_LOADING),
            "planning_bound_usd": str(total), "working_limit_gbp": str(SOFT_LIMIT),
            "user_limit_gbp": str(HARD_LIMIT), "rate_date": RATE_DATE.isoformat(),
            "planning_conversion": "£1.25 per USD including a conservative VAT/fee loading; not a quoted exchange rate"}


def check_budget(planned, ledger):
    if ledger.data["uncertain"] or any(e["state"] == "in_flight" for e in ledger.data["entries"]):
        raise BudgetStop("Unresolved prior usage; do not resume without reconciliation")
    bound = Decimal(planned["planning_bound_gbp"]) + ledger.planning_gbp
    if bound > SOFT_LIMIT or bound > HARD_LIMIT:
        raise BudgetStop("Full batch estimate exceeds the working budget; no paid session started")


def save_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def resume_report(path, planned, manifest, ledger):
    """Skip only trials proved accounted for by BOTH the report and journal."""
    try:
        report = json.loads(path.read_text())
        if (report.get("synthetic_only") is not True or report.get("caller_audio") != manifest
                or report["plan"] != planned
                or report["status"] not in {"stopped_on_error", "partial", "live_trials_completed_human_review_required"}):
            raise ValueError()
        known = {(case["id"], model): case for case, model in paired_order()}
        skipped = set()
        for row in report["results"]:
            pair = (row["case"], row["model"])
            if pair not in known or pair in skipped or row["status"] != "completed":
                raise ValueError()
            skipped.add(pair)
        failures = list(report.get("accounted_failed_trials", []))
        stopped = report.get("stopped_trial")
        if stopped and not any((f["case"], f["model"]) == (stopped["case"], stopped["model"]) for f in failures):
            failures.append({**stopped, "status": "accounted_failed_not_replayed",
                "extraction_scored": False,
                "reason": "Paid trial failed; retained as a failure, never retried automatically."})
        for row in failures:
            pair = (row["case"], row["model"])
            if pair not in known or pair in skipped:
                raise ValueError()
            skipped.add(pair)
        expected_labels = set()
        for pair in skipped:
            prefix = ":".join(pair)
            expected_labels.update(f"{prefix}:turn-{i + 1}" for i in range(len(known[pair]["turns"])))
            expected_labels.add(prefix + ":capture")
        labels = [entry["label"] for entry in ledger.data["entries"]]
        if (ledger.data["uncertain"] or any(e["state"] != "reported" for e in ledger.data["entries"])
                or len(labels) != len(set(labels)) or set(labels) != expected_labels):
            raise ValueError()
        report["accounted_failed_trials"] = failures
        report.pop("stopped_trial", None)
        pending = [row for row in planned["trials"] if (row["case"], row["model"]) not in skipped]
        remaining = sum((Decimal(row["reservation_bound_usd"]) for row in pending), Decimal(0))
        report["resume"] = {"skipped_accounted_trials": len(skipped), "remaining_trials": len(pending),
            "remaining_bound_gbp": str(remaining * GBP_PER_USD_WITH_LOADING),
            "existing_spend_gbp": str(ledger.planning_gbp),
            "combined_bound_gbp": str(remaining * GBP_PER_USD_WITH_LOADING + ledger.planning_gbp),
            "working_limit_gbp": str(SOFT_LIMIT), "hard_limit_gbp": str(HARD_LIMIT)}
        return report, skipped, {"planning_bound_gbp": report["resume"]["remaining_bound_gbp"]}
    except (OSError, KeyError, TypeError, ValueError):
        raise BudgetStop("Report/audio/ledger mismatch or unresolved usage; no automatic replay or ledger reset") from None


async def live(report, ledger, key, audio_directory, output_directory, report_path, skipped=()):
    from voice_lab.realtime import ExtractionError, run_trial
    for case, model in paired_order():
        if (case["id"], model) in skipped:
            continue
        try:
            row = await run_trial(case, model, key, ledger, audio_directory, output_directory)
        except Exception as exc:
            # Do not serialize exceptions that might contain authentication or
            # provider headers. Persist a class and explicit stop state instead.
            report["status"] = "stopped_on_error"
            report["stopped_trial"] = {"case": case["id"], "model": model,
                                      "error_class": type(exc).__name__}
            if isinstance(exc, ExtractionError):
                report["stopped_trial"]["diagnostic"] = str(exc)
                report["stopped_trial"]["evidence_file"] = str(output_directory / case["id"] / model / "paid-evidence.json")
            break
        report["results"].append(row)
        report["status"] = "partial"
        report["comparison"] = summary(report["results"])
        report["ledger_planning_gbp"] = str(ledger.planning_gbp)
        save_report(report_path, report)
        print(json.dumps({"case": case["id"], "model": model, "status": row["status"],
                          "ledger_planning_gbp": str(ledger.planning_gbp)}), flush=True)
    else:
        report["status"] = "live_trials_completed_human_review_required"
    report["comparison"] = summary(report["results"])
    report["ledger_planning_gbp"] = str(ledger.planning_gbp)
    report["unresolved_usage"] = ledger.data["uncertain"] or any(e["state"] == "in_flight" for e in ledger.data["entries"])
    report["incomplete_pairs"] = [case["id"] for case in CASES if
        {row["model"] for row in report["results"] if row["case"] == case["id"]} != set(MODELS)]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-dir", type=Path, required=True,
                        help="Private scratch folder for synthetic WAV, ledger and reports")
    parser.add_argument("--generate-audio", action="store_true", help="Free local synthesis only")
    parser.add_argument("--live", action="store_true", help="Explicit opt-in to budgeted paid API trials")
    parser.add_argument("--prompt-key", action="store_true", help="Locally prompt without echo; never put keys in chat")
    parser.add_argument("--resume", action="store_true", help="Check existing report/journal and skip accounted trials; never retry them")
    args = parser.parse_args(argv)
    private = args.private_dir.resolve()
    repository = Path(__file__).resolve().parents[1]
    production_data = Path("/var/data").resolve()
    if private == repository or repository in private.parents or private == production_data or production_data in private.parents:
        parser.error("Private output must be outside the repository and production data directory")
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    audio = private / "audio"
    if args.generate_audio:
        generate(audio)
    manifest, durations = verify_manifest(audio)
    planned = plan(durations)
    report = {"status": "prepared_no_live_requests", "synthetic_only": True,
              "plan": planned, "caller_audio": manifest, "results": [], "comparison": summary([]),
              "paid_api_requests_this_run": 0, "production_changes": False,
              "limitations": ["One robotic caller voice; no claim of human accent coverage.",
                              "Virtual playback; no measurement of browser speaker or microphone latency.",
                              "Keyword screens require listening and semantic safety review.",
                              "No live app, database, telephony, messages or booking tools are connected."]}
    report_path = private / "benchmark-report.json"
    ledger = Ledger(private / "spending-ledger.json")
    destination = private / "benchmark-resume-preflight.json" if args.resume or ledger.data["entries"] else report_path
    skipped = set()
    try:
        budget_plan = planned
        if args.resume:
            report, skipped, budget_plan = resume_report(report_path, planned, manifest, ledger)
            check_budget(budget_plan, ledger)
        elif ledger.data["entries"]:
            raise BudgetStop("Existing paid work: use --resume; report and ledger will not be overwritten")
        report["ledger_planning_gbp"] = str(ledger.planning_gbp)
        if not args.live:
            if args.resume:
                report["status"] = "resume_preflight_passed_no_live_requests"
                report["paid_api_requests_this_run"] = 0
            report["live_blockers"] = [] if os.getenv("OPENAI_API_KEY") else ["Secure OpenAI API credentials are not configured"]
        else:
            verify_rate_date()
            check_budget(budget_plan, ledger)
            if os.getenv("VOICE_API_TEST_ENABLED") != "1":
                raise BudgetStop("Set VOICE_API_TEST_ENABLED=1 explicitly for this standalone lab")
            key = getpass.getpass("OpenAI API key (hidden, local process only): ") if args.prompt_key else os.getenv("OPENAI_API_KEY", "")
            if not key:
                raise BudgetStop("Secure API credential missing; no paid requests made")
            if args.resume:
                backup = private / "benchmark-report.before-resume.json"
                if not backup.exists():
                    save_report(backup, json.loads(report_path.read_text()))
            destination = report_path
            report["paid_api_requests_this_run"] = None  # Fill from usage, never infer successful billing.
            save_report(report_path, report)
            asyncio.run(live(report, ledger, key, audio, private / "responses", report_path, skipped))
    except BudgetStop as exc:
        report["status"] = "blocked_before_live_requests"
        report["live_blockers"] = [str(exc)]
    finally:
        report["comparison"] = summary(report["results"])
        save_report(destination, report)
        ledger.close()
    print(json.dumps({"status": report["status"], "planned_trials": planned["planned_trials"],
                      "planning_bound_gbp": planned["planning_bound_gbp"],
                      "measured_trials": len(report["results"]), "report": str(destination),
                      "resume": report.get("resume")}))
    return report


if __name__ == "__main__":
    main()

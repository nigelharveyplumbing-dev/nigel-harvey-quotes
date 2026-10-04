"""Larger-model-only Step 4.5 validation; offline unless --live is explicit."""
import argparse
import asyncio
import getpass
import json
import logging
import os
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_voice_api_benchmark import save_report
from business.voice_prompts import PILOT_MODEL, PROMPT_VERSION, RECEPTIONIST_PROMPT
from voice_lab.budget import BudgetStop, response_bound, verify_rate_date
from voice_lab.cases import CAPTURE_TOOL
from voice_lab.hardening import (Baseline, CandidateLedger, ORDER, VALIDATION_CASES,
                                 behaviour_screens, candidate_modules, matched_comparison,
                                 prepare_audio, private_directory, speech_metrics, validation_journal_path)
from voice_lab import realtime


class CandidateTrial(realtime.Trial):
    async def run(self, case, audio_directory, output_directory):
        try:
            return await super().run(case, audio_directory, output_directory)
        finally:
            if self.responses:
                self.archive(case, output_directory)  # Preserve partial paid evidence too.


async def trial(case, key, ledger, audio, output):
    import websockets
    logger = logging.getLogger("private-hardening-websocket")
    logger.disabled = True
    with candidate_modules():
        async with websockets.connect("wss://api.openai.com/v1/realtime?model=" + PILOT_MODEL,
                additional_headers={"Authorization": "Bearer " + key}, logger=logger,
                open_timeout=15, close_timeout=3, max_size=1024 * 1024) as socket:
            return await CandidateTrial(socket, PILOT_MODEL, ledger).run(case, audio, output)


def plan(durations):
    from voice_lab.budget import GBP_PER_USD_WITH_LOADING
    items, total = [], Decimal(0)
    text = len(RECEPTIONIST_PROMPT.encode()) + len(json.dumps(CAPTURE_TOOL).encode())
    for name in ORDER:
        bound, seconds = Decimal(0), 0
        for index, duration in enumerate(durations[name]):
            seconds += duration + .7
            bound += response_bound(PILOT_MODEL, text, seconds, index, 768)
        bound += response_bound(PILOT_MODEL, text, seconds, len(durations[name]), 768)
        items.append({"case": name, "worst_case_reservation_gbp": str(bound * GBP_PER_USD_WITH_LOADING)})
        total += bound
    return {"model": PILOT_MODEL, "max_output_tokens": 768, "cases": items,
            "all_responses_at_maximum_bound_gbp": str(total * GBP_PER_USD_WITH_LOADING),
            "additional_limit_gbp": "1.00", "working_limit_gbp": "4.85", "hard_limit_gbp": "5.00",
            "budget_policy": "Reserve each response before creating it; never exceed £1 additional or cumulative caps. Stop even mid-trial when the next reservation cannot fit. Full scenario coverage is not guaranteed within £1."}


async def live(report, ledger, key, directory, baseline):
    for name in ORDER:
        case = next(c for c in VALIDATION_CASES if c["id"] == name)
        try:
            row = await trial(case, key, ledger, directory / "audio", directory / "responses")
            row["behaviour_screens"] = behaviour_screens(case, row)
            report["results"].append(row)
            report["status"] = "partial"
        except Exception as exc:
            unresolved = ledger.data["uncertain"] or any(e["state"] != "reported" for e in ledger.data["entries"])
            report["status"] = "stopped_before_next_paid_response" if isinstance(exc, BudgetStop) and not unresolved else "stopped_on_error"
            report["stopped_trial"] = {"case": name, "error_class": type(exc).__name__,
                "evidence_file": str(directory / "responses" / name / PILOT_MODEL / "paid-evidence.json")
                    if (directory / "responses" / name / PILOT_MODEL / "paid-evidence.json").exists() else None}
            # Only locally generated BudgetStop messages are safe; no raw API/auth exception text.
            if isinstance(exc, BudgetStop):
                report["stopped_trial"]["reason"] = str(exc)
            break
        finally:
            refresh(report, ledger, baseline)
            save_report(directory / "hardening-report.json", report)
            print(json.dumps({"case": name, "status": report["status"],
                              "additional_planning_gbp": report["additional_planning_gbp"],
                              "combined_planning_gbp": report["combined_planning_gbp"]}), flush=True)
    else:
        report["status"] = "live_validation_completed_human_review_required"


def refresh(report, ledger, baseline):
    report["additional_planning_gbp"] = str(ledger.planning_gbp)
    report["combined_planning_gbp"] = str(baseline.spend + ledger.planning_gbp)
    report["unresolved_usage"] = ledger.data["uncertain"] or any(e["state"] != "reported" for e in ledger.data["entries"])
    report["reported_paid_responses"] = sum(e["state"] == "reported" for e in ledger.data["entries"])
    report["speech_metrics"] = speech_metrics(report["results"])
    report["comparison"] = matched_comparison(report["results"], baseline.report)
    report["not_measured_cases"] = [name for name in ORDER if name not in {r["case"] for r in report["results"]}]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, required=True, help="Completed Mac Step 4 directory; read-only")
    parser.add_argument("--private-dir", type=Path, required=True, help="New private candidate directory outside repository")
    parser.add_argument("--prepare-audio", action="store_true", help="Copy original clips and locally synthesize five extras; no API")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--prompt-key", action="store_true", help="Hidden local process-only key prompt")
    args = parser.parse_args(argv)
    baseline, ledger = None, None
    try:
        private = private_directory(args.private_dir, args.baseline_dir)
        baseline = Baseline(args.baseline_dir)
        manifest_path = private / "audio" / "manifest.json"
        if not manifest_path.exists() and not args.prepare_audio:
            raise BudgetStop("Use --prepare-audio once before live validation")
        manifest, durations = prepare_audio(baseline.directory / "audio", private / "audio")
        report_path = private / "hardening-report.json"
        if report_path.exists():
            old = json.loads(report_path.read_text())
            if old.get("baseline") != baseline.identity or old.get("prompt") != RECEPTIONIST_PROMPT or old.get("caller_audio") != manifest:
                raise BudgetStop("Candidate report/baseline/prompt/audio mismatch; never overwrite paid evidence")
            if old.get("results") or old.get("reported_paid_responses", 0) or old.get("unresolved_usage"):
                raise BudgetStop("Candidate paid evidence exists; never automatically replay it")
        ledger = CandidateLedger(validation_journal_path(baseline), baseline)
        if ledger.data["entries"] or ledger.data["uncertain"]:
            raise BudgetStop("Candidate paid work exists; review it instead of automatically replaying or resetting usage")
        report = {"status": "prepared_no_live_requests", "synthetic_only": True, "model": PILOT_MODEL,
            "prompt_version": PROMPT_VERSION, "prompt": RECEPTIONIST_PROMPT, "baseline": baseline.identity,
            "caller_audio": manifest, "plan": plan(durations), "results": [], "phone_pilot_ready": False,
            "limitations": ["One robotic caller voice; virtual playback, no real microphone/speaker/phone measurement.",
                            "Word/question/keyword screens need human listening and semantic review.",
                            "No app, real customer history, booking, telephony or transfer tools connected."]}
        if args.live:
            verify_rate_date()
            if os.getenv("VOICE_API_TEST_ENABLED") != "1":
                raise BudgetStop("Set VOICE_API_TEST_ENABLED=1 explicitly")
            if args.prompt_key and not sys.stdin.isatty():
                raise BudgetStop("Hidden key prompt requires an interactive local Terminal")
            key = getpass.getpass("Existing plumbing OpenAI API key (hidden, process only): ") if args.prompt_key else os.getenv("OPENAI_API_KEY", "")
            if not key:
                raise BudgetStop("Secure API key missing; no paid requests made")
            print(json.dumps({"secure_key_loaded": True, "key_printed_or_saved": False}), flush=True)
            if args.prompt_key:
                os.environ["OPENAI_API_KEY"] = key
            try:
                save_report(report_path, report)
                asyncio.run(live(report, ledger, key, private, baseline))
            finally:
                if args.prompt_key:
                    os.environ.pop("OPENAI_API_KEY", None)
        refresh(report, ledger, baseline)
        baseline.unchanged()
        save_report(report_path, report)
        print(json.dumps({key: report[key] for key in ("status", "additional_planning_gbp", "combined_planning_gbp", "reported_paid_responses", "not_measured_cases")}))
        return report
    except (BudgetStop, OSError, ValueError, KeyError) as exc:
        # No raw credential-bearing exceptions; failure prior to live does not overwrite reports.
        print(json.dumps({"status": "blocked", "error_class": type(exc).__name__,
                          "reason": str(exc) if isinstance(exc, BudgetStop) else "Local evidence/fixture/setup validation failed"}))
        return None
    finally:
        if ledger:
            ledger.close()
        if baseline:
            baseline.close()


if __name__ == "__main__":
    result = main()
    raise SystemExit(0 if result and result["status"] in {"prepared_no_live_requests", "live_validation_completed_human_review_required"} else 2)

"""Run synthetic conversations through the real signed API in disposable storage."""
import argparse
import json
from pathlib import Path
from fastapi.testclient import TestClient
from local_browser_server import disposable_app
from voice_support import voice_test_settings, signed_post


def run():
    config = voice_test_settings()
    report = {"synthetic_only": True, "extractor": "annotated scripted fixtures; no AI API or audio", "scenarios": []}
    with disposable_app("synthetic-staff", "synthetic-password", environment="test", voice_settings=config) as (app, _):
        from business.voice_simulator import Conversation, scenarios
        from business.voice_store import get_call, deliver_one
        from business.lead_store import get_lead_by_id
        from business.db import get_db
        conn = get_db()
        with conn:
            conn.execute("INSERT INTO customers(name,address,phone,created_at,updated_at) VALUES(?,?,?,?,?)",
                         ("Alex Example", "Saved synthetic address", "07700 900123", "synthetic", "synthetic"))
        conn.close()
        with TestClient(app.app) as client:
            final = None
            for name, turns, hangup in scenarios():
                convo = Conversation("sim-" + name)
                responses = []
                for text, facts in turns:
                    final = convo.caller(text, facts)
                    response = signed_post(client, final, config["VOICE_WEBHOOK_SECRET"])
                    response.raise_for_status()
                    responses.append(response.json())
                if hangup:
                    final = convo.hangup()
                    response = signed_post(client, final, config["VOICE_WEBHOOK_SECRET"])
                    response.raise_for_status()
                    responses.append(response.json())
                record = get_call(responses[-1]["id"])
                # Exclude ciphertext, receipt timestamps and expiry epochs from the
                # deterministic example report, while keeping explicit policy.
                report["scenarios"].append({"name": name, "conversation": convo.turns, "event_results": responses,
                    "call": {key: record[key] for key in ("id", "root_call_id", "lead_id", "sequence", "outcome", "urgency", "transfer_requested", "content")},
                    "lead": get_lead_by_id(record["lead_id"]) if record["lead_id"] else None,
                    "transcript_retention_days": 30, "call_content_retention_days": 90})
            report["duplicate_final_event"] = signed_post(client, final, config["VOICE_WEBHOOK_SECRET"]).json()
            sent = []
            while deliver_one(lambda message_id, payload: sent.append({"message_id": message_id, **payload})) != "idle":
                pass
            report["simulated_notifications"] = sent
            conn = get_db()
            report["counts"] = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                                for table in ("customers", "leads", "voice_calls", "voice_events", "voice_notifications", "quotes", "invoices", "appointments", "jobs")}
            conn.close()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run()
    content = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content)
    print(json.dumps({"synthetic_only": True, "counts": report["counts"], "scenarios": len(report["scenarios"])}))

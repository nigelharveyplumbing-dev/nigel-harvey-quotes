"""Optional localhost-only disposable API inspection; no provider connections."""
import argparse
import secrets
import uvicorn
from local_browser_server import disposable_app
from voice_support import voice_test_settings


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Choose an unprivileged local port")
    password = secrets.token_urlsafe(18)
    config = voice_test_settings()
    with disposable_app("synthetic-staff", password, environment="test", voice_settings=config) as (app, _):
        from business.voice_simulator import Conversation, scenarios
        from business.voice_store import ingest
        for name, turns, hangup in scenarios():
            convo = Conversation("sim-" + name)
            for utterance, facts in turns:
                ingest(convo.caller(utterance, facts), secrets.token_hex(16))
            if hangup:
                ingest(convo.hangup(), secrets.token_hex(16))
        print(f"Local synthetic records: http://127.0.0.1:{args.port}/api/voice/calls", flush=True)
        print(f"Temporary staff login: synthetic-staff / {password}", flush=True)
        print("Database and ephemeral credentials are discarded on exit.", flush=True)
        uvicorn.run(app.app, host="127.0.0.1", port=args.port, access_log=False)

# Stage 6 local browser checks

Run `python -B tests/run_stage6_local.py` with the Python test dependencies,
Node, Playwright and a **preinstalled** Chromium executable. If Chromium is
installed outside Playwright's cache, set `STAGE6_CHROMIUM_EXECUTABLE` to its
local executable path. `STAGE6_TEST_PYTHON` can select the Python interpreter
used for the disposable loopback server. The runner performs no installation
or browser download.

Run `python -B tests/run_stage6_local.py --python-only` for the accepted
automated checks while Chromium remains outstanding for isolated staging.

The server copies `app.py`, `business/`, `templates/` and `static/` into a
temporary directory. It replaces the three `/var/data` paths **before** the
first app import, checks the imported paths, supplies synthetic payment details
through the same environment configuration as staging, generates only synthetic records, and
blocks external DNS, HTTP, sockets and SMTP. Browser requests to origins
other than the loopback test server are aborted. Test credentials are generated
per run. The copy and its database/photos are removed when the server exits.

The Python portion runs the existing 27 tests plus local integration tests with
outbound calls blocked. The browser portion drives the real `/app` JavaScript,
records console errors and failed requests, and inspects WhatsApp links without
opening them. A missing local browser is an **incomplete run**, even if the
Python suite passes. No real email, merchant, Google or OpenAI calls are made.

Staging URL checks use a synthetic origin and never open a generated link on
the live website.
The future staging service must set both `APP_ENVIRONMENT` to `staging` and
`PUBLIC_BASE_URL` to its own origin before startup. A missing or live-domain
origin then prevents startup.

"""Run both the regression suite and offline browser checks. No downloads."""

import os
import subprocess
import sys
import unittest
from pathlib import Path

from local_browser_server import block_external_connections


ROOT = Path(__file__).resolve().parents[1]


def main():
    restore = block_external_connections()
    try:
        suite = unittest.TestLoader().discover(str(ROOT / "tests"), pattern="test_*.py")
        outcome = unittest.TextTestRunner(verbosity=1).run(suite)
    finally:
        restore()
    if not outcome.wasSuccessful():
        return 1
    if sys.argv[1:] == ["--python-only"]:
        print("Browser checks deferred to isolated staging", flush=True)
        return 0
    if sys.argv[1:]:
        raise SystemExit("Usage: run_stage6_local.py [--python-only]")
    print("Running offline Playwright browser workflows", flush=True)
    environment = dict(os.environ)
    environment.setdefault("STAGE6_TEST_PYTHON", sys.executable)
    for script in ("run_local_browser.mjs", "run_project_browser.mjs", "run_advice_browser.mjs"):
        result = subprocess.run(["node", str(ROOT / "tests" / script)],
                                cwd=ROOT, env=environment, check=False)
        if result.returncode:
            return result.returncode
    print("Running published project desktop/mobile workflows", flush=True)
    result = subprocess.run(["node", str(ROOT / "tests/run_project_browser.mjs")],
                            cwd=ROOT, env={**environment, "PROJECT_TEST_PUBLISHED": "1"}, check=False)
    if result.returncode:
        return result.returncode
    print("Running advice with isolated staging controls", flush=True)
    result = subprocess.run(["node", str(ROOT / "tests/run_advice_browser.mjs")],
                            cwd=ROOT, env={**environment, "ADVICE_TEST_STAGING": "1"}, check=False)
    if result.returncode:
        return result.returncode
    print("Running published advice desktop/mobile workflows", flush=True)
    result = subprocess.run(["node", str(ROOT / "tests/run_advice_browser.mjs")],
                            cwd=ROOT, env={**environment, "ADVICE_TEST_PUBLISHED": "1"}, check=False)
    if result.returncode:
        return result.returncode
    print("Running Batch 8 mixed-catalogue desktop/mobile proposals", flush=True)
    # The harness owns browser/server cleanup and has a 180-second deadline.
    # This independent parent deadline protects against a stuck Node process.
    process = subprocess.Popen(["node", str(ROOT / "tests/run_batch8_browser.mjs")],
                               cwd=ROOT, env=environment)
    try:
        return process.wait(timeout=210)
    except subprocess.TimeoutExpired:
        print("Batch 8 harness exceeded 210 seconds; requesting owned-process cleanup", flush=True)
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

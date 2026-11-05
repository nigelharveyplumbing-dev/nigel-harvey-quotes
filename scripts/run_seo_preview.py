"""PR48 protected staging: ephemeral data, disabled email, revision header.

Uses the established staging launcher and its review-display fallback. Never
configure production credentials or a persistent disk for this preview.
"""
import os
from pathlib import Path
import runpy
import subprocess
import sys

if os.getenv("APP_ENVIRONMENT") != "staging":
    raise SystemExit("SEO preview requires staging")

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()

# The established launcher imports app only after relocating its storage.
# Add the revision header when it calls uvicorn, after that isolation is ready.
import uvicorn
original_run = uvicorn.run


def run_preview(application, **kwargs):
    @application.middleware("http")
    async def preview_revision(request, call_next):
        response = await call_next(request)
        response.headers["X-Preview-Commit"] = revision
        return response
    return original_run(application, **kwargs)


uvicorn.run = run_preview
runpy.run_path(str(root / "scripts/run_design_preview.py"), run_name="__main__")

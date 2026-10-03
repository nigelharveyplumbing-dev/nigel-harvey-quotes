"""Private, synthetic-only voice intake. No provider credentials or outbound I/O."""
import hashlib
import hmac
import os
import re
import time
from pathlib import Path

INTAKE_PATH = "/integrations/voice/v1/enquiries"
MAX_BODY = 64 * 1024


def enabled():
    return os.getenv("VOICE_ENABLED") == "1"


def settings():
    from business.config import DB_PATH
    if not enabled():
        raise ValueError("Voice integration disabled")
    # A feature flag alone must never enable ingestion against the live DB.
    if os.getenv("APP_ENVIRONMENT") not in {"development", "test"}:
        raise ValueError("Synthetic voice requires development or test")
    root = Path(os.getenv("VOICE_SANDBOX_ROOT", "")).resolve()
    if not os.getenv("VOICE_SANDBOX_ROOT") or root == Path("/"):
        raise ValueError("Explicit sandbox root required")
    if not DB_PATH.resolve().is_relative_to(root) or DB_PATH.resolve().is_relative_to(Path("/var/data")):
        raise ValueError("Voice database must be isolated")
    secret = os.getenv("VOICE_WEBHOOK_SECRET", "")
    if len(secret.encode()) < 32:
        raise ValueError("Voice signing secret must be at least 32 bytes")
    from cryptography.fernet import Fernet
    cipher = Fernet(os.getenv("VOICE_ENCRYPTION_KEY", "").encode())
    return secret, cipher


def signature(secret, body, timestamp, nonce):
    message = b"v1\nPOST\n" + INTAKE_PATH.encode() + b"\n" + str(timestamp).encode() + b"\n" + nonce.encode() + b"\n" + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify(body, headers, now=None):
    secret, _ = settings()
    timestamp = headers.get("x-voice-timestamp", "")
    nonce = headers.get("x-voice-nonce", "")
    supplied = headers.get("x-voice-signature", "")
    if not re.fullmatch(r"[0-9]{10}", timestamp) or not re.fullmatch(r"[A-Za-z0-9_-]{16,80}", nonce):
        raise PermissionError("Invalid voice authentication")
    if abs((time.time() if now is None else now) - int(timestamp)) > 300:
        raise PermissionError("Expired voice authentication")
    if not hmac.compare_digest(signature(secret, body, timestamp, nonce), supplied):
        raise PermissionError("Invalid voice authentication")
    return nonce


def seal(value):
    import json
    return settings()[1].encrypt(json.dumps(value, ensure_ascii=False).encode()).decode()


def unseal(value):
    import json
    return json.loads(settings()[1].decrypt(value.encode())) if value else None

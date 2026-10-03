"""Ephemeral synthetic credentials and signed local requests."""
import json
import secrets
import time
from cryptography.fernet import Fernet


def voice_test_settings():
    return {"VOICE_ENABLED": "1", "VOICE_WEBHOOK_SECRET": secrets.token_hex(32),
            "VOICE_ENCRYPTION_KEY": Fernet.generate_key().decode()}


def signed_post(client, event, secret, *, nonce=None, timestamp=None, body=None, signature=None):
    from business.voice_security import INTAKE_PATH, signature as sign
    body = body if body is not None else event.model_dump_json().encode()
    timestamp = str(int(time.time()) if timestamp is None else timestamp)
    nonce = nonce or secrets.token_hex(16)
    headers = {"Content-Type": "application/json", "X-Voice-Timestamp": timestamp,
               "X-Voice-Nonce": nonce, "X-Voice-Signature": signature or sign(secret, body, timestamp, nonce)}
    return client.post(INTAKE_PATH, content=body, headers=headers)

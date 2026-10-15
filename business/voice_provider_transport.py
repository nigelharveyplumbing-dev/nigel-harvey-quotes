"""Credential-injected Realtime connection factory, closed to paid admission.

No env-file reads, connection or credential access at import/construction time.
The default admission gate always refuses this development-only build. Tests
inject a fictional authority, credential reader and connector under an egress
guard; that test seam is not a live accounting approval mechanism.
"""
import logging

from business.voice_prompts import PILOT_MODEL


class PilotAdmissionBlocked(RuntimeError):
    pass


class ProviderConnectionFailed(RuntimeError):
    pass


class ClosedPilotAdmission:
    def require(self):
        # Do not infer authority from API-key presence, feature flags, matching
        # provider aggregates, a new ledger, or the earlier benchmark allowance.
        # A separately reviewed paid admission/accounting controller is required.
        raise PilotAdmissionBlocked('Pilot disabled: original-journal reconciliation, live budget controller and separate paid-test approval required')


def no_credentials():
    raise PilotAdmissionBlocked('No private-pilot credentials have been configured')


class RealtimeProviderFactory:
    synthetic_only = False

    def __init__(self, *, admission=None, credential_reader=no_credentials, connector=None):
        self.admission = admission if admission is not None else ClosedPilotAdmission()
        self.credential_reader = credential_reader
        self.connector = connector

    async def __call__(self):
        self.admission.require()  # Must precede credential access and ANY I/O.
        try:
            key = self.credential_reader()
            if not isinstance(key, str) or len(key) < 20 or '\r' in key or '\n' in key:
                raise ValueError('Invalid private credential')
            if self.connector is None:
                from websockets.asyncio.client import connect
                connector = connect
            else:
                connector = self.connector
            # Suppress this connection's protocol/handshake debug logging: it
            # could otherwise expose auth headers or caller audio/transcripts.
            logger = logging.Logger('nhp-private-realtime-no-payload-logging')
            logger.disabled = True
            return await connector(
                'wss://api.openai.com/v1/realtime?model=' + PILOT_MODEL,
                additional_headers={'Authorization': 'Bearer ' + key},
                open_timeout=8, close_timeout=3, ping_interval=20,
                max_size=100000, max_queue=8, logger=logger,
            )
        except Exception:
            # Never pass through credential-bearing request/response exceptions.
            raise ProviderConnectionFailed('Private AI transport unavailable; no automatic retry') from None

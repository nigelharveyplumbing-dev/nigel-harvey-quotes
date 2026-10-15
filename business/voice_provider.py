"""Separate Twilio private-pilot ASGI adapter. Never mounted in app.py.

Only the explicitly constructed, fictional-number offline harness is admitted
in this change. Default HTTP/WS admission refuses BEFORE a model factory is
called. Environment flags and API-key presence cannot clear accounting gates.
"""
from dataclasses import dataclass, field, asdict
import hashlib
import hmac
import json
import re
import secrets
import time
from urllib.parse import parse_qsl
from xml.etree.ElementTree import Element, SubElement, tostring

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from starlette.datastructures import FormData

from business.phone_numbers import normalise_uk_phone
from business.voice_pilot_plan import (PilotConfig, PilotState, callback_url,
    ring_twiml, screen_twiml, acceptance_twiml, ai_notice_twiml, media_twiml)
from business.voice_provider_store import CallConflict

SID = re.compile(r'^CA[0-9a-fA-F]{32}$')
MAX_FORM = 16384


def pin_digest(secret, caller, pin):
    return hmac.new(secret.encode(), (caller + '\n' + pin).encode(), hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class ProviderSettings:
    plan: PilotConfig
    account_sid: str
    auth_token: str = field(repr=False)
    pin_hashes: dict = field(repr=False)

    def validate(self):
        self.plan.validate()  # Existing inactive-only, staging-only policy.
        if not re.fullmatch(r'AC[0-9a-fA-F]{32}', self.account_sid) or len(self.auth_token) < 32:
            raise ValueError('Invalid private provider configuration')
        if not self.pin_hashes or any(not normalise_uk_phone(n) or not re.fullmatch(r'[0-9a-f]{64}', v)
                                      for n, v in self.pin_hashes.items()):
            raise ValueError('Caller allowlist and private PIN digests required')


def say(text, hangup=True):
    root = Element('Response')
    SubElement(root, 'Say', {'language': 'en-GB'}).text = text
    if hangup:
        SubElement(root, 'Hangup')
    return tostring(root, encoding='unicode')


def gather(settings, token, route, text, digits):
    root = Element('Response')
    el = SubElement(root, 'Gather', {'input': 'dtmf', 'numDigits': str(digits),
        'timeout': '6', 'actionOnEmptyResult': 'true', 'method': 'POST',
        'action': callback_url(settings.plan, route, 'first', token)})
    SubElement(el, 'Say', {'language': 'en-GB'}).text = text
    SubElement(root, 'Hangup')
    return tostring(root, encoding='unicode')


def create_pilot_app(settings, store, *, synthetic=False, model_factory=None, clock=time.time):
    settings.validate()
    if model_factory is None:
        from business.voice_provider_transport import RealtimeProviderFactory
        model_factory = RealtimeProviderFactory()
    if synthetic:
        # No real-number or real-origin switch masquerades as an offline test.
        phones = [settings.plan.mobile, settings.plan.number, *settings.pin_hashes]
        if (not settings.plan.origin.endswith('.example.invalid') or
                any(not re.fullmatch(r'\+447700900\d{3}', n) for n in phones) or
                not getattr(model_factory, 'synthetic_only', False)):
            raise ValueError('Offline harness requires fictional endpoints and injected synthetic transport')
    from twilio.request_validator import RequestValidator
    validator = RequestValidator(settings.auth_token)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store

    def admitted():
        if not synthetic:
            raise HTTPException(503, 'Private pilot disabled: original-journal and separate paid-approval gates remain blocked')

    def xml(text):
        return Response(text, media_type='application/xml', headers={'Cache-Control': 'no-store'})

    async def signed_form(request):
        admitted()
        if request.headers.get('content-type', '').split(';')[0].strip() != 'application/x-www-form-urlencoded':
            raise HTTPException(415, 'Form webhook required')
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_FORM:
                raise HTTPException(413, 'Webhook too large')
        try:
            pairs = parse_qsl(bytes(raw).decode('utf-8'), keep_blank_values=True, max_num_fields=80, errors='strict')
        except (ValueError, UnicodeError):
            raise HTTPException(400, 'Invalid webhook')
        # Reject ambiguity rather than collapsing duplicate signed parameters.
        if len({k for k, _ in pairs}) != len(pairs):
            raise HTTPException(400, 'Duplicate webhook parameters')
        form = FormData(pairs)
        url = settings.plan.origin.rstrip('/') + request.url.path
        if request.url.query:
            url += '?' + request.url.query
        if not validator.validate(url, form, request.headers.get('x-twilio-signature', '')):
            raise HTTPException(403, 'Webhook authentication rejected')
        if form.get('AccountSid') != settings.account_sid or not SID.fullmatch(form.get('CallSid', '')):
            raise HTTPException(403, 'Webhook account or call rejected')
        return dict(form)

    def callback_notice(token):
        return gather(settings, token, 'callback-number',
                      'Please enter your eleven digit UK callback number. Nigel will review your request; attendance is not guaranteed.', 11)

    @app.get('/health', include_in_schema=False)
    async def health():
        return {'customer_access_enabled': False, 'live_enabled': False,
                'synthetic_harness': synthetic, 'historical_journals_reconciled': False}

    @app.post('/pilot/incoming', include_in_schema=False)
    async def incoming(request: Request):
        form = await signed_form(request)
        if form.get('To') != settings.plan.number or form.get('From') not in settings.pin_hashes:
            return xml(say('This private test number is unavailable.'))
        now, sid = clock(), form['CallSid']
        digest = hashlib.sha256(json.dumps(form, sort_keys=True).encode()).hexdigest()
        with store.transaction() as db:
            existing = db.execute('SELECT * FROM pilot_calls WHERE sid=?', (sid,)).fetchone()
            if existing:
                call = store.unseal(existing['content'])
                if now >= existing['expires'] or call['incoming_digest'] != digest:
                    raise HTTPException(409, 'Expired or conflicting incoming event')
                # A signed replay never rings again or regresses an active call.
                return xml(call['incoming_reply'])
            active = db.execute('SELECT content FROM pilot_calls WHERE expires>?', (now,)).fetchall()
            if any(not store.unseal(row[0]).get('final') for row in active):
                return xml(say('The private test line is busy. Please try again later.'))
            token = secrets.token_urlsafe(24)
            reply = gather(settings, token, 'pin', 'Private plumbing test line. Please enter your six digit test PIN.', 6)
            call = {'sid': sid, 'caller': form['From'], 'controller': asdict(PilotState()),
                    'stage': 'pin', 'pin_attempts': 0, 'final': False, 'started_at': now,
                    'stream_claimed': False, 'incoming_digest': digest, 'incoming_reply': reply}
            db.execute('INSERT INTO pilot_calls VALUES(?,?,?,?)',
                       (sid, hashlib.sha256(token.encode()).hexdigest(), store.seal(call), now + 300))
        return xml(reply)

    @app.post('/pilot/{route}', include_in_schema=False)
    async def webhook(route: str, request: Request):
        form = await signed_form(request)
        query = list(request.query_params.multi_items())
        if len(query) != 2 or set(k for k, _ in query) != {'phase', 'token'}:
            raise HTTPException(400, 'Invalid callback context')
        token, phase = request.query_params['token'], request.query_params['phase']
        if phase != 'first' or not re.fullmatch(r'[A-Za-z0-9_-]{16,80}', token):
            raise HTTPException(400, 'Invalid callback context')
        now = clock()
        try:
            with store.transaction() as db:
                call = store.load(db, token, now)
                child_route = route in {'screen', 'accept'}
                if child_route:
                    if (form.get('ParentCallSid') != call['sid'] or form.get('To') != settings.plan.mobile
                            or form.get('From') != settings.plan.number):
                        raise CallConflict('Child call correlation rejected')
                elif form['CallSid'] != call['sid']:
                    raise CallConflict('Parent call correlation rejected')
                cache_key = hashlib.sha256((call['sid'] + '\n' + route + '\n' + phase).encode()).hexdigest()
                digest = hashlib.sha256(json.dumps(form, sort_keys=True).encode()).hexdigest()
                cached = db.execute('SELECT * FROM pilot_webhooks WHERE event_key=?', (cache_key,)).fetchone()
                # PIN attempts have a separate bounded counter; all other callback
                # results are immutable and safely replayed on provider retry.
                if cached and (route != 'pin' or cached['digest'] == digest):
                    if cached['digest'] != digest:
                        raise CallConflict('Conflicting callback retry')
                    return xml(store.unseal(cached['reply']))
                state = PilotState(**call['controller'])
                if call.get('final') and route not in {'stream-ended', 'callback-number'}:
                    raise CallConflict('Final call cannot be reopened')
                if route == 'pin':
                    if call['stage'] != 'pin':
                        if cached and cached['digest'] == digest:
                            return xml(store.unseal(cached['reply']))
                        raise CallConflict('PIN stage already consumed')
                    caller_hash = hashlib.sha256(call['caller'].encode()).hexdigest()
                    attempt = db.execute('SELECT * FROM pilot_attempts WHERE caller_hash=?', (caller_hash,)).fetchone()
                    count = attempt['count'] if attempt and now - attempt['started'] < 600 else 0
                    call['pin_attempts'] += 1
                    db.execute('INSERT INTO pilot_attempts VALUES(?,?,?) ON CONFLICT(caller_hash) DO UPDATE SET count=excluded.count,started=excluded.started',
                               (caller_hash, count + 1, attempt['started'] if count else now))
                    digit = form.get('Digits', '')
                    valid = re.fullmatch(r'\d{6}', digit) and hmac.compare_digest(
                        pin_digest(settings.auth_token, call['caller'], digit), settings.pin_hashes[call['caller']])
                    if count >= 10 or call['pin_attempts'] > 3 or not valid:
                        if call['pin_attempts'] >= 3 or count >= 10:
                            call['final'] = True
                            reply = say('Private test access denied.')
                        else:
                            reply = gather(settings, token, 'pin', 'PIN not accepted. Enter your six digit test PIN.', 6)
                    else:
                        state.start(allowlisted=True, pin_verified=True, leg='pending-first', now=now)
                        call['stage'] = 'ring'
                        reply = ring_twiml(settings.plan, token=token)
                elif route == 'screen':
                    if call['stage'] != 'ring' or state.leg not in {'pending-first', form['CallSid']} or now >= state.deadline:
                        raise CallConflict('Unrelated or late child leg')
                    state.leg = form['CallSid']
                    reply = screen_twiml(settings.plan, token=token)
                elif route == 'accept':
                    accepted = state.accept(leg=form['CallSid'], digit=form.get('Digits', ''), now=now) == 'authorise_bridge'
                    reply = acceptance_twiml(accepted)
                elif route == 'dial-finished':
                    if call['stage'] != 'ring' or form.get('DialCallStatus') not in {'completed', 'busy', 'failed', 'no-answer', 'canceled'}:
                        raise CallConflict('Unexpected dial completion')
                    leg = form.get('DialCallSid', '')
                    if state.leg != 'pending-first' and leg != state.leg:
                        raise CallConflict('Dial leg mismatch')
                    if form.get('DialBridged') == 'true' and state.state == 'bridge_pending':
                        state.bridge_verified(leg=leg)
                    decision = state.dial_finished(leg=state.leg)
                    if decision == 'hangup':
                        call.update(final=True, stage='human_finished')
                        reply = '<Response><Hangup /></Response>'
                    else:
                        call['stage'] = 'notice'
                        reply = ai_notice_twiml(settings.plan, token=token)
                elif route == 'ai-choice':
                    if call['stage'] != 'notice':
                        raise CallConflict('AI notice must precede stream choice')
                    if form.get('Digits', '') not in {'', '1'}:
                        state.non_ai_callback()
                        call.update(stage='callback', callback=True)
                        reply = callback_notice(token)
                    else:
                        call['stage'] = 'media_ready'
                        reply = media_twiml(settings.plan, token=token)
                elif route == 'callback-number':
                    if not call.get('callback'):
                        raise CallConflict('Callback not requested')
                    number = normalise_uk_phone(form.get('Digits', ''))
                    facts = {'callback_phone': number or '', 'callback_confirmed': bool(number)}
                    store.queue(db, call, facts, 'non_ai_callback', now)
                    call.update(final=True, stage='callback_saved')
                    reply = say('Your callback request has been saved for Nigel to review. No appointment is confirmed.')
                elif route == 'stream-ended':
                    if call.get('guidance'):
                        reply = say(call['guidance'])
                    elif call.get('callback'):
                        reply = callback_notice(token)
                    else:
                        if not call.get('final'):
                            store.queue(db, call, {}, 'interrupted', now)
                            call.update(final=True, stage='interrupted')
                        reply = say('Your enquiry is waiting for Nigel to review. Attendance is not guaranteed.')
                else:
                    raise CallConflict('Unknown private callback')
                call['controller'] = asdict(state)
                store.save(db, call)
                db.execute('INSERT INTO pilot_webhooks VALUES(?,?,?) ON CONFLICT(event_key) DO UPDATE SET digest=excluded.digest,reply=excluded.reply',
                           (cache_key, digest, store.seal(reply)))
                return xml(reply)
        except CallConflict:
            raise HTTPException(409, 'Call state or correlation rejected')

    @app.websocket('/pilot/media')
    async def media(websocket: WebSocket):
        # Validate a fixed public origin, never an attacker-controlled Host or
        # X-Forwarded-* value. No signature bypass for HTTP or WebSocket tests.
        if not synthetic:
            await websocket.close(code=1008)
            return
        url = settings.plan.origin.rstrip('/') + '/pilot/media'
        signature = websocket.headers.get('x-twilio-signature', '')
        if websocket.url.query or not any(validator.validate(u, {}, signature) for u in (url, url.replace('https:', 'wss:', 1))):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        from business.voice_provider_media import run_media
        await run_media(websocket, settings, store, model_factory, clock)

    return app

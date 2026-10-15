"""Bounded Twilio PCMU <-> connected Realtime socket protocol adapter.

The socket is injected; this module neither reads API keys nor opens provider
connections. Default app admission is disabled. No audio is written to disk.
"""
import asyncio
import base64
import json
import re

from business.voice_models import VoiceFacts
from business.voice_contacts import normalise_postcode
from business.phone_numbers import normalise_uk_phone
from business.voice_policy import service_scope, triage
from business.voice_prompts import RECEPTIONIST_PROMPT, PILOT_MODEL, MAX_OUTPUT_TOKENS, NORMAL_WORD_LIMIT
from business.voice_provider_store import CallConflict

MAX_EVENT = 20000
MAX_AUDIO = 240000  # 30 seconds at 8 kHz PCMU; memory only.
MAX_RESPONSES = 12


class ProtocolStop(ValueError):
    pass


def session_config():
    # Same frozen receptionist instructions/model/cap as the inactive pilot.
    # Automatic responses are disabled: application owns every response request.
    from business.voice_models import VoiceFacts
    schema = VoiceFacts.model_json_schema()
    return {'type': 'realtime', 'model': PILOT_MODEL, 'instructions': RECEPTIONIST_PROMPT,
            'max_output_tokens': MAX_OUTPUT_TOKENS, 'output_modalities': ['audio'],
            'reasoning': {'effort': 'low'}, 'truncation': 'disabled',
            'tools': [{'type': 'function', 'name': 'capture_enquiry',
                       'description': 'Capture heard caller facts for Nigel to review. Never book or accept gas work.',
                       'parameters': schema}], 'tool_choice': 'auto',
            'audio': {'input': {'format': {'type': 'audio/pcmu'},
                'transcription': {'model': 'gpt-4o-mini-transcribe'},
                'turn_detection': {'type': 'server_vad', 'threshold': 0.5,
                    'prefix_padding_ms': 300, 'silence_duration_ms': 500,
                    'create_response': False, 'interrupt_response': False}},
                'output': {'format': {'type': 'audio/pcmu'}, 'voice': 'marin'}}}


async def packet(ws):
    raw = await asyncio.wait_for(ws.receive_text(), timeout=25)
    if len(raw.encode()) > MAX_EVENT:
        raise ProtocolStop('Oversized stream packet')
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ProtocolStop('Invalid stream packet')
    return value


def audio_bytes(payload):
    if not isinstance(payload, str) or len(payload) > 12000:
        raise ProtocolStop('Oversized audio frame')
    value = base64.b64decode(payload, validate=True)
    if not value or len(value) > 8000 or value.startswith((b'RIFF', b'OggS')):
        raise ProtocolStop('Invalid raw PCMU frame')
    return value


def validate_usage(value):
    # Preserve complete, partial and cancelled usage without pretending this
    # private protocol receipt is an original spending journal or billing audit.
    if not isinstance(value, dict):
        raise ProtocolStop('Missing provider usage')
    for total, details in (('input_tokens', 'input_token_details'), ('output_tokens', 'output_token_details')):
        data = value.get(details)
        if not isinstance(data, dict):
            raise ProtocolStop('Incomplete provider usage')
        values = [data.get('text_tokens'), data.get('audio_tokens')]
        if any(type(v) is not int or v < 0 for v in values) or value.get(total) != sum(values):
            raise ProtocolStop('Unrecognised provider usage')
        if data.get('image_tokens', 0):
            raise ProtocolStop('Unexpected usage modality')
    incoming = value['input_token_details']
    cached = incoming.get('cached_tokens_details', {})
    if not isinstance(cached, dict):
        raise ProtocolStop('Unknown cached usage')
    counts = [cached.get('text_tokens', 0), cached.get('audio_tokens', 0)]
    if (any(type(n) is not int or n < 0 for n in counts) or
        counts[0] > incoming['text_tokens'] or counts[1] > incoming['audio_tokens'] or
        incoming.get('cached_tokens', 0) != sum(counts)):
        raise ProtocolStop('Unknown cached usage')
    return value


class MediaBridge:
    def __init__(self, ws, model, settings, store, call, token, stream, clock):
        self.ws, self.model, self.settings, self.store = ws, model, settings, store
        self.call, self.token, self.stream, self.clock = call, token, stream, clock
        self.done, self.ready = asyncio.Event(), False
        self.configuration_ready = asyncio.Event()
        self.pending, self.active, self.count = False, None, 0
        self.last_sequence, self.last_timestamp = 1, 0
        self.facts = VoiceFacts().model_dump()
        self.caller_text, self.transcripts, self.function_calls = '', {}, set()
        self.need_response, self.captured = False, False
        self.playback, self.marks = None, {}
        self.outcome, self.usage_uncertain = 'incomplete', False

    async def send_model(self, value):
        await asyncio.wait_for(self.model.send(json.dumps(value)), timeout=5)

    async def send_twilio(self, value):
        await asyncio.wait_for(self.ws.send_json({'streamSid': self.stream, **value}), timeout=5)

    async def request_response(self):
        if not self.ready or not self.need_response or self.pending or self.active:
            return
        if self.count >= MAX_RESPONSES:
            self.outcome = 'response_limit'
            self.done.set()
            return
        # In the admitted harness, this is a synthetic response. A live connector
        # is deliberately not supplied by this development-only implementation.
        self.count += 1
        with self.store.transaction() as db:
            db.execute("INSERT INTO pilot_response_requests VALUES(?,?,'intent',NULL)", (self.call['sid'], self.count))
        self.pending, self.need_response = True, False
        await self.send_model({'type': 'response.create', 'response': {'max_output_tokens': MAX_OUTPUT_TOKENS}})

    async def interrupt(self):
        if self.active:
            self.active['discarded'] = True
            self.active['audio'].clear()
            await self.send_model({'type': 'response.cancel'})
        previous = self.playback
        if previous and self.marks:
            # Marks returned after clear acknowledge discarded audio, not heard
            # audio. Invalidate them BEFORE clear and truncate conservatively to
            # the last already acknowledged chunk boundary, never wall-clock time.
            self.marks.clear()
            await self.send_twilio({'event': 'clear'})
            await self.send_model({'type': 'conversation.item.truncate',
                'item_id': previous['item'], 'content_index': 0,
                'audio_end_ms': previous['ack_ms']})
        self.playback = None

    async def caller(self):
        await asyncio.wait_for(self.configuration_ready.wait(), timeout=5)
        while not self.done.is_set():
            event = await packet(self.ws)
            if event.get('streamSid') != self.stream:
                raise ProtocolStop('Cross-stream packet')
            seq = event.get('sequenceNumber', '')
            if not isinstance(seq, str) or not seq.isdecimal() or int(seq) != self.last_sequence + 1:
                raise ProtocolStop('Reordered stream packet')
            self.last_sequence = int(seq)
            kind = event.get('event')
            if kind == 'media':
                media = event['media']
                if media.get('track') != 'inbound':
                    raise ProtocolStop('Unexpected audio track')
                stamp = int(media['timestamp'])
                if stamp < self.last_timestamp:
                    raise ProtocolStop('Reordered audio timestamp')
                self.last_timestamp = stamp
                raw = audio_bytes(media.get('payload'))
                if not self.ready:
                    raise ProtocolStop('Audio before model configuration acknowledgement')
                await self.send_model({'type': 'input_audio_buffer.append', 'audio': base64.b64encode(raw).decode()})
            elif kind == 'mark':
                name = event.get('mark', {}).get('name')
                if name in self.marks:
                    end = self.marks.pop(name)
                    self.playback['ack_ms'] = max(end, self.playback['ack_ms'])
                if self.captured and not self.marks and not self.active and not self.pending:
                    self.done.set()
            elif kind == 'dtmf':
                if event.get('dtmf', {}).get('digit') == '0':
                    await self.non_ai_callback()
            elif kind == 'stop':
                stop = event.get('stop', {})
                if stop.get('callSid') != self.call['sid'] or stop.get('accountSid') != self.settings.account_sid:
                    raise ProtocolStop('Stop correlation mismatch')
                self.done.set()
            else:
                raise ProtocolStop('Unexpected stream event')

    async def non_ai_callback(self):
        await self.interrupt()
        with self.store.transaction() as db:
            call = self.store.load(db, self.token, self.clock())
            call['callback'] = True
            self.store.save(db, call)
        self.outcome = 'non_ai_callback'
        self.done.set()

    async def heard(self, event):
        text, item = event.get('transcript', ''), event.get('item_id', '')
        if not isinstance(text, str) or not item or len(text) > 4000:
            raise ProtocolStop('Invalid caller transcript')
        if item in self.transcripts:
            if self.transcripts[item] != text:
                raise ProtocolStop('Conflicting caller transcript')
            return
        self.transcripts[item] = text
        if len(self.transcripts) > 50 or len(self.caller_text) + len(text) > 16000:
            raise ProtocolStop('Call transcript bound reached')
        self.caller_text += '\n' + text
        if re.search(r'non[- ]?ai|no (?:ai|robot)|human callback|(?:do not|don.t) want.{0,15}(?:ai|robot)', text, re.I):
            await self.non_ai_callback()
            return
        urgency, guidance, _ = triage(self.caller_text)
        scope = service_scope(self.caller_text)
        if guidance and scope != 'appliance_clarification_required':
            await self.interrupt()
            self.facts.update(urgency=urgency, description=text)
            with self.store.transaction() as db:
                call = self.store.load(db, self.token, self.clock())
                call['guidance'] = guidance
                self.store.save(db, call)
            self.outcome = 'safety_redirect' if urgency in {'gas_co', 'electrical_water', 'urgent'} else 'unsupported_gas_work'
            self.done.set()
            return
        self.need_response = True
        await self.request_response()

    def receipt(self, event):
        response = event['response']
        if not self.active or response.get('id') != self.active['id']:
            raise ProtocolStop('Usage for an untracked response')
        usage = validate_usage(response.get('usage'))
        with self.store.transaction() as db:
            db.execute('INSERT INTO pilot_usage VALUES(?,?,?)', (self.call['sid'], response['id'],
                self.store.seal({'status': response.get('status'), 'usage': usage,
                                 'synthetic': True, 'not_a_spending_journal': True})))
            updated = db.execute("UPDATE pilot_response_requests SET state='settled' WHERE sid=? AND response_id=? AND state='in_flight'",
                                 (self.call['sid'], response['id'])).rowcount
            if updated != 1:
                raise ProtocolStop('Response intent settlement mismatch')

    async def receive_model(self):
        while not self.done.is_set():
            raw = await asyncio.wait_for(self.model.recv(), timeout=25)
            if not isinstance(raw, str) or len(raw.encode()) > 100000:
                raise ProtocolStop('Invalid model event size')
            event = json.loads(raw)
            kind = event.get('type')
            if kind == 'error':
                raise ProtocolStop('Provider failure; no automatic retry')
            if kind == 'session.updated':
                config = event['session']
                wanted = session_config()
                if any(config.get(k) != wanted[k] for k in wanted):
                    raise ProtocolStop('Unconfirmed model settings')
                self.ready = True
                self.configuration_ready.set()
            elif kind == 'input_audio_buffer.speech_started':
                await self.interrupt()
            elif kind == 'conversation.item.input_audio_transcription.completed':
                await self.heard(event)
            elif kind == 'conversation.item.input_audio_transcription.failed':
                raise ProtocolStop('Caller transcription failed')
            elif kind == 'response.created':
                if not self.pending or self.active:
                    self.usage_uncertain = True
                    raise ProtocolStop('Unrequested provider response')
                self.pending = False
                with self.store.transaction() as db:
                    changed = db.execute("UPDATE pilot_response_requests SET state='in_flight',response_id=? WHERE sid=? AND ordinal=? AND state='intent'",
                                         (event['response']['id'], self.call['sid'], self.count)).rowcount
                    if changed != 1:
                        raise ProtocolStop('Missing durable response intent')
                self.active = {'id': event['response']['id'], 'item': '', 'audio': bytearray(),
                               'text': '', 'discarded': False, 'tools': {}}
            elif kind == 'response.output_item.added':
                self.response_match(event)
                if event['item'].get('type') == 'message':
                    if self.active['item']:
                        raise ProtocolStop('Unexpected second speech item')
                    self.active['item'] = event['item']['id']
                elif event['item'].get('type') == 'function_call':
                    item = event['item']
                    if not item.get('call_id') or item['call_id'] in self.active['tools']:
                        raise ProtocolStop('Duplicate or missing tool identity')
                    self.active['tools'][item['call_id']] = item.get('name')
            elif kind == 'response.output_audio.delta':
                self.response_match(event)
                value = base64.b64decode(event['delta'], validate=True)
                if len(value) > MAX_AUDIO or len(self.active['audio']) + len(value) > MAX_AUDIO:
                    raise ProtocolStop('Model audio buffer bound reached')
                if not self.active['discarded']:
                    self.active['audio'].extend(value)
            elif kind == 'response.output_audio_transcript.done':
                self.response_match(event)
                self.active['text'] = event.get('transcript', '')
            elif kind == 'response.function_call_arguments.done':
                self.response_match(event)
                name = self.active['tools'].get(event.get('call_id'))
                if (name != 'capture_enquiry' or event.get('name', name) != name
                        or event.get('call_id') in self.function_calls):
                    raise ProtocolStop('Unexpected or replayed model tool')
                self.function_calls.add(event['call_id'])
                facts = VoiceFacts.model_validate_json(event['arguments']).model_dump()
                if facts['appointment_confirmed'] or service_scope(self.caller_text + ' ' + facts['description']) != 'plumbing':
                    raise ProtocolStop('Unsafe enquiry extraction')
                facts['name_confirmed'] = facts['callback_confirmed'] = False
                facts['urgency'] = triage(self.caller_text)[0]
                facts['callback_phone'] = normalise_uk_phone(facts['callback_phone']) or ''
                facts['postcode'] = normalise_postcode(facts['postcode']) or ''
                self.facts, self.captured = facts, True
            elif kind == 'response.done':
                self.receipt(event)
                active, self.active = self.active, None
                status = event['response'].get('status')
                if status not in {'completed', 'incomplete', 'cancelled', 'failed'}:
                    raise ProtocolStop('Unknown provider response status')
                if status != 'completed' and not active['discarded']:
                    raise ProtocolStop('Incomplete provider response; no retry')
                if not active['discarded'] and active['audio']:
                    text = active['text']
                    if (not active['item'] or not isinstance(text, str) or not text or len(text.split()) > NORMAL_WORD_LIMIT or
                        re.search(r'(?:appointment|booking).{0,30}(?:confirmed|booked)|(?:will|definitely|guarantee).{0,25}(?:attend|come|arrive)|(?:Nigel|we|I).{0,20}(?:service|repair|install).{0,15}gas', text, re.I)):
                        raise ProtocolStop('Spoken response held for safety review')
                    self.playback = {'item': active['item'], 'ack_ms': 0}
                    for offset in range(0, len(active['audio']), 8000):
                        chunk = active['audio'][offset:offset + 8000]
                        name = active['id'] + ':' + str(offset)
                        self.marks[name] = (offset + len(chunk)) // 8
                        await self.send_twilio({'event': 'media', 'media': {'payload': base64.b64encode(chunk).decode()}})
                        await self.send_twilio({'event': 'mark', 'mark': {'name': name}})
                if self.captured:
                    required = ('name', 'callback_phone', 'postcode', 'description')
                    self.outcome = 'completed' if all(self.facts[k] for k in required) else 'incomplete'
                    if not self.marks:
                        self.done.set()
                else:
                    await self.request_response()

    def response_match(self, event):
        if not self.active or event.get('response_id') != self.active['id']:
            raise ProtocolStop('Cross-response model event')

    async def run(self):
        tasks = []
        try:
            await self.send_model({'type': 'session.update', 'session': session_config()})
            tasks = [asyncio.create_task(self.caller()), asyncio.create_task(self.receive_model()), asyncio.create_task(self.done.wait())]
            completed, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in completed:
                task.result()
        finally:
            if self.pending or self.active:
                self.usage_uncertain = True
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


async def run_media(ws, settings, store, model_factory, clock):
    token, bridge, model = None, None, None
    owned = False
    outcome = 'interrupted'
    try:
        connected = await packet(ws)
        if connected != {'event': 'connected', 'protocol': 'Call', 'version': '1.0.0'}:
            raise ProtocolStop('Unexpected stream protocol')
        event = await packet(ws)
        start = event.get('start', {})
        token = start.get('customParameters', {}).get('context', '')
        stream = event.get('streamSid', '')
        if (not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,80}', token) or
            event.get('event') != 'start' or event.get('sequenceNumber') != '1' or
            not re.fullmatch(r'MZ[0-9a-fA-F]{32}', stream) or start.get('streamSid') != stream or
            start.get('accountSid') != settings.account_sid or start.get('tracks') != ['inbound'] or
            start.get('mediaFormat') != {'encoding': 'audio/x-mulaw', 'sampleRate': 8000, 'channels': 1}):
            raise ProtocolStop('Stream identity or codec rejected')
        with store.transaction() as db:
            call = store.load(db, token, clock())
            if call['sid'] != start.get('callSid') or call['stage'] != 'media_ready' or call.get('stream_claimed') or call.get('final'):
                raise ProtocolStop('Stream replay or call correlation rejected')
            call.update(stream_claimed=True, stage='streaming')
            store.save(db, call)  # Claim BEFORE opening the injected transport.
        owned = True
        model = await model_factory()
        bridge = MediaBridge(ws, model, settings, store, call, token, stream, clock)
        await asyncio.wait_for(bridge.run(), timeout=max(.01, min(270, 300 - (clock() - (call.get('started_at', clock()))))))
        outcome = bridge.outcome
    except (Exception, asyncio.CancelledError):
        # Never echo provider exceptions, transcripts, signatures or credentials.
        outcome = 'interrupted'
    finally:
        close_failed = False
        if model is not None:
            try:
                await asyncio.wait_for(model.close(), timeout=3)
            except Exception:
                close_failed = True
        if token and bridge:
            with store.transaction() as db:
                row = db.execute('SELECT content FROM pilot_calls WHERE sid=?', (bridge.call['sid'],)).fetchone()
                call = store.unseal(row[0])
                call['usage_uncertain'] = bridge.usage_uncertain or close_failed
                store.save(db, call)
            store.finish(token, bridge.facts, outcome, clock())
        elif owned and token and model is None:
            # Only an authenticated, claimed context may generate a failure item.
            with store.transaction() as db:
                try:
                    call = store.load(db, token, clock())
                except CallConflict:
                    call = None
                if call and call.get('stage') == 'streaming' and call.get('stream_claimed'):
                    call['usage_uncertain'] = True
                    store.queue(db, call, {}, 'interrupted', clock())
                    call['final'] = True
                    store.save(db, call)
        try:
            await ws.close(code=1000 if outcome in {'completed', 'non_ai_callback', 'safety_redirect', 'unsupported_gas_work'} else 1011)
        except Exception:
            pass

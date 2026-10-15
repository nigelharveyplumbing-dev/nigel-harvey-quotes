"""Signed ASGI + real WebSocket frames; synthetic transport, no provider I/O."""
import asyncio
import base64
import json
import os
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit, parse_qs, urlencode
from xml.etree import ElementTree as ET
from unittest.mock import patch

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from twilio.request_validator import RequestValidator

from business.voice_pilot_plan import PilotConfig
from business.voice_provider import ProviderSettings, create_pilot_app, pin_digest
from business.voice_provider_store import PilotStore
from business.voice_provider_media import MediaBridge, session_config
from business.voice_policy import GAS_GUIDANCE, GAS_WORK_GUIDANCE, ELECTRICAL_GUIDANCE
from business.voice_provider_transport import RealtimeProviderFactory, PilotAdmissionBlocked, ProviderConnectionFailed

ACCOUNT = 'AC' + '0' * 32
ROOT = 'CA' + '1' * 32
CHILD = 'CA' + '2' * 32
OTHER = 'CA' + '3' * 32
STREAM = 'MZ' + '4' * 32
CALLER = '+447700900125'
ORIGIN = 'https://voice-pilot.example.invalid'
TOKEN = 'synthetic-twilio-signing-secret-not-live'
USAGE = {'input_tokens': 3, 'output_tokens': 3,
         'input_token_details': {'text_tokens': 1, 'audio_tokens': 2},
         'output_token_details': {'text_tokens': 1, 'audio_tokens': 2}}
FACTS = {'name': 'Alex Example', 'callback_phone': '07700900125',
         'postcode': 'GU1 1AA', 'description': 'Kitchen tap dripping',
         'appointment_confirmed': False}


class ModelFactory:
    synthetic_only = True

    def __init__(self, **options):
        self.options, self.calls, self.model = options, 0, None

    async def __call__(self):
        self.calls += 1
        if self.options.get('connect_failure'):
            raise RuntimeError('Synthetic connect failure; no credentials')
        self.model = SyntheticModel(**self.options)
        return self.model


class SyntheticModel:
    def __init__(self, **options):
        self.options, self.events, self.sent, self.closed = options, asyncio.Queue(), [], False
        self.frames = 0

    async def emit(self, **event):
        await self.events.put(json.dumps(event))

    async def send(self, raw):
        event = json.loads(raw)
        self.sent.append(event)
        kind = event['type']
        if kind == 'session.update':
            config = event['session']
            if self.options.get('bad_config'):
                config['audio']['input']['turn_detection']['create_response'] = True
            await self.emit(type='session.updated', session=config)
            if self.options.get('automatic_response'):
                await self.emit(type='response.created', response={'id': 'unrequested'})
        elif kind == 'input_audio_buffer.append':
            self.frames += 1
            if self.frames == 1:
                await self.emit(type='conversation.item.input_audio_transcription.completed', item_id='caller1',
                    transcript=self.options.get('caller_text', 'My name is Alex Example. My number is 07700 900125, postcode GU1 1AA. My kitchen tap is dripping.'))
            elif self.frames == 2 and self.options.get('interrupt_second'):
                await self.emit(type='input_audio_buffer.speech_started')
        elif kind == 'response.create':
            await self.emit(type='response.created', response={'id': 'response1'})
            if self.options.get('provider_error'):
                await self.emit(type='error', error={'message': 'Synthetic private error must not be echoed'})
                return
            await self.emit(type='response.output_item.added', response_id='response1', item={'type': 'message', 'id': 'message1'})
            await self.emit(type='response.output_audio.delta', response_id='response1', delta=base64.b64encode(b'\xff' * 160).decode())
            await self.emit(type='response.output_audio_transcript.done', response_id='response1',
                transcript=self.options.get('spoken_text', 'Thank you. Nigel will review your enquiry before confirming anything.'))
            if not self.options.get('no_capture'):
                await self.emit(type='response.output_item.added', response_id='response1',
                    item={'type':'function_call','id':'tool_item1','name':self.options.get('tool','capture_enquiry'),'call_id':'tool1'})
                await self.emit(type='response.function_call_arguments.done', response_id='response1',
                    call_id='tool1',
                    arguments=json.dumps({**FACTS, **self.options.get('facts', {})}))
            await self.emit(type='response.done', response={'id': 'response1',
                'status': self.options.get('status', 'completed'),
                'usage': None if self.options.get('missing_usage') else USAGE})

    async def recv(self):
        return await self.events.get()

    async def close(self):
        self.closed = True


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='nhp-private-provider-')
        self.now = 1000.0
        self.settings = ProviderSettings(PilotConfig(ORIGIN, '+447700900123', '+447700900124'),
            ACCOUNT, TOKEN, {CALLER: pin_digest(TOKEN, CALLER, '123456')})
        self.key = Fernet.generate_key()
        self.store = PilotStore(Path(self.tmp.name) / 'private', self.key)
        self.factory = ModelFactory()
        self.build()

    def build(self, synthetic=True):
        self.app = create_pilot_app(self.settings, self.store, synthetic=synthetic,
                                    model_factory=self.factory, clock=lambda: self.now)
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def post(self, path, **fields):
        if path.startswith('https://'):
            split = urlsplit(path)
            path = split.path + ('?' + split.query if split.query else '')
        data = {'AccountSid': ACCOUNT, 'CallSid': ROOT, **fields}
        signature = RequestValidator(TOKEN).compute_signature(ORIGIN + path, data)
        return self.client.post(path, data=data, headers={'x-twilio-signature': signature})

    def action(self, response, noun='Gather'):
        self.assertEqual(response.status_code, 200, response.text)
        return ET.fromstring(response.text).find(noun).attrib['action']

    def incoming(self, **overrides):
        response = self.post('/pilot/incoming', From=CALLER, To=self.settings.plan.number, **overrides)
        self.pin_url = self.action(response)
        self.token = parse_qs(urlsplit(self.pin_url).query)['token'][0]
        return response

    def ring(self):
        self.incoming()
        response = self.post(self.pin_url, Digits='123456')
        root = ET.fromstring(response.text)
        self.dial_url = root.find('Dial').attrib['action']
        self.screen_url = root.find('Dial/Number').attrib['url']
        return response

    def ready(self):
        self.ring()
        response = self.post(self.dial_url, DialCallStatus='no-answer', DialCallSid=CHILD)
        self.choice_url = self.action(response)
        response = self.post(self.choice_url, Digits='')
        self.redirect_url = ET.fromstring(response.text).find('Redirect').text
        self.assertIsNotNone(ET.fromstring(response.text).find('Connect/Stream'))
        return response

    def state(self):
        with self.store.transaction() as db:
            return self.store.load(db, self.token, self.now)

    def records(self):
        with self.store.transaction() as db:
            return [self.store.unseal(r[0]) for r in db.execute('SELECT content FROM pilot_enquiries')]

    def handshake(self, ws, **changes):
        ws.send_json({'event': 'connected', 'protocol': 'Call', 'version': '1.0.0'})
        start = {'accountSid': ACCOUNT, 'callSid': ROOT, 'streamSid': STREAM,
                 'tracks': ['inbound'], 'mediaFormat': {'encoding': 'audio/x-mulaw', 'sampleRate': 8000, 'channels': 1},
                 'customParameters': {'context': self.token}, **changes}
        ws.send_json({'event': 'start', 'sequenceNumber': '1', 'streamSid': STREAM, 'start': start})

    def ws(self):
        sig = RequestValidator(TOKEN).compute_signature(ORIGIN + '/pilot/media', {})
        return self.client.websocket_connect('/pilot/media', headers={'x-twilio-signature': sig})

    def audio(self, ws, seq=2, payload=None, stream=STREAM):
        ws.send_json({'event': 'media', 'sequenceNumber': str(seq), 'streamSid': stream,
            'media': {'track': 'inbound', 'timestamp': '0',
                      'payload': payload or base64.b64encode(b'\xff' * 160).decode()}})

    def test_default_app_refuses_before_signature_or_model_even_with_flags(self):
        self.build(synthetic=False)
        with patch.dict(os.environ, {'VOICE_PILOT_ENABLED': '1', 'VOICE_API_TEST_ENABLED': '1', 'OPENAI_API_KEY': 'synthetic-not-a-key'}):
            self.assertEqual(self.post('/pilot/incoming', From=CALLER, To=self.settings.plan.number).status_code, 503)
        self.assertEqual(self.factory.calls, 0)
        with self.assertRaises(WebSocketDisconnect):
            with self.ws():
                pass
        self.assertFalse(self.client.get('/health').json()['live_enabled'])

    def test_offline_harness_refuses_real_numbers_or_real_origin(self):
        bad = ProviderSettings(PilotConfig('https://staging.example.com', '+447700900123', '+447700900124'), ACCOUNT, TOKEN, self.settings.pin_hashes)
        with self.assertRaises(ValueError):
            create_pilot_app(bad, self.store, synthetic=True, model_factory=self.factory)

    def test_missing_forged_and_host_spoofed_signature_rejected(self):
        data = {'AccountSid': ACCOUNT, 'CallSid': ROOT, 'From': CALLER, 'To': self.settings.plan.number}
        for headers in ({}, {'x-twilio-signature': 'forged'},
                        {'x-twilio-signature': RequestValidator(TOKEN).compute_signature('https://attacker.invalid/pilot/incoming', data), 'host': 'attacker.invalid', 'x-forwarded-host': 'attacker.invalid'}):
            with self.subTest(headers=bool(headers)):
                self.assertEqual(self.client.post('/pilot/incoming', data=data, headers=headers).status_code, 403)
        self.assertEqual(self.factory.calls, 0)

    def test_unknown_signed_parameters_are_validated_not_ignored(self):
        response = self.post('/pilot/incoming', From=CALLER, To=self.settings.plan.number, FutureProviderField='value')
        self.assertEqual(response.status_code, 200)
        self.assertIn('PIN', response.text)

    def test_account_mismatch_and_duplicate_fields_rejected(self):
        self.assertEqual(self.post('/pilot/incoming', AccountSid='AC'+'9'*32, From=CALLER, To=self.settings.plan.number).status_code, 403)
        response = self.client.post('/pilot/incoming', content='CallSid=a&CallSid=b', headers={'content-type': 'application/x-www-form-urlencoded'})
        self.assertEqual(response.status_code, 400)

    def test_allowlist_pin_and_mobile_first_no_recording(self):
        self.ring()
        self.assertEqual(self.state()['stage'], 'ring')
        self.assertEqual(self.factory.calls, 0)
        self.assertEqual(self.state()['controller']['state'], 'first_ring')

    def test_pin_retry_is_idempotent_and_three_distinct_failures_lock(self):
        self.incoming()
        first = self.post(self.pin_url, Digits='111111')
        self.assertEqual(self.post(self.pin_url, Digits='111111').text, first.text)
        self.assertEqual(self.state()['pin_attempts'], 1)
        self.post(self.pin_url, Digits='222222')
        third = self.post(self.pin_url, Digits='333333')
        self.assertIn('denied', third.text)
        self.assertTrue(self.state()['final'])
        self.assertEqual(self.factory.calls, 0)

    def test_private_call_admission_is_single_flight(self):
        self.incoming()
        reply = self.post('/pilot/incoming', CallSid=OTHER, From=CALLER, To=self.settings.plan.number)
        self.assertIn('busy', reply.text)
        self.assertEqual(self.factory.calls, 0)

    def test_concurrent_admission_has_only_one_active_root_call(self):
        def incoming(index):
            return self.post('/pilot/incoming',CallSid='CA'+format(index,'032x'),
                             From=CALLER,To=self.settings.plan.number).text
        with ThreadPoolExecutor(max_workers=4) as pool:
            replies=list(pool.map(incoming,range(10,18)))
        self.assertEqual(sum('six digit test PIN' in reply for reply in replies),1)
        self.assertEqual(sum('busy' in reply for reply in replies),7)
        self.assertEqual(self.factory.calls,0)

    def test_storage_refuses_evidence_directory_symlink_and_unrelated_database(self):
        import sqlite3,hashlib
        evidence=Path(self.tmp.name)/'evidence'
        evidence.mkdir()
        original=evidence/'spending-ledger.json'
        original.write_text('{"synthetic_test_only":true}')
        before=hashlib.sha256(original.read_bytes()).hexdigest()
        with self.assertRaises(ValueError):
            PilotStore(evidence,self.key)
        self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(),before)
        self.assertFalse((evidence/'private-pilot.sqlite3').exists())
        linked=Path(self.tmp.name)/'linked'
        linked.symlink_to(self.store.root)
        with self.assertRaises(ValueError):
            PilotStore(linked,self.key)
        unrelated=Path(self.tmp.name)/'unrelated'
        unrelated.mkdir()
        path=unrelated/'private-pilot.sqlite3'
        db=sqlite3.connect(path)
        db.execute('CREATE TABLE customer_secret(value TEXT)')
        db.commit();db.close()
        before=hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaises(ValueError):
            PilotStore(unrelated,self.key)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)

    def test_correct_human_acceptance_hangs_up_after_verified_bridge(self):
        self.ring()
        screen = self.post(self.screen_url, CallSid=CHILD, ParentCallSid=ROOT, From=self.settings.plan.number, To=self.settings.plan.mobile)
        accept = self.action(screen)
        self.assertIn('press 1', screen.text)
        reply = self.post(accept, CallSid=CHILD, ParentCallSid=ROOT, From=self.settings.plan.number, To=self.settings.plan.mobile, Digits='1')
        self.assertIsNone(ET.fromstring(reply.text).find('Hangup'))
        self.assertEqual(self.state()['controller']['state'], 'bridge_pending')
        end = self.post(self.dial_url, DialCallSid=CHILD, DialCallStatus='completed', DialBridged='true')
        self.assertIsNotNone(ET.fromstring(end.text).find('Hangup'))
        self.assertTrue(self.state()['final'])
        self.assertEqual(self.factory.calls, 0)

    def test_voicemail_without_acceptance_falls_back_to_notice(self):
        self.ring()
        end = self.post(self.dial_url, DialCallSid=CHILD, DialCallStatus='completed', DialBridged='false')
        self.assertIn('AI receptionist', end.text)
        self.assertIsNone(ET.fromstring(end.text).find('Connect'))
        self.assertEqual(self.factory.calls, 0)

    def test_wrong_child_parent_late_accept_and_conflicting_retries_fail(self):
        self.ring()
        self.assertEqual(self.post(self.screen_url, CallSid=CHILD, ParentCallSid=OTHER, From=self.settings.plan.number, To=self.settings.plan.mobile).status_code, 409)
        self.now += 21
        self.assertEqual(self.post(self.screen_url, CallSid=CHILD, ParentCallSid=ROOT, From=self.settings.plan.number, To=self.settings.plan.mobile).status_code, 409)

    def test_non_ai_callback_uses_dtmf_no_model_and_atomic_outbox(self):
        self.ring()
        end = self.post(self.dial_url, DialCallStatus='no-answer', DialCallSid=CHILD)
        callback = self.post(self.action(end), Digits='0')
        saved = self.post(self.action(callback), Digits='07700900125')
        self.assertIn('saved', saved.text)
        self.assertEqual(self.post(self.action(callback), Digits='07700900125').text, saved.text)
        self.assertEqual(self.factory.calls, 0)
        self.assertEqual(len(self.records()), 1)
        self.assertTrue(self.records()[0]['callback_requested'])
        with self.store.transaction() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM pilot_notifications').fetchone()[0], 1)

    def test_bad_websocket_signature_never_opens_model(self):
        self.ready()
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect('/pilot/media', headers={'x-twilio-signature': 'bad'}):
                pass
        self.assertEqual(self.factory.calls, 0)

    def test_codec_or_cross_call_start_rejected_before_model(self):
        for changes in ({'callSid': OTHER}, {'mediaFormat': {'encoding': 'audio/pcm','sampleRate':24000,'channels':1}}):
            with self.subTest(changes=changes):
                self.ready()
                with self.ws() as ws:
                    self.handshake(ws, **changes)
                    with self.assertRaises(WebSocketDisconnect):
                        ws.receive_json()
                self.assertEqual(self.factory.calls, 0)
                self.assertFalse(self.state()['stream_claimed'])
                self.assertFalse(self.state()['final'])

    def test_duplicate_stream_cannot_end_the_owned_call(self):
        self.ready()
        with self.store.transaction() as db:
            call = self.store.load(db, self.token, self.now)
            call.update(stage='streaming', stream_claimed=True)
            self.store.save(db, call)
        with self.ws() as ws:
            self.handshake(ws)
            with self.assertRaises(WebSocketDisconnect):
                ws.receive_json()
        self.assertFalse(self.state()['final'])
        self.assertEqual(self.factory.calls, 0)

    def test_end_to_end_audio_capture_enquiry_and_notification(self):
        self.ready()
        with self.ws() as ws:
            self.handshake(ws)
            self.audio(ws)
            audio, mark = ws.receive_json(), ws.receive_json()
            self.assertEqual(audio['event'], 'media')
            self.assertEqual(base64.b64decode(audio['media']['payload']), b'\xff'*160)
            ws.send_json({'event':'mark','sequenceNumber':'3','streamSid':STREAM,'mark':mark['mark']})
            with self.assertRaises(WebSocketDisconnect):
                ws.receive_json()
        record = self.records()[0]
        self.assertEqual(record['outcome'], 'completed')
        self.assertEqual(record['facts']['name'], 'Alex Example')
        self.assertEqual(record['facts']['callback_phone'], '+447700900125')
        self.assertFalse(record['facts']['callback_confirmed'])
        self.assertFalse(record['appointment_confirmed'])
        self.assertEqual(self.factory.calls, 1)
        self.assertTrue(self.factory.model.closed)
        self.assertEqual(len([e for e in self.factory.model.sent if e['type']=='response.create']), 1)
        self.assertNotIn(b'Alex Example', self.store.path.read_bytes())
        self.assertEqual(list(self.store.root.glob('*.wav')), [])
        with self.store.transaction() as db:
            self.assertEqual(db.execute('SELECT state FROM pilot_response_requests').fetchone()[0], 'settled')

    def test_failures_record_partial_enquiry_without_retry_or_fake_zero_usage(self):
        for options in ({'missing_usage':True},{'status':'incomplete'},{'status':'cancelled'},
                        {'provider_error':True},{'bad_config':True},{'automatic_response':True}):
            with self.subTest(options=options):
                # Separate isolated DB per synthetic call, never historical data.
                self.store = PilotStore(Path(self.tmp.name)/('case'+str(len(list(Path(self.tmp.name).iterdir())))), self.key)
                self.factory = ModelFactory(**options)
                self.build()
                self.ready()
                with self.ws() as ws:
                    self.handshake(ws)
                    self.audio(ws)
                    with self.assertRaises(WebSocketDisconnect):
                        ws.receive_json()
                self.assertEqual(self.factory.calls, 1)
                self.assertEqual(len(self.records()), 1)
                self.assertEqual(self.records()[0]['outcome'], 'interrupted')
                if options.get('missing_usage') or options.get('provider_error') or options.get('automatic_response'):
                    self.assertTrue(self.records()[0]['usage_uncertain'])

    def test_unsafe_model_speech_is_not_forwarded(self):
        self.factory = ModelFactory(spoken_text='Your appointment is confirmed. Nigel will definitely attend tomorrow.')
        self.build()
        self.ready()
        with self.ws() as ws:
            self.handshake(ws)
            self.audio(ws)
            with self.assertRaises(WebSocketDisconnect):
                ws.receive_json()
        self.assertEqual(self.records()[0]['outcome'], 'interrupted')

    def test_gas_work_and_hazards_use_existing_fixed_guidance(self):
        for text,expected in [('I smell gas',GAS_GUIDANCE),('Please service my gas boiler',GAS_WORK_GUIDANCE),('Water is leaking into the fuse box',ELECTRICAL_GUIDANCE)]:
            with self.subTest(text=text):
                self.store = PilotStore(Path(self.tmp.name)/('safety'+str(len(list(Path(self.tmp.name).iterdir())))), self.key)
                self.factory = ModelFactory(caller_text=text)
                self.build()
                self.ready()
                with self.ws() as ws:
                    self.handshake(ws)
                    self.audio(ws)
                    with self.assertRaises(WebSocketDisconnect):
                        ws.receive_json()
                reply = self.post(self.redirect_url)
                self.assertEqual(ET.fromstring(reply.text).find('Say').text, expected)
                self.assertEqual(len([e for e in self.factory.model.sent if e['type']=='response.create']),0)
                self.assertFalse(self.records()[0]['gas_work_permitted'])

    def test_expiry_recovery_is_durable_idempotent_and_never_reopens_calls(self):
        self.ready()
        self.now += 301
        restarted = PilotStore(self.store.root, self.key)
        self.assertEqual(restarted.recover_interrupted(self.now), 1)
        self.assertEqual(restarted.recover_interrupted(self.now), 0)
        self.assertEqual(self.post(self.choice_url, Digits='').status_code, 409)
        self.assertEqual(len(self.records()), 1)

    def test_oversized_body_and_changed_query_signature_rejected(self):
        self.assertEqual(self.client.post('/pilot/incoming', content='a='+'x'*17000,headers={'content-type':'application/x-www-form-urlencoded'}).status_code, 413)
        self.incoming()
        data={'AccountSid':ACCOUNT,'CallSid':ROOT,'Digits':'123456'}
        sig=RequestValidator(TOKEN).compute_signature(self.pin_url,data)
        self.assertEqual(self.client.post(self.pin_url+'&other=1',data=data,headers={'x-twilio-signature':sig}).status_code,403)

    def test_barge_in_clears_and_truncates_only_to_acknowledged_playback(self):
        self.factory = ModelFactory(no_capture=True, interrupt_second=True)
        self.build()
        self.ready()
        with self.ws() as ws:
            self.handshake(ws)
            self.audio(ws)
            audio, mark = ws.receive_json(), ws.receive_json()
            self.audio(ws, seq=3)
            self.assertEqual(ws.receive_json()['event'], 'clear')
            # The mark for cleared audio is NOT proof that it was heard.
            ws.send_json({'event':'mark','sequenceNumber':'4','streamSid':STREAM,'mark':mark['mark']})
            ws.send_json({'event':'stop','sequenceNumber':'5','streamSid':STREAM,'stop':{'callSid':ROOT,'accountSid':ACCOUNT}})
            with self.assertRaises(WebSocketDisconnect):
                ws.receive_json()
        truncations=[e for e in self.factory.model.sent if e['type']=='conversation.item.truncate']
        self.assertEqual(len(truncations), 1)
        self.assertEqual(truncations[0]['audio_end_ms'], 0)
        self.assertEqual(truncations[0]['item_id'], 'message1')
        self.assertEqual(self.factory.calls, 1)

    def test_spoken_non_ai_request_and_keypad_opt_out_close_ai(self):
        for spoken in (True, False):
            with self.subTest(spoken=spoken):
                self.store = PilotStore(Path(self.tmp.name)/('optout'+str(len(list(Path(self.tmp.name).iterdir())))), self.key)
                self.factory = ModelFactory(caller_text='I want a non AI callback' if spoken else 'My tap drips', no_capture=True)
                self.build()
                self.ready()
                with self.ws() as ws:
                    self.handshake(ws)
                    if spoken:
                        self.audio(ws)
                    else:
                        ws.send_json({'event':'dtmf','sequenceNumber':'2','streamSid':STREAM,'dtmf':{'digit':'0','track':'inbound_track'}})
                    with self.assertRaises(WebSocketDisconnect):
                        ws.receive_json()
                self.assertTrue(self.state()['callback'])
                self.assertEqual(self.records()[0]['outcome'], 'non_ai_callback')
                self.assertIn('eleven digit', self.post(self.redirect_url).text)
                self.assertTrue(self.factory.model.closed)

    def test_malformed_reordered_and_cross_stream_audio_never_reaches_model(self):
        for changes in ({'payload':'not-base64!'}, {'seq':3}, {'stream':'MZ'+'9'*32}):
            with self.subTest(changes=changes):
                self.store = PilotStore(Path(self.tmp.name)/('invalid'+str(len(list(Path(self.tmp.name).iterdir())))), self.key)
                self.factory = ModelFactory()
                self.build()
                self.ready()
                with self.ws() as ws:
                    self.handshake(ws)
                    self.audio(ws, **changes)
                    with self.assertRaises(WebSocketDisconnect):
                        ws.receive_json()
                self.assertEqual([e for e in self.factory.model.sent if e['type']=='input_audio_buffer.append'], [])

    def test_failed_factory_queues_once_and_a_reconnect_cannot_replay(self):
        self.factory = ModelFactory(connect_failure=True)
        self.build()
        self.ready()
        for _ in range(2):
            with self.ws() as ws:
                self.handshake(ws)
                with self.assertRaises(WebSocketDisconnect):
                    ws.receive_json()
        self.assertEqual(self.factory.calls, 1)
        self.assertEqual(len(self.records()), 1)

    def test_rejects_model_booking_tool_and_false_confirmation_before_playback(self):
        for options in ({'tool':'book_appointment'}, {'facts':{'appointment_confirmed':True}}):
            with self.subTest(options=options):
                self.store = PilotStore(Path(self.tmp.name)/('booking'+str(len(list(Path(self.tmp.name).iterdir())))), self.key)
                self.factory = ModelFactory(**options)
                self.build()
                self.ready()
                with self.ws() as ws:
                    self.handshake(ws)
                    self.audio(ws)
                    with self.assertRaises(WebSocketDisconnect):
                        ws.receive_json()
                self.assertFalse(self.records()[0]['appointment_confirmed'])
                self.assertEqual(self.records()[0]['outcome'], 'interrupted')

    def test_model_safety_words_do_not_fabricate_caller_hazards(self):
        self.factory = ModelFactory(facts={'urgency':'gas_co'})
        self.build()
        self.ready()
        with self.ws() as ws:
            self.handshake(ws)
            self.audio(ws)
            audio, mark = ws.receive_json(), ws.receive_json()
            ws.send_json({'event':'mark','sequenceNumber':'3','streamSid':STREAM,'mark':mark['mark']})
            with self.assertRaises(WebSocketDisconnect):
                ws.receive_json()
        self.assertEqual(self.records()[0]['facts']['urgency'], 'routine')


class ProviderTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_admission_refuses_before_credentials_and_connector(self):
        calls = []
        def credentials():
            calls.append('credential')
            raise AssertionError('Should not read credentials')
        async def connector(*args, **kwargs):
            calls.append('network')
            raise AssertionError('Should not connect')
        factory = RealtimeProviderFactory(credential_reader=credentials, connector=connector)
        with patch.dict(os.environ, {'VOICE_PILOT_ENABLED':'1','VOICE_API_TEST_ENABLED':'1','OPENAI_API_KEY':'synthetic-not-a-key'}):
            with self.assertRaises(PilotAdmissionBlocked):
                await factory()
        self.assertEqual(calls, [])

    async def test_injected_synthetic_authority_exercises_fixed_endpoint_without_network(self):
        from unittest.mock import Mock, AsyncMock
        authority = Mock()
        socket = object()
        connector = AsyncMock(return_value=socket)
        factory = RealtimeProviderFactory(admission=authority,
            credential_reader=lambda:'synthetic-credential-not-live',connector=connector)
        self.assertIs(await factory(),socket)
        authority.require.assert_called_once_with()
        args, kwargs = connector.call_args
        self.assertEqual(args[0],'wss://api.openai.com/v1/realtime?model=gpt-realtime-2.1')
        self.assertEqual(kwargs['max_queue'],8)
        self.assertEqual(kwargs['open_timeout'],8)
        self.assertTrue(kwargs['logger'].disabled)

    async def test_provider_exception_is_sanitised_and_never_retried(self):
        from unittest.mock import Mock, AsyncMock
        connector = AsyncMock(side_effect=RuntimeError('synthetic-secret-must-not-escape'))
        factory = RealtimeProviderFactory(admission=Mock(),
            credential_reader=lambda:'synthetic-credential-not-live',connector=connector)
        with self.assertRaises(ProviderConnectionFailed) as caught:
            await factory()
        self.assertNotIn('synthetic-secret',str(caught.exception))
        self.assertEqual(connector.await_count,1)


if __name__ == '__main__':
    unittest.main()

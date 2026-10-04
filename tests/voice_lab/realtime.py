"""Opt-in WebSocket audio lab. No telephony, app imports, DB or real tools.

Live protocol compatibility remains unverified until API credentials are supplied.
"""
import asyncio
import base64
import json
import logging
import time
from decimal import Decimal
from pathlib import Path
from voice_lab.audio import read_wav, write_wav
from voice_lab.budget import BudgetStop, response_bound, usage_cost
from voice_lab.cases import CAPTURE_TOOL, INSTRUCTIONS, MAX_OUTPUT_TOKENS, MODELS, VOICE
from voice_lab.scoring import score

RATE = 24000
BYTES_PER_SECOND = RATE * 2
SESSION_TIMEOUT = 150
CAPTURE_INSTRUCTIONS = """Capture only facts actually heard in this fictional conversation.
Return exactly every field in the capture_enquiry schema, with no additional fields.
Unknown string fields must be empty strings. photos_useful must be true, false,
or null (null when unknown). Confirmation fields must be booleans: false unless
the caller explicitly confirmed. urgency must be routine, urgent, electrical_water,
or gas_co, according to the safety rules and facts heard. A requested appointment
is not a confirmed booking. Do not invent missing details."""


class ExtractionError(ValueError):
    """Only our static diagnostic messages may be persisted, never provider errors."""


def capture_facts(response):
    if response["status"] != "completed":
        raise ExtractionError("Capture response did not complete")
    calls = [item for item in response["output"] if item.get("type") == "function_call"
             and item.get("name") == "capture_enquiry"]
    if len(calls) != 1:
        raise ExtractionError("Model did not produce exactly one capture function call")
    try:
        facts = json.loads(calls[0]["arguments"])
    except (KeyError, TypeError, ValueError):
        raise ExtractionError("Capture arguments were not valid JSON") from None
    validate_facts(facts)
    return facts


def session_config(model):
    if model not in MODELS:
        raise ValueError("Only the two approved realtime models are allowed")
    return {"type": "realtime", "model": model, "instructions": INSTRUCTIONS,
        "max_output_tokens": MAX_OUTPUT_TOKENS, "output_modalities": ["audio"],
        "reasoning": {"effort": "low"}, "tools": [CAPTURE_TOOL], "tool_choice": "none",
        "truncation": "disabled", "audio": {
            "input": {"format": {"type": "audio/pcm", "rate": RATE},
                "turn_detection": {"type": "server_vad", "threshold": 0.5,
                    "prefix_padding_ms": 300, "silence_duration_ms": 500,
                    "create_response": False, "interrupt_response": True}},
            "output": {"format": {"type": "audio/pcm", "rate": RATE}, "voice": VOICE}}}


def validate_resolved(config):
    vad = config["audio"]["input"]["turn_detection"]
    if (config.get("max_output_tokens") != MAX_OUTPUT_TOKENS or vad.get("create_response") is not False
            or vad.get("interrupt_response") is not True or config["audio"]["input"].get("transcription")
            or config.get("tool_choice") != "none"):
        raise BudgetStop("Server configuration did not confirm paid-response controls")


class Trial:
    def __init__(self, socket, model, ledger):
        self.socket, self.model, self.ledger = socket, model, ledger
        self.events, self.responses = [], []
        self.active = None
        self.pending = None
        self.error = None
        self.audio_seconds = 0
        self.last_caller_end = None
        self.caller_start = None
        self.interruptions = []
        self.listener = None

    async def send(self, event):
        await self.socket.send(json.dumps(event))

    async def listen(self):
        try:
            async for raw in self.socket:
                event = json.loads(raw)
                kind = event.get("type", "")
                event["received_monotonic"] = time.monotonic()
                self.events.append(event)
                if kind == "error":
                    raise BudgetStop("Realtime API returned an error; no automatic retry")
                if kind == "response.created":
                    if self.pending is None:
                        self.ledger.mark_uncertain()
                        raise BudgetStop("Unbudgeted automatic response; close immediately")
                    response = {"id": event["response"]["id"], "reservation": self.pending,
                        "audio": bytearray(), "transcript": "", "item_id": None, "first_audio": None,
                        "done": False, "latency_ms": None, "played_end_ms": None}
                    self.responses.append(response)
                    self.active = response
                    self.pending = None
                elif kind == "response.output_item.added" and self.active:
                    if event["item"].get("type") == "message":
                        self.active["item_id"] = event["item"]["id"]
                elif kind == "response.output_audio.delta" and self.active:
                    if self.active["first_audio"] is None:
                        self.active["first_audio"] = event["received_monotonic"]
                        if self.last_caller_end is not None:
                            self.active["latency_ms"] = 1000 * (event["received_monotonic"] - self.last_caller_end)
                    self.active["audio"].extend(base64.b64decode(event["delta"], validate=True))
                elif kind == "response.output_audio_transcript.done" and self.active:
                    self.active["transcript"] = event.get("transcript", "")
                elif kind == "input_audio_buffer.speech_started":
                    await self.handle_interruption(event["received_monotonic"])
                elif kind == "response.done":
                    response = next((r for r in self.responses if r["id"] == event["response"]["id"]), None)
                    if response is None:
                        raise BudgetStop("Usage received for an untracked response")
                    response["usage"] = event["response"].get("usage")
                    cost = usage_cost(self.model, response["usage"])
                    self.ledger.settle(response["reservation"], cost)
                    response.update(done=True, usage_usd=float(cost), status=event["response"].get("status"),
                                    output=event["response"].get("output", []),
                                    status_details=event["response"].get("status_details"))
        except Exception as exc:
            self.error = exc
            await self.socket.close()

    async def wait(self, predicate, timeout=35):
        async def poll():
            while not predicate():
                if self.error:
                    raise self.error
                if self.listener and self.listener.done():
                    raise BudgetStop("Realtime connection closed before expected event")
                await asyncio.sleep(0.01)
        await asyncio.wait_for(poll(), timeout)

    async def handle_interruption(self, detected_at):
        previous = self.active
        if not previous or previous["first_audio"] is None or not previous["item_id"]:
            return
        # A virtual PCM player advances at recorded sample rate. The transport
        # test does not claim measurement of speaker playback or human talk-over.
        duration_ms = len(previous["audio"]) / BYTES_PER_SECOND * 1000
        elapsed_ms = max(0, 1000 * (detected_at - previous["first_audio"]))
        if elapsed_ms >= duration_ms and previous["done"]:
            return
        played_ms = int(min(duration_ms, elapsed_ms))
        previous["played_end_ms"] = played_ms
        await self.send({"type": "conversation.item.truncate", "item_id": previous["item_id"],
                         "content_index": 0, "audio_end_ms": played_ms})
        self.interruptions.append({"vad_detection_ms": 1000 * (detected_at - self.caller_start)
            if self.caller_start is not None else None, "item_id": previous["item_id"],
            "virtual_playback_stopped_ms": played_ms, "truncate_sent": True})

    async def start_response(self, label, extraction=False):
        if self.pending is not None or (self.active and not self.active["done"]):
            raise BudgetStop("A paid response is still outstanding")
        text_bytes = len(INSTRUCTIONS.encode()) + len(json.dumps(CAPTURE_TOOL).encode())
        reserve = response_bound(self.model, text_bytes, self.audio_seconds, len(self.responses), MAX_OUTPUT_TOKENS)
        self.pending = self.ledger.reserve(label, reserve)
        previous_count = len(self.responses)
        response = {"max_output_tokens": MAX_OUTPUT_TOKENS, "output_modalities": ["text"] if extraction else ["audio"],
            "tool_choice": {"type": "function", "name": "capture_enquiry"} if extraction else "none"}
        if extraction:
            response["instructions"] = CAPTURE_INSTRUCTIONS
        await self.send({"type": "response.create", "response": response})
        await self.wait(lambda: len(self.responses) > previous_count)
        return self.responses[-1]

    async def caller_audio(self, path):
        pcm, duration = read_wav(path)
        previous_commits = sum(e["type"] == "input_audio_buffer.committed" for e in self.events)
        self.caller_start = time.monotonic()
        self.audio_seconds += duration + 0.7
        for offset in range(0, len(pcm), 2400):
            await self.send({"type": "input_audio_buffer.append", "audio": base64.b64encode(pcm[offset:offset + 2400]).decode()})
            await asyncio.sleep(0.05)
        self.last_caller_end = time.monotonic()
        for _ in range(14):
            await self.send({"type": "input_audio_buffer.append", "audio": base64.b64encode(bytes(2400)).decode()})
            await asyncio.sleep(0.05)
        await self.wait(lambda: sum(e["type"] == "input_audio_buffer.committed" for e in self.events) > previous_commits)

    async def run(self, case, audio_directory, output_directory):
        self.listener = asyncio.create_task(self.listen())
        try:
            async with asyncio.timeout(SESSION_TIMEOUT):
                await self.wait(lambda: any(e["type"] == "session.created" for e in self.events))
                await self.send({"type": "session.update", "session": session_config(self.model)})
                await self.wait(lambda: any(e["type"] == "session.updated" for e in self.events))
                resolved = next(e["session"] for e in reversed(self.events) if e["type"] == "session.updated")
                validate_resolved(resolved)
                for index, _ in enumerate(case["turns"]):
                    if index:
                        previous = self.responses[-1]
                        if case["interrupt"]:
                            await self.wait(lambda: previous["first_audio"] is not None or previous["done"])
                            if previous["first_audio"] is not None:
                                await asyncio.sleep(max(0, previous["first_audio"] + 0.3 - time.monotonic()))
                        else:
                            await self.wait(lambda: previous["done"])
                            if previous["first_audio"] is not None:
                                await asyncio.sleep(max(0, previous["first_audio"] + len(previous["audio"]) / BYTES_PER_SECOND - time.monotonic()))
                    await self.caller_audio(Path(audio_directory) / f"{case['id']}-{index + 1}.wav")
                    if self.active:
                        await self.wait(lambda: self.active["done"])
                    await self.start_response(f"{case['id']}:{self.model}:turn-{index + 1}")
                await self.wait(lambda: self.active["done"])
                await self.start_response(f"{case['id']}:{self.model}:capture", extraction=True)
                await self.wait(lambda: self.active["done"])
                # Retain paid evidence BEFORE extraction validation can fail.
                evidence = self.archive(case, output_directory)
                facts = capture_facts(self.active)
                spoken = "\n".join(r["transcript"] for r in self.responses)
                report = {"case": case["id"], "model": self.model, "status": "completed",
                    "resolved_model": resolved.get("model"), "settings": session_config(self.model), "facts": facts,
                    "spoken_transcript": spoken, "interruptions": self.interruptions,
                    "latency_ms": [r["latency_ms"] for r in self.responses if r["latency_ms"] is not None],
                    "usage_usd": sum(r["usage_usd"] for r in self.responses), "responses": evidence,
                    "capture_instruction_version": 2,
                    "scores": score(case, facts, spoken), "transport": "WebSocket PCM with virtual playback"}
                report["generated_transcript_warning"] = "Transcript includes unplayed audio; safety and interruption review must use heard-prefix audio where present."
                report["model_failures"] = [r["status"] for r in self.responses if r["status"] not in {"completed", "cancelled"}]
                return report
        finally:
            await self.socket.close()
            if self.listener:
                self.listener.cancel()
                await asyncio.gather(self.listener, return_exceptions=True)

    def archive(self, case, output_directory):
        # Whitelist model evidence; socket events and authentication never leave memory.
        directory = Path(output_directory) / case["id"] / self.model
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        rows = []
        for index, response in enumerate(self.responses):
            row = {key: response.get(key) for key in (
                "status", "status_details", "usage", "usage_usd", "latency_ms",
                "transcript", "played_end_ms", "output")}
            if response["audio"]:
                path = directory / f"response-{index + 1}.wav"
                write_wav(path, response["audio"])
                row["audio_file"] = str(path)
                if response["played_end_ms"] is not None:
                    played = directory / f"response-{index + 1}-heard-prefix.wav"
                    write_wav(played, response["audio"][:int(response["played_end_ms"] * BYTES_PER_SECOND / 1000)])
                    row["virtual_heard_prefix_file"] = str(played)
            rows.append(row)
        # The runner's atomic, private writer has no provider or application dependency.
        from run_voice_api_benchmark import save_report
        save_report(directory / "paid-evidence.json", {"case": case["id"], "model": self.model,
            "synthetic_only": True, "capture_instruction_version": 2, "responses": rows})
        return rows


async def run_trial(case, model, key, ledger, audio_directory, output_directory):
    import websockets
    logger = logging.getLogger("private-voice-websocket")
    logger.disabled = True
    # No alternate host, telephony URL, fallback model or retry loop allowed.
    async with websockets.connect("wss://api.openai.com/v1/realtime?model=" + model,
        additional_headers={"Authorization": "Bearer " + key}, logger=logger,
        open_timeout=15, close_timeout=3, max_size=1024 * 1024) as socket:
        return await Trial(socket, model, ledger).run(case, audio_directory, output_directory)


def validate_facts(facts):
    properties = CAPTURE_TOOL["parameters"]["properties"]
    if not isinstance(facts, dict) or set(facts) != set(properties):
        raise ExtractionError("Invalid extraction keys")
    for key, spec in properties.items():
        value = facts[key]
        if spec["type"] == "string":
            if not isinstance(value, str) or len(value) > 2000:
                raise ExtractionError("Invalid extraction string: " + key)
            if "enum" in spec and value not in spec["enum"]:
                raise ExtractionError("Invalid urgency")
        elif spec["type"] == "boolean" and type(value) is not bool:
            raise ExtractionError("Invalid confirmation: " + key)
        elif isinstance(spec["type"], list) and value is not None and type(value) is not bool:
            raise ExtractionError("Invalid photo preference")

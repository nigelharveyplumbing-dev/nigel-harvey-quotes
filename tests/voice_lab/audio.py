"""Free local caller synthesis and strict 24 kHz mono PCM fixture validation."""
import ctypes
import hashlib
import json
import subprocess
import wave
from pathlib import Path
from voice_lab.cases import CASES, MAX_AUDIO_SECONDS


def write_wav(path, pcm):
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(24000)
        out.writeframes(pcm)


def read_wav(path):
    with wave.open(str(path), "rb") as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getcomptype()) != (1, 2, 24000, "NONE"):
            raise ValueError("Fixtures must be uncompressed mono 16-bit 24 kHz WAV")
        seconds = source.getnframes() / 24000
        if not 0.1 <= seconds <= MAX_AUDIO_SECONDS:
            raise ValueError("Fixture duration must be between 0.1 and 30 seconds")
        return source.readframes(source.getnframes()), seconds


def generate(directory):
    """Render only the fixed fictional scripts. No API or browser is used."""
    import espeakng_loader
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    lib = espeakng_loader.load_library()
    if lib is None:
        raise RuntimeError("Local eSpeak NG library unavailable")
    lib.espeak_Initialize.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    lib.espeak_Initialize.restype = ctypes.c_int
    rate = lib.espeak_Initialize(2, 0, str(Path(espeakng_loader.get_data_path()).parent).encode(), 0)
    if rate <= 0:
        raise RuntimeError("Local speech initialization failed")
    lib.espeak_SetVoiceByName.argtypes = [ctypes.c_char_p]
    if lib.espeak_SetVoiceByName(b"en-gb-x-rp") != 0:
        raise RuntimeError("British English fixture voice unavailable")
    lib.espeak_SetParameter.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
    lib.espeak_SetParameter(1, 175, 0)
    samples = []
    callback_type = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_short), ctypes.c_int, ctypes.c_void_p)

    @callback_type
    def collect(pointer, count, _events):
        if pointer and count:
            samples.append(ctypes.string_at(pointer, count * 2))
        return 0

    lib.espeak_SetSynthCallback.argtypes = [callback_type]
    lib.espeak_SetSynthCallback(collect)
    lib.espeak_Synth.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint,
                               ctypes.c_int, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    manifest = {"synthetic_only": True, "generator": "local eSpeak NG en-gb-x-rp, 175 wpm; espeakng-loader 0.2.4",
                "limitation": "Robotic synthetic caller audio; not evidence of performance across human UK accents.", "files": []}
    try:
        for case in CASES:
            for index, text in enumerate(case["turns"]):
                samples.clear()
                encoded = text.encode() + b"\0"
                buffer = ctypes.create_string_buffer(encoded)
                if lib.espeak_Synth(buffer, len(encoded), 0, 1, 0, 1, None, None) != 0:
                    raise RuntimeError("Local fixture synthesis failed")
                pcm = subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "s16le", "-ar", str(rate),
                    "-ac", "1", "-i", "pipe:0", "-f", "s16le", "-ar", "24000", "-ac", "1", "pipe:1"],
                    input=b"".join(samples), capture_output=True, check=True, timeout=10).stdout
                path = directory / f"{case['id']}-{index + 1}.wav"
                write_wav(path, pcm)
                _, seconds = read_wav(path)
                manifest["files"].append({"filename": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                         "seconds": seconds, "script_sha256": hashlib.sha256(text.encode()).hexdigest()})
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    finally:
        lib.espeak_Terminate()
    return manifest


def verify_manifest(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("synthetic_only") is not True:
        raise ValueError("Only synthetic fixture manifests accepted")
    entries = {entry["filename"]: entry for entry in manifest["files"]}
    if len(entries) != sum(len(case["turns"]) for case in CASES):
        raise ValueError("Fixture manifest does not match the fixed scenario set")
    durations = {}
    for case in CASES:
        durations[case["id"]] = []
        for index, text in enumerate(case["turns"]):
            filename = f"{case['id']}-{index + 1}.wav"
            entry = entries[filename]
            if entry["script_sha256"] != hashlib.sha256(text.encode()).hexdigest():
                raise ValueError("Scenario script changed since fixture synthesis")
            path = directory / filename
            if entry["sha256"] != hashlib.sha256(path.read_bytes()).hexdigest():
                raise ValueError("Caller audio differs from the paired fixture")
            _, seconds = read_wav(path)
            durations[case["id"]].append(seconds)
    return manifest, durations

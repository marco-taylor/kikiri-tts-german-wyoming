#!/usr/bin/env python3

import io
import os
import sys
import time
import threading
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
KOKORO_DIR = ROOT / "kokoro"
MODELS_DIR = ROOT / "models"
CONFIG_PATH = ROOT / "training" / "config.json"

if str(KOKORO_DIR) not in sys.path:
    sys.path.insert(0, str(KOKORO_DIR))

from kokoro import KModel, KPipeline


# ---------------------------------------------------------
# CPU-Konfiguration
# ---------------------------------------------------------

THREADS = int(os.getenv("KOKORO_THREADS", "4"))

torch.set_num_threads(THREADS)
torch.set_num_interop_threads(1)

print("=" * 60, flush=True)
print("Kikiri German TTS Server", flush=True)
print("=" * 60, flush=True)
print(f"CPU Threads : {torch.get_num_threads()}", flush=True)
print(f"Interop     : {torch.get_num_interop_threads()}", flush=True)
print(f"Models      : {MODELS_DIR}", flush=True)
print(f"Config      : {CONFIG_PATH}", flush=True)


# ---------------------------------------------------------
# Stimmen automatisch finden
# ---------------------------------------------------------

def discover_voices():
    voices = {}

    if not MODELS_DIR.exists():
        return voices

    for directory in sorted(MODELS_DIR.iterdir()):
        if not directory.is_dir():
            continue

        model_path = directory / "model.pth"
        voice_path = directory / "voice.pt"

        if model_path.exists() and voice_path.exists():
            voices[directory.name.lower()] = {
                "name": directory.name,
                "model": model_path,
                "voice": voice_path,
            }

    return voices


VOICE_CONFIG = discover_voices()

if not VOICE_CONFIG:
    raise RuntimeError(f"Keine Stimmen in {MODELS_DIR} gefunden")

print("Gefundene Stimmen:", flush=True)

for voice_name in VOICE_CONFIG:
    print(f"  - {voice_name}", flush=True)


# ---------------------------------------------------------
# Lazy Model Cache
# ---------------------------------------------------------

loaded_voices = {}
load_lock = threading.Lock()


def load_voice(voice_name: str):

    voice_name = voice_name.lower()

    if voice_name not in VOICE_CONFIG:
        raise ValueError(f"Unbekannte Stimme: {voice_name}")

    if voice_name in loaded_voices:
        return loaded_voices[voice_name]

    with load_lock:

        if voice_name in loaded_voices:
            return loaded_voices[voice_name]

        cfg = VOICE_CONFIG[voice_name]

        print(flush=True)
        print("=" * 60, flush=True)
        print(f"Lade Stimme: {voice_name}", flush=True)
        print(f"Modell      : {cfg['model']}", flush=True)
        print(f"Voicepack   : {cfg['voice']}", flush=True)

        started = time.perf_counter()

        model = KModel(
            repo_id="hexgrad/Kokoro-82M",
            config=str(CONFIG_PATH),
            model=str(cfg["model"]),
        ).to("cpu").eval()

        pipeline = KPipeline(
            lang_code="d",
            repo_id="hexgrad/Kokoro-82M",
            model=model,
        )

        voicepack = torch.load(
            cfg["voice"],
            map_location="cpu",
            weights_only=True,
        )

        loaded_voices[voice_name] = {
            "model": model,
            "pipeline": pipeline,
            "voice": voicepack,
            "lock": threading.Lock(),
        }

        elapsed = time.perf_counter() - started

        print(
            f"Stimme {voice_name} geladen in {elapsed:.3f}s",
            flush=True,
        )

        return loaded_voices[voice_name]


# ---------------------------------------------------------
# Synthese
# ---------------------------------------------------------

def synthesize(text: str, voice_name: str, speed: float):

    runtime = load_voice(voice_name)

    started = time.perf_counter()

    chunks = []

    # Eine Pipeline nicht gleichzeitig aus mehreren Threads benutzen.
    with runtime["lock"], torch.inference_mode():

        generator = runtime["pipeline"](
            text,
            voice=runtime["voice"],
            speed=speed,
        )

        for _, phonemes, audio in generator:

            if phonemes:
                print(
                    f"[{voice_name}] Phoneme: {phonemes[:120]}",
                    flush=True,
                )

            if audio is None:
                continue

            if isinstance(audio, torch.Tensor):
                audio = audio.detach().cpu().numpy()

            audio = np.asarray(audio, dtype=np.float32).reshape(-1)

            if audio.size:
                chunks.append(audio)

    if not chunks:
        raise RuntimeError("Kokoro hat keine Audiodaten erzeugt")

    audio = np.concatenate(chunks)

    elapsed = time.perf_counter() - started
    duration = len(audio) / 24000.0
    rtf = elapsed / duration if duration else 0

    print(
        f"[{voice_name}] Synthese={elapsed:.3f}s "
        f"Audio={duration:.3f}s "
        f"RTF={rtf:.3f}",
        flush=True,
    )

    return audio


def make_wav(audio):

    buffer = io.BytesIO()

    sf.write(
        buffer,
        audio,
        24000,
        format="WAV",
        subtype="PCM_16",
    )

    return buffer.getvalue()


# ---------------------------------------------------------
# OpenAI-kompatible API
# ---------------------------------------------------------

app = FastAPI(
    title="Kikiri German TTS",
    version="1.0",
)


class SpeechRequest(BaseModel):
    model: str = "kokoro"
    input: str
    voice: str = "martin"
    speed: float = 1.0
    response_format: str = "wav"


@app.get("/")
def root():
    return {
        "service": "Kikiri German TTS",
        "voices": list(VOICE_CONFIG.keys()),
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "voices": list(VOICE_CONFIG.keys()),
        "loaded": list(loaded_voices.keys()),
    }


@app.get("/v1/audio/voices")
def voices():
    return {
        "voices": list(VOICE_CONFIG.keys())
    }


@app.post("/v1/audio/speech")
def speech(req: SpeechRequest):

    voice_name = req.voice.lower().strip()

    if voice_name not in VOICE_CONFIG:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"Unbekannte Stimme: {voice_name}",
                "voices": list(VOICE_CONFIG.keys()),
            },
        )

    text = req.input.strip()

    if not text:
        raise HTTPException(
            status_code=400,
            detail="Text darf nicht leer sein",
        )

    speed = max(0.5, min(float(req.speed), 2.0))

    print(flush=True)
    print("-" * 60, flush=True)
    print(f"Voice : {voice_name}", flush=True)
    print(f"Speed : {speed}", flush=True)
    print(f"Text  : {text}", flush=True)

    try:
        audio = synthesize(
            text=text,
            voice_name=voice_name,
            speed=speed,
        )

        wav = make_wav(audio)

        return Response(
            content=wav,
            media_type="audio/wav",
            headers={
                "X-TTS-Voice": voice_name,
                "X-TTS-Sample-Rate": "24000",
            },
        )

    except Exception as exc:

        print(
            f"TTS FEHLER: {exc!r}",
            flush=True,
        )

        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


# ---------------------------------------------------------
# Optionaler Warmup
# ---------------------------------------------------------

@app.on_event("startup")
def startup():

    warmup = os.getenv(
        "KOKORO_PRELOAD",
        "martin,victoria",
    )

    requested = [
        x.strip().lower()
        for x in warmup.split(",")
        if x.strip()
    ]

    for voice_name in requested:

        if voice_name not in VOICE_CONFIG:
            print(
                f"Warmup übersprungen: {voice_name} nicht vorhanden",
                flush=True,
            )
            continue

        try:
            load_voice(voice_name)

        except Exception as exc:
            print(
                f"FEHLER beim Laden von {voice_name}: {exc!r}",
                flush=True,
            )


if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8881")),
        workers=1,
    )

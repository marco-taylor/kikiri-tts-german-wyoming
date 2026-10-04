"""Shared HTTP/Wyoming model cache and single synthesis executor."""

import asyncio
import io
import json
from pathlib import Path
import time
import wave

from .config import Config
from .history import Policies
from .session import EXECUTOR, Session

policies = None


def initialize(config: Config):
    global policies
    policies = Policies(Path("/tmp/kikiri-tts/history"), config)
    return policies


async def http_speech(text, voice, requested_speed):
    import server

    loop = asyncio.get_running_loop()
    if requested_speed != 1.0:
        # Preserve the existing explicit OpenAI request-speed behavior.
        audio = await loop.run_in_executor(
            EXECUTOR, server.synthesize, text, voice, requested_speed
        )
        return server.make_wav(audio)

    async def unused_send(event):
        raise RuntimeError("HTTP producer must not send Wyoming events")

    session = Session(text, voice, policies, unused_send, chunk_ms=80)
    original_select = session.policy.select

    def full_http(durations, *args, **kwargs):
        plan = original_select(durations, *args, **kwargs)
        plan.update(
            mode="fallback",
            reason="http_non_streaming",
            required_pcm_seconds=sum(durations),
            prefix_segments=len(durations),
        )
        return plan

    session.policy.select = full_http
    session.loop = loop
    session.start = time.monotonic()
    await loop.run_in_executor(EXECUTOR, session.produce)
    if session.error:
        session.complete = False
        print(
            "KIKIRI_REQUEST " + json.dumps(session.metrics(), default=str), flush=True
        )
        raise RuntimeError(session.error)
    pcm = bytes(session.buffer)
    if not pcm:
        raise RuntimeError("No PCM generated")
    session.complete = True
    session.sent = session.produced
    session.ttfa = session.total_seconds = time.monotonic() - session.start
    if len(pcm) / 48000 >= 5:
        session.policy.record(
            voice,
            session.synthesis_seconds / (len(pcm) / 48000),
            max(c["rtf"] for c in session.chunks),
        )
    record = session.metrics()
    record["transport"] = "http_non_streaming"
    print(
        "KIKIRI_REQUEST "
        + json.dumps(
            {k: v for k, v in record.items() if k not in ["text", "timeline"]}
        ),
        flush=True,
    )
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(pcm)
    return out.getvalue()

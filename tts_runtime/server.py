import asyncio, json, pathlib, collections
from wyoming.event import async_read_event, async_write_event
from wyoming.info import Info, TtsProgram, TtsVoice, Attribution
from wyoming.tts import SynthesizeStopped
from .session import Session
from server import VOICE_CONFIG


class Server:
    def __init__(self, policy, results=None):
        self.policy = policy
        self.results = pathlib.Path(results) if results else None
        self.sessions = collections.deque(maxlen=2)
        self.current = None

    async def connect(self, reader, writer):
        active = None
        incoming = None
        task = None

        async def send(event):
            await async_write_event(event, writer)

        async def perform(session):
            try:
                await session.run()
            except (ConnectionError, asyncio.CancelledError):
                pass
            except Exception as exc:
                session.error = session.error or f"{type(exc).__name__}: {exc}"
                session.complete = False
            finally:
                try:
                    self.sessions.append(session)
                    record = session.metrics()
                    print(
                        "KIKIRI_REQUEST "
                        + json.dumps(
                            {
                                k: v
                                for k, v in record.items()
                                if k not in ["timeline", "text"]
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                    if self.results:
                        destination = self.results / (session.id + ".json")
                        temporary = destination.with_suffix(".tmp")
                        temporary.write_text(json.dumps(record, indent=2))
                        temporary.replace(destination)
                        with (self.results / "metrics.jsonl").open("a") as f:
                            f.write(
                                json.dumps(
                                    {k: v for k, v in record.items() if k != "timeline"}
                                )
                                + "\n"
                            )
                finally:
                    if self.current is session:
                        self.current = None
                    try:
                        await send(SynthesizeStopped().event())
                    except (ConnectionError, asyncio.CancelledError):
                        pass

        try:
            while True:
                event = await async_read_event(reader)
                if event is None:
                    break
                if event.type == "describe":
                    attr = Attribution(
                        name="Kikiri TTS German + Wyoming",
                        url="https://github.com/marco-taylor/kikiri-tts-german-wyoming",
                    )
                    voices = [
                        TtsVoice(
                            name=v,
                            description=v,
                            attribution=attr,
                            installed=True,
                            version=None,
                            languages=["de"],
                        )
                        for v in VOICE_CONFIG
                    ]
                    await send(
                        Info(
                            tts=[
                                TtsProgram(
                                    name="Kikiri TTS German + Wyoming",
                                    description="Local German TTS powered by Kikiri/Kokoro",
                                    attribution=attr,
                                    installed=True,
                                    version=None,
                                    voices=voices,
                                    supports_synthesize_streaming=True,
                                )
                            ]
                        ).event()
                    )
                    continue
                busy = task is not None and not task.done()
                if event.type in ["synthesize", "synthesize-start"] and (
                    busy or incoming is not None
                ):
                    if busy and active:
                        active.ignored += 1
                        active.trace("ignored_synthesize")
                    elif incoming is not None:
                        incoming["ignored"] = incoming.get("ignored", 0) + 1
                    continue
                if event.type == "synthesize-start":
                    incoming = dict(
                        text="", voice=event.data.get("voice", {}).get("name", "martin")
                    )
                    continue
                if event.type == "synthesize-chunk" and incoming is not None:
                    incoming["text"] += event.data.get("text", "")
                    continue
                if event.type == "synthesize-stop" and incoming is not None:
                    data = incoming
                    incoming = None
                elif event.type == "synthesize":
                    data = dict(
                        text=event.data.get("text", ""),
                        voice=event.data.get("voice", {}).get("name", "martin"),
                    )
                else:
                    continue
                if self.current is not None:
                    # Separate connections are serialized by the model worker; avoid overlapping playback.
                    await send(SynthesizeStopped().event())
                    continue
                active = Session(
                    data["text"], data["voice"], self.policy, send, chunk_ms=80
                )
                active.ignored = data.get("ignored", 0)
                self.current = active
                task = asyncio.create_task(perform(active))
        finally:
            if task and not task.done():
                active.cancelled.set()
                async with active.condition:
                    active.condition.notify_all()
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass

    async def listen(self, port=10203, host="127.0.0.1"):
        return await asyncio.start_server(self.connect, host, port)

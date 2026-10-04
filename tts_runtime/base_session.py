import asyncio, concurrent.futures, time, threading, uuid
from wyoming.audio import AudioStart, AudioChunk, AudioStop
from . import model

EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="single-kokoro-producer"
)


class Session:
    def __init__(self, text, voice, policy, send, chunk_ms=80, seed=None):
        self.id = uuid.uuid4().hex
        self.text = text
        self.voice = voice
        self.policy = policy
        self.send = send
        self.chunk_ms = chunk_ms
        self.seed = seed
        self.buffer = bytearray()
        self.condition = asyncio.Condition()
        self.cancelled = threading.Event()
        self.started_event = threading.Event()
        self.started = False
        self.done = False
        self.error = None
        self.plan = None
        self.chunks = []
        self.timeline = []
        self.sent = 0
        self.produced = 0
        self.underruns = []
        self.start_reserve = None
        self.minimum = None
        self.maximum = 0
        self.last_chunk = None
        self.stop_at = None
        self.producer_end = None
        self.ignored = 0

    def trace(self, event, **extra):
        reserve = len(self.buffer) / 48
        if self.started and not self.done:
            self.minimum = (
                reserve if self.minimum is None else min(self.minimum, reserve)
            )
        self.maximum = max(self.maximum, reserve)
        self.timeline.append(
            dict(
                at=time.monotonic() - self.start,
                event=event,
                buffer_ms=reserve,
                produced_bytes=self.produced,
                sent_bytes=self.sent,
                **extra,
            )
        )

    async def planned(self, durations, prediction_time, sentence_count):
        async with self.condition:
            self.durations = durations
            self.prediction_seconds = prediction_time
            self.sentence_count = sentence_count
            self.plan = self.policy.select(durations, self.voice, self.chunk_ms)
            self.trace("prediction", **self.plan)
            self.condition.notify_all()

    async def add(self, data, index, elapsed):
        async with self.condition:
            self.buffer.extend(data)
            self.produced += len(data)
            actual = len(data) / 48000
            self.chunks.append(
                dict(
                    index=index,
                    predicted_audio_seconds=self.durations[index],
                    audio_seconds=actual,
                    synthesis_seconds=elapsed,
                    rtf=elapsed / actual,
                    ready_seconds=time.monotonic() - self.start,
                )
            )
            if not self.started:
                old = self.plan
                peak = max(c["rtf"] for c in self.chunks)
                self.plan = self.policy.select(
                    self.durations, self.voice, self.chunk_ms, peak
                )
                if old != self.plan:
                    self.trace("plan_updated", **self.plan)
            self.trace("segment_ready", segment=index + 1, **self.chunks[-1])
            self.condition.notify_all()

    async def ended(self, error=None):
        async with self.condition:
            self.producer_end = time.monotonic() - self.start
            self.error = error or self.error
            self.done = True
            self.trace("producer_done", error=self.error)
            self.condition.notify_all()

    def produce(self):
        cpu = time.process_time()
        tick = time.monotonic()
        try:
            runtime = model.load(self.voice)
            with runtime["lock"], model.torch.inference_mode():
                if self.seed is not None:
                    model.torch.manual_seed(self.seed)
                rng = model.torch.get_rng_state().clone()
                t = time.monotonic()
                segments = list(model.quiet(self.text))
                if len(segments) == 1:
                    # Keep the original model call for single-segment fallback.
                    # Its predictor runs once; read the exact duration at the decoder boundary.
                    def predicted(decoder, args):
                        if self.cancelled.is_set():
                            raise RuntimeError("Cancelled before decoder")
                        assert model.torch.equal(rng, model.torch.get_rng_state()), (
                            "Pre-decoder stages changed RNG"
                        )
                        samples = args[0].shape[-1] * 600
                        sentences = max(
                            1,
                            len(
                                __import__("re").findall(
                                    r"[.!?]+", segments[0].graphemes
                                )
                            ),
                        )
                        asyncio.run_coroutine_threadsafe(
                            self.planned(
                                [samples / 24000], time.monotonic() - t, sentences
                            ),
                            self.loop,
                        ).result()

                    hook = runtime["model"].decoder.register_forward_pre_hook(predicted)
                    try:
                        result = model.b.KPipeline.infer(
                            runtime["model"],
                            segments[0].phonemes,
                            runtime["voice"],
                            1.0,
                        )
                    finally:
                        hook.remove()
                    audio = result.audio.numpy().reshape(-1)
                    pcm = model.pcm(audio)
                    elapsed = time.monotonic() - t
                    asyncio.run_coroutine_threadsafe(
                        self.add(pcm, 0, elapsed), self.loop
                    ).result()
                    self.synthesis_seconds = time.monotonic() - tick
                    self.cpu_percent = (
                        100 * (time.process_time() - cpu) / self.synthesis_seconds
                    )
                    asyncio.run_coroutine_threadsafe(self.ended(), self.loop).result()
                    return
                chunks = model.prepare(self.text, runtime, segments=segments)
                assert model.torch.equal(rng, model.torch.get_rng_state()), (
                    "Predictor changed RNG state"
                )
                assert chunks, "No audio segments"
                prediction_time = time.monotonic() - t
                sentence_count = sum(
                    max(1, len(__import__("re").findall(r"[.!?]+", c["text"])))
                    for c in chunks
                )
                asyncio.run_coroutine_threadsafe(
                    self.planned(
                        [c["samples"] / 24000 for c in chunks],
                        prediction_time,
                        sentence_count,
                    ),
                    self.loop,
                ).result()
                for index, c in enumerate(chunks):
                    if self.cancelled.is_set():
                        break
                    t = time.monotonic()
                    audio = model.finish(c, runtime)
                    pcm = model.pcm(audio)
                    elapsed = time.monotonic() - t
                    asyncio.run_coroutine_threadsafe(
                        self.add(pcm, index, elapsed), self.loop
                    ).result()
            self.synthesis_seconds = time.monotonic() - tick
            self.cpu_percent = (
                100 * (time.process_time() - cpu) / max(self.synthesis_seconds, 1e-9)
            )
            asyncio.run_coroutine_threadsafe(self.ended(), self.loop).result()
        except BaseException as exc:
            self.synthesis_seconds = time.monotonic() - tick
            self.cpu_percent = (
                100 * (time.process_time() - cpu) / max(self.synthesis_seconds, 1e-9)
            )
            asyncio.run_coroutine_threadsafe(
                self.ended(f"{type(exc).__name__}: {exc}"), self.loop
            ).result()

    async def run(self):
        self.loop = asyncio.get_running_loop()
        self.start = time.monotonic()
        worker = self.loop.run_in_executor(EXECUTOR, self.produce)
        complete = False
        play_start = None
        try:
            async with self.condition:
                await self.condition.wait_for(
                    lambda: (
                        self.done
                        or (
                            self.plan
                            and len(self.buffer) / 48000 + 1e-8
                            >= self.plan["required_pcm_seconds"]
                        )
                    )
                )
                if self.cancelled.is_set() or self.error:
                    return
                if not self.buffer:
                    raise RuntimeError("Empty producer output")
                self.start_reserve = len(self.buffer) / 48
                self.started = True
                self.minimum = self.start_reserve
                self.started_event.set()
                self.trace("audio_start")
            await self.send(AudioStart(rate=24000, width=2, channels=1).event())
            play_start = time.monotonic()
            self.ttfa = play_start - self.start
            size = int(self.chunk_ms * 48)
            under_start = None
            while True:
                async with self.condition:
                    if not self.buffer and not self.done:
                        under_start = time.monotonic()
                        self.trace("underrun_start")
                        await self.condition.wait_for(
                            lambda: self.buffer or self.done or self.cancelled.is_set()
                        )
                        gap = time.monotonic() - under_start
                        self.underruns.append(gap)
                        self.trace("underrun_end", duration_seconds=gap)
                        play_start += gap
                    if self.cancelled.is_set():
                        break
                    if not self.buffer:
                        if self.done:
                            break
                        continue
                    packet = bytes(self.buffer[:size])
                    del self.buffer[:size]
                    offset = self.sent / 48
                    self.sent += len(packet)
                    self.trace("consume", consumer_rate_bytes_per_second=48000)
                await self.send(
                    AudioChunk(
                        rate=24000, width=2, channels=1, audio=packet, timestamp=offset
                    ).event()
                )
                self.last_chunk = time.monotonic() - self.start
                await asyncio.sleep(
                    max(
                        0,
                        play_start
                        + self.sent / 48000
                        - self.policy.lookahead
                        - time.monotonic(),
                    )
                )
            # AudioStop follows the complete nominal duration, including the original lookahead PCM.
            await asyncio.sleep(
                max(0, play_start + self.sent / 48000 - time.monotonic())
            )
            await self.send(AudioStop(timestamp=self.sent / 48).event())
            self.stop_at = time.monotonic() - self.start
            self.trace("audio_stop")
            complete = (
                not self.error
                and not self.cancelled.is_set()
                and self.done
                and self.sent == self.produced
            )
        except asyncio.CancelledError:
            self.cancelled.set()
            self.error = self.error or "Consumer cancelled"
            raise
        except BaseException as exc:
            self.cancelled.set()
            self.error = self.error or f"{type(exc).__name__}: {exc}"
        finally:
            self.cancelled.set()
            await asyncio.shield(worker)
            self.complete = complete
            self.total_seconds = time.monotonic() - self.start
            D = self.produced / 48000
            if complete and not self.underruns and D >= 5:
                self.policy.record(
                    self.voice,
                    self.synthesis_seconds / D,
                    max(c["rtf"] for c in self.chunks),
                )

    def metrics(self):
        D = self.produced / 48000
        return dict(
            request_id=self.id,
            voice=self.voice,
            text=self.text,
            chunk_ms=self.chunk_ms,
            complete=getattr(self, "complete", False),
            cancelled=self.cancelled.is_set() and not getattr(self, "complete", False),
            error=self.error,
            ignored_synthesize=self.ignored,
            plan=self.plan,
            predictor_seconds=getattr(self, "prediction_seconds", None),
            predicted_audio_seconds=sum(getattr(self, "durations", [])),
            audio_seconds=D,
            segments=self.chunks,
            sentence_count=getattr(self, "sentence_count", 0),
            synthesis_seconds=getattr(self, "synthesis_seconds", None),
            rtf=getattr(self, "synthesis_seconds", 0) / D if D else None,
            cpu_percent=getattr(self, "cpu_percent", None),
            ttfa=getattr(self, "ttfa", None),
            start_buffer_ms=self.start_reserve,
            minimum_buffer_ms=self.minimum,
            maximum_buffer_ms=self.maximum,
            underruns=self.underruns,
            underrun_seconds=sum(self.underruns),
            produced_bytes=self.produced,
            sent_bytes=self.sent,
            last_audio_chunk=self.last_chunk,
            audio_stop=self.stop_at,
            total_seconds=getattr(self, "total_seconds", None),
            timeline=self.timeline,
        )

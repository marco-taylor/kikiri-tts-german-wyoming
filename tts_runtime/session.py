import asyncio, time, re
from . import base_session
from . import model

EXECUTOR = base_session.EXECUTOR


class Session(base_session.Session):
    def __init__(self, text, voice, policies, send, **kwargs):
        self.config = policies.config
        super().__init__(text, voice, policies.request(), send, **kwargs)
        self.original_seconds = None
        self.raw_samples = 0
        self.factor = 1.0 if self.config.speed == 1.0 else None
        self.soundtouch_seconds = 0.0
        self.soundtouch_used = False
        self.max_hold_seconds = 0.0

    def call(self, coroutine):
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result()

    async def segment_forecast(self, index, kokoro_seconds):
        # Update slowdown guard BEFORE publishing PCM that might open the gate.
        async with self.condition:
            d = self.durations[index]
            self.chunks.append(
                dict(
                    index=index,
                    predicted_audio_seconds=d,
                    audio_seconds=d,
                    synthesis_seconds=kokoro_seconds,
                    rtf=kokoro_seconds / d,
                    ready_seconds=time.monotonic() - self.start,
                )
            )
            if not self.started:
                self.plan = self.policy.select(
                    self.durations,
                    self.voice,
                    self.chunk_ms,
                    max(c["rtf"] for c in self.chunks),
                )
            self.trace("segment_forecast", segment=index + 1, **self.chunks[-1])
            self.condition.notify_all()

    async def append_pcm(self, pcm, index):
        async with self.condition:
            if self.cancelled.is_set():
                return
            self.buffer.extend(pcm)
            self.produced += len(pcm)
            self.trace("pcm_ready", segment=index + 1)
            self.condition.notify_all()

    async def finish_segment(self, index, elapsed, st_seconds, expected_cumulative):
        async with self.condition:
            c = self.chunks[index]
            c.update(
                synthesis_seconds=elapsed,
                rtf=elapsed / c["audio_seconds"],
                soundtouch_seconds=st_seconds,
                ready_seconds=time.monotonic() - self.start,
            )
            hold = max(0, expected_cumulative - self.produced / 48000)
            self.max_hold_seconds = max(self.max_hold_seconds, hold)
            self.policy.max_hold_seconds = self.max_hold_seconds
            self.policy.current_hold_seconds = self.max_hold_seconds
            # Guard a newly observed larger retention before any later start.
            if not self.started:
                peak = max(x["rtf"] for x in self.chunks)
                self.plan = self.policy.select(
                    self.durations, self.voice, self.chunk_ms, peak
                )
                assumed = self.plan.get("soundtouch_reserve_seconds", 0)
                if hold > assumed:
                    self.plan.update(
                        mode="fallback",
                        reason="unexpected_soundtouch_retention",
                        required_pcm_seconds=sum(self.durations),
                        prefix_segments=len(self.durations),
                    )
            self.trace("segment_ready", segment=index + 1, soundtouch_hold_seconds=hold)
            self.condition.notify_all()

    def produce(self):
        if self.config.speed == 1.0:
            # Exact accepted producer, no import/initialization/feed of SoundTouch.
            super().produce()
            self.original_seconds = sum(getattr(self, "durations", []))
            self.raw_samples = self.produced // 2
            return
        tick = time.monotonic()
        cpu = time.process_time()
        st = None
        try:
            runtime = model.load(self.voice)
            with runtime["lock"], model.torch.inference_mode():
                if self.seed is not None:
                    model.torch.manual_seed(self.seed)
                rng = model.torch.get_rng_state().clone()
                t = time.monotonic()
                original = model.prepare(self.text, runtime)
                chunks = model.speed_chunks(original, self.config.speed)
                if not chunks:
                    raise ValueError(
                        "Text enthält keine synthetisierbaren Audiosegmente"
                    )
                assert model.torch.equal(rng, model.torch.get_rng_state()), (
                    "Predictor consumed RNG"
                )
                original_samples = sum(c["samples"] for c in original)
                predicted_raw = sum(c["samples"] for c in chunks)
                self.original_seconds = original_samples / 24000
                self.factor = original_samples / predicted_raw
                self.call(
                    self.planned(
                        [c["samples"] / 24000 * self.factor for c in chunks],
                        time.monotonic() - t,
                        sum(
                            max(1, len(re.findall(r"[.!?]+", c["text"])))
                            for c in chunks
                        ),
                    )
                )
                from .stretch import Stretcher

                st = Stretcher(self.factor)
                self.soundtouch_used = True
                expected_cumulative = 0.0
                for index, c in enumerate(chunks):
                    if self.cancelled.is_set():
                        break
                    t = time.monotonic()
                    audio = model.finish(c, runtime)
                    raw = model.pcm(audio)
                    self.raw_samples += len(raw) // 2
                    self.call(self.segment_forecast(index, time.monotonic() - t))
                    st_start = time.monotonic()
                    for pcm in st.feed(raw):
                        if self.cancelled.is_set():
                            break
                        self.call(self.append_pcm(pcm, index))
                    st_time = time.monotonic() - st_start
                    self.soundtouch_seconds += st_time
                    expected_cumulative += self.durations[index]
                    self.call(
                        self.finish_segment(
                            index, time.monotonic() - t, st_time, expected_cumulative
                        )
                    )
                if not self.cancelled.is_set():
                    t = time.monotonic()
                    for pcm in st.finish():
                        self.call(self.append_pcm(pcm, len(chunks) - 1))
                    self.soundtouch_seconds += time.monotonic() - t
                    assert (
                        self.raw_samples == predicted_raw
                        and st.input_frames == predicted_raw
                    )
                    assert abs(st.output_frames - original_samples) <= 1, (
                        "SoundTouch sample-count mismatch"
                    )
                self.synthesis_seconds = time.monotonic() - tick
                self.cpu_percent = (
                    100
                    * (time.process_time() - cpu)
                    / max(self.synthesis_seconds, 1e-9)
                )
            self.call(self.ended())
        except BaseException as exc:
            self.synthesis_seconds = time.monotonic() - tick
            self.cpu_percent = (
                100 * (time.process_time() - cpu) / max(self.synthesis_seconds, 1e-9)
            )
            self.call(self.ended(f"{type(exc).__name__}: {exc}"))
        finally:
            if st:
                st.close()

    def metrics(self):
        record = super().metrics()
        record.update(
            configured_KIKIRI_TTS_SYNTH_SPEED=self.config.requested,
            actual_kokoro_speed=self.config.speed,
            soundtouch_factor=self.factor,
            soundtouch_tempo=1 / self.factor if self.factor else None,
            soundtouch_used=self.soundtouch_used,
            estimated_original_audio_seconds=self.original_seconds,
            raw_audio_seconds=self.raw_samples / 24000,
            stretched_audio_seconds=self.produced / 48000,
            soundtouch_seconds=self.soundtouch_seconds,
            max_soundtouch_hold_seconds=self.max_hold_seconds,
        )
        return record

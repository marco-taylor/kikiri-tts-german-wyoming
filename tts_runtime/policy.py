import collections, json, math, os, pathlib
import numpy as np


class Policy:
    def __init__(self, path=None):
        self.path = pathlib.Path(path) if path else None
        self.history = collections.defaultdict(lambda: collections.deque(maxlen=20))
        self.floor = float(os.getenv("KIKIRI_ADAPTIVE_MIN_RTF", "1.35"))
        self.multiplier = float(os.getenv("KIKIRI_ADAPTIVE_RTF_MARGIN", "1.20"))
        self.safety = float(os.getenv("KIKIRI_ADAPTIVE_SAFETY_MS", "750")) / 1000
        self.lookahead = (
            float(os.getenv("KIKIRI_ADAPTIVE_OUTPUT_LOOKAHEAD_MS", "200")) / 1000
        )
        self.max_seconds = float(os.getenv("KIKIRI_ADAPTIVE_MAX_AUDIO_SECONDS", "65"))
        self.min_saved = 2.0
        self.min_saved_fraction = 0.15
        if self.path and self.path.exists():
            try:
                stored = json.loads(self.path.read_text())
                for voice, values in stored.items():
                    self.history[voice].extend(
                        x
                        for x in values
                        if isinstance(x, dict)
                        and all(
                            isinstance(x.get(k), (int, float))
                            and math.isfinite(x[k])
                            and x[k] > 0
                            for k in ["rtf", "segment_peak_rtf"]
                        )
                    )
            except (OSError, ValueError, TypeError, AttributeError):
                self.history.clear()

    def estimate(self, voice):
        values = list(self.history[voice])
        p90 = (
            float(
                np.percentile(
                    [max(x["rtf"], x["segment_peak_rtf"]) for x in values], 90
                )
            )
            if values
            else None
        )
        return max(self.floor, p90 or 0) * self.multiplier, p90, len(values)

    def select(self, durations, voice, chunk_ms, current_peak=0):
        D = sum(durations)
        r, p90, n = self.estimate(voice)
        r = max(r, current_peak * self.multiplier)
        base = D * max(0, 1 - 1 / r)
        safety = self.safety + chunk_ms / 1000 + self.lookahead
        prefix = 0
        chosen = None
        reserve = None
        reason = "adaptive"
        for k, d in enumerate(durations, 1):
            prefix += d
            tail = durations[k:]
            previous = 0
            needed = 0
            for t in tail:
                needed = max(needed, r * (previous + t) - previous)
                previous += t
            if prefix >= needed + safety:
                chosen = k
                reserve = max(0, prefix - base - safety)
                break
        if len(durations) == 1:
            reason = "single_native_segment"
        elif n < 3:
            reason = "insufficient_history"
        elif D > self.max_seconds:
            reason = "long_answer_limit"
        elif chosen is None or chosen == len(durations):
            reason = "insufficient_deadline_reserve"
        elif r * sum(durations[chosen:]) < max(
            self.min_saved, self.min_saved_fraction * r * D
        ):
            reason = "insufficient_latency_gain"
        if reason != "adaptive":
            chosen = len(durations)
        B = sum(durations[:chosen])
        return dict(
            mode="adaptive" if reason == "adaptive" else "fallback",
            reason=reason,
            estimated_rtf=r,
            recent_p90_rtf=p90,
            history_requests=n,
            predicted_audio_seconds=D,
            b_min_seconds=base,
            chunk_reserve_seconds=max(0, B - base - safety),
            safety_seconds=safety,
            required_pcm_seconds=B,
            prefix_segments=chosen,
            rtf_margin=self.multiplier,
            output_lookahead_seconds=self.lookahead,
        )

    def record(self, voice, rtf, peak):
        self.history[voice].append(dict(rtf=rtf, segment_peak_rtf=peak))
        if self.path:
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(
                    {voice: list(values) for voice, values in self.history.items()},
                    indent=2,
                )
            )
            temporary.replace(self.path)

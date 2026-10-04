"""Independent successful-production histories for each configured speed/voice."""

import pathlib
from .combined_policy import CombinedPolicy


class RequestPolicy(CombinedPolicy):
    def __init__(self, path, speed):
        super().__init__(path)
        self.speed = speed
        self.max_hold_seconds = 0.0

    def record(self, voice, rtf, peak):
        # One sequential server request at a time: own policy snapshot, own file.
        latest = CombinedPolicy(self.path)
        self.history = latest.history
        self.history[voice].append(
            dict(rtf=rtf, segment_peak_rtf=peak, max_hold_seconds=self.max_hold_seconds)
        )
        if self.path:
            import json

            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps({v: list(xs) for v, xs in self.history.items()}, indent=2)
            )
            temporary.replace(self.path)


class Policies:
    def __init__(self, root, config):
        self.root = pathlib.Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.config = config
        self.mode = __import__("os").getenv("KIKIRI_TTS_MODE", "adaptive")
        if self.mode not in ["adaptive", "non_streaming"]:
            raise ValueError("KIKIRI_TTS_MODE must be adaptive or non_streaming")

    def request(self):
        policy = RequestPolicy(
            self.root / f"speed-{self.config.key}.json", self.config.speed
        )
        if self.mode == "non_streaming":
            original = policy.select

            def full(durations, *args, **kwargs):
                plan = original(durations, *args, **kwargs)
                plan.update(
                    mode="fallback",
                    reason="non_streaming_requested",
                    required_pcm_seconds=sum(durations),
                    prefix_segments=len(durations),
                )
                return plan

            policy.select = full
        return policy

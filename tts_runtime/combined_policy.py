from .policy import Policy


class CombinedPolicy(Policy):
    def select(self, durations, voice, chunk_ms, current_peak=0):
        # speed1 uses the exact current10208 strategy. Only the SoundTouch path
        # adds bounded internal retention and avoids waiting for retained samples.
        if getattr(self, "speed", 1) == 1:
            return super().select(durations, voice, chunk_ms, current_peak)
        D = sum(durations)
        r, p90, n = self.estimate(voice)
        r = max(r, current_peak * self.multiplier)
        base = D * max(0, 1 - 1 / r)
        measured = max(
            getattr(self, "current_hold_seconds", 0),
            max((x.get("max_hold_seconds", 0) for x in self.history[voice]), default=0),
        )
        hold = max(0.250, 2 * measured + 0.080)
        safety = self.safety + chunk_ms / 1000 + self.lookahead + hold
        prefix = 0.0
        chosen = None
        required = D
        for k, d in enumerate(durations, 1):
            prefix += d
            tail = durations[k:]
            previous = 0.0
            needed = 0.0
            for t in tail:
                needed = max(needed, r * (previous + t) - previous)
                previous += t
            threshold = max(base, needed) + safety
            if prefix - hold >= threshold:
                chosen = k
                required = threshold
                break
        reason = "adaptive"
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
            required = D
        return dict(
            mode="adaptive" if reason == "adaptive" else "fallback",
            reason=reason,
            estimated_rtf=r,
            recent_p90_rtf=p90,
            history_requests=n,
            predicted_audio_seconds=D,
            b_min_seconds=base,
            chunk_reserve_seconds=max(0, required - base - safety),
            safety_seconds=safety,
            required_pcm_seconds=required,
            prefix_segments=chosen,
            rtf_margin=self.multiplier,
            output_lookahead_seconds=self.lookahead,
            soundtouch_reserve_seconds=hold,
            measured_history_hold_seconds=measured,
        )

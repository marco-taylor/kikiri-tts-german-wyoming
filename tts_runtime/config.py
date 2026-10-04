"""Immutable startup configuration; reject rather than clamp."""

import dataclasses, decimal, os

NAME = "KIKIRI_TTS_SYNTH_SPEED"


@dataclasses.dataclass(frozen=True)
class Config:
    requested: str
    speed: float
    key: str

    @classmethod
    def from_env(cls, environ=None):
        env = os.environ if environ is None else environ
        raw = env.get(NAME, "1.00")
        try:
            value = decimal.Decimal(raw)
            if not value.is_finite() or not decimal.Decimal(
                "1.00"
            ) <= value <= decimal.Decimal("1.25"):
                raise ValueError()
            speed = float(value)
            if value > 1 and speed == 1:
                raise ValueError()
        except (decimal.InvalidOperation, ValueError, TypeError, OverflowError):
            raise ValueError(
                f"{NAME}={raw!r} ist ungültig. Erwartet wird eine endliche Dezimalzahl von 1.00 bis 1.25 (z. B. 1.175); keine automatische Korrektur."
            ) from None
        return cls(raw, speed, format(value.normalize(), "f"))


if __name__ == "__main__":
    import sys

    try:
        Config.from_env()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)

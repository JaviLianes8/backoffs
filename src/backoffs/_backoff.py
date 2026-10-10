"""The backoff delay iterator: it yields delays, it never sleeps or retries."""

from __future__ import annotations

import random
from collections.abc import Iterator

_JITTER_MODES = ("none", "full", "equal", "decorrelated")


def backoff(
    base: float = 0.1,
    factor: float = 2.0,
    cap: float = 30.0,
    jitter: str = "none",
    max_attempts: int | None = None,
    rng: random.Random | None = None,
) -> Iterator[float]:
    """Yield a backoff delay sequence in seconds, without ever sleeping.

    Delays grow geometrically (``base * factor ** attempt``) and are clamped to
    ``cap``. ``jitter`` reshapes each delay following the AWS "Exponential Backoff
    And Jitter" strategies: ``"none"`` yields the raw capped delay, ``"full"`` picks
    uniformly in ``[0, raw]``, ``"equal"`` in ``[raw / 2, raw]``, and
    ``"decorrelated"`` derives each delay from the previous one. ``max_attempts``
    bounds how many delays are produced (``None`` means an unbounded sequence).
    Pass a seeded ``rng`` for reproducible jittered sequences.

    The caller drives its own loop, for example ``for d in backoff(): time.sleep(d)``.
    """
    base = float(base)
    factor = float(factor)
    cap = float(cap)
    _validate(base, factor, cap, jitter, max_attempts)
    source = rng if rng is not None else random.Random()
    return _generate(base, factor, cap, jitter, max_attempts, source)


def _validate(
    base: float,
    factor: float,
    cap: float,
    jitter: str,
    max_attempts: int | None,
) -> None:
    if base <= 0.0:
        raise ValueError("base must be greater than 0")
    if factor < 1.0:
        raise ValueError("factor must be at least 1")
    if cap <= 0.0:
        raise ValueError("cap must be greater than 0")
    if cap < base:
        raise ValueError("cap must be greater than or equal to base")
    if jitter not in _JITTER_MODES:
        raise ValueError(f"jitter must be one of {_JITTER_MODES}, got {jitter!r}")
    if max_attempts is not None and max_attempts < 0:
        raise ValueError("max_attempts must be None or a non-negative integer")


def _generate(
    base: float,
    factor: float,
    cap: float,
    jitter: str,
    max_attempts: int | None,
    rng: random.Random,
) -> Iterator[float]:
    if jitter == "decorrelated":
        yield from _decorrelated(base, cap, max_attempts, rng)
        return

    raw = base
    attempt = 0
    while max_attempts is None or attempt < max_attempts:
        current = cap if raw > cap else raw
        if jitter == "none":
            yield current
        elif jitter == "full":
            yield rng.uniform(0.0, current)
        else:  # "equal"
            half = current / 2.0
            yield half + rng.uniform(0.0, half)
        # Grow by multiplication so a huge exponent overflows to a clamped cap
        # instead of raising OverflowError the way ``factor ** attempt`` would.
        if raw < cap:
            raw *= factor
        attempt += 1


def _decorrelated(
    base: float,
    cap: float,
    max_attempts: int | None,
    rng: random.Random,
) -> Iterator[float]:
    previous = base
    attempt = 0
    while max_attempts is None or attempt < max_attempts:
        upper = previous * 3.0
        value = min(cap, rng.uniform(base, upper))
        previous = value
        yield value
        attempt += 1

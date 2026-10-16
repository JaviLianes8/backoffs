"""The original 0.1 entry point, kept as a thin wrapper over :class:`Policy`."""

from __future__ import annotations

import math
import random
import sys
from collections.abc import Iterator

from ._errors import InvalidPolicyError
from ._jitter import DecorrelatedJitter, EqualJitter, FullJitter, Jitter, NoJitter
from ._policy import Policy
from ._schedules import Exponential
from ._validate import optional_count, preview

_JITTERS: dict[str, Jitter] = {
    "none": NoJitter(),
    "full": FullJitter(),
    "equal": EqualJitter(),
    "decorrelated": DecorrelatedJitter(),
}


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
    ``"decorrelated"`` yields ``min(cap, uniform(base, previous * 3))``.
    ``max_attempts`` bounds how many delays are produced (``None`` means an unbounded
    sequence). Pass a seeded ``rng`` for reproducible jittered sequences.

    Arguments are validated eagerly and raise :class:`~backoffs.InvalidPolicyError`
    (a ``ValueError``). For linear, Fibonacci or constant growth, time budgets and
    the gRPC and Google Cloud strategies, use :class:`~backoffs.Policy`.

    The caller drives its own loop, for example ``for d in backoff(): time.sleep(d)``.

    >>> list(backoff(base=1.0, cap=5.0, max_attempts=5))
    [1.0, 2.0, 4.0, 5.0, 5.0]
    """
    if not isinstance(jitter, str) or jitter not in _JITTERS:
        raise InvalidPolicyError(f"jitter must be one of {tuple(_JITTERS)}, got {preview(jitter)}")
    # 0.1 coerced with float() and accepted infinities and float counts; keep that.
    base, factor, cap = _as_float("base", base), _as_float("factor", factor), _as_float("cap", cap)
    if factor == math.inf:
        factor = sys.float_info.max
    if isinstance(max_attempts, float) and max_attempts >= 0 and math.isfinite(max_attempts):
        max_attempts = math.ceil(max_attempts)
    attempts = optional_count("max_attempts", max_attempts)
    policy = Policy(
        Exponential(base, factor),
        _JITTERS[jitter],
        cap=None if cap == math.inf else cap,
        max_retries=attempts,
    )
    return policy.delays(rng=rng)


def _as_float(name: str, value: float) -> float:
    try:
        return float(value)
    except (ValueError, OverflowError):
        # float() echoes the whole text it could not read; keep messages short.
        raise InvalidPolicyError(f"{name} must be a number, got {preview(value)}") from None

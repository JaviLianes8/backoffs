"""The original 0.1 entry point, kept as a thin wrapper over :class:`Policy`."""

from __future__ import annotations

import random
from collections.abc import Iterator

from ._errors import InvalidPolicyError
from ._jitter import DecorrelatedJitter, EqualJitter, FullJitter, Jitter, NoJitter
from ._policy import Policy
from ._schedules import Exponential
from ._validate import optional_count

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
    """
    if jitter not in _JITTERS:
        raise InvalidPolicyError(f"jitter must be one of {tuple(_JITTERS)}, got {jitter!r}")
    attempts = optional_count("max_attempts", max_attempts)
    policy = Policy(Exponential(base, factor), _JITTERS[jitter], cap=cap, max_retries=attempts)
    return policy.delays(rng=rng)

"""Frozen backoff policy: schedule + jitter + cap + retry and time budgets."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field

from ._delays import Delays
from ._errors import InvalidPolicyError
from ._jitter import AdditiveJitter, DecorrelatedJitter, Jitter, NoJitter, ProportionalJitter
from ._schedules import Exponential, Schedule
from ._validate import non_negative, optional_count, positive


@dataclass(frozen=True, slots=True)
class Policy:
    """An immutable, reusable description of a backoff schedule.

    Each delay is computed as ``jitter(min(cap, schedule delay))``. ``max_retries``
    bounds how many delays are produced (one delay per retry, so a call is attempted
    at most ``max_retries + 1`` times). ``max_elapsed`` is a time budget in seconds:
    a delay is only produced if ``elapsed + delay <= max_elapsed``, where ``elapsed``
    is the sum of earlier delays, or the clock reading when a clock is injected.
    ``None`` disables a bound (a schedule of zero delays bounded only by
    ``max_elapsed`` without a clock never ends). A policy never sleeps; call
    :meth:`delays` for a fresh iterator, or hand it to :func:`~backoffs.retry`.

    >>> from backoffs import Policy, Exponential
    >>> list(Policy(Exponential(base=1.0), cap=5.0, max_retries=5).delays())
    [1.0, 2.0, 4.0, 5.0, 5.0]
    """

    schedule: Schedule = field(default_factory=Exponential)
    jitter: Jitter = field(default_factory=NoJitter)
    cap: float | None = 30.0
    max_retries: int | None = None
    max_elapsed: float | None = None

    def __post_init__(self) -> None:
        if self.cap is not None:
            cap = positive("cap", self.cap)
            if cap < self.schedule.first:
                raise InvalidPolicyError(
                    f"cap must be greater than or equal to the first delay "
                    f"({self.schedule.first!r}), got {self.cap!r}"
                )
            object.__setattr__(self, "cap", cap)
        object.__setattr__(self, "max_retries", optional_count("max_retries", self.max_retries))
        if self.max_elapsed is not None:
            elapsed = non_negative("max_elapsed", self.max_elapsed)
            object.__setattr__(self, "max_elapsed", elapsed)
        if isinstance(self.jitter, DecorrelatedJitter) and self.schedule.first <= 0.0:
            raise InvalidPolicyError("decorrelated jitter needs a first delay greater than 0")

    def delays(
        self,
        *,
        rng: random.Random | None = None,
        clock: Callable[[], float] | None = None,
    ) -> Delays:
        """Return a fresh delay iterator for this policy.

        Pass a seeded ``rng`` for reproducible jitter. Pass a monotonic ``clock``
        (such as :func:`time.monotonic`) to measure ``max_elapsed`` in real time,
        including the time spent in your own calls, instead of summing delays.
        """
        return Delays(self, rng=rng, clock=clock)

    @classmethod
    def grpc(cls, *, max_retries: int | None = None, max_elapsed: float | None = None) -> Policy:
        """gRPC connection backoff defaults (``doc/connection-backoff.md``).

        ``INITIAL_BACKOFF = 1 s``, ``MULTIPLIER = 1.6``, ``JITTER = 0.2``,
        ``MAX_BACKOFF = 120 s``; the first wait is the plain initial backoff.
        """
        return cls(
            Exponential(base=1.0, factor=1.6),
            ProportionalJitter(fraction=0.2, jitter_first=False),
            cap=120.0,
            max_retries=max_retries,
            max_elapsed=max_elapsed,
        )

    @classmethod
    def google_cloud(
        cls,
        *,
        maximum_backoff: float = 32.0,
        max_retries: int | None = None,
        max_elapsed: float | None = None,
    ) -> Policy:
        """Google Cloud truncated exponential backoff.

        ``wait = min((2 ** n) + random_number_milliseconds, maximum_backoff)`` with
        a random part of up to 1000 ms; ``maximum_backoff`` is typically 32 or 64 s.
        """
        return cls(
            Exponential(base=1.0, factor=2.0),
            AdditiveJitter(amount=1.0),
            cap=maximum_backoff,
            max_retries=max_retries,
            max_elapsed=max_elapsed,
        )

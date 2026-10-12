"""Jitter strategies: how a raw (already capped) delay becomes the delay you sleep.

Formulas, with ``raw = min(cap, schedule delay)``:

* :class:`FullJitter`, :class:`EqualJitter` and :class:`DecorrelatedJitter` follow the
  AWS Architecture Blog post "Exponential Backoff And Jitter" (Marc Brooker, 2015).
* :class:`ProportionalJitter` is the ``UniformRandom(-JITTER * b, JITTER * b)`` term
  of the gRPC connection backoff spec (``doc/connection-backoff.md``).
* :class:`AdditiveJitter` is Google Cloud's truncated exponential backoff,
  ``min((2 ** n) + random_number_milliseconds, maximum_backoff)``.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Protocol

from ._errors import InvalidPolicyError
from ._validate import finite, non_negative


class Jitter(Protocol):
    """A strategy that turns one raw delay into the delay to sleep."""

    def apply(
        self,
        raw: float,
        *,
        attempt: int,
        previous: float,
        base: float,
        cap: float | None,
        rng: random.Random,
    ) -> float:
        """Return the delay for retry ``attempt`` (0 based).

        ``previous`` is the delay this strategy returned last time (``base`` before
        the first retry), ``base`` is the schedule's first raw delay and ``cap`` the
        policy cap, if any.
        """
        ...


@dataclass(frozen=True, slots=True)
class NoJitter:
    """``sleep = raw``: the deterministic capped schedule."""

    def apply(self, raw: float, **_: object) -> float:
        return raw


@dataclass(frozen=True, slots=True)
class FullJitter:
    """AWS Full Jitter: ``sleep = random_between(0, raw)``. Mean ``raw / 2``."""

    def apply(self, raw: float, *, rng: random.Random, **_: object) -> float:
        return rng.uniform(0.0, raw)


@dataclass(frozen=True, slots=True)
class EqualJitter:
    """AWS Equal Jitter: ``sleep = raw / 2 + random_between(0, raw / 2)``. Mean ``3 raw / 4``."""

    def apply(self, raw: float, *, rng: random.Random, **_: object) -> float:
        half = raw / 2.0
        return half + rng.uniform(0.0, half)


@dataclass(frozen=True, slots=True)
class DecorrelatedJitter:
    """AWS Decorrelated Jitter: ``sleep = min(cap, random_between(base, sleep * 3))``.

    ``sleep`` starts at ``base``. Each delay derives from the previous one, so the
    growth schedule only supplies ``base`` (its first delay); the ``multiplier`` is
    the ``3`` of the published formula. Without a cap the ``min`` is skipped.
    """

    multiplier: float = 3.0

    def __post_init__(self) -> None:
        multiplier = finite("multiplier", self.multiplier)
        if multiplier < 1.0:
            raise InvalidPolicyError(f"multiplier must be at least 1, got {self.multiplier!r}")
        object.__setattr__(self, "multiplier", multiplier)

    def apply(
        self,
        raw: float,
        *,
        previous: float,
        base: float,
        cap: float | None,
        rng: random.Random,
        **_: object,
    ) -> float:
        value = rng.uniform(base, previous * self.multiplier)
        return value if cap is None else min(cap, value)


@dataclass(frozen=True, slots=True)
class ProportionalJitter:
    """gRPC style: ``sleep = raw + random_between(-fraction * raw, fraction * raw)``.

    The result may exceed the cap by up to ``fraction``, exactly as in the gRPC spec,
    where jitter is added after ``Min(current_backoff * MULTIPLIER, MAX_BACKOFF)``.
    gRPC waits the plain ``INITIAL_BACKOFF`` first: set ``jitter_first=False`` for that.
    """

    fraction: float = 0.2
    jitter_first: bool = True

    def __post_init__(self) -> None:
        fraction = non_negative("fraction", self.fraction)
        if fraction > 1.0:
            raise InvalidPolicyError(f"fraction must be at most 1, got {self.fraction!r}")
        object.__setattr__(self, "fraction", fraction)

    def apply(self, raw: float, *, attempt: int, rng: random.Random, **_: object) -> float:
        if attempt == 0 and not self.jitter_first:
            return raw
        spread = self.fraction * raw
        return raw + rng.uniform(-spread, spread)


@dataclass(frozen=True, slots=True)
class AdditiveJitter:
    """Google Cloud style: ``sleep = min(raw + random_between(0, amount), cap)``.

    ``amount`` is in seconds; Google's guidance uses up to 1000 milliseconds.
    """

    amount: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", non_negative("amount", self.amount))

    def apply(self, raw: float, *, cap: float | None, rng: random.Random, **_: object) -> float:
        value = raw + rng.uniform(0.0, self.amount)
        return value if cap is None else min(value, cap)

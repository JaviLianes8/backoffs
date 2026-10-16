"""Jitter strategies: how a raw (already capped) delay becomes the delay you sleep.

Full, equal and decorrelated jitter follow the AWS Architecture Blog post "Exponential
Backoff And Jitter" (Marc Brooker, 2015); proportional jitter is the gRPC connection
backoff spec; additive jitter is Google Cloud's truncated exponential backoff.
"""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass
from typing import Protocol

from ._errors import InvalidPolicyError
from ._validate import finite, non_negative, preview

_CEILING = sys.float_info.max


class Jitter(Protocol):
    """A strategy that turns one raw delay into the delay to sleep.

    Any object with this ``apply`` method fits; accept ``**_`` for the keyword
    arguments you do not use. The result must be a finite number ``>= 0``.

    >>> import random
    >>> from backoffs import Constant, Policy
    >>> class Halve:
    ...     def apply(self, raw: float, **_: object) -> float:
    ...         return raw / 2
    >>> list(Policy(Constant(4.0), Halve(), max_retries=2).delays())
    [2.0, 2.0]
    """

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
    """``sleep = raw``: the deterministic capped schedule.

    >>> from backoffs import Exponential, NoJitter, Policy
    >>> list(Policy(Exponential(1.0), NoJitter(), cap=4.0, max_retries=4).delays())
    [1.0, 2.0, 4.0, 4.0]
    """

    def apply(self, raw: float, **_: object) -> float:
        return raw


@dataclass(frozen=True, slots=True)
class FullJitter:
    """AWS Full Jitter: ``sleep = random_between(0, raw)``. Mean ``raw / 2``.

    >>> import random
    >>> from backoffs import Constant, FullJitter, Policy
    >>> delays = Policy(Constant(4.0), FullJitter(), max_retries=50).delays(rng=random.Random(1))
    >>> all(0.0 <= d <= 4.0 for d in delays)
    True
    """

    def apply(self, raw: float, *, rng: random.Random, **_: object) -> float:
        return rng.uniform(0.0, raw)


@dataclass(frozen=True, slots=True)
class EqualJitter:
    """AWS Equal Jitter: ``sleep = raw / 2 + random_between(0, raw / 2)``. Mean ``3 raw / 4``.

    >>> import random
    >>> from backoffs import Constant, EqualJitter, Policy
    >>> delays = Policy(Constant(4.0), EqualJitter(), max_retries=50).delays(rng=random.Random(1))
    >>> all(2.0 <= d <= 4.0 for d in delays)
    True
    """

    def apply(self, raw: float, *, rng: random.Random, **_: object) -> float:
        half = raw / 2.0
        return half + rng.uniform(0.0, half)


@dataclass(frozen=True, slots=True)
class DecorrelatedJitter:
    """AWS Decorrelated Jitter: ``sleep = min(cap, random_between(base, sleep * 3))``.

    ``sleep`` starts at ``base``. Each delay derives from the previous one, so the
    growth schedule only supplies ``base`` (its first delay); the ``multiplier`` is
    the ``3`` of the published formula. Without a cap the ``min`` is skipped.
    ``multiplier`` must be a finite number ``>= 1``.

    >>> import random
    >>> from backoffs import DecorrelatedJitter, Exponential, Policy
    >>> policy = Policy(Exponential(1.0), DecorrelatedJitter(), cap=10.0, max_retries=50)
    >>> all(1.0 <= d <= 10.0 for d in policy.delays(rng=random.Random(1)))
    True
    """

    multiplier: float = 3.0

    def __post_init__(self) -> None:
        multiplier = finite("multiplier", self.multiplier)
        if multiplier < 1.0:
            raise InvalidPolicyError(f"multiplier must be at least 1, got {preview(multiplier)}")
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
        # Saturate so an uncapped chain stays finite instead of reaching infinity.
        upper = min(previous * self.multiplier, _CEILING)
        value = rng.uniform(base, upper)
        return value if cap is None else min(cap, value)


@dataclass(frozen=True, slots=True)
class ProportionalJitter:
    """gRPC style: ``sleep = raw + random_between(-fraction * raw, fraction * raw)``.

    The result may exceed the cap by up to ``fraction``, exactly as in the gRPC spec,
    where jitter is added after ``Min(current_backoff * MULTIPLIER, MAX_BACKOFF)``.
    gRPC waits the plain ``INITIAL_BACKOFF`` first: set ``jitter_first=False`` for that.
    ``fraction`` must be between 0 and 1.

    >>> import random
    >>> from backoffs import Constant, Policy, ProportionalJitter
    >>> jitter = ProportionalJitter(0.2, jitter_first=False)
    >>> delays = list(Policy(Constant(10.0), jitter, max_retries=50).delays(rng=random.Random(1)))
    >>> delays[0], all(8.0 <= d <= 12.0 for d in delays)
    (10.0, True)
    """

    fraction: float = 0.2
    jitter_first: bool = True

    def __post_init__(self) -> None:
        fraction = non_negative("fraction", self.fraction)
        if fraction > 1.0:
            raise InvalidPolicyError(f"fraction must be at most 1, got {preview(fraction)}")
        if not isinstance(self.jitter_first, bool):
            raise InvalidPolicyError("jitter_first must be a bool")
        object.__setattr__(self, "fraction", fraction)

    def apply(self, raw: float, *, attempt: int, rng: random.Random, **_: object) -> float:
        if attempt == 0 and not self.jitter_first:
            return raw
        spread = self.fraction * raw
        return min(raw + rng.uniform(-spread, spread), _CEILING)


@dataclass(frozen=True, slots=True)
class AdditiveJitter:
    """Google Cloud style: ``sleep = min(raw + random_between(0, amount), cap)``.

    ``amount`` is in seconds (finite, ``>= 0``); Google's guidance uses up to 1000
    milliseconds.

    >>> import random
    >>> from backoffs import AdditiveJitter, Constant, Policy
    >>> policy = Policy(Constant(2.0), AdditiveJitter(1.0), cap=2.5, max_retries=50)
    >>> all(2.0 <= d <= 2.5 for d in policy.delays(rng=random.Random(1)))
    True
    """

    amount: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", non_negative("amount", self.amount))

    def apply(self, raw: float, *, cap: float | None, rng: random.Random, **_: object) -> float:
        value = min(raw + rng.uniform(0.0, self.amount), _CEILING)
        return value if cap is None else min(value, cap)

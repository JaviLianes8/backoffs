"""Growth schedules: the raw, uncapped, unjittered delay for each retry."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

from ._errors import InvalidPolicyError
from ._validate import finite, non_negative, positive, preview

# Growth saturates here instead of reaching infinity, so an uncapped schedule still
# yields finite floats that jitter can scale without producing NaN.
_CEILING = sys.float_info.max


class Schedule(Protocol):
    """Anything that can produce an endless sequence of raw delays in seconds.

    Any object with a ``first`` attribute and a ``raw()`` method fits. Raw delays
    must be finite numbers ``>= 0``, and ``raw()`` must never end.

    >>> import itertools
    >>> from backoffs import Policy
    >>> class Squares:
    ...     first = 1.0
    ...     def raw(self):
    ...         return (float(n * n) for n in itertools.count(1))
    >>> list(Policy(Squares(), max_retries=4).delays())
    [1.0, 4.0, 9.0, 16.0]
    """

    @property
    def first(self) -> float:
        """The raw delay before the first retry (``base`` for decorrelated jitter)."""
        ...

    def raw(self) -> Iterator[float]:
        """Yield the raw delays forever, starting with :attr:`first`."""
        ...


def _saturate(value: float) -> float:
    return _CEILING if value > _CEILING else value


@dataclass(frozen=True, slots=True)
class Constant:
    """The same delay every time: ``delay, delay, delay, ...`` (``delay >= 0``).

    >>> import itertools
    >>> from backoffs import Constant
    >>> list(itertools.islice(Constant(1.5).raw(), 3))
    [1.5, 1.5, 1.5]
    """

    delay: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "delay", non_negative("delay", self.delay))

    @property
    def first(self) -> float:
        return self.delay

    def raw(self) -> Iterator[float]:
        while True:
            yield self.delay


@dataclass(frozen=True, slots=True)
class Linear:
    """Arithmetic growth: retry ``n`` (from 0) waits ``start + step * n``.

    ``start`` and ``step`` are finite numbers ``>= 0``.

    >>> import itertools
    >>> from backoffs import Linear
    >>> list(itertools.islice(Linear(1.0, 0.5).raw(), 4))
    [1.0, 1.5, 2.0, 2.5]
    """

    start: float = 1.0
    step: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", non_negative("start", self.start))
        object.__setattr__(self, "step", non_negative("step", self.step))

    @property
    def first(self) -> float:
        return self.start

    def raw(self) -> Iterator[float]:
        n = 0
        while True:
            yield _saturate(self.start + self.step * n)
            n += 1


@dataclass(frozen=True, slots=True)
class Exponential:
    """Geometric growth: retry ``n`` (from 0) waits ``base * factor ** n``.

    With ``factor=2`` this is the ``base * 2 ** attempt`` term of the AWS
    Architecture Blog post "Exponential Backoff And Jitter". ``base`` must be
    ``> 0`` and ``factor >= 1``, both finite; growth saturates at the largest float.

    >>> import itertools
    >>> from backoffs import Exponential
    >>> list(itertools.islice(Exponential(0.5, 3.0).raw(), 4))
    [0.5, 1.5, 4.5, 13.5]
    """

    base: float = 0.1
    factor: float = 2.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "base", positive("base", self.base))
        factor = finite("factor", self.factor)
        if factor < 1.0:
            raise InvalidPolicyError(f"factor must be at least 1, got {preview(factor)}")
        object.__setattr__(self, "factor", factor)

    @property
    def first(self) -> float:
        return self.base

    def raw(self) -> Iterator[float]:
        value = self.base
        while True:
            yield value
            # Multiplying (instead of computing factor ** n) cannot raise OverflowError.
            value = _saturate(value * self.factor)


@dataclass(frozen=True, slots=True)
class Fibonacci:
    """Fibonacci growth: ``base * F(n + 1)``, so ``base, base, 2b, 3b, 5b, 8b, ...``.

    ``base`` must be a finite number ``> 0``.

    >>> import itertools
    >>> from backoffs import Fibonacci
    >>> list(itertools.islice(Fibonacci(0.5).raw(), 6))
    [0.5, 0.5, 1.0, 1.5, 2.5, 4.0]
    """

    base: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "base", positive("base", self.base))

    @property
    def first(self) -> float:
        return self.base

    def raw(self) -> Iterator[float]:
        current, following = 1.0, 1.0
        while True:
            yield _saturate(self.base * current)
            current, following = following, _saturate(current + following)

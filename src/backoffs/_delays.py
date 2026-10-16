"""The stateful delay iterator produced by :meth:`Policy.delays`."""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING

from ._errors import InvalidPolicyError
from ._validate import non_negative, preview

if TYPE_CHECKING:
    from ._policy import Policy


class Delays(Iterator[float]):
    """Iterator of delays in seconds for one retry sequence. It never sleeps.

    Besides iterating, it records progress (:attr:`retries`, :attr:`total`), says why
    it stopped (:attr:`stop_reason`) and accepts a server hint through
    :meth:`floor_next`, for example a parsed ``Retry-After`` header. Get one from
    :meth:`Policy.delays`; once stopped it stays stopped.

    >>> from backoffs import Constant, Policy
    >>> delays = Policy(Constant(2.0), max_elapsed=5.0).delays()
    >>> list(delays), delays.total, delays.stop_reason
    ([2.0, 2.0], 4.0, 'max_elapsed')
    >>> delays = Policy(Constant(1.0), max_retries=2).delays()
    >>> delays.floor_next(30.0)
    >>> list(delays)
    [30.0, 1.0]
    """

    def __init__(
        self,
        policy: Policy,
        *,
        rng: random.Random | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        from ._policy import Policy

        if not isinstance(policy, Policy):
            raise InvalidPolicyError(f"policy must be a Policy, got {preview(policy)}")
        if rng is not None and not isinstance(rng, random.Random):
            raise InvalidPolicyError(f"rng must be a random.Random, got {preview(rng)}")
        if clock is not None and not callable(clock):
            raise InvalidPolicyError(f"clock must be callable, got {preview(clock)}")
        self.policy = policy
        self._rng = rng if rng is not None else random.Random()
        self._clock = clock
        self._start = clock() if clock is not None else 0.0
        self._raw = policy.schedule.raw()
        self._base = policy.schedule.first
        self._previous = self._base
        self._floor = 0.0
        self.retries = 0
        """Number of delays produced so far."""
        self.total = 0.0
        """Sum of the delays produced so far, in seconds."""
        self.stop_reason: str | None = None
        """``None`` while running, then ``"max_retries"`` or ``"max_elapsed"``."""

    @property
    def elapsed(self) -> float:
        """Budget consumed: clock time since creation, or :attr:`total` without a clock.

        A clock reading that is not a finite number counts as an exhausted budget.
        """
        if self._clock is None:
            return self.total
        return self._clock() - self._start

    def floor_next(self, seconds: float) -> None:
        """Make the next delay at least ``seconds`` (a server hint wins over the cap).

        Calling it twice before the next delay keeps the larger floor. The floored
        delay still counts against ``max_elapsed``: if it does not fit, iteration stops.
        """
        self._floor = max(self._floor, non_negative("seconds", seconds))

    def __iter__(self) -> Delays:
        return self

    def __next__(self) -> float:
        policy = self.policy
        if self.stop_reason is not None:
            raise StopIteration
        if policy.max_retries is not None and self.retries >= policy.max_retries:
            return self._stop("max_retries")
        raw = next(self._raw, None)
        if raw is None:
            raise InvalidPolicyError("the schedule ended; a schedule must yield forever")
        # Built-in schedules and jitters always pass; this guards custom ones.
        raw = non_negative("schedule delay", raw)
        if policy.cap is not None and raw > policy.cap:
            raw = policy.cap
        delay = policy.jitter.apply(
            raw,
            attempt=self.retries,
            previous=self._previous,
            base=self._base,
            cap=policy.cap,
            rng=self._rng,
        )
        delay = non_negative("jitter delay", delay)
        self._previous = delay
        delay = max(delay, self._floor)
        self._floor = 0.0
        if policy.max_elapsed is not None:
            spent = self.elapsed
            # NaN compares false, so a broken clock must not keep the budget open.
            if not math.isfinite(spent) or spent + delay > policy.max_elapsed:
                return self._stop("max_elapsed")
        self.retries += 1
        self.total += delay
        return delay

    def _stop(self, reason: str) -> float:
        self.stop_reason = reason
        raise StopIteration

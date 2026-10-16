"""The retry loop state shared by :func:`retry` and :func:`aretry`."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeAlias

from ._delays import Delays
from ._errors import InvalidPolicyError, RetryError
from ._policy import Policy
from ._validate import callable_or_raise, preview

ExceptionTypes: TypeAlias = type[BaseException] | tuple[type[BaseException], ...]


@dataclass(frozen=True, slots=True)
class RetryState:
    """What ``on_retry`` receives just before each sleep.

    >>> from backoffs import Constant, Policy, RetryState, retry
    >>> seen: list[RetryState] = []
    >>> calls = iter([ValueError("a"), ValueError("b"), "done"])
    >>> def flaky() -> str:
    ...     item = next(calls)
    ...     if isinstance(item, Exception):
    ...         raise item
    ...     return item
    >>> retry(flaky, Policy(Constant(0.5)), on_retry=seen.append, sleep=lambda s: None)
    'done'
    >>> [(s.attempt, s.delay, str(s.exception)) for s in seen]
    [(1, 0.5, 'a'), (2, 0.5, 'b')]
    """

    attempt: int
    """The call that just failed, counting from 1."""
    delay: float
    """Seconds about to be slept before the next call."""
    elapsed: float
    """Seconds since the first call, measured by the injected clock."""
    exception: BaseException
    """The exception the failed call raised."""


@dataclass(slots=True)
class Controller:
    policy: Policy
    retry_on: ExceptionTypes
    giveup: Callable[[BaseException], bool] | None
    retry_after: Callable[[BaseException], float | None] | None
    on_retry: Callable[[RetryState], None] | None
    clock: Callable[[], float]
    rng: random.Random | None
    delays: Delays = field(init=False)
    attempts: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.policy, Policy):
            raise InvalidPolicyError(f"policy must be a Policy, got {preview(self.policy)}")
        types = self.retry_on if isinstance(self.retry_on, tuple) else (self.retry_on,)
        if not all(isinstance(t, type) and issubclass(t, BaseException) for t in types):
            raise InvalidPolicyError("retry_on must be an exception type or a tuple of them")
        hooks: dict[str, object] = {
            "giveup": self.giveup,
            "retry_after": self.retry_after,
            "on_retry": self.on_retry,
        }
        for name, hook in hooks.items():
            if hook is not None:
                callable_or_raise(name, hook)
        callable_or_raise("clock", self.clock)
        self.delays = self.policy.delays(rng=self.rng, clock=self.clock)

    def next_delay(self, exc: BaseException) -> float | None:
        """Return the delay before the next call, or ``None`` to re-raise ``exc``.

        Raises :class:`RetryError` when the policy is exhausted.
        """
        self.attempts += 1
        if not isinstance(exc, self.retry_on):
            return None
        if self.giveup is not None and self.giveup(exc):
            return None
        if self.retry_after is not None:
            hint = self.retry_after(exc)
            if hint is not None:
                self.delays.floor_next(hint)
        delay = next(self.delays, None)
        if delay is None:
            raise RetryError(
                attempts=self.attempts,
                elapsed=self.delays.elapsed,
                reason=self.delays.stop_reason or "max_retries",
                last_exception=exc,
            ) from exc
        if self.on_retry is not None:
            self.on_retry(RetryState(self.attempts, delay, self.delays.elapsed, exc))
        return delay

"""Retry helpers (sync and async) that drive a :class:`Policy` with injectable time."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TypeAlias, TypeVar

from ._delays import Delays
from ._errors import RetryError
from ._policy import Policy

T = TypeVar("T")
ExceptionTypes: TypeAlias = type[BaseException] | tuple[type[BaseException], ...]


@dataclass(frozen=True, slots=True)
class RetryState:
    """What ``on_retry`` receives just before each sleep."""

    attempt: int
    """The call that just failed, counting from 1."""
    delay: float
    """Seconds about to be slept before the next call."""
    elapsed: float
    """Seconds since the first call, measured by the injected clock."""
    exception: BaseException
    """The exception the failed call raised."""


@dataclass(slots=True)
class _Controller:
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


def retry(
    fn: Callable[[], T],
    policy: Policy | None = None,
    *,
    retry_on: ExceptionTypes = Exception,
    giveup: Callable[[BaseException], bool] | None = None,
    retry_after: Callable[[BaseException], float | None] | None = None,
    on_retry: Callable[[RetryState], None] | None = None,
    sleep: Callable[[float], object] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    rng: random.Random | None = None,
) -> T:
    """Call ``fn()`` until it returns, sleeping between failures per ``policy``.

    * Only exceptions matching ``retry_on`` are retried; others propagate unchanged.
    * ``giveup(exc)`` returning true also propagates ``exc`` unchanged.
    * ``retry_after(exc)`` may return a server-requested wait in seconds (see
      :func:`~backoffs.parse_retry_after`); it becomes a floor for the next delay.
      It must return ``None`` or a finite number of seconds ``>= 0``; anything else
      raises :class:`~backoffs.InvalidPolicyError` chained to the failure.
    * ``on_retry`` is called with a :class:`RetryState` before each sleep.
    * When the policy runs out (``max_retries`` or ``max_elapsed``, the latter
      measured with ``clock``), :class:`~backoffs.RetryError` is raised from the last
      exception.

    The default policy is ``Policy(max_retries=5)``. ``sleep``, ``clock`` and ``rng``
    are injectable so tests never wait for real.
    """
    ctl = _Controller(
        Policy(max_retries=5) if policy is None else policy,
        retry_on,
        giveup,
        retry_after,
        on_retry,
        clock,
        rng,
    )
    while True:
        try:
            return fn()
        except BaseException as exc:
            delay = ctl.next_delay(exc)
            if delay is None:
                raise
        sleep(delay)


async def aretry(
    fn: Callable[[], Awaitable[T]],
    policy: Policy | None = None,
    *,
    retry_on: ExceptionTypes = Exception,
    giveup: Callable[[BaseException], bool] | None = None,
    retry_after: Callable[[BaseException], float | None] | None = None,
    on_retry: Callable[[RetryState], None] | None = None,
    sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
    clock: Callable[[], float] = time.monotonic,
    rng: random.Random | None = None,
) -> T:
    """Async twin of :func:`retry`: awaits ``fn()`` and ``sleep(delay)``.

    ``asyncio.CancelledError`` is a ``BaseException``, so with the default
    ``retry_on=Exception`` cancellation is never swallowed.
    """
    ctl = _Controller(
        Policy(max_retries=5) if policy is None else policy,
        retry_on,
        giveup,
        retry_after,
        on_retry,
        clock,
        rng,
    )
    while True:
        try:
            return await fn()
        except BaseException as exc:
            delay = ctl.next_delay(exc)
            if delay is None:
                raise
        await sleep(delay)

"""Retry helpers (sync and async) that drive a :class:`Policy` with injectable time."""

from __future__ import annotations

import asyncio
import inspect
import random
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from ._controller import Controller, ExceptionTypes, RetryState
from ._errors import InvalidPolicyError
from ._policy import Policy
from ._validate import callable_or_raise, preview

T = TypeVar("T")


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
    are injectable so tests never wait for real. Invalid arguments raise
    :class:`~backoffs.InvalidPolicyError` before ``fn`` is first called.

    >>> from backoffs import Exponential, Policy, retry
    >>> attempts, slept = [], []
    >>> def connect() -> str:
    ...     attempts.append(1)
    ...     if len(attempts) < 3:
    ...         raise ConnectionError("refused")
    ...     return "connected"
    >>> retry(connect, Policy(Exponential(0.5), max_retries=5), sleep=slept.append)
    'connected'
    >>> slept
    [0.5, 1.0]
    """
    callable_or_raise("fn", fn)
    callable_or_raise("sleep", sleep)
    ctl = Controller(
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
    ``retry_on=Exception`` cancellation is never swallowed. ``fn`` and ``sleep`` must
    return awaitables; a result that is not one raises
    :class:`~backoffs.InvalidPolicyError` the first time, and is never retried.

    >>> import asyncio
    >>> from backoffs import Constant, Policy, aretry
    >>> attempts = []
    >>> async def fetch() -> str:
    ...     attempts.append(1)
    ...     if len(attempts) < 2:
    ...         raise TimeoutError
    ...     return "ok"
    >>> async def no_wait(seconds: float) -> None:
    ...     pass
    >>> asyncio.run(aretry(fetch, Policy(Constant(1.0)), sleep=no_wait))
    'ok'
    """
    callable_or_raise("fn", fn)
    callable_or_raise("sleep", sleep)
    ctl = Controller(
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
            pending = fn()
            if inspect.isawaitable(pending):
                return await pending
        except BaseException as exc:
            delay = ctl.next_delay(exc)
            if delay is None:
                raise
        else:
            raise InvalidPolicyError(f"fn must return an awaitable, got {preview(pending)}")
        nap = sleep(delay)
        if not inspect.isawaitable(nap):
            raise InvalidPolicyError(f"sleep must return an awaitable, got {preview(nap)}")
        await nap

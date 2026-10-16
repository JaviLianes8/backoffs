"""aretry refuses plain functions where awaitables belong, and clocks must return numbers."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from backoffs import Constant, InvalidPolicyError, Policy, RetryError, aretry, retry


def test_a_plain_function_is_refused_at_once_and_never_retried() -> None:
    calls: list[int] = []

    def fetch() -> str:
        calls.append(1)
        return "ok"

    with pytest.raises(InvalidPolicyError, match="fn must return an awaitable"):
        asyncio.run(aretry(fetch, sleep=asyncio.sleep))  # type: ignore[arg-type]
    assert calls == [1]


def test_a_blocking_sleep_is_refused_before_it_blocks() -> None:
    slept: list[float] = []

    async def failing() -> str:
        raise OSError("down")

    def blocking(seconds: float) -> None:
        slept.append(seconds)

    with pytest.raises(InvalidPolicyError, match="sleep must return an awaitable"):
        asyncio.run(aretry(failing, sleep=blocking))  # type: ignore[arg-type]
    assert slept == [0.1]  # called once, and its result refused


def test_a_coroutine_factory_that_raises_before_awaiting_is_still_retried() -> None:
    calls: list[int] = []

    def factory() -> Any:
        calls.append(1)
        if len(calls) < 3:
            raise OSError("not yet")

        async def done() -> str:
            return "ok"

        return done()

    async def no_wait(seconds: float) -> None:
        pass

    assert asyncio.run(aretry(factory, Policy(Constant(0.0)), sleep=no_wait)) == "ok"
    assert len(calls) == 3


@pytest.mark.parametrize("reading", [None, "12", True, object()])
def test_a_clock_must_return_a_number(reading: object) -> None:
    def fail() -> None:
        raise OSError

    with pytest.raises(InvalidPolicyError, match="clock must return a number"):
        retry(fail, Policy(Constant(0.0), max_retries=2), clock=lambda: reading,  # type: ignore[arg-type, return-value]
              sleep=lambda s: None)  # fmt: skip
    with pytest.raises(InvalidPolicyError, match="clock must return a number"):
        Policy().delays(clock=lambda: reading)  # type: ignore[arg-type, return-value]


def test_integer_clocks_are_fine() -> None:
    ticks = iter(range(100))
    delays = Policy(Constant(1.0), max_elapsed=10.0).delays(clock=lambda: next(ticks))
    assert len(list(delays)) >= 1
    assert isinstance(time.monotonic(), float)


def test_a_clock_reading_too_large_for_a_float_spends_the_budget() -> None:
    readings = iter([0, 10**400])
    delays = Policy(Constant(1.0), max_elapsed=5.0).delays(clock=lambda: next(readings))
    assert next(delays, None) is None and delays.stop_reason == "max_elapsed"


@pytest.mark.parametrize("hint", [False, "", [], -1, float("nan")])
def test_a_bad_retry_after_hint_is_refused_by_both_helpers(hint: object) -> None:
    def fail() -> None:
        raise OSError("busy")

    async def afail() -> None:
        raise OSError("busy")

    async def no_wait(seconds: float) -> None:
        pass

    with pytest.raises(InvalidPolicyError):
        retry(fail, retry_after=lambda exc: hint, sleep=lambda s: None)  # type: ignore[arg-type, return-value]
    with pytest.raises(InvalidPolicyError):
        asyncio.run(aretry(afail, retry_after=lambda exc: hint, sleep=no_wait))  # type: ignore[arg-type, return-value]


def test_a_zero_retry_after_hint_retries_normally() -> None:
    slept: list[float] = []
    with pytest.raises(RetryError):
        retry(lambda: 1 / 0, Policy(Constant(0.5), max_retries=2), retry_after=lambda exc: 0,
              sleep=slept.append)  # fmt: skip
    assert slept == [0.5, 0.5]

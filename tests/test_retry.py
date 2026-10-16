from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest

from backoffs import Constant, Exponential, Policy, RetryError, RetryState, aretry, retry


class Flaky:
    """Raises the given exceptions in order, then returns ``"ok"``."""

    def __init__(self, *errors: BaseException) -> None:
        self.errors = list(errors)
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return "ok"


class Time:
    """A fake clock that a fake sleep advances."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def run(fn: Callable[[], str], policy: Policy, t: Time, **kwargs: object) -> str:
    return retry(fn, policy, sleep=t.sleep, clock=t.clock, **kwargs)  # type: ignore[arg-type]


def test_success_on_the_first_call_never_sleeps() -> None:
    t = Time()
    assert run(Flaky(), Policy(), t) == "ok"
    assert t.slept == []


def test_retries_until_success_sleeping_the_schedule() -> None:
    t, fn = Time(), Flaky(OSError(), OSError(), OSError())
    assert run(fn, Policy(Exponential(1.0), max_retries=5), t) == "ok"
    assert fn.calls == 4
    assert t.slept == [1.0, 2.0, 4.0]


def test_exhausting_max_retries_raises_retry_error_from_the_last_exception() -> None:
    t = Time()
    last = OSError("third")
    with pytest.raises(RetryError) as caught:
        run(Flaky(OSError(), OSError(), last), Policy(Constant(1.0), max_retries=2), t)
    error = caught.value
    assert (error.attempts, error.reason, error.elapsed) == (3, "max_retries", 2.0)
    assert error.last_exception is last and error.__cause__ is last
    assert "3 attempt(s)" in str(error) and "OSError" in str(error)
    assert "third" not in str(error)  # the text of the last error may hold secrets


def test_max_elapsed_uses_the_clock_including_call_time() -> None:
    t = Time()

    def slow() -> str:
        t.now += 3.0
        raise TimeoutError

    with pytest.raises(RetryError) as caught:
        run(slow, Policy(Constant(1.0), max_elapsed=8.0), t)
    # calls fail at t=3 and t=7 (3 + 1 <= 8, 7 + 1 <= 8), then at t=11 (11 + 1 > 8)
    assert caught.value.reason == "max_elapsed"
    assert caught.value.attempts == 3
    assert t.slept == [1.0, 1.0]


def test_exceptions_outside_retry_on_propagate_unchanged() -> None:
    t, fn = Time(), Flaky(KeyError("boom"))
    with pytest.raises(KeyError):
        run(fn, Policy(), t, retry_on=OSError)
    assert fn.calls == 1 and t.slept == []


def test_retry_on_accepts_a_tuple() -> None:
    t, fn = Time(), Flaky(OSError(), KeyError())
    assert run(fn, Policy(), t, retry_on=(OSError, KeyError)) == "ok"


def test_giveup_propagates_the_exception_unchanged() -> None:
    t, fn = Time(), Flaky(OSError(1, "fatal"))
    with pytest.raises(OSError, match="fatal"):
        run(fn, Policy(), t, giveup=lambda e: "fatal" in str(e))
    assert t.slept == []


def test_base_exceptions_are_not_retried_by_default() -> None:
    t, fn = Time(), Flaky(KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        run(fn, Policy(), t)
    assert fn.calls == 1


def test_retry_after_hint_is_a_floor_for_the_next_delay() -> None:
    t = Time()
    hints = {"slow": 7.0}

    fn = Flaky(OSError("slow"), OSError("other"))
    run(fn, Policy(Constant(1.0)), t, retry_after=lambda e: hints.get(str(e)))
    assert t.slept == [7.0, 1.0]


def test_on_retry_sees_each_failure_before_sleeping() -> None:
    t, seen = Time(), list[RetryState]()
    first, second = OSError("a"), OSError("b")
    run(Flaky(first, second), Policy(Exponential(1.0)), t, on_retry=seen.append)
    assert seen == [RetryState(1, 1.0, 0.0, first), RetryState(2, 2.0, 1.0, second)]


def test_default_policy_allows_five_retries() -> None:
    t = Time()
    with pytest.raises(RetryError) as caught:
        run(Flaky(*[OSError()] * 10), None, t)  # type: ignore[arg-type]
    assert caught.value.attempts == 6


def test_aretry_mirrors_retry() -> None:
    t, fn = Time(), Flaky(OSError(), OSError())

    async def call() -> str:
        return fn()

    async def sleep(seconds: float) -> None:
        t.sleep(seconds)

    result = asyncio.run(
        aretry(call, Policy(Exponential(1.0)), sleep=sleep, clock=t.clock, retry_on=OSError)
    )
    assert result == "ok" and t.slept == [1.0, 2.0]


def test_aretry_raises_retry_error_and_never_swallows_cancellation() -> None:
    async def failing() -> str:
        raise OSError("down")

    async def cancelled() -> str:
        raise asyncio.CancelledError

    async def no_sleep(seconds: float) -> None:
        return None

    with pytest.raises(RetryError):
        asyncio.run(aretry(failing, Policy(max_retries=2), sleep=no_sleep))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(aretry(cancelled, Policy(max_retries=2), sleep=no_sleep))


def test_aretry_really_sleeps_with_asyncio_by_default() -> None:
    fn = Flaky(OSError())

    async def call() -> str:
        return fn()

    assert asyncio.run(aretry(call, Policy(Constant(0.01), max_retries=1))) == "ok"

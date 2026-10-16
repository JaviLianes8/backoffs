"""Errors: every bad argument is refused early, typed, and described in a bounded message."""

from __future__ import annotations

import asyncio
import pickle
from collections.abc import Callable
from typing import Any

import pytest

from backoffs import (
    AdditiveJitter,
    Constant,
    DecorrelatedJitter,
    Delays,
    Exponential,
    InvalidPolicyError,
    Linear,
    Policy,
    ProportionalJitter,
    RetryAfterError,
    RetryError,
    aretry,
    backoff,
    parse_retry_after,
    retry,
)


class LoudInt(int):
    def __repr__(self) -> str:
        return "x" * 10_000


class LoudStr(str):
    def __repr__(self) -> str:
        return "y" * 10_000


HOSTILE: list[object] = [
    "s" * 100_000,
    -(10**5000),
    -(10**400),
    LoudStr("short"),
    LoudStr("z" * 50_000),
    LoudInt(-7),
    object(),
    [1.0] * 10_000,
]


@pytest.mark.parametrize("value", HOSTILE, ids=lambda v: type(v).__name__)
@pytest.mark.parametrize(
    "build",
    [
        lambda v: Exponential(base=v),
        lambda v: Exponential(1.0, factor=v),
        lambda v: Linear(v),
        lambda v: Constant(v),
        lambda v: Policy(cap=v),
        lambda v: Policy(max_retries=v),
        lambda v: Policy(max_elapsed=v),
        lambda v: AdditiveJitter(v),
        lambda v: ProportionalJitter(v),
        lambda v: DecorrelatedJitter(v),
        lambda v: Policy(v),
        lambda v: Policy(jitter=v),
        lambda v: Policy().delays(rng=v),
        lambda v: Policy().delays(clock=v),
        lambda v: Policy().delays().floor_next(v),
        lambda v: Delays(v),
        lambda v: backoff(jitter=v),
    ],
)
def test_bad_arguments_raise_short_typed_errors(
    build: Callable[[object], object], value: object
) -> None:
    with pytest.raises(InvalidPolicyError) as caught:
        build(value)
    message = str(caught.value)
    assert len(message) < 120, message
    assert "xxxx" not in message and "yyyy" not in message and "ssss" not in message


def test_the_legacy_function_keeps_short_messages_and_its_type_errors() -> None:
    for value in ("q" * 100_000, 10**400, -(10**400)):
        with pytest.raises(InvalidPolicyError) as caught:
            backoff(base=value)  # type: ignore[arg-type]
        assert len(str(caught.value)) < 120
    with pytest.raises(TypeError):  # 0.1 and 0.2 raised TypeError here too
        backoff(base=None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value", ["9" * 400, "0" * 10_000 + "1", " " * 5 + "x" * 100_000], ids=["big", "zeros", "long"]
)
def test_retry_after_messages_stay_short(value: str) -> None:
    if value.startswith("0"):
        assert parse_retry_after(value) == 1.0
        return
    with pytest.raises(RetryAfterError) as caught:
        parse_retry_after(value)
    assert len(str(caught.value)) < 120


@pytest.mark.parametrize("value", [b"120", 120, None, LoudStr("x" * 100)])
def test_parse_retry_after_refuses_non_strings_or_reads_str_subclasses(value: Any) -> None:
    if isinstance(value, str):
        with pytest.raises(RetryAfterError) as caught:
            parse_retry_after(value)
        assert "yyy" not in str(caught.value)
        return
    with pytest.raises(RetryAfterError, match="must be a str"):
        parse_retry_after(value)


@pytest.mark.parametrize("now", ["2026-01-01", 0, object()])
def test_now_must_be_an_aware_datetime(now: Any) -> None:
    with pytest.raises(RetryAfterError, match="timezone-aware"):
        parse_retry_after("Sun, 06 Nov 1994 08:49:37 GMT", now=now)


def never_called() -> str:
    raise AssertionError("fn must not run when the arguments are invalid")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"retry_on": "OSError"},
        {"retry_on": (OSError, 3)},
        {"retry_on": int},
        {"giveup": 1},
        {"retry_after": "soon"},
        {"on_retry": 2.0},
        {"sleep": None},
        {"clock": 5},
        {"rng": 42},
        {"policy": "fast"},
    ],
)
def test_retry_and_aretry_check_every_argument_before_the_first_call(
    kwargs: dict[str, Any],
) -> None:
    with pytest.raises(InvalidPolicyError):
        retry(never_called, **kwargs)

    async def never_awaited() -> str:
        raise AssertionError

    with pytest.raises(InvalidPolicyError):
        asyncio.run(aretry(never_awaited, **kwargs))
    with pytest.raises(InvalidPolicyError, match="fn must be callable"):
        retry("not callable")  # type: ignore[arg-type]


def test_retry_error_hides_the_last_message_and_survives_pickling() -> None:
    secret = OSError("token=abc123")
    error = RetryError(attempts=4, elapsed=2.5, reason="max_elapsed", last_exception=secret)
    assert "abc123" not in str(error) and "OSError" in str(error)
    copy = pickle.loads(pickle.dumps(error))
    assert (copy.attempts, copy.elapsed, copy.reason) == (4, 2.5, "max_elapsed")
    assert str(copy) == str(error) and isinstance(copy.last_exception, OSError)

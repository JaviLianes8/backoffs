"""Contracts added after the blind mutation round: defaults, twin code paths, strict edges."""

from __future__ import annotations

import asyncio
import itertools
import json
import random
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from backoffs import (
    AdditiveJitter,
    Constant,
    DecorrelatedJitter,
    Exponential,
    FullJitter,
    InvalidPolicyError,
    Policy,
    ProportionalJitter,
    RetryAfterError,
    RetryError,
    aretry,
    backoff,
    parse_retry_after,
)
from backoffs._cli import main

Capture = pytest.CaptureFixture[str]


def test_short_non_ascii_values_are_previewed_in_ascii() -> None:
    with pytest.raises(InvalidPolicyError) as caught:
        backoff(jitter="\xe9t\xe9")
    assert str(caught.value).isascii() and "\\xe9" in str(caught.value)


def test_the_legacy_defaults_and_float_counts_are_kept() -> None:
    assert list(backoff(max_attempts=12))[-1] == 30.0
    assert len(list(backoff(max_attempts=2.5))) == 3  # type: ignore[arg-type]


def test_a_stopped_iterator_stays_stopped_with_its_reason() -> None:
    delays = Policy(Constant(4.0), FullJitter(), max_elapsed=5.0).delays(rng=random.Random(2))
    list(delays)
    reason, total = delays.stop_reason, delays.total
    for _ in range(20):
        assert next(delays, None) is None
    assert (delays.stop_reason, delays.total) == (reason, total)


class NotIterable:
    first = 1.0

    def raw(self) -> int:
        return 5


class BadFirst:
    def __init__(self, first: object) -> None:
        self.first = first

    def raw(self) -> Iterator[float]:
        return itertools.repeat(1.0)


def test_a_schedule_whose_raw_is_not_iterable_is_refused() -> None:
    with pytest.raises(InvalidPolicyError, match="iterable"):
        Policy(NotIterable(), max_retries=1).delays()  # type: ignore[arg-type]


@pytest.mark.parametrize("first", [-1.0, float("nan"), "x"])
def test_a_schedule_with_a_bad_first_delay_is_refused(first: object) -> None:
    with pytest.raises(InvalidPolicyError):
        Policy(BadFirst(first))  # type: ignore[arg-type]


def test_jitter_defaults_are_the_published_values() -> None:
    assert ProportionalJitter().fraction == 0.2
    assert AdditiveJitter().amount == 1.0
    assert DecorrelatedJitter().multiplier == 3.0


def test_uncapped_proportional_and_decorrelated_chains_stay_finite() -> None:
    proportional = Policy(Exponential(1.0, 10.0), ProportionalJitter(), cap=None, max_retries=400)
    assert all(d <= sys.float_info.max for d in proportional.delays(rng=random.Random(1)))
    decorrelated = Policy(Exponential(1.0), DecorrelatedJitter(1e6), cap=None, max_retries=200)
    assert all(d <= sys.float_info.max for d in decorrelated.delays(rng=random.Random(1)))


def test_a_zero_cap_is_refused_even_for_zero_delays() -> None:
    with pytest.raises(InvalidPolicyError):
        Policy(Constant(0.0), cap=0.0)


def test_both_presets_keep_their_budgets() -> None:
    for maker in (Policy.grpc, Policy.google_cloud):
        policy = maker(max_retries=3, max_elapsed=5.0)
        assert (policy.max_retries, policy.max_elapsed) == (3, 5.0)


def test_aretry_defaults_to_six_calls_and_checks_fn() -> None:
    calls: list[int] = []

    async def fail() -> None:
        calls.append(1)
        raise OSError

    async def no_wait(seconds: float) -> None:
        pass

    with pytest.raises(RetryError):
        asyncio.run(aretry(fail, sleep=no_wait))
    assert len(calls) == 6
    with pytest.raises(InvalidPolicyError, match="fn must be callable"):
        asyncio.run(aretry(5))  # type: ignore[arg-type]


NOW = datetime(1994, 11, 6, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "value", ["120\n", "\x0b120", "120\r", "Sun, 06 Nov 1994 08:49:37 GMTxyz", "x120"]
)
def test_only_spaces_and_tabs_are_trimmed_and_nothing_may_trail(value: str) -> None:
    with pytest.raises(RetryAfterError):
        parse_retry_after(value, now=NOW)


def test_rfc850_years_near_the_limits_of_datetime() -> None:
    early = datetime(10, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(RetryAfterError):
        parse_retry_after("Thursday, 01-Jan-70 00:00:00 GMT", now=early)
    late = datetime(9980, 1, 1, tzinfo=timezone.utc)
    assert parse_retry_after("Monday, 01-Jan-90 00:00:00 GMT", now=late) == 315619200.0


def json_schedule(capsys: Capture, *args: str) -> dict[str, Any]:
    assert main(["schedule", "--format", "json", *args]) == 0
    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    return payload


def test_cli_defaults_match_the_library(capsys: Capture) -> None:
    linear = json_schedule(capsys, "--strategy", "linear", "--base", "0.5", "--max-retries", "3")
    assert linear["delays"] == [0.5, 1.0, 1.5]
    seeded = json_schedule(capsys, "--jitter", "proportional", "--seed", "1")
    policy = Policy(Exponential(1.0), ProportionalJitter(0.2), cap=30.0, max_retries=10)
    assert seeded["delays"] == list(policy.delays(rng=random.Random(1)))
    budget = json_schedule(capsys, "--preset", "google-cloud", "--max-elapsed", "10")
    assert budget["stop_reason"] == "max_elapsed" and budget["total"] <= 10


def test_plain_format_keeps_six_significant_digits(capsys: Capture) -> None:
    args = ["schedule", "--strategy", "constant", "--base", "1.2345", "--max-retries", "1"]
    assert main([*args, "--format", "plain"]) == 0
    assert capsys.readouterr().out.strip() == "1.2345"


def test_run_without_bounds_makes_six_attempts(tmp_path: Path) -> None:
    counter = tmp_path / "n"
    script = tmp_path / "cmd.py"
    script.write_text(
        f"import pathlib\np = pathlib.Path({str(counter)!r})\n"
        "p.write_text(str(int(p.read_text()) + 1 if p.exists() else 1))\nraise SystemExit(3)\n"
    )
    assert main(["run", "-q", "--base", "0.001", "--", sys.executable, str(script)]) == 3
    assert counter.read_text() == "6"

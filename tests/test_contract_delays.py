"""Delays: custom schedules and jitters, broken clocks and rng types are handled safely."""

from __future__ import annotations

import random
from collections.abc import Iterator

import pytest

from backoffs import Constant, DecorrelatedJitter, InvalidPolicyError, Policy, ProportionalJitter


class Finite:
    first = 1.0

    def raw(self) -> Iterator[float]:
        yield 1.0


class Bad:
    def __init__(self, value: float) -> None:
        self.first, self.value = 1.0, value

    def raw(self) -> Iterator[float]:
        while True:
            yield self.value


class BadJitter:
    def __init__(self, value: float) -> None:
        self.value = value

    def apply(self, raw: float, **_: object) -> float:
        return self.value


def test_a_schedule_that_ends_is_an_error_not_a_silent_stop() -> None:
    delays = Policy(Finite(), max_retries=5).delays()
    assert next(delays) == 1.0
    with pytest.raises(InvalidPolicyError, match="schedule ended"):
        next(delays)


@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf")])
def test_bad_custom_delays_are_refused(value: float) -> None:
    with pytest.raises(InvalidPolicyError, match="schedule delay"):
        next(Policy(Bad(value), cap=None).delays())
    with pytest.raises(InvalidPolicyError, match="jitter delay"):
        next(Policy(Constant(1.0), BadJitter(value)).delays())


@pytest.mark.parametrize("reading", [float("nan"), float("inf"), float("-inf")])
def test_a_broken_clock_spends_the_budget(reading: float) -> None:
    readings = iter([0.0, reading])
    delays = Policy(Constant(1.0), max_elapsed=100.0).delays(clock=lambda: next(readings))
    assert next(delays, None) is None and delays.stop_reason == "max_elapsed"


def test_a_clock_is_ignored_without_a_time_budget() -> None:
    delays = Policy(Constant(1.0), max_retries=2).delays(clock=lambda: float("nan"))
    assert list(delays) == [1.0, 1.0]


def test_random_subclasses_are_accepted_as_rng() -> None:
    policy = Policy(jitter=DecorrelatedJitter(), max_retries=3)
    assert len(list(policy.delays(rng=random.SystemRandom()))) == 3


def test_jitter_first_must_be_a_bool() -> None:
    with pytest.raises(InvalidPolicyError, match="jitter_first"):
        ProportionalJitter(0.2, jitter_first=0)  # type: ignore[arg-type]


def test_a_floor_lengthens_one_wait_without_inflating_the_decorrelated_chain() -> None:
    policy = Policy(Constant(1.0), DecorrelatedJitter(), cap=1000.0, max_retries=4)
    plain = list(policy.delays(rng=random.Random(9)))
    floored = policy.delays(rng=random.Random(9))
    floored.floor_next(500.0)
    assert list(floored) == [500.0, *plain[1:]]

from __future__ import annotations

import itertools
import sys

import pytest

from backoffs import Constant, Exponential, Fibonacci, InvalidPolicyError, Linear, Policy


def first(schedule: object, count: int) -> list[float]:
    return list(itertools.islice(schedule.raw(), count))  # type: ignore[attr-defined]


def test_constant_repeats_the_delay() -> None:
    assert first(Constant(2.5), 4) == [2.5, 2.5, 2.5, 2.5]


def test_constant_zero_is_allowed_for_immediate_retries() -> None:
    assert first(Constant(0), 2) == [0.0, 0.0]


def test_linear_adds_the_step_each_time() -> None:
    assert first(Linear(1.0, 0.5), 5) == [1.0, 1.5, 2.0, 2.5, 3.0]


def test_exponential_multiplies_by_the_factor() -> None:
    assert first(Exponential(0.25, 3.0), 4) == [0.25, 0.75, 2.25, 6.75]


def test_fibonacci_scales_the_fibonacci_numbers() -> None:
    assert first(Fibonacci(0.5), 8) == [0.5, 0.5, 1.0, 1.5, 2.5, 4.0, 6.5, 10.5]


def test_first_is_the_first_raw_delay() -> None:
    for schedule in (Constant(3), Linear(2, 1), Exponential(0.5), Fibonacci(4)):
        assert schedule.first == first(schedule, 1)[0]


def test_growth_saturates_at_the_largest_float_instead_of_infinity() -> None:
    for schedule in (Exponential(1.0, 10.0), Fibonacci(1e300), Linear(0, 1e308)):
        tail = first(schedule, 2000)[-1]
        assert tail == sys.float_info.max


def test_policy_caps_every_schedule() -> None:
    for schedule in (Linear(1, 4), Exponential(1), Fibonacci(1)):
        delays = list(Policy(schedule, cap=6.0, max_retries=30).delays())
        assert max(delays) == 6.0
        assert delays[-1] == 6.0


def test_schedules_are_frozen_and_hashable() -> None:
    schedule = Exponential(1.0)
    with pytest.raises(AttributeError):
        schedule.base = 2.0  # type: ignore[misc]
    assert hash(schedule) == hash(Exponential(1.0))


def test_integer_arguments_are_stored_as_floats() -> None:
    assert Linear(1, 2) == Linear(1.0, 2.0)
    assert isinstance(Linear(1, 2).start, float)


@pytest.mark.parametrize(
    "build",
    [
        lambda: Constant(-1),
        lambda: Linear(-1, 1),
        lambda: Linear(1, -1),
        lambda: Exponential(0),
        lambda: Exponential(1, 0.5),
        lambda: Exponential(float("inf")),
        lambda: Fibonacci(0),
        lambda: Fibonacci(True),
        lambda: Constant("1"),  # type: ignore[arg-type]
    ],
)
def test_invalid_schedule_arguments_raise(build: object) -> None:
    with pytest.raises(InvalidPolicyError):
        build()  # type: ignore[operator]

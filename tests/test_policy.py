from __future__ import annotations

import itertools
import random

import pytest

from backoffs import (
    Constant,
    DecorrelatedJitter,
    Delays,
    Exponential,
    FullJitter,
    InvalidPolicyError,
    Linear,
    Policy,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_default_policy_is_exponential_from_a_tenth_capped_at_thirty() -> None:
    delays = list(itertools.islice(Policy().delays(), 12))
    assert delays[:4] == [0.1, 0.2, 0.4, 0.8]
    assert delays[-1] == 30.0


def test_max_retries_bounds_the_number_of_delays() -> None:
    delays = Policy(max_retries=3).delays()
    assert len(list(delays)) == 3
    assert delays.stop_reason == "max_retries"
    assert delays.retries == 3


def test_max_retries_zero_yields_nothing() -> None:
    assert list(Policy(max_retries=0).delays()) == []


def test_max_elapsed_stops_before_a_delay_that_would_overrun() -> None:
    delays = Policy(Exponential(1.0), max_elapsed=10.0).delays()
    assert list(delays) == [1.0, 2.0, 4.0]  # 1 + 2 + 4 = 7, adding 8 would reach 15
    assert delays.stop_reason == "max_elapsed"
    assert delays.total == 7.0


def test_max_elapsed_allows_landing_exactly_on_the_budget() -> None:
    assert list(Policy(Constant(2.5), max_elapsed=10.0).delays()) == [2.5] * 4


def test_stopped_iterator_stays_stopped() -> None:
    delays = Policy(max_retries=1).delays()
    assert list(delays) == [0.1]
    assert next(delays, None) is None


def test_a_clock_measures_the_budget_in_real_time() -> None:
    clock = FakeClock()
    delays = Policy(Constant(1.0), max_elapsed=5.0).delays(clock=clock)
    assert next(delays) == 1.0
    clock.now += 3.5  # the caller's own work took time too
    assert next(delays) == 1.0  # 3.5 + 1.0 <= 5
    clock.now += 1.0
    assert next(delays, None) is None  # 4.5 + 1.0 > 5
    assert delays.stop_reason == "max_elapsed"
    assert delays.elapsed == 4.5


def test_floor_next_raises_only_the_next_delay_and_beats_the_cap() -> None:
    delays = Policy(Exponential(1.0), cap=4.0).delays()
    assert next(delays) == 1.0
    delays.floor_next(9.0)
    assert next(delays) == 9.0
    assert next(delays) == 4.0


def test_floor_next_keeps_the_larger_of_two_hints_and_never_lowers() -> None:
    delays = Policy(Constant(5.0)).delays()
    delays.floor_next(1.0)
    delays.floor_next(7.0)
    delays.floor_next(2.0)
    assert next(delays) == 7.0
    delays.floor_next(1.0)
    assert next(delays) == 5.0


def test_a_floor_that_does_not_fit_the_budget_stops_iteration() -> None:
    delays = Policy(Constant(1.0), max_elapsed=10.0).delays()
    delays.floor_next(30.0)
    assert list(delays) == []
    assert delays.stop_reason == "max_elapsed"


def test_floor_next_rejects_negative_and_nan() -> None:
    delays = Policy().delays()
    for bad in (-1.0, float("nan")):
        with pytest.raises(InvalidPolicyError):
            delays.floor_next(bad)


def test_delays_is_a_typed_iterator() -> None:
    delays = Policy().delays()
    assert isinstance(delays, Delays)
    assert iter(delays) is delays


def test_one_policy_gives_independent_iterators() -> None:
    policy = Policy(Linear(1, 1), max_retries=3)
    assert list(policy.delays()) == list(policy.delays()) == [1.0, 2.0, 3.0]


def test_uncapped_policy_grows_without_a_ceiling() -> None:
    assert list(Policy(Exponential(1.0), cap=None, max_retries=8).delays())[-1] == 128.0


def test_seeded_rng_reproduces_a_jittered_run() -> None:
    policy = Policy(jitter=FullJitter(), max_retries=20)
    first = list(policy.delays(rng=random.Random(4)))
    assert first == list(policy.delays(rng=random.Random(4)))
    assert first != list(policy.delays(rng=random.Random(5)))


def test_policy_is_frozen_and_comparable() -> None:
    policy = Policy(max_retries=2)
    with pytest.raises(AttributeError):
        policy.cap = 1.0  # type: ignore[misc]
    assert policy == Policy(max_retries=2)
    assert Policy.grpc() == Policy.grpc()


def test_presets_accept_budgets() -> None:
    assert Policy.grpc(max_retries=3, max_elapsed=9.0).max_elapsed == 9.0
    assert Policy.google_cloud(maximum_backoff=64.0).cap == 64.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"cap": 0.0},
        {"cap": -1.0},
        {"cap": float("inf")},
        {"schedule": Exponential(5.0), "cap": 1.0},
        {"max_retries": -1},
        {"max_retries": 1.5},
        {"max_retries": True},
        {"max_elapsed": -1.0},
        {"max_elapsed": float("nan")},
        {"schedule": Constant(0.0), "jitter": DecorrelatedJitter(), "cap": None},
    ],
)
def test_invalid_policies_raise_a_value_error_subclass(kwargs: dict[str, object]) -> None:
    with pytest.raises(InvalidPolicyError) as caught:
        Policy(**kwargs)  # type: ignore[arg-type]
    assert isinstance(caught.value, ValueError)

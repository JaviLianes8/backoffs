"""Every jitter strategy against its published formula: exact seeded runs and statistics.

Sources: AWS Architecture Blog "Exponential Backoff And Jitter" (full, equal and
decorrelated), gRPC doc/connection-backoff.md (proportional) and Google Cloud's
truncated exponential backoff (additive).
"""

from __future__ import annotations

import random
import statistics

import pytest

from backoffs import (
    AdditiveJitter,
    DecorrelatedJitter,
    EqualJitter,
    Exponential,
    FullJitter,
    InvalidPolicyError,
    NoJitter,
    Policy,
    ProportionalJitter,
)

BASE, CAP, N = 0.5, 10.0, 12
SAMPLES = 20_000


def raw(attempt: int) -> float:
    return min(CAP, BASE * 2.0**attempt)


def run(jitter: object, seed: int = 11, count: int = N) -> list[float]:
    policy = Policy(Exponential(BASE, 2.0), jitter, cap=CAP, max_retries=count)  # type: ignore[arg-type]
    return list(policy.delays(rng=random.Random(seed)))


def test_no_jitter_is_min_cap_base_times_two_to_the_attempt() -> None:
    assert run(NoJitter()) == [raw(n) for n in range(N)]


def test_full_jitter_matches_random_between_zero_and_raw() -> None:
    oracle = random.Random(11)
    assert run(FullJitter()) == [oracle.uniform(0, raw(n)) for n in range(N)]


def test_equal_jitter_matches_half_plus_random_between_zero_and_half() -> None:
    oracle = random.Random(11)
    expected = [raw(n) / 2 + oracle.uniform(0, raw(n) / 2) for n in range(N)]
    assert run(EqualJitter()) == expected


def test_decorrelated_jitter_matches_min_cap_random_between_base_and_three_sleeps() -> None:
    oracle = random.Random(11)
    sleep, expected = BASE, []
    for _ in range(N):
        sleep = min(CAP, oracle.uniform(BASE, sleep * 3))
        expected.append(sleep)
    assert run(DecorrelatedJitter()) == expected


def test_proportional_jitter_matches_the_grpc_uniform_spread() -> None:
    oracle = random.Random(11)
    expected = [raw(n) + oracle.uniform(-0.2 * raw(n), 0.2 * raw(n)) for n in range(N)]
    assert run(ProportionalJitter(0.2)) == expected


def test_additive_jitter_matches_google_min_raw_plus_random_and_maximum() -> None:
    oracle = random.Random(11)
    expected = [min(BASE * 2**n + oracle.uniform(0, 1.0), CAP) for n in range(N)]
    assert run(AdditiveJitter(1.0)) == expected


def test_grpc_preset_waits_the_plain_initial_backoff_then_jitters_1_6_growth() -> None:
    oracle = random.Random(5)
    expected, backoff = [1.0], 1.0
    for _ in range(14):
        backoff = min(backoff * 1.6, 120.0)
        expected.append(backoff + oracle.uniform(-0.2 * backoff, 0.2 * backoff))
    assert list(Policy.grpc(max_retries=15).delays(rng=random.Random(5))) == expected


def test_google_cloud_preset_is_two_to_the_n_plus_up_to_a_second_truncated() -> None:
    oracle = random.Random(9)
    expected = [min(2.0**n + oracle.uniform(0, 1.0), 64.0) for n in range(10)]
    policy = Policy.google_cloud(maximum_backoff=64.0, max_retries=10)
    assert list(policy.delays(rng=random.Random(9))) == expected


def samples_at(jitter: object, attempt: int) -> list[float]:
    """SAMPLES independent draws of the delay for one attempt (seeded, so deterministic)."""
    rng = random.Random(1234)
    policy = Policy(Exponential(BASE, 2.0), jitter, cap=CAP, max_retries=attempt + 1)  # type: ignore[arg-type]
    return [list(policy.delays(rng=rng))[-1] for _ in range(SAMPLES)]


@pytest.mark.parametrize(
    ("jitter", "low", "high", "mean"),
    [
        (FullJitter(), 0.0, 4.0, 2.0),
        (EqualJitter(), 2.0, 4.0, 3.0),
        (ProportionalJitter(0.2), 3.2, 4.8, 4.0),
        (AdditiveJitter(1.0), 4.0, 5.0, 4.5),
    ],
)
def test_distribution_bounds_and_mean_match_the_formula(
    jitter: object, low: float, high: float, mean: float
) -> None:
    # attempt 3 has raw = 0.5 * 2 ** 3 = 4.0
    drawn = samples_at(jitter, 3)
    assert low <= min(drawn) and max(drawn) <= high
    assert statistics.fmean(drawn) == pytest.approx(mean, rel=0.02)
    # A uniform spread of width w has standard deviation w / sqrt(12).
    assert statistics.pstdev(drawn) == pytest.approx((high - low) / 12**0.5, rel=0.03)


def test_decorrelated_first_draw_is_uniform_between_base_and_three_base() -> None:
    drawn = samples_at(DecorrelatedJitter(), 0)
    assert min(drawn) >= BASE and max(drawn) <= 3 * BASE
    assert statistics.fmean(drawn) == pytest.approx(2 * BASE, rel=0.02)


def test_decorrelated_long_run_stays_between_base_and_cap() -> None:
    delays = run(DecorrelatedJitter(), seed=3, count=5000)
    assert all(BASE <= d <= CAP for d in delays)
    assert max(delays) == CAP  # the cap is reached and clamps


def test_additive_jitter_never_exceeds_the_cap() -> None:
    assert max(run(AdditiveJitter(5.0), count=200)) <= CAP


def test_proportional_jitter_may_exceed_the_cap_by_the_fraction_as_grpc_does() -> None:
    delays = run(ProportionalJitter(0.2), count=500)[10:]
    assert max(delays) > CAP
    assert max(delays) <= CAP * 1.2


@pytest.mark.parametrize(
    "build",
    [
        lambda: DecorrelatedJitter(multiplier=0.5),
        lambda: ProportionalJitter(fraction=1.5),
        lambda: ProportionalJitter(fraction=-0.1),
        lambda: AdditiveJitter(amount=-1.0),
        lambda: AdditiveJitter(amount=float("nan")),
    ],
)
def test_invalid_jitter_arguments_raise(build: object) -> None:
    with pytest.raises(InvalidPolicyError):
        build()  # type: ignore[operator]

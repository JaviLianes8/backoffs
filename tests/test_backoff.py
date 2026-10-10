from __future__ import annotations

import itertools
import random
from collections.abc import Iterator

import pytest

from backoffs import backoff


def test_no_jitter_yields_the_exact_exponential_sequence() -> None:
    delays = list(backoff(base=1.0, factor=2.0, cap=100.0, max_attempts=5))
    assert delays == [1.0, 2.0, 4.0, 8.0, 16.0]


def test_cap_clamps_the_growing_delay() -> None:
    delays = list(backoff(base=1.0, factor=10.0, cap=25.0, max_attempts=4))
    assert delays == [1.0, 10.0, 25.0, 25.0]


def test_factor_one_keeps_a_constant_delay() -> None:
    delays = list(backoff(base=3.0, factor=1.0, cap=100.0, max_attempts=3))
    assert delays == [3.0, 3.0, 3.0]


def test_max_attempts_stops_the_sequence() -> None:
    delays = list(backoff(base=0.1, max_attempts=7))
    assert len(delays) == 7


def test_max_attempts_zero_yields_nothing() -> None:
    assert list(backoff(max_attempts=0)) == []


def test_unbounded_sequence_is_infinite_and_stays_capped() -> None:
    stream = backoff(base=1.0, factor=2.0, cap=30.0)
    first_thousand = list(itertools.islice(stream, 1000))
    assert len(first_thousand) == 1000
    assert first_thousand[-1] == 30.0


def test_full_jitter_stays_within_zero_and_the_raw_delay() -> None:
    rng = random.Random(1)
    raw = [1.0, 2.0, 4.0, 8.0, 16.0]
    for drawn, ceiling in zip(
        backoff(base=1.0, factor=2.0, cap=100.0, jitter="full", max_attempts=5, rng=rng),
        raw,
        strict=True,
    ):
        assert 0.0 <= drawn <= ceiling


def test_equal_jitter_stays_within_half_and_the_raw_delay() -> None:
    rng = random.Random(2)
    raw = [1.0, 2.0, 4.0, 8.0, 16.0]
    for drawn, ceiling in zip(
        backoff(base=1.0, factor=2.0, cap=100.0, jitter="equal", max_attempts=5, rng=rng),
        raw,
        strict=True,
    ):
        assert ceiling / 2.0 <= drawn <= ceiling


def test_decorrelated_jitter_stays_within_base_and_cap() -> None:
    rng = random.Random(3)
    for drawn in backoff(base=1.0, cap=50.0, jitter="decorrelated", max_attempts=200, rng=rng):
        assert 1.0 <= drawn <= 50.0


def test_seeded_jitter_is_reproducible() -> None:
    def run() -> list[float]:
        return list(backoff(jitter="full", max_attempts=20, rng=random.Random(42)))

    assert run() == run()


def test_different_seeds_diverge() -> None:
    first = list(backoff(jitter="full", max_attempts=20, rng=random.Random(1)))
    second = list(backoff(jitter="full", max_attempts=20, rng=random.Random(2)))
    assert first != second


def test_the_result_is_an_iterator() -> None:
    stream = backoff(max_attempts=3)
    assert isinstance(stream, Iterator)
    assert iter(stream) is stream


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"base": 0.0}, "base"),
        ({"base": -1.0}, "base"),
        ({"factor": 0.5}, "factor"),
        ({"cap": 0.0}, "cap"),
        ({"base": 10.0, "cap": 5.0}, "cap"),
        ({"jitter": "wobble"}, "jitter"),
        ({"max_attempts": -1}, "max_attempts"),
    ],
)
def test_invalid_arguments_raise_value_error(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        backoff(**kwargs)  # type: ignore[arg-type]


def test_validation_happens_eagerly_not_on_first_next() -> None:
    # A plain generator would defer the error until iteration; this must raise now.
    with pytest.raises(ValueError, match="jitter"):
        backoff(jitter="nope")

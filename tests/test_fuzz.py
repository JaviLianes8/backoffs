"""Seeded fuzzing: hostile Retry-After input, random policies, and retry against aretry."""

from __future__ import annotations

import math
import random
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime

import pytest

from backoffs import (
    AdditiveJitter,
    Constant,
    DecorrelatedJitter,
    EqualJitter,
    Exponential,
    Fibonacci,
    FullJitter,
    Jitter,
    Linear,
    NoJitter,
    Policy,
    ProportionalJitter,
    RetryAfterError,
    Schedule,
    parse_retry_after,
)

NOW = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
TOKENS = [
    *("Sun", "Sunday", "Nov", "Feb", "GMT", ",", " ", "  ", "-", ":", "\t", "\x00", "+", "."),
    *("06", "6", "29", "60", "1994", "94", "08:49:37", "0", "9" * 30, "e", "\u0666"),
]


def rfc850(moment: datetime) -> str:
    day = moment.strftime("%A")  # strftime's %y refuses years before 1900 on Windows
    return f"{day}, {moment.day:02}-{moment:%b}-{moment.year % 100:02} {moment:%H:%M:%S} GMT"


def asctime(moment: datetime) -> str:
    return f"{moment:%a %b} {moment.day:>2} {moment:%H:%M:%S} {moment.year:04}"


def valid_values(rng: random.Random) -> list[str]:
    moment = datetime(rng.randint(1, 9999), 1, 1, tzinfo=timezone.utc)
    moment += timedelta(seconds=rng.randrange(365 * 86400))
    imf = f"{moment:%a, %d %b} {moment.year:04} {moment:%H:%M:%S} GMT"
    return [str(rng.randrange(10**12)), imf, rfc850(moment), asctime(moment)]


def mutate(rng: random.Random, text: str) -> str:
    chars = list(text)
    for _ in range(rng.randint(1, 3)):
        position = rng.randint(0, len(chars))
        action = rng.randrange(3)
        if action == 0:
            chars.insert(position, rng.choice(TOKENS))
        elif chars and action == 1:
            del chars[min(position, len(chars) - 1)]
        elif chars:
            chars[min(position, len(chars) - 1)] = rng.choice(TOKENS)
    return "".join(chars)


@pytest.mark.parametrize("seed", range(4))
def test_retry_after_never_crashes_on_random_or_mutated_input(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(4000):
        if rng.random() < 0.5:
            value = "".join(rng.choice(TOKENS) for _ in range(rng.randint(0, 12)))
        else:
            value = mutate(rng, rng.choice(valid_values(rng)))
        try:
            seconds = parse_retry_after(value, now=NOW)
        except RetryAfterError as exc:
            assert len(str(exc)) < 120
        else:
            assert math.isfinite(seconds) and seconds >= 0.0


@pytest.mark.parametrize("seed", range(3))
def test_imf_fixdate_agrees_with_the_standard_library(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(3000):
        # The standard library reads years below 100 as two-digit years (RFC 2822);
        # RFC 9110 has four-digit years only, so the oracle is used from 100 on.
        moment = datetime(rng.randint(100, 9999), 1, 1, tzinfo=timezone.utc)
        moment += timedelta(seconds=rng.randrange(365 * 86400))
        value = format_datetime(moment, usegmt=True)
        shift = timedelta(seconds=rng.randint(-(10**9), 10**9))
        now = moment + shift if 200 < moment.year < 9900 else moment - shift / 10**6
        expected = max(0.0, (parsedate_to_datetime(value) - now).total_seconds())
        assert parse_retry_after(value, now=now) == expected


@pytest.mark.parametrize("seed", range(3))
def test_obsolete_forms_name_the_same_instant_as_imf_fixdate(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(3000):
        # Within 49 years either way, so the two-digit year is unambiguous.
        moment = NOW + timedelta(seconds=rng.randint(-49 * 365 * 86400, 49 * 365 * 86400))
        imf = format_datetime(moment.replace(microsecond=0), usegmt=True)
        forms = (imf, rfc850(moment), asctime(moment))
        assert len({parse_retry_after(v, now=NOW) for v in forms}) == 1, forms


@pytest.mark.parametrize("size", [10**6, 4 * 10**6])
def test_huge_values_are_refused_in_linear_time(size: int) -> None:
    for value in ("9" * size, " " * size + "1 2", "Sun, " + "0" * size, "x" * size):
        start = time.perf_counter()
        with pytest.raises(RetryAfterError):
            parse_retry_after(value, now=NOW)
        assert time.perf_counter() - start < 2.0


def random_policy(rng: random.Random) -> Policy:
    base = rng.choice([0.0, 0.001, 0.1, 1.0, 7.5])
    schedules: list[Schedule] = [Constant(base), Linear(base, rng.choice([0.0, 0.5, 3.0]))]
    if base > 0:
        schedules += [Exponential(base, rng.choice([1.0, 1.6, 2.0, 10.0])), Fibonacci(base)]
    schedule = rng.choice(schedules)
    proportional = ProportionalJitter(rng.choice([0.0, 0.2, 1.0]), rng.random() < 0.5)
    jitters: list[Jitter] = [NoJitter(), FullJitter(), EqualJitter(), AdditiveJitter(0.5)]
    jitters.append(proportional)
    if base > 0:
        jitters.append(DecorrelatedJitter(rng.choice([1.0, 3.0])))
    cap = rng.choice([None, max(base, 0.1) * rng.choice([1, 4, 1e6])])
    budget = rng.choice([None, 0.0, 1.0, 50.0])
    retries = rng.choice([0, 1, 30]) if budget is None or rng.random() < 0.5 else None
    if retries is None and base < 0.1:
        retries = 50  # tiny delays under a budget alone would take long to add up
    return Policy(schedule, rng.choice(jitters), cap=cap, max_retries=retries, max_elapsed=budget)


@pytest.mark.parametrize("seed", range(5))
def test_random_policies_keep_every_promise(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(400):
        policy = random_policy(rng)
        delays = policy.delays(rng=random.Random(seed))
        values = list(delays)
        assert values == list(policy.delays(rng=random.Random(seed)))
        assert all(math.isfinite(v) and v >= 0.0 for v in values)
        if policy.max_retries is not None:
            assert len(values) <= policy.max_retries
        if policy.max_elapsed is not None:
            assert sum(values) <= policy.max_elapsed + 1e-9
        ceiling = math.inf if policy.cap is None else policy.cap
        if isinstance(policy.jitter, ProportionalJitter):
            ceiling *= 1 + policy.jitter.fraction
        assert all(v <= ceiling for v in values)
        assert delays.stop_reason in ("max_retries", "max_elapsed")

"""The complete public promise of backoffs, pinned in one place."""

from __future__ import annotations

import importlib.resources
import itertools
import random
import re
from pathlib import Path

import backoffs
from backoffs import (
    AdditiveJitter,
    BackoffError,
    Constant,
    DecorrelatedJitter,
    EqualJitter,
    Exponential,
    Fibonacci,
    FullJitter,
    InvalidPolicyError,
    Jitter,
    Linear,
    NoJitter,
    Policy,
    ProportionalJitter,
    RetryAfterError,
    RetryError,
    Schedule,
    backoff,
)

PUBLIC_API: list[str] = [
    "AdditiveJitter",
    "BackoffError",
    "Constant",
    "DecorrelatedJitter",
    "Delays",
    "EqualJitter",
    "Exponential",
    "Fibonacci",
    "FullJitter",
    "InvalidPolicyError",
    "Jitter",
    "Linear",
    "NoJitter",
    "Policy",
    "ProportionalJitter",
    "RetryAfterError",
    "RetryError",
    "RetryState",
    "Schedule",
    "aretry",
    "backoff",
    "parse_retry_after",
    "retry",
]
ROOT = Path(__file__).resolve().parents[1]


def test_all_lists_exactly_the_public_api() -> None:
    assert sorted(backoffs.__all__) == sorted(PUBLIC_API)


def test_every_exported_name_resolves() -> None:
    for name in backoffs.__all__:
        assert hasattr(backoffs, name)


def test_version_is_a_three_part_string_matching_pyproject() -> None:
    parts = backoffs.__version__.split(".")
    assert len(parts) == 3 and all(part.isdigit() for part in parts)
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    version = re.search(r'^version = "(.+)"$', pyproject, re.MULTILINE)
    assert version is not None and version.group(1) == backoffs.__version__
    assert re.search(r'^backoffs = "backoffs\._cli:main"$', pyproject, re.MULTILINE)
    assert re.search(r"^dependencies = \[\]$", pyproject, re.MULTILINE)


def test_the_package_ships_type_information() -> None:
    assert importlib.resources.files("backoffs").joinpath("py.typed").is_file()


def test_errors_form_one_typed_hierarchy() -> None:
    for error in (InvalidPolicyError, RetryAfterError, RetryError):
        assert issubclass(error, BackoffError)
    assert issubclass(InvalidPolicyError, ValueError)
    assert issubclass(RetryAfterError, ValueError)


def test_every_schedule_and_jitter_yields_bounded_reproducible_delays() -> None:
    schedules: list[Schedule] = [Constant(1.0), Linear(0.5, 0.5), Exponential(0.5), Fibonacci(0.5)]
    jitters: list[Jitter] = [
        NoJitter(),
        FullJitter(),
        EqualJitter(),
        DecorrelatedJitter(),
        ProportionalJitter(0.2),
        AdditiveJitter(0.5),
    ]
    for schedule, jitter in itertools.product(schedules, jitters):
        policy = Policy(schedule, jitter, cap=8.0, max_retries=40)
        first = list(policy.delays(rng=random.Random(99)))
        assert first == list(policy.delays(rng=random.Random(99)))
        assert len(first) == 40
        ceiling = 8.0 * 1.2 if isinstance(jitter, ProportionalJitter) else 8.0
        assert all(0.0 <= d <= ceiling for d in first), (schedule, jitter)


def test_budgets_are_never_exceeded() -> None:
    for seed in range(50):
        policy = Policy(jitter=EqualJitter(), max_retries=30, max_elapsed=12.5)
        delays = policy.delays(rng=random.Random(seed))
        assert sum(delays) <= 12.5
        assert delays.retries <= 30
        assert delays.stop_reason in ("max_retries", "max_elapsed")


def test_legacy_backoff_equals_the_matching_policy() -> None:
    pairs: list[tuple[str, Jitter]] = [
        ("full", FullJitter()),
        ("decorrelated", DecorrelatedJitter()),
    ]
    for jitter, strategy in pairs:
        legacy = backoff(base=0.2, factor=3.0, cap=9.0, jitter=jitter, max_attempts=25,
                         rng=random.Random(3))  # fmt: skip
        policy = Policy(Exponential(0.2, 3.0), strategy, cap=9.0, max_retries=25)
        assert list(legacy) == list(policy.delays(rng=random.Random(3)))


def test_source_files_stay_under_two_hundred_lines() -> None:
    for path in itertools.chain((ROOT / "src").rglob("*.py"), (ROOT / "tests").rglob("*.py")):
        assert len(path.read_text(encoding="utf-8").splitlines()) <= 200, path

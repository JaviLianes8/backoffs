"""Seeded fuzzing of the retry helpers: retry and aretry agree on random failure patterns."""

from __future__ import annotations

import asyncio
import random

import pytest
from test_fuzz import random_policy

from backoffs import Policy, RetryError, aretry, retry


@pytest.mark.parametrize("seed", range(3))
def test_retry_and_aretry_agree_on_random_failure_patterns(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(200):
        policy = random_policy(rng)
        outcomes = [rng.random() < 0.6 for _ in range(40)]
        sync = run_sync(policy, outcomes, seed)
        assert sync == run_async(policy, outcomes, seed)


def run_sync(policy: Policy, outcomes: list[bool], seed: int) -> tuple[object, list[float]]:
    slept: list[float] = []
    calls = iter(outcomes)

    def fn() -> str:
        if next(calls):
            raise OSError("down")
        return "up"

    try:
        result: object = retry(fn, policy, sleep=slept.append, clock=lambda: sum(slept),
                               rng=random.Random(seed))  # fmt: skip
    except RetryError as exc:
        result = (exc.attempts, exc.reason)
    return result, slept


def run_async(policy: Policy, outcomes: list[bool], seed: int) -> tuple[object, list[float]]:
    slept: list[float] = []
    calls = iter(outcomes)

    async def fn() -> str:
        if next(calls):
            raise OSError("down")
        return "up"

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    try:
        result: object = asyncio.run(aretry(fn, policy, sleep=sleep, clock=lambda: sum(slept),
                                            rng=random.Random(seed)))  # fmt: skip
    except RetryError as exc:
        result = (exc.attempts, exc.reason)
    return result, slept

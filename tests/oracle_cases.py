"""Scenarios run through independent backoff implementations and through backoffs.

``reference(case)`` runs a scenario through the real third-party code: the AWS
Architecture Blog's own simulator classes (fetched source, see ``tests/sources``),
tenacity's wait strategies and the ``backoff`` package's generators. Each draws from
the global ``random`` module seeded with the case seed. ``ours(case)`` runs the same
scenario through the matching :class:`backoffs.Policy` with ``random.Random(seed)``.
``scripts/oracle_fixture.py`` records the reference output in
``tests/fixtures/oracle_runs.json``.
"""

from __future__ import annotations

import ast
import importlib
import itertools
import random
import types
from pathlib import Path
from typing import Any

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
    Schedule,
)

Case = dict[str, Any]
SIMULATOR = Path(__file__).parent / "sources" / "aws_backoff_simulator.py.txt"
AWS_CLASSES: dict[str, Jitter] = {
    "ExpoBackoff": NoJitter(),
    "ExpoBackoffFullJitter": FullJitter(),
    "ExpoBackoffEqualJitter": EqualJitter(),
    "ExpoBackoffDecorr": DecorrelatedJitter(),
}


def cases() -> list[Case]:
    """Every scenario, with small, large and fractional bases and caps."""
    out: list[Case] = []
    for name, (base, cap), seed in itertools.product(
        AWS_CLASSES, [(5, 2000), (0.1, 30.0), (1.0, 7.5), (0.003, 1.0)], range(3)
    ):
        out.append({"oracle": "aws", "kind": name, "base": base, "cap": cap, "seed": seed})
    for (base, cap, factor), seed in itertools.product(
        [(0.5, 60.0, 2.0), (1.0, 120.0, 1.6), (0.2, 9.0, 3.0)], range(2)
    ):
        out.append({"oracle": "tenacity", "kind": "wait_exponential", "base": base, "cap": cap,
                    "factor": factor, "seed": seed})  # fmt: skip
    for kind, (base, cap), seed in itertools.product(
        ["wait_random_exponential", "wait_exponential_jitter"],
        [(0.5, 60.0), (1.0, 32.0), (2.0, 3.0)],
        range(3),
    ):
        out.append({"oracle": "tenacity", "kind": kind, "base": base, "cap": cap, "seed": seed})
    out.append({"oracle": "tenacity", "kind": "wait_incrementing", "base": 0.5, "step": 1.5,
                "cap": 20.0, "seed": 0})  # fmt: skip
    out.append({"oracle": "tenacity", "kind": "wait_fixed", "base": 2.5, "seed": 0})
    for kind, seed in itertools.product(["expo", "expo_full_jitter"], range(3)):
        out.append({"oracle": "backoff", "kind": kind, "base": 0.25, "cap": 40.0, "seed": seed})
    for seed in range(3):
        # The package adds random_jitter after its own cap, so compare it uncapped.
        out.append({"oracle": "backoff", "kind": "expo_random_jitter", "base": 0.25, "seed": seed})
    out.append({"oracle": "backoff", "kind": "fibo", "base": 1.0, "cap": 100.0, "seed": 0})
    out.append({"oracle": "backoff", "kind": "constant", "base": 3.0, "seed": 0})
    return out


def count(case: Case) -> int:
    return 40 if case["oracle"] == "aws" else 25


def ours(case: Case) -> list[float]:
    schedule, jitter, cap = _policy_parts(case)
    policy = Policy(schedule, jitter, cap=cap, max_retries=count(case))
    return list(policy.delays(rng=random.Random(case["seed"])))


def _policy_parts(case: Case) -> tuple[Schedule, Jitter, float | None]:
    kind, base, cap = case["kind"], float(case["base"]), case.get("cap")
    cap = None if cap is None else float(cap)
    if case["oracle"] == "aws":
        return Exponential(base, 2.0), AWS_CLASSES[kind], cap
    if kind in ("wait_fixed", "constant"):
        return Constant(base), NoJitter(), None
    if kind == "wait_incrementing":
        return Linear(base, case["step"]), NoJitter(), cap
    if kind == "fibo":
        return Fibonacci(base), NoJitter(), cap
    factor = float(case.get("factor", 2.0))
    jitters: dict[str, Jitter] = {
        "wait_random_exponential": FullJitter(),
        "wait_exponential_jitter": AdditiveJitter(1.0),
        "expo_full_jitter": FullJitter(),
        "expo_random_jitter": AdditiveJitter(1.0),
    }
    jitter = jitters.get(kind, NoJitter())
    return Exponential(base, factor), jitter, cap


def reference(case: Case) -> list[float]:
    """Run ``case`` through the third-party implementation (needs it importable)."""
    random.seed(case["seed"])
    n, kind = count(case), case["kind"]
    if case["oracle"] == "aws":
        simulator = load_simulator()[kind](case["base"], case["cap"])
        return [float(simulator.backoff(k)) for k in range(n)]
    if case["oracle"] == "tenacity":
        strategy = _tenacity_strategy(importlib.import_module("tenacity"), case)
        states = (types.SimpleNamespace(attempt_number=k + 1) for k in range(n))
        return [float(strategy(state)) for state in states]
    return _backoff_package(case, n)


def _tenacity_strategy(tenacity: Any, case: Case) -> Any:
    kind, base, cap = case["kind"], case["base"], case.get("cap")
    if kind == "wait_exponential":
        return tenacity.wait_exponential(multiplier=base, max=cap, exp_base=case["factor"])
    if kind == "wait_random_exponential":
        return tenacity.wait_random_exponential(multiplier=base, max=cap)
    if kind == "wait_exponential_jitter":
        return tenacity.wait_exponential_jitter(multiplier=base, max=cap, jitter=1)
    if kind == "wait_incrementing":
        return tenacity.wait_incrementing(start=base, increment=case["step"], max=cap)
    return tenacity.wait_fixed(base)


def _backoff_package(case: Case, n: int) -> list[float]:
    backoff: Any = importlib.import_module("backoff")
    kind, base = case["kind"], case["base"]
    if kind == "fibo":
        generator = backoff.fibo(max_value=case["cap"])
    elif kind == "constant":
        generator = backoff.constant(interval=base)
    else:
        generator = backoff.expo(base=2, factor=base, max_value=case.get("cap"))
    next(generator)  # the package primes its generators with one bare yield
    values = [float(next(generator)) for _ in range(n)]
    if kind == "expo_full_jitter":
        return [float(backoff.full_jitter(v)) for v in values]
    if kind == "expo_random_jitter":
        return [float(backoff.random_jitter(v)) for v in values]
    return values


def load_simulator() -> dict[str, Any]:
    """Execute only the backoff classes of the fetched AWS simulator source.

    The file ends by running a long simulation (written for Python 2), so the class
    definitions are taken from its syntax tree and nothing else runs.
    """
    tree = ast.parse(SIMULATOR.read_text(encoding="utf-8"))
    wanted = {"Backoff", *AWS_CLASSES}
    body: list[ast.stmt] = [
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in wanted
    ]
    namespace: dict[str, Any] = {"random": random}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(SIMULATOR), "exec"), namespace)
    return {name: namespace[name] for name in AWS_CLASSES}

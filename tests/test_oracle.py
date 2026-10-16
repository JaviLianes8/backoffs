"""backoffs against independent implementations: recorded runs, and live reruns.

The fixture holds what the AWS Architecture Blog's own simulator classes, tenacity and
the ``backoff`` package returned for the same seeds (see ``oracle_cases.py`` and
``scripts/oracle_fixture.py``). backoffs must match them value for value; only where
the reference raises the factor to a power while backoffs multiplies step by step
(factors other than 2) may the last bit differ.
"""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path
from typing import Any

import oracle_cases
import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "oracle_runs.json"
RUNS: list[dict[str, Any]] = json.loads(FIXTURE.read_text(encoding="utf-8"))["runs"]


def run_id(run: dict[str, Any]) -> str:
    return f"{run['oracle']}-{run['kind']}-{run['base']}-{run.get('cap')}-{run['seed']}"


def same(expected: list[float], actual: list[float], case: dict[str, Any]) -> bool:
    if case.get("factor", 2.0) == 2.0:
        return expected == actual
    pairs = zip(expected, actual, strict=True)
    return all(math.isclose(e, a, rel_tol=1e-12) for e, a in pairs)


def test_the_fixture_covers_every_case_and_every_reference() -> None:
    assert [{k: v for k, v in r.items() if k != "delays"} for r in RUNS] == oracle_cases.cases()
    assert {r["oracle"] for r in RUNS} == {"aws", "tenacity", "backoff"}
    kinds = {r["kind"] for r in RUNS if r["oracle"] == "aws"}
    assert kinds == set(oracle_cases.AWS_CLASSES)


@pytest.mark.parametrize("run", RUNS, ids=run_id)
def test_backoffs_matches_the_recorded_reference(run: dict[str, Any]) -> None:
    case = {k: v for k, v in run.items() if k != "delays"}
    assert len(run["delays"]) == oracle_cases.count(case)
    assert same(run["delays"], oracle_cases.ours(case), case)


def available(oracle: str) -> bool:
    if oracle == "aws":
        return oracle_cases.SIMULATOR.is_file()
    return importlib.util.find_spec(oracle) is not None


@pytest.mark.parametrize("oracle", ["aws", "tenacity", "backoff"])
def test_the_live_reference_still_produces_the_recorded_runs(oracle: str) -> None:
    if not available(oracle):
        pytest.skip(f"{oracle} reference not installed or fetched")
    for run in (r for r in RUNS if r["oracle"] == oracle):
        case = {k: v for k, v in run.items() if k != "delays"}
        assert same(run["delays"], oracle_cases.reference(case), case), run_id(run)

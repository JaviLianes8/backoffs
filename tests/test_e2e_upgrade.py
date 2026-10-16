"""Upgrade in place from the PyPI release to this wheel and compare what a consumer sees.

Needs the network, so it runs only with ``BACKOFFS_E2E_PYPI=1``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import venv
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYPI_VERSION = "0.2.0"
pytestmark = [
    pytest.mark.skipif(
        os.environ.get("BACKOFFS_E2E_PYPI") != "1", reason="set BACKOFFS_E2E_PYPI=1 (network)"
    ),
    pytest.mark.skipif(not (ROOT / "src").is_dir(), reason="needs the source tree to build"),
]
PROBE = r"""
import json, random, subprocess, sys
import backoffs
from backoffs import *
out = {"version": backoffs.__version__, "names": sorted(backoffs.__all__)}
out["plain"] = list(Policy(max_retries=6).delays())
for name, jitter in [("full", FullJitter()), ("equal", EqualJitter()),
                     ("decorrelated", DecorrelatedJitter()), ("additive", AdditiveJitter())]:
    out[name] = list(Policy(Exponential(0.3), jitter, cap=9.0, max_retries=12).delays(
        rng=random.Random(5)))
out["grpc"] = list(Policy.grpc(max_retries=10).delays(rng=random.Random(2)))
out["google"] = list(Policy.google_cloud(max_retries=8).delays(rng=random.Random(2)))
out["fibonacci"] = list(Policy(Fibonacci(0.5), max_elapsed=40.0).delays())
out["legacy"] = list(backoff(jitter="full", max_attempts=9, rng=random.Random(8)))
out["retry_after"] = parse_retry_after("120")
slept = []
calls = iter([OSError("a"), OSError("b"), "ok"])
def fn():
    item = next(calls)
    if isinstance(item, Exception):
        raise item
    return item
out["retry"] = [retry(fn, Policy(Linear(1.0, 2.0)), sleep=slept.append), slept]
try:
    retry(lambda: 1 / 0, Policy(max_retries=1), sleep=lambda s: None)
except RetryError as exc:
    out["retry_error"] = [exc.attempts, exc.reason, str(exc)]
cli = [sys.executable, "-m", "backoffs"]
fail = [sys.executable, "-c", "raise SystemExit(5)"]
out["exit_usage"] = subprocess.run(cli + ["schedule", "--max-retries", "-1"],
                                   capture_output=True).returncode
out["exit_give_up"] = subprocess.run(cli + ["run", "-q", "--base", "0.01", "--max-retries",
                                            "1", "--"] + fail, capture_output=True).returncode
print(json.dumps(out))
"""


def probe(python: Path) -> dict[str, Any]:
    result = subprocess.run(
        [str(python), "-c", PROBE], capture_output=True, text=True, check=True, cwd=python.parent
    )
    loaded: dict[str, Any] = json.loads(result.stdout)
    return loaded


def test_upgrading_from_pypi_keeps_every_sequence_and_changes_only_what_the_changelog_says(
    tmp_path: Path,
) -> None:
    wheels = tmp_path / "wheels"
    pip_wheel = [sys.executable, "-m", "pip", "wheel", "--no-deps", "-q", "-w", str(wheels)]
    subprocess.run([*pip_wheel, str(ROOT)], check=True)
    (wheel,) = wheels.glob("backoffs-*.whl")
    venv.EnvBuilder(with_pip=True).create(tmp_path / "venv")
    bin_dir = tmp_path / "venv" / ("Scripts" if os.name == "nt" else "bin")
    python = bin_dir / ("python.exe" if os.name == "nt" else "python")
    install = [str(python), "-m", "pip", "install", "-q", "--disable-pip-version-check"]
    subprocess.run([*install, f"backoffs=={PYPI_VERSION}"], check=True)
    before = probe(python)
    subprocess.run([*install, "--upgrade", str(wheel)], check=True)
    after = probe(python)

    assert (before["version"], after["version"]) == (PYPI_VERSION, "1.0.0")
    assert before["names"] == after["names"]
    same = ["plain", "full", "equal", "decorrelated", "additive", "grpc", "google",
            "fibonacci", "legacy", "retry_after", "retry"]  # fmt: skip
    for key in same:
        assert before[key] == after[key], key
    # The documented changes: exit statuses and the RetryError message.
    assert (before["exit_usage"], after["exit_usage"]) == (1, 2)
    assert (before["exit_give_up"], after["exit_give_up"]) == (1, 5)
    assert before["retry_error"][:2] == after["retry_error"][:2] == [2, "max_retries"]
    assert "division by zero" in before["retry_error"][2]
    assert "division by zero" not in after["retry_error"][2]
    assert after["retry_error"][2].endswith("last error: ZeroDivisionError")

"""Build the real wheel, install it into a throwaway venv and drive the real script."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import venv
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def installed(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """Yield the path of the installed ``backoffs`` console script."""
    work = tmp_path_factory.mktemp("e2e")
    wheels = work / "wheels"
    # Reuse a locally installed build backend when there is one, so the test also
    # works offline; otherwise pip fetches hatchling into an isolated environment.
    isolation = ["--no-build-isolation"] if importlib.util.find_spec("hatchling") else []
    command = [sys.executable, "-m", "pip", "wheel", "--no-deps", "-q", *isolation]
    subprocess.run([*command, "-w", str(wheels), str(ROOT)], check=True)
    (wheel,) = wheels.glob("backoffs-*.whl")
    env_dir = work / "venv"
    venv.EnvBuilder(with_pip=True).create(env_dir)
    bin_dir = env_dir / ("Scripts" if os.name == "nt" else "bin")
    python = bin_dir / ("python.exe" if os.name == "nt" else "python")
    subprocess.run([str(python), "-m", "pip", "install", "-q", str(wheel)], check=True)
    yield bin_dir / ("backoffs.exe" if os.name == "nt" else "backoffs")


def cli(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(script), *args], capture_output=True, text=True, timeout=120, check=False
    )


def test_the_installed_script_reports_the_version(installed: Path) -> None:
    from backoffs import __version__

    result = cli(installed, "--version")
    assert result.returncode == 0
    assert result.stdout.strip() == f"backoffs {__version__}"


def test_the_installed_script_prints_a_reproducible_schedule(installed: Path) -> None:
    args = ("schedule", "--jitter", "decorrelated", "--seed", "7", "--format", "json")
    first, second = cli(installed, *args), cli(installed, *args)
    assert first.returncode == 0 and first.stdout == second.stdout
    delays = json.loads(first.stdout)["delays"]
    assert len(delays) == 10 and all(1.0 <= d <= 30.0 for d in delays)


def test_the_installed_script_retries_a_really_failing_command(
    installed: Path, tmp_path: Path
) -> None:
    counter = tmp_path / "count"
    script = tmp_path / "flaky.py"
    script.write_text(
        "import pathlib, sys\n"
        f"p = pathlib.Path({str(counter)!r})\n"
        "n = int(p.read_text()) if p.exists() else 0\n"
        "p.write_text(str(n + 1))\n"
        "sys.exit(0 if n >= 2 else 3)\n"
    )
    result = cli(installed, "run", "--base", "0.05", "--", sys.executable, str(script))
    assert result.returncode == 0, result.stderr
    assert counter.read_text() == "3"
    assert result.stderr.count("failed (exit code 3); retrying in") == 2


def test_the_installed_script_gives_up_with_exit_one(installed: Path, tmp_path: Path) -> None:
    script = tmp_path / "broken.py"
    script.write_text("import sys\nsys.exit(9)\n")
    args = ("run", "--base", "0.01", "--max-retries", "2", "--", sys.executable, str(script))
    result = cli(installed, *args)
    assert result.returncode == 1
    assert "giving up after 3 attempt(s) (max_retries); last failure: exit code 9" in result.stderr


def test_the_installed_script_rejects_bad_usage_on_stderr(installed: Path) -> None:
    result = cli(installed, "schedule", "--max-retries", "-3")
    assert result.returncode == 1 and result.stdout == ""
    assert "max_retries" in result.stderr


def test_the_installed_library_imports_in_the_venv(installed: Path) -> None:
    python = installed.parent / installed.name.replace("backoffs", "python")
    code = "import backoffs; print(list(backoffs.Policy(max_retries=3).delays()))"
    result = subprocess.run([str(python), "-c", code], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "[0.1, 0.2, 0.4]"

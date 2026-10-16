from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import pytest

from backoffs import Exponential, FullJitter, Policy, __version__
from backoffs._cli import main

Capture = pytest.CaptureFixture[str]


def test_schedule_table_lists_delays_and_totals(capsys: Capture) -> None:
    assert main(["schedule", "--max-retries", "3"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[1].split() == ["1", "1.000", "1.000"]
    assert lines[3].split() == ["3", "4.000", "7.000"]
    assert lines[-1] == "stopped by max_retries: 3 retries, 7.000s in total"


def test_schedule_defaults_to_ten_retries(capsys: Capture) -> None:
    assert main(["schedule", "--format", "plain"]) == 0
    assert len(capsys.readouterr().out.split()) == 10


def test_schedule_json_matches_the_library_for_the_same_seed(capsys: Capture) -> None:
    assert main(["schedule", "--jitter", "full", "--seed", "42", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    expected = Policy(Exponential(1.0, 2.0), FullJitter(), cap=30.0, max_retries=10)
    assert payload["delays"] == list(expected.delays(rng=random.Random(42)))
    assert payload["stop_reason"] == "max_retries"


def test_schedule_max_elapsed_replaces_the_default_bound(capsys: Capture) -> None:
    assert main(["schedule", "--max-elapsed", "10", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["delays"] == [1.0, 2.0, 4.0]
    assert payload["stop_reason"] == "max_elapsed"


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["--strategy", "linear", "--base", "1", "--step", "0.5"], [1.0, 1.5, 2.0]),
        (["--strategy", "fibonacci", "--base", "2"], [2.0, 2.0, 4.0]),
        (["--strategy", "constant", "--base", "3"], [3.0, 3.0, 3.0]),
        (["--factor", "3", "--cap", "5"], [1.0, 3.0, 5.0]),
        (["--preset", "grpc"], [1.0]),
    ],
)
def test_schedule_strategies(capsys: Capture, args: list[str], expected: list[float]) -> None:
    max_retries = str(len(expected))
    assert main(["schedule", *args, "--max-retries", max_retries, "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["delays"] == expected


def test_schedule_jitter_options(capsys: Capture) -> None:
    common = ["--max-retries", "50", "--seed", "1", "--format", "json"]
    assert main(["schedule", "--jitter", "additive", "--amount", "0.5", "--cap", "4", *common]) == 0
    assert max(json.loads(capsys.readouterr().out)["delays"]) <= 4.0
    assert main(["schedule", "--jitter", "proportional", "--fraction", "0.1", *common]) == 0
    assert max(json.loads(capsys.readouterr().out)["delays"]) <= 33.0
    assert main(["schedule", "--preset", "google-cloud", *common]) == 0
    assert max(json.loads(capsys.readouterr().out)["delays"]) == 32.0


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["schedule", "--preset", "grpc", "--cap", "3"], "--preset cannot be combined"),
        (["schedule", "--strategy", "linear", "--factor", "3"], "--factor only applies"),
        (["schedule", "--strategy", "constant", "--step", "3"], "--step only applies"),
        (["schedule", "--fraction", "0.1"], "--fraction only applies"),
        (["schedule", "--amount", "0.1"], "--amount only applies"),
        (["schedule", "--base", "-1"], "base must be greater than 0"),
        (["schedule", "--strategy", "constant", "--base", "60"], "cap must be"),
        (["retry-after", "soon"], "not delay-seconds or an HTTP-date"),
        (["run"], "run needs a command"),
    ],
)
def test_errors_go_to_stderr_with_exit_two_or_one(
    capsys: Capture, args: list[str], message: str
) -> None:
    # A Retry-After value that does not parse is a data error (1); the rest are usage (2).
    assert main(args) == (1 if args[0] == "retry-after" else 2)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert message in captured.err


def test_usage_errors_exit_two(capsys: Capture) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["schedule", "--jitter", "wobble"])
    assert caught.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_version_and_help(capsys: Capture) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["--version"])
    assert caught.value.code == 0
    assert capsys.readouterr().out.strip() == f"backoffs {__version__}"
    with pytest.raises(SystemExit):
        main(["run", "--help"])
    assert "backoffs run --max-retries 4" in capsys.readouterr().out


def test_retry_after_prints_seconds(capsys: Capture) -> None:
    assert main(["retry-after", "120"]) == 0
    assert capsys.readouterr().out.strip() == "120"
    assert main(["retry-after", "Sun, 06 Nov 1994 08:49:37 GMT"]) == 0
    assert capsys.readouterr().out.strip() == "0"


def test_retry_after_prints_large_values_in_full(capsys: Capture) -> None:
    assert main(["retry-after", "1234567"]) == 0
    assert capsys.readouterr().out.strip() == "1234567"


def test_schedule_of_zero_delays_with_only_a_budget_is_truncated(capsys: Capture) -> None:
    args = ["schedule", "--strategy", "constant", "--base", "0", "--max-elapsed", "1"]
    assert main([*args, "--format", "plain"]) == 0
    captured = capsys.readouterr()
    assert len(captured.out.split()) == 10_000
    assert "truncated at 10000 rows" in captured.err


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "1e9", "soon"])
def test_attempt_timeout_must_be_positive_and_waitable(capsys: Capture, value: str) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["run", "--attempt-timeout", value, "--", "x"])
    assert caught.value.code == 2
    assert "positive number of seconds" in capsys.readouterr().err


def test_python_dash_m_runs_the_command() -> None:
    import subprocess

    result = subprocess.run(
        [sys.executable, "-m", "backoffs", "schedule", "--max-retries", "2", "--format", "plain"],
        capture_output=True,
        text=True,
        check=False,
        env={**__import__("os").environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
    )
    assert result.returncode == 0 and result.stdout.split() == ["1", "2"]


def script(tmp_path: Path, body: str) -> list[str]:
    path = tmp_path / "cmd.py"
    path.write_text(body)
    return [sys.executable, str(path)]


def test_run_succeeds_after_real_failures(tmp_path: Path, capsys: Capture) -> None:
    counter = tmp_path / "n"
    cmd = script(
        tmp_path,
        f"import pathlib, sys\np = pathlib.Path({str(counter)!r})\n"
        "n = int(p.read_text()) if p.exists() else 0\np.write_text(str(n + 1))\n"
        "sys.exit(0 if n >= 2 else 5)\n",
    )
    assert main(["run", "--base", "0.01", "--", *cmd]) == 0
    assert counter.read_text() == "3"
    assert capsys.readouterr().err.count("failed (exit code 5)") == 2


def test_run_gives_up_with_the_last_exit_status(tmp_path: Path, capsys: Capture) -> None:
    cmd = script(tmp_path, "import sys\nsys.exit(4)\n")
    assert main(["run", "--base", "0.01", "--max-retries", "2", "--", *cmd]) == 4
    assert "giving up after 3 attempt(s) (max_retries)" in capsys.readouterr().err


def test_run_stops_on_a_non_retryable_exit_code(tmp_path: Path, capsys: Capture) -> None:
    cmd = script(tmp_path, "import sys\nsys.exit(4)\n")
    assert main(["run", "--retry-on-exit", "75", "--", *cmd]) == 4
    err = capsys.readouterr().err
    assert "non-retryable exit code 4" in err and "retrying" not in err


def test_run_retries_a_timed_out_attempt(tmp_path: Path, capsys: Capture) -> None:
    cmd = script(tmp_path, "import time\ntime.sleep(5)\n")
    args = ["run", "-q", "--attempt-timeout", "0.3", "--base", "0.01", "--max-retries", "1"]
    assert main([*args, "--", *cmd]) == 124
    err = capsys.readouterr().err
    assert "timed out after 0.3s" in err and "retrying" not in err


def test_run_reports_a_missing_program(capsys: Capture) -> None:
    assert main(["run", "--", "backoffs-no-such-program-xyz"]) == 127
    assert "cannot run 'backoffs-no-such-program-xyz'" in capsys.readouterr().err

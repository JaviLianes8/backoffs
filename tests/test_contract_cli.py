"""The ``backoffs`` command's exit statuses, each pinned with a real process where possible."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from backoffs._cli import main
from backoffs._cli_run import exit_status

Capture = pytest.CaptureFixture[str]


def script(tmp_path: Path, body: str) -> list[str]:
    path = tmp_path / "cmd.py"
    path.write_text(body)
    return [sys.executable, str(path)]


@pytest.mark.parametrize("code", [1, 3, 75, 255])
def test_giving_up_exits_with_the_last_status(tmp_path: Path, capsys: Capture, code: int) -> None:
    cmd = script(tmp_path, f"import sys\nsys.exit({code})\n")
    assert main(["run", "-q", "--base", "0.001", "--max-retries", "1", "--", *cmd]) == code
    assert f"last failure: exit code {code}" in capsys.readouterr().err


def test_the_status_is_the_last_attempt_not_the_first(tmp_path: Path) -> None:
    counter = tmp_path / "n"
    cmd = script(
        tmp_path,
        f"import pathlib, sys\np = pathlib.Path({str(counter)!r})\n"
        "n = int(p.read_text()) if p.exists() else 0\np.write_text(str(n + 1))\n"
        "sys.exit(10 + n)\n",
    )
    assert main(["run", "-q", "--base", "0.001", "--max-retries", "2", "--", *cmd]) == 12


def test_a_non_retryable_status_ends_at_once_with_that_status(tmp_path: Path) -> None:
    counter = tmp_path / "n"
    cmd = script(
        tmp_path,
        f"import pathlib, sys\np = pathlib.Path({str(counter)!r})\n"
        "n = int(p.read_text()) if p.exists() else 0\np.write_text(str(n + 1))\n"
        "sys.exit(75 if n == 0 else 9)\n",
    )
    args = ["run", "-q", "--base", "0.001", "--retry-on-exit", "75", "--max-retries", "5"]
    assert main([*args, "--", *cmd]) == 9
    assert counter.read_text() == "2"


def test_a_file_that_cannot_be_executed_exits_126(tmp_path: Path, capsys: Capture) -> None:
    path = tmp_path / "not-a-program.txt"
    path.write_text("plain text\n")
    assert main(["run", "--max-retries", "0", "--", str(path)]) == 126
    assert "cannot run" in capsys.readouterr().err


def test_a_missing_program_exits_127_without_echoing_a_long_name(capsys: Capture) -> None:
    name = "backoffs-missing-" + "q" * 500
    assert main(["run", "--max-retries", "3", "--", name]) == 127
    err = capsys.readouterr().err
    assert "qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq" not in err and "retrying" not in err


def test_an_interrupt_exits_130_without_a_traceback(
    capsys: Capture, monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupted(*args: object, **kwargs: object) -> object:
        raise KeyboardInterrupt

    monkeypatch.setattr(subprocess, "run", interrupted)
    assert main(["run", "--", "anything"]) == 130
    assert capsys.readouterr().err == "backoffs: interrupted\n"


@pytest.mark.parametrize(
    "args",
    [
        ["run", "--retry-on-exit", "0", "--", "x"],
        ["run", "--cap", "1e300", "--", "x"],
        ["run", "--base", "nan", "--", "x"],
        ["schedule", "--max-retries", "-1"],
        ["schedule", "--cap", "inf"],
        ["run"],
        ["run", "--"],
    ],
)
def test_bad_values_exit_2_before_running_anything(capsys: Capture, args: list[str]) -> None:
    assert main(args) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err.startswith("backoffs: error: ")


def test_a_cap_the_platform_can_wait_is_accepted(tmp_path: Path) -> None:
    cmd = script(tmp_path, "pass\n")
    assert main(["run", "--cap", "1000000", "--", *cmd]) == 0


@pytest.mark.parametrize(
    ("returncode", "platform", "status"),
    [
        (0, "linux", 0),
        (7, "linux", 7),
        (-9, "linux", 137),
        (-15, "darwin", 143),
        (-1073741510, "win32", -1073741510),
        (3221225786, "win32", 3221225786 - 2**32),
        (3, "win32", 3),
    ],
)
def test_exit_status_maps_signals_and_windows_codes(
    monkeypatch: pytest.MonkeyPatch, returncode: int, platform: str, status: int
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    assert exit_status(returncode) == status


def test_the_real_entry_point_reports_the_status_to_the_shell(tmp_path: Path) -> None:
    cmd = script(tmp_path, "import sys\nsys.exit(42)\n")
    src = str(Path(__file__).parents[1] / "src")
    result = subprocess.run(
        [sys.executable, "-c", f"import sys; sys.path.insert(0, {src!r}); "
         "from backoffs._cli import main; raise SystemExit(main())",
         "run", "-q", "--max-retries", "0", "--", *cmd],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert result.returncode == 42

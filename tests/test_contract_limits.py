"""Extremes: huge delays saturate, odd schedules and clocks fail typed, CLI output stays valid."""

from __future__ import annotations

import json
import random
import sys
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backoffs import AdditiveJitter, Constant, Policy, RetryAfterError, parse_retry_after
from backoffs._cli import main

HUGE = sys.float_info.max


def test_additive_jitter_saturates_instead_of_overflowing() -> None:
    policy = Policy(Constant(1e308), AdditiveJitter(1e308), cap=None, max_retries=50)
    delays = policy.delays(rng=random.Random(1))
    values = list(delays)
    assert len(values) == 50 and all(v <= HUGE for v in values)
    assert delays.total == HUGE


def test_the_running_total_saturates_under_huge_floors() -> None:
    delays = Policy(Constant(1.0), max_retries=5).delays()
    for _ in range(5):
        delays.floor_next(HUGE)
        assert next(delays) == HUGE
    assert delays.total == HUGE == delays.elapsed


class ListSchedule:
    first = 1.0

    def raw(self) -> Iterable[float]:
        return [1.0, 2.0, 3.0]


def test_a_schedule_may_return_any_iterable() -> None:
    assert list(Policy(ListSchedule(), max_retries=3).delays()) == [1.0, 2.0, 3.0]  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "now",
    [
        datetime.min.replace(tzinfo=timezone(timedelta(hours=14))),
        datetime.max.replace(tzinfo=timezone(timedelta(hours=-14))),
    ],
)
def test_an_rfc850_date_against_an_extreme_now_fails_typed(now: datetime) -> None:
    with pytest.raises(RetryAfterError):
        parse_retry_after("Sunday, 06-Nov-94 08:49:37 GMT", now=now)


def test_schedule_json_stays_valid_for_huge_delays(capsys: pytest.CaptureFixture[str]) -> None:
    args = ["schedule", "--strategy", "constant", "--base", "1e308", "--cap", "1.7e308"]
    assert main([*args, "--max-retries", "3", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out, parse_constant=pytest.fail)
    assert payload["total"] == HUGE


@pytest.mark.skipif(sys.platform != "win32", reason="Windows reports exit codes unsigned")
def test_a_negative_retry_on_exit_code_matches_on_windows(tmp_path: Path) -> None:
    counter = tmp_path / "n"
    body = (
        f"import pathlib\np = pathlib.Path({str(counter)!r})\n"
        "n = int(p.read_text()) if p.exists() else 0\np.write_text(str(n + 1))\n"
        "raise SystemExit(0 if n else -1)\n"
    )
    script = tmp_path / "cmd.py"
    script.write_text(body)
    args = ["run", "-q", "--retry-on-exit", "-1", "--base", "0.001", "--max-retries", "2"]
    assert main([*args, "--", sys.executable, str(script)]) == 0
    assert counter.read_text() == "2"

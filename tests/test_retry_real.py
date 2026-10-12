"""Real retries, nothing mocked: a flaky local HTTP server and a flaky subprocess."""

from __future__ import annotations

import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

from backoffs import Constant, Exponential, Policy, RetryError, parse_retry_after, retry


class FlakyHandler(BaseHTTPRequestHandler):
    """Answers 503 with a Retry-After header ``failures`` times, then 200."""

    failures = 0
    retry_after = "0"
    hits: ClassVar[list[float]] = []

    def do_GET(self) -> None:
        FlakyHandler.hits.append(time.monotonic())
        if len(FlakyHandler.hits) <= FlakyHandler.failures:
            self.send_response(503)
            self.send_header("Retry-After", FlakyHandler.retry_after)
            self.end_headers()
            return
        body = b"healthy"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return None


@pytest.fixture
def server() -> Iterator[str]:
    FlakyHandler.hits = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FlakyHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}/"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=5) as response:
        body: bytes = response.read()
        return body


def hint(exc: BaseException) -> float | None:
    if isinstance(exc, urllib.error.HTTPError):
        value = exc.headers.get("Retry-After")
        return None if value is None else parse_retry_after(value)
    return None


def test_retry_recovers_from_a_server_that_fails_three_times(server: str) -> None:
    FlakyHandler.failures = 3
    FlakyHandler.retry_after = "0"
    policy = Policy(Exponential(0.01), max_retries=5)
    assert retry(lambda: fetch(server), policy, retry_on=urllib.error.HTTPError) == b"healthy"
    assert len(FlakyHandler.hits) == 4


def test_retry_after_seconds_from_the_server_is_honoured(server: str) -> None:
    FlakyHandler.failures = 1
    FlakyHandler.retry_after = "1"
    policy = Policy(Constant(0.01), max_retries=2)
    assert retry(lambda: fetch(server), policy, retry_after=hint) == b"healthy"
    first, second = FlakyHandler.hits
    assert second - first >= 0.95


def test_retry_after_http_date_from_the_server_is_honoured(server: str) -> None:
    FlakyHandler.failures = 1
    moment = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=3)
    FlakyHandler.retry_after = format_datetime(moment, usegmt=True)
    policy = Policy(Constant(0.01), max_retries=2)
    assert retry(lambda: fetch(server), policy, retry_after=hint) == b"healthy"
    first, second = FlakyHandler.hits
    assert second - first >= 1.5


def test_a_server_that_never_recovers_exhausts_the_policy(server: str) -> None:
    FlakyHandler.failures = 100
    FlakyHandler.retry_after = "0"
    with pytest.raises(RetryError) as caught:
        retry(lambda: fetch(server), Policy(Constant(0.01), max_retries=2))
    assert caught.value.attempts == 3
    assert isinstance(caught.value.last_exception, urllib.error.HTTPError)


FLAKY_SCRIPT = """
import pathlib, sys
counter = pathlib.Path(sys.argv[1])
seen = int(counter.read_text()) if counter.exists() else 0
counter.write_text(str(seen + 1))
sys.exit(0 if seen >= int(sys.argv[2]) else 7)
"""


def run_flaky(tmp_path: Path, failures: int) -> None:
    script = tmp_path / "flaky.py"
    script.write_text(FLAKY_SCRIPT)
    subprocess.run(
        [sys.executable, str(script), str(tmp_path / "count"), str(failures)], check=True
    )


def test_retry_recovers_from_a_subprocess_that_fails_twice(tmp_path: Path) -> None:
    retry(
        lambda: run_flaky(tmp_path, 2),
        Policy(Constant(0.01), max_retries=4),
        retry_on=subprocess.CalledProcessError,
    )
    assert (tmp_path / "count").read_text() == "3"


def test_a_subprocess_that_keeps_failing_gives_up_with_its_error(tmp_path: Path) -> None:
    with pytest.raises(RetryError) as caught:
        retry(
            lambda: run_flaky(tmp_path, 50),
            Policy(Constant(0.01), max_retries=2),
            retry_on=subprocess.CalledProcessError,
        )
    last = caught.value.last_exception
    assert isinstance(last, subprocess.CalledProcessError) and last.returncode == 7
    assert (tmp_path / "count").read_text() == "3"

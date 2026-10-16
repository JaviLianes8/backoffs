"""The ``backoffs`` command: print a backoff schedule, or retry a command with backoff."""

from __future__ import annotations

import argparse
import itertools
import json
import math
import random
import sys
import threading
from collections.abc import Sequence
from typing import NoReturn

from . import __version__
from ._cli_policy import add_policy_options, build_policy
from ._cli_run import run_command
from ._errors import BackoffError, RetryAfterError
from ._retry_after import parse_retry_after
from ._validate import positive, preview

_MAX_ROWS = 10_000
_EPILOG = """examples:
  backoffs schedule --max-retries 6
  backoffs schedule --jitter full --seed 42 --format json
  backoffs schedule --strategy fibonacci --base 0.5 --cap 10 --max-elapsed 30
  backoffs schedule --preset grpc --max-retries 8
  backoffs run --max-retries 4 --base 0.5 -- curl --fail https://example.com/health
  backoffs run --retry-on-exit 75 --attempt-timeout 10 -- python job.py
  backoffs retry-after "Sun, 06 Nov 1994 08:49:37 GMT"
"""


USAGE = 2
INTERRUPTED = 130


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(USAGE, f"{self.prog}: error: {message}\n")


def _subparser(
    sub: argparse._SubParsersAction[_Parser], name: str, summary: str, description: str
) -> _Parser:
    return sub.add_parser(
        name,
        help=summary,
        description=description,
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def _seconds(text: str) -> float:
    try:
        seconds = positive("--attempt-timeout", float(text))
    except ValueError:
        seconds = math.nan
    if not seconds <= threading.TIMEOUT_MAX:
        raise argparse.ArgumentTypeError(f"must be a positive number of seconds: {preview(text)}")
    return seconds


def _parser() -> _Parser:
    parser = _Parser(
        prog="backoffs",
        description="Plan backoff schedules and retry commands with backoff and jitter.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
    schedule = _subparser(
        sub,
        "schedule",
        "print the delays a policy produces (default bound: 10 retries)",
        "Print each delay and the running total. Nothing sleeps.",
    )
    add_policy_options(schedule)
    schedule.add_argument("--format", choices=("table", "json", "plain"), default="table")
    run = _subparser(
        sub,
        "run",
        "run a command, retrying with backoff until it exits 0 (default bound: 5 retries)",
        "Run COMMAND; on failure sleep the next delay and try again. Exits 0 on "
        "success; otherwise with the status of the last attempt (124 if it timed "
        "out), 126 or 127 if the command cannot start, 2 for bad options and 130 "
        "when interrupted.",
    )
    add_policy_options(run)
    run.add_argument(
        "--retry-on-exit",
        type=int,
        action="append",
        default=[],
        metavar="CODE",
        help="retry only on this exit code (repeatable; default: any non-zero code); "
        "a timed out attempt is always retried",
    )
    run.add_argument(
        "--attempt-timeout", type=_seconds, metavar="S", help="kill an attempt after S seconds"
    )
    run.add_argument("-q", "--quiet", action="store_true", help="do not report retries")
    run.add_argument("argv", nargs=argparse.REMAINDER, metavar="-- COMMAND [ARG ...]")
    after = _subparser(
        sub,
        "retry-after",
        "convert a Retry-After header value to seconds",
        "Print the seconds a Retry-After value asks for (a past date prints 0). "
        "Exits 1 if the value is neither delay-seconds nor an HTTP-date.",
    )
    after.add_argument("value", help="delay-seconds or an HTTP-date (RFC 9110)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``backoffs`` script; returns the process exit status."""
    args = _parser().parse_args(argv)
    try:
        if args.command == "retry-after":
            return _retry_after(args.value)
        rng = random.Random(args.seed) if args.seed is not None else None
        if args.command == "schedule":
            _print_schedule(args, rng)
            return 0
        command = list(args.argv)
        if command and command[0] == "--":
            command = command[1:]
        if not command:
            raise ValueError("run needs a command after --")
        if 0 in args.retry_on_exit:
            raise ValueError("--retry-on-exit 0 is success and cannot be retried")
        policy = build_policy(args, default_retries=5)
        # Jitter can stretch a delay to twice the cap at most; the sleep must accept it.
        if policy.cap is not None and policy.cap * 2 > threading.TIMEOUT_MAX:
            raise ValueError(f"--cap must be at most {threading.TIMEOUT_MAX / 2:g} seconds")
    except (BackoffError, ValueError) as exc:
        print(f"backoffs: error: {exc}", file=sys.stderr)
        return USAGE
    except KeyboardInterrupt:
        return INTERRUPTED
    try:
        return run_command(
            command,
            policy,
            retry_on_exit=args.retry_on_exit,
            attempt_timeout=args.attempt_timeout,
            quiet=args.quiet,
            rng=rng,
        )
    except KeyboardInterrupt:
        print("backoffs: interrupted", file=sys.stderr)
        return INTERRUPTED


def _retry_after(value: str) -> int:
    try:
        seconds = parse_retry_after(value)
    except RetryAfterError as exc:
        print(f"backoffs: error: {exc}", file=sys.stderr)
        return 1
    print(int(seconds) if seconds.is_integer() else f"{seconds:.3f}")
    return 0


def _print_schedule(args: argparse.Namespace, rng: random.Random | None) -> None:
    delays = build_policy(args, default_retries=10).delays(rng=rng)
    # A zero-delay schedule bounded only by --max-elapsed would never end.
    values = list(itertools.islice(delays, _MAX_ROWS))
    if len(values) == _MAX_ROWS and delays.stop_reason is None:
        print(f"backoffs: schedule truncated at {_MAX_ROWS} rows", file=sys.stderr)
    if args.format == "json":
        payload = {"delays": values, "total": delays.total, "stop_reason": delays.stop_reason}
        print(json.dumps(payload, indent=2))
        return
    if args.format == "plain":
        for value in values:
            print(f"{value:.6g}")
        return
    print(f"{'retry':>5}  {'delay_s':>10}  {'total_s':>10}")
    total = 0.0
    for index, value in enumerate(values, start=1):
        total += value
        print(f"{index:>5}  {value:>10.3f}  {total:>10.3f}")
    print(f"stopped by {delays.stop_reason}: {len(values)} retries, {delays.total:.3f}s in total")

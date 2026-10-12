"""``backoffs run``: retry a real command with backoff until it exits cleanly."""

from __future__ import annotations

import random
import subprocess
import sys
from collections.abc import Sequence

from ._errors import RetryError
from ._policy import Policy
from ._retry import RetryState, retry


class CommandFailed(Exception):
    """One attempt of the command exited with a retryable status or timed out."""


class _NotRetryable(Exception):
    pass


def run_command(
    command: Sequence[str],
    policy: Policy,
    *,
    retry_on_exit: Sequence[int],
    attempt_timeout: float | None,
    quiet: bool,
    rng: random.Random | None,
) -> int:
    """Run ``command`` until it exits 0; return the exit status for ``main``."""

    def attempt() -> None:
        try:
            done = subprocess.run(list(command), timeout=attempt_timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise CommandFailed(f"timed out after {attempt_timeout:g}s") from exc
        if done.returncode == 0:
            return
        description = f"exit code {done.returncode}"
        if retry_on_exit and done.returncode not in retry_on_exit:
            raise _NotRetryable(description)
        raise CommandFailed(description)

    def report(state: RetryState) -> None:
        if not quiet:
            print(
                f"backoffs: attempt {state.attempt} failed ({state.exception}); "
                f"retrying in {state.delay:.3f}s",
                file=sys.stderr,
                flush=True,
            )

    try:
        retry(attempt, policy, retry_on=CommandFailed, on_retry=report, rng=rng)
    except OSError as exc:
        print(f"backoffs: cannot run {command[0]!r}: {exc.strerror or exc}", file=sys.stderr)
        return 1
    except _NotRetryable as exc:
        print(f"backoffs: command failed with non-retryable {exc}", file=sys.stderr)
        return 1
    except RetryError as exc:
        print(
            f"backoffs: giving up after {exc.attempts} attempt(s) "
            f"({exc.reason}); last failure: {exc.last_exception}",
            file=sys.stderr,
        )
        return 1
    return 0

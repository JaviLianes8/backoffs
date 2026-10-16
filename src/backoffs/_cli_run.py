"""``backoffs run``: retry a real command with backoff until it exits cleanly."""

from __future__ import annotations

import random
import subprocess
import sys
from collections.abc import Sequence

from ._controller import RetryState
from ._errors import RetryError
from ._policy import Policy
from ._retry import retry
from ._validate import preview

# The status the coreutils ``timeout`` command uses for a run it had to stop.
TIMED_OUT = 124
CANNOT_EXECUTE = 126
NOT_FOUND = 127


class CommandFailed(Exception):
    """One attempt of the command exited with a retryable status or timed out."""

    def __init__(self, description: str, status: int) -> None:
        super().__init__(description)
        self.status = status


class _NotRetryable(CommandFailed):
    pass


def exit_status(returncode: int) -> int:
    """Map a child's return code to the status this process should exit with."""
    if returncode < 0 and sys.platform != "win32":
        return 128 - returncode  # killed by a signal, as a shell reports it
    if returncode > 0x7FFFFFFF:
        return returncode - 2**32  # Windows codes are unsigned; sys.exit wants signed
    return returncode


def run_command(
    command: Sequence[str],
    policy: Policy,
    *,
    retry_on_exit: Sequence[int],
    attempt_timeout: float | None,
    quiet: bool,
    rng: random.Random | None,
) -> int:
    """Run ``command`` until it exits 0; return the exit status for ``main``.

    On failure that is the status of the last attempt (124 for a timeout), 127 when
    the command is not found and 126 when it cannot be executed.
    """

    def attempt() -> None:
        try:
            done = subprocess.run(list(command), timeout=attempt_timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise CommandFailed(f"timed out after {attempt_timeout:g}s", TIMED_OUT) from exc
        if done.returncode == 0:
            return
        description = f"exit code {done.returncode}"
        status = exit_status(done.returncode)
        # Accept a code in either form: as the child returned it or as this process exits.
        listed = done.returncode in retry_on_exit or status in retry_on_exit
        if retry_on_exit and not listed:
            raise _NotRetryable(description, status)
        raise CommandFailed(description, status)

    def report(state: RetryState) -> None:
        if not quiet:
            print(
                f"backoffs: attempt {state.attempt} failed ({state.exception}); "
                f"retrying in {state.delay:.3f}s",
                file=sys.stderr,
                flush=True,
            )

    try:
        retry(
            attempt,
            policy,
            retry_on=CommandFailed,
            giveup=lambda exc: isinstance(exc, _NotRetryable),
            on_retry=report,
            rng=rng,
        )
    except OSError as exc:
        reason = exc.strerror or type(exc).__name__
        print(f"backoffs: cannot run {preview(command[0])}: {reason}", file=sys.stderr)
        return NOT_FOUND if isinstance(exc, FileNotFoundError) else CANNOT_EXECUTE
    except _NotRetryable as exc:
        print(f"backoffs: command failed with non-retryable {exc}", file=sys.stderr)
        return exc.status
    except RetryError as exc:
        last = exc.last_exception
        print(
            f"backoffs: giving up after {exc.attempts} attempt(s) "
            f"({exc.reason}); last failure: {last}",
            file=sys.stderr,
        )
        return last.status if isinstance(last, CommandFailed) else 1
    return 0

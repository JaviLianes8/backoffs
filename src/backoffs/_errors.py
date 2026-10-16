"""Typed errors raised by backoffs, all rooted at :class:`BackoffError`."""

from __future__ import annotations


class BackoffError(Exception):
    """Base class for every error this library raises on purpose.

    >>> from backoffs import BackoffError, Policy
    >>> try:
    ...     Policy(max_retries=-1)
    ... except BackoffError as exc:
    ...     print(exc)
    max_retries must be None or a non-negative integer, got -1
    """


class InvalidPolicyError(BackoffError, ValueError):
    """An argument of a schedule, jitter, policy or retry helper is invalid.

    Raised for a wrong type as well as for a value out of range. It subclasses
    :class:`ValueError` so code written against the 0.1 API, which raised plain
    ``ValueError``, keeps working. Messages never echo more than a short preview of
    the rejected value.

    >>> from backoffs import Exponential, InvalidPolicyError
    >>> try:
    ...     Exponential(base=0)
    ... except InvalidPolicyError as exc:
    ...     print(exc)
    base must be greater than 0, got 0
    """


class RetryAfterError(BackoffError, ValueError):
    """A ``Retry-After`` value is neither delay-seconds nor an HTTP-date (RFC 9110).

    >>> from backoffs import RetryAfterError, parse_retry_after
    >>> try:
    ...     parse_retry_after("soon")
    ... except RetryAfterError as exc:
    ...     print(exc)
    not delay-seconds or an HTTP-date: 'soon'
    """


class RetryError(BackoffError):
    """Raised by :func:`~backoffs.retry` when the policy runs out of retries or time.

    The final exception is attached as ``__cause__`` and as :attr:`last_exception`.
    The message names only its type, never its text, which may hold data you do not
    want in a log. Exceptions that the filters reject, or that ``giveup`` accepts, are
    never wrapped: they propagate unchanged.

    >>> from backoffs import Constant, Policy, RetryError, retry
    >>> def always_fails() -> None:
    ...     raise ConnectionError("refused")
    >>> try:
    ...     retry(always_fails, Policy(Constant(0.0), max_retries=2), sleep=lambda s: None)
    ... except RetryError as exc:
    ...     print(exc.attempts, exc.reason, type(exc.last_exception).__name__)
    3 max_retries ConnectionError
    """

    def __init__(
        self,
        *,
        attempts: int,
        elapsed: float,
        reason: str,
        last_exception: BaseException,
    ) -> None:
        self.attempts = attempts
        """Total number of calls made, the first one included."""
        self.elapsed = elapsed
        """Seconds measured by the injected clock from the first call to the end."""
        self.reason = reason
        """Why retrying stopped: ``"max_retries"`` or ``"max_elapsed"``."""
        self.last_exception = last_exception
        """The exception raised by the final call."""
        super().__init__(
            f"gave up after {attempts} attempt(s) in {elapsed:.3f}s ({reason[:32]}); "
            f"last error: {type(last_exception).__name__[:64]}"
        )

    def __reduce__(self) -> tuple[object, ...]:
        # The keyword-only constructor needs help to survive pickling.
        state = (self.attempts, self.elapsed, self.reason, self.last_exception)
        return (_rebuild_retry_error, state)


def _rebuild_retry_error(
    attempts: int, elapsed: float, reason: str, last_exception: BaseException
) -> RetryError:
    return RetryError(
        attempts=attempts, elapsed=elapsed, reason=reason, last_exception=last_exception
    )

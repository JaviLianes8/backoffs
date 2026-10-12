"""Typed errors raised by backoffs, all rooted at :class:`BackoffError`."""

from __future__ import annotations


class BackoffError(Exception):
    """Base class for every error this library raises on purpose."""


class InvalidPolicyError(BackoffError, ValueError):
    """A schedule, jitter or policy argument is out of range.

    It subclasses :class:`ValueError` so code written against the 0.1 API, which
    raised plain ``ValueError``, keeps working.
    """


class RetryAfterError(BackoffError, ValueError):
    """A ``Retry-After`` value is neither delay-seconds nor an HTTP-date (RFC 9110)."""


class RetryError(BackoffError):
    """Raised by :func:`~backoffs.retry` when the policy runs out of retries or time.

    The final exception is attached as ``__cause__`` and as :attr:`last_exception`.
    Exceptions that the filters reject, or that ``giveup`` accepts, are never wrapped:
    they propagate unchanged.
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
            f"gave up after {attempts} attempt(s) in {elapsed:.3f}s ({reason}): "
            f"{type(last_exception).__name__}: {last_exception}"
        )

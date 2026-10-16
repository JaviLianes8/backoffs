"""Pure backoff delays: growth schedules, cap, jitter, budgets and an optional retry helper."""

from __future__ import annotations

from ._backoff import backoff
from ._controller import RetryState
from ._delays import Delays
from ._errors import BackoffError, InvalidPolicyError, RetryAfterError, RetryError
from ._jitter import (
    AdditiveJitter,
    DecorrelatedJitter,
    EqualJitter,
    FullJitter,
    Jitter,
    NoJitter,
    ProportionalJitter,
)
from ._policy import Policy
from ._retry import aretry, retry
from ._retry_after import parse_retry_after
from ._schedules import Constant, Exponential, Fibonacci, Linear, Schedule

__version__ = "0.2.0"

__all__ = [
    "AdditiveJitter",
    "BackoffError",
    "Constant",
    "DecorrelatedJitter",
    "Delays",
    "EqualJitter",
    "Exponential",
    "Fibonacci",
    "FullJitter",
    "InvalidPolicyError",
    "Jitter",
    "Linear",
    "NoJitter",
    "Policy",
    "ProportionalJitter",
    "RetryAfterError",
    "RetryError",
    "RetryState",
    "Schedule",
    "aretry",
    "backoff",
    "parse_retry_after",
    "retry",
]

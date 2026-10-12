"""Shared argument checks that raise :class:`InvalidPolicyError` with a clear message."""

from __future__ import annotations

import math

from ._errors import InvalidPolicyError


def finite(name: str, value: float) -> float:
    """Return ``value`` as a float, rejecting bools, NaN and infinities."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidPolicyError(f"{name} must be a number, got {value!r}")
    result = float(value)
    if not math.isfinite(result):
        raise InvalidPolicyError(f"{name} must be finite, got {value!r}")
    return result


def non_negative(name: str, value: float) -> float:
    result = finite(name, value)
    if result < 0.0:
        raise InvalidPolicyError(f"{name} must be greater than or equal to 0, got {value!r}")
    return result


def positive(name: str, value: float) -> float:
    result = finite(name, value)
    if result <= 0.0:
        raise InvalidPolicyError(f"{name} must be greater than 0, got {value!r}")
    return result


def optional_count(name: str, value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidPolicyError(f"{name} must be None or a non-negative integer, got {value!r}")
    return value

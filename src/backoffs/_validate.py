"""Shared argument checks that raise :class:`InvalidPolicyError` with a short message."""

from __future__ import annotations

import math

from ._errors import InvalidPolicyError

_PREVIEW = 32


def preview(value: object) -> str:
    """Describe ``value`` for an error message in at most a few dozen characters.

    Numbers and short strings are shown; anything else, or anything long, is reduced
    to its type name (and length), so a message never carries a huge or secret input.
    """
    # The base-class methods ignore any __repr__ a subclass defines.
    if isinstance(value, bool) or value is None:
        return repr(value)
    if isinstance(value, float):
        return float.__repr__(value)
    if isinstance(value, int):
        bits = int.bit_length(value)
        return int.__repr__(value) if bits <= 64 else f"an int of {bits} bits"
    if isinstance(value, str):
        text = str.__str__(value)
        return ascii(text) if len(text) <= _PREVIEW else f"a str of {len(text)} characters"
    return f"a value of type {type(value).__name__[:_PREVIEW]}"


def finite(name: str, value: float) -> float:
    """Return ``value`` as a float, rejecting bools, non-numbers, NaN and infinities."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidPolicyError(f"{name} must be a number, got {preview(value)}")
    try:
        result = float(value)
    except OverflowError:
        raise InvalidPolicyError(f"{name} must be finite, got {preview(value)}") from None
    if not math.isfinite(result):
        raise InvalidPolicyError(f"{name} must be finite, got {preview(value)}")
    return result


def non_negative(name: str, value: float) -> float:
    result = finite(name, value)
    if result < 0.0:
        raise InvalidPolicyError(f"{name} must be greater than or equal to 0, got {preview(value)}")
    return result


def positive(name: str, value: float) -> float:
    result = finite(name, value)
    if result <= 0.0:
        raise InvalidPolicyError(f"{name} must be greater than 0, got {preview(value)}")
    return result


def optional_count(name: str, value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidPolicyError(
            f"{name} must be None or a non-negative integer, got {preview(value)}"
        )
    return value


def callable_or_raise(name: str, value: object) -> None:
    if not callable(value):
        raise InvalidPolicyError(f"{name} must be callable, got {preview(value)}")

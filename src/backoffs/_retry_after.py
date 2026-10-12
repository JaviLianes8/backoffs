"""Parse an HTTP ``Retry-After`` field value (RFC 9110, section 10.2.3) into seconds."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from ._errors import RetryAfterError

_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_LONG_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_TIME = r"(\d{2}):(\d{2}):(\d{2})"
_MONTH = "(" + "|".join(_MONTHS) + ")"
# The three HTTP-date forms of RFC 9110 section 5.6.7. Names are case-sensitive there.
_IMF_FIXDATE = re.compile(
    r"(" + "|".join(_DAYS) + r"), (\d{2}) " + _MONTH + r" (\d{4}) " + _TIME + r" GMT"
)
_RFC850 = re.compile(
    r"(" + "|".join(_LONG_DAYS) + r"), (\d{2})-" + _MONTH + r"-(\d{2}) " + _TIME + r" GMT"
)
_ASCTIME = re.compile(
    r"(" + "|".join(_DAYS) + r") " + _MONTH + r" ([ \d]\d) " + _TIME + r" (\d{4})"
)
_DELAY_SECONDS = re.compile(r"[0-9]+")


def parse_retry_after(value: str, *, now: datetime | None = None) -> float:
    """Return how many seconds a ``Retry-After`` value asks the client to wait.

    ``value`` is either delay-seconds (``"120"``, a non-negative integer) or an
    HTTP-date in any of the three forms RFC 9110 requires recipients to accept
    (``"Sun, 06 Nov 1994 08:49:37 GMT"``, the obsolete RFC 850 and asctime forms).
    A date is measured against ``now`` (timezone-aware, default: the current UTC
    time); a date in the past yields ``0.0``. Surrounding whitespace is ignored.

    Raises :class:`~backoffs.RetryAfterError` (a ``ValueError``) for anything else,
    including fractions and negative numbers, which the grammar does not allow.

    >>> parse_retry_after("120")
    120.0
    """
    if not isinstance(value, str):
        raise RetryAfterError(f"Retry-After must be a string, got {value!r}")
    text = value.strip(" \t")
    if _DELAY_SECONDS.fullmatch(text):
        try:
            return float(int(text))
        except (OverflowError, ValueError) as exc:
            raise RetryAfterError(f"Retry-After delay is too large: {text[:20]}...") from exc
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None or now.utcoffset() is None:
        raise RetryAfterError("now must be a timezone-aware datetime")
    moment = _parse_http_date(text, now)
    return max(0.0, (moment - now).total_seconds())


def _parse_http_date(text: str, now: datetime) -> datetime:
    match = _IMF_FIXDATE.fullmatch(text)
    if match:
        _, day, month, year, hh, mm, ss = match.groups()
        return _build(int(year), month, int(day), hh, mm, ss, text)
    match = _RFC850.fullmatch(text)
    if match:
        _, day, month, yy, hh, mm, ss = match.groups()
        return _rfc850(int(yy), month, int(day), hh, mm, ss, text, now)
    match = _ASCTIME.fullmatch(text)
    if match:
        _, month, day, hh, mm, ss, year = match.groups()
        return _build(int(year), month, int(day.strip()), hh, mm, ss, text)
    raise RetryAfterError(f"not delay-seconds or an HTTP-date: {text!r}")


def _rfc850(
    yy: int, month: str, day: int, hh: str, mm: str, ss: str, text: str, now: datetime
) -> datetime:
    # RFC 9110 5.6.7: a two-digit year that appears more than 50 years in the future
    # is the most recent past year with the same last two digits. So the answer is the
    # latest year ending in ``yy`` that is at most 50 years ahead of ``now``.
    horizon = timedelta(days=50 * 365.2425)
    century = now.year - now.year % 100
    for year in (century + 100 + yy, century + yy, century - 100 + yy):
        if 1 <= year <= 9999:
            moment = _build(year, month, day, hh, mm, ss, text)
            if moment - now <= horizon:
                return moment
    raise RetryAfterError(f"invalid HTTP-date: {text!r}")


def _build(year: int, month: str, day: int, hh: str, mm: str, ss: str, text: str) -> datetime:
    hour, minute, second = int(hh), int(mm), int(ss)
    # The grammar allows second 60 for a leap second; datetime does not.
    leap = second == 60
    try:
        moment = datetime(
            year,
            _MONTHS.index(month) + 1,
            day,
            hour,
            minute,
            59 if leap else second,
            tzinfo=timezone.utc,
        )
    except ValueError as exc:
        raise RetryAfterError(f"invalid HTTP-date: {text!r}") from exc
    return moment + timedelta(seconds=1) if leap else moment

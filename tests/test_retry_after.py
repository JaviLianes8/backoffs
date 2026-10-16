"""Retry-After parsing per RFC 9110 sections 10.2.3 and 5.6.7."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backoffs import RetryAfterError, parse_retry_after

NOW = datetime(1994, 11, 6, 8, 49, 0, tzinfo=timezone.utc)


def test_delay_seconds_is_a_plain_integer() -> None:
    assert parse_retry_after("120") == 120.0
    assert parse_retry_after("0") == 0.0


def test_surrounding_whitespace_is_ignored() -> None:
    assert parse_retry_after(" \t30 ") == 30.0


@pytest.mark.parametrize(
    "value",
    [
        "Sun, 06 Nov 1994 08:49:37 GMT",  # IMF-fixdate, the preferred form
        "Sunday, 06-Nov-94 08:49:37 GMT",  # obsolete RFC 850 form
        "Sun Nov  6 08:49:37 1994",  # obsolete asctime form
    ],
)
def test_all_three_http_date_forms_are_accepted(value: str) -> None:
    assert parse_retry_after(value, now=NOW) == 37.0


def test_asctime_with_a_two_digit_day() -> None:
    later = NOW.replace(day=16)
    assert parse_retry_after("Wed Nov 16 08:49:37 1994", now=later) == 37.0


def test_a_date_in_the_past_means_no_wait() -> None:
    assert parse_retry_after("Sat, 05 Nov 1994 08:49:37 GMT", now=NOW) == 0.0


def test_a_non_utc_now_is_compared_correctly() -> None:
    madrid = NOW.astimezone(timezone(timedelta(hours=1)))
    assert parse_retry_after("Sun, 06 Nov 1994 08:49:37 GMT", now=madrid) == 37.0


def test_default_now_is_the_current_time() -> None:
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    value = future.strftime("%a, %d %b %Y %H:%M:%S GMT")
    assert 3590.0 < parse_retry_after(value) <= 3600.0


def test_leap_second_is_accepted() -> None:
    assert parse_retry_after("Sun, 06 Nov 1994 08:49:60 GMT", now=NOW) == 60.0


def test_rfc850_two_digit_year_in_the_near_future_stays_in_this_century() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    seconds = parse_retry_after("Friday, 01-Jan-27 00:00:00 GMT", now=now)
    assert seconds == (datetime(2027, 1, 1, tzinfo=timezone.utc) - now).total_seconds()


def test_rfc850_two_digit_year_can_roll_into_the_next_century() -> None:
    now = datetime(2099, 6, 1, tzinfo=timezone.utc)
    seconds = parse_retry_after("Monday, 01-Jun-01 00:00:00 GMT", now=now)
    assert seconds == (datetime(2101, 6, 1, tzinfo=timezone.utc) - now).total_seconds()


def test_rfc850_year_more_than_fifty_years_ahead_means_the_past_century() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # 99 would be 2099 (73 years ahead), so it is 1999: already past.
    assert parse_retry_after("Friday, 31-Dec-99 23:59:59 GMT", now=now) == 0.0


@pytest.mark.parametrize(
    "value",
    [
        "",
        "-5",
        "1.5",
        "+3",
        "soon",
        "sun, 06 Nov 1994 08:49:37 GMT",  # names are case-sensitive
        "Sun, 06 Nov 1994 08:49:37 UTC",
        "Sun, 32 Nov 1994 08:49:37 GMT",
        "Sun, 06 Nov 1994 25:49:37 GMT",
        "Sun, 6 Nov 1994 08:49:37 GMT",
        "9" * 5000,
    ],
)
def test_malformed_values_raise_a_value_error_subclass(value: str) -> None:
    with pytest.raises(RetryAfterError) as caught:
        parse_retry_after(value, now=NOW)
    assert isinstance(caught.value, ValueError)


def test_a_huge_but_valid_integer_is_reported_not_crashed() -> None:
    with pytest.raises(RetryAfterError, match="too large"):
        parse_retry_after("9" * 400, now=NOW)


def test_naive_now_is_rejected() -> None:
    with pytest.raises(RetryAfterError, match="timezone-aware"):
        parse_retry_after("Sun, 06 Nov 1994 08:49:37 GMT", now=datetime(1994, 11, 6))


def test_non_string_is_rejected() -> None:
    with pytest.raises(RetryAfterError):
        parse_retry_after(120)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("now", "value", "year"),
    [
        (datetime(2026, 6, 15, tzinfo=timezone.utc), "Monday, 15-Jun-76 00:00:00 GMT", 2076),
        (datetime(2026, 6, 15, tzinfo=timezone.utc), "Monday, 15-Jun-76 00:00:01 GMT", 1976),
        (datetime(1999, 1, 1, tzinfo=timezone.utc), "Friday, 01-Jan-49 00:00:00 GMT", 2049),
        (datetime(2028, 2, 29, tzinfo=timezone.utc), "Tuesday, 01-Mar-78 00:00:00 GMT", 2078),
    ],
)
def test_rfc850_fifty_years_are_calendar_years(now: datetime, value: str, year: int) -> None:
    seconds = parse_retry_after(value, now=now)
    moment = now + timedelta(seconds=seconds) if seconds else None
    assert (moment.year if moment else 1900 + int(value[-15:-13])) == year

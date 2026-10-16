# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-10-16

The public API is now stable and follows Semantic Versioning: the 23 names in
`backoffs.__all__` (schedules, jitters, `Policy`, `Delays`, `retry`, `aretry`,
`RetryState`, `parse_retry_after`, `backoff` and the four errors), their signatures and
defaults, the formulas in GUIDE.md, and the `backoffs` command's options, output and
exit statuses.

### Changed

- The `backoffs` command exits with meaningful statuses instead of 1 for everything:
  2 for bad options or values (was 1), and `run` exits with the status of the last
  attempt (124 when it timed out, 128 plus the signal number when a signal killed it),
  127 when the command is not found, 126 when it cannot be executed and 130 when
  interrupted (was a traceback). `retry-after` still exits 1 for an unreadable value.
- `RetryError`'s message names the type of the last exception but no longer repeats its
  text, which may hold data you do not want in a log; the exception itself is still
  `last_exception` and `__cause__`.
- Error messages show at most a short preview of a rejected value.
- `parse_retry_after()` accepts ASCII digits only, as RFC 9110 requires (a date written
  with other scripts' digits used to be read).
- Public names report `backoffs` as their module.

### Fixed

- `Policy`, `Delays`, `retry()` and `aretry()` check their arguments' types when called
  and raise `InvalidPolicyError`; a wrong schedule, jitter, policy, `rng`, `clock`,
  `sleep`, hook or `retry_on` used to fail later with an `AttributeError` or
  `TypeError`, some only after the first failure. What callables return is checked when
  it is used: a clock that returns something other than a number, and in `aretry()` an
  `fn` or `sleep` that returns something other than an awaitable, raise
  `InvalidPolicyError` (a plain function given to `aretry()` used to be called and
  retried until the policy ran out; a blocking `sleep` blocked the event loop first).
- `ProportionalJitter(jitter_first=...)` accepts only a `bool` (any value was read by its
  truth before), and `backoff(rng=...)` accepts only a `random.Random`, also with
  `jitter="none"`, where 0.2.0 ignored it.
- A custom schedule that ends, or a custom schedule or jitter that yields a negative,
  NaN or infinite delay, raises `InvalidPolicyError` instead of ending the iterator
  silently or handing the value to `sleep`.
- A clock that returns NaN, an infinity or an integer too large for a float no longer
  keeps a `max_elapsed` budget open forever or crashes; the budget counts as spent.
- An integer too large for a float raises `InvalidPolicyError` instead of
  `OverflowError`, everywhere a number is accepted.
- `parse_retry_after()`: the RFC 850 "more than 50 years in the future" rule counts
  calendar years (a date just under 50 years ahead was read as the previous century);
  an RFC 850 date on 29 February of a year that has one is no
  longer refused when the next century's year does not; a leap second on 31 December
  9999 raises `RetryAfterError` instead of `OverflowError`; a delay longer than 309
  digits is refused without converting it; `now` must be a `datetime`.
- `RetryError` survives pickling.
- `backoffs run` refuses `--retry-on-exit 0`, an `--attempt-timeout` or `--cap` too long
  for the platform to wait, instead of failing with a traceback.

### Upgrading from 0.2.0

Code that only uses the library keeps working unless it relies on one of these:

1. Scripts that test `backoffs` exit statuses for 1: usage errors are now 2, and `run`
   returns the command's own status when it gives up.
2. Code that reads the last exception's text from `str(RetryError)`: use
   `exc.last_exception` instead.
3. Code that passes a wrong type and catches `AttributeError` or `TypeError`: catch
   `InvalidPolicyError` (a `ValueError`). This includes a non-`bool` `jitter_first`,
   a non-`Random` `rng`, a clock that does not return numbers and a synchronous
   function given to `aretry()`.

## [0.2.0]

### Added

- `Policy`: a frozen, reusable backoff description (schedule, jitter, cap,
  `max_retries`, `max_elapsed`) with `Policy.grpc()` and `Policy.google_cloud()` presets.
- `Delays`: the iterator returned by `Policy.delays()`, with `retries`, `total`,
  `elapsed`, `stop_reason` and `floor_next()` for server hints. Accepts an injected
  `rng` and `clock`.
- Schedules `Constant`, `Linear`, `Exponential` and `Fibonacci`.
- Jitter strategies `NoJitter`, `FullJitter`, `EqualJitter`, `DecorrelatedJitter`
  (AWS), `ProportionalJitter` (gRPC) and `AdditiveJitter` (Google Cloud).
- `parse_retry_after()` for RFC 9110 delay-seconds and all three HTTP-date forms.
- `retry()` and `aretry()` helpers with `retry_on`, `giveup`, `retry_after` and
  `on_retry`, plus injectable `sleep`, `clock` and `rng`.
- Typed errors: `BackoffError`, `InvalidPolicyError`, `RetryAfterError`, `RetryError`.
- The `backoffs` command: `schedule`, `run` and `retry-after`.
- `GUIDE.md` with the formulas, their sources and recipes.

### Changed

- `backoff()` is now a thin wrapper over `Policy`. Its seeded sequences are unchanged
  and it raises `InvalidPolicyError`, a `ValueError` subclass. NaN arguments are now
  rejected. It returns a `Delays` iterator rather than a generator object.

## [0.1.0]

- First release: `backoff()` iterator yielding an exponential delay sequence with a
  cap and none / full / equal / decorrelated jitter, bounded by `max_attempts` and
  reproducible through a seedable `rng`. It never sleeps or retries.

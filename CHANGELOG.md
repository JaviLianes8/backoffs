# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
  and it raises `InvalidPolicyError`, a `ValueError` subclass.

## [0.1.0]

- First release: `backoff()` iterator yielding an exponential delay sequence with a
  cap and none / full / equal / decorrelated jitter, bounded by `max_attempts` and
  reproducible through a seedable `rng`. It never sleeps or retries.

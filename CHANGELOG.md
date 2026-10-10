# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0]

- First release: `backoff()` iterator yielding an exponential delay sequence with a
  cap and none / full / equal / decorrelated jitter, bounded by `max_attempts` and
  reproducible through a seedable `rng`. It never sleeps or retries.

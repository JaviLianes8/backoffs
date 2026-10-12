# Improvements round (0.2.0)

Ranked by value to users, highest first. Every item is additive: `backoff()` keeps its
signature and produces bit-identical seeded sequences (pinned by a golden test).

| Rank | Improvement | Why it matters | Status |
|---:|---|---|---|
| 1 | Frozen `Policy` (schedule + jitter + cap + budgets) with a `Delays` iterator | One immutable, comparable, reusable description instead of loose keyword arguments; the iterator reports `retries`, `total`, `elapsed` and `stop_reason` | Done |
| 2 | AWS jitter strategies implemented exactly as published | `FullJitter`, `EqualJitter`, `DecorrelatedJitter` follow Marc Brooker's formulas; verified with seeded oracles and distribution tests | Done |
| 3 | gRPC and Google Cloud strategies | `ProportionalJitter` (gRPC `UniformRandom(-JITTER*b, JITTER*b)`, plain first wait) and `AdditiveJitter` (`min(2**n + random_ms, maximum_backoff)`), plus `Policy.grpc()` and `Policy.google_cloud()` presets | Done |
| 4 | `retry()` and `aretry()` helpers | Sync and async loops with exception filters, `giveup` predicate, `on_retry` hook, injectable `sleep`, `clock` and `rng`; `RetryError` carries attempts, elapsed, reason and the last exception | Done |
| 5 | Retry-After as a floor | `parse_retry_after()` accepts delay-seconds and all three RFC 9110 HTTP-date forms; `Delays.floor_next()` and the `retry_after=` hook make the server hint win over the cap | Done |
| 6 | Time budget `max_elapsed` | Stops before a delay that would overrun the budget; measured by summed delays, or by an injected clock (which includes call time) | Done |
| 7 | Growth schedules | `Constant`, `Linear`, `Exponential`, `Fibonacci`; growth saturates at the largest float, never overflows | Done |
| 8 | `backoffs` command line | `schedule` prints a plan (table, JSON or plain), `run` retries a real command with backoff, `retry-after` converts a header value | Done |
| 9 | Typed errors | `BackoffError` root; `InvalidPolicyError` and `RetryAfterError` are also `ValueError` so 0.1 callers keep working | Done |
| 10 | Docs | README rewritten around the new API, `GUIDE.md` with formulas, sources and recipes | Done |

## Verification

- Exact seeded sequences for every strategy, checked against an independent oracle that
  evaluates the published formula with the same seed.
- Distribution checks over 20,000 seeded draws: bounds, mean and standard deviation of
  each uniform spread match the formula (deterministic, no flaky tolerances).
- Real retries against a local HTTP server that answers 503 with `Retry-After`
  (seconds and HTTP-date) before recovering, and against a flaky subprocess.
- End to end: the wheel is built, installed into a throwaway venv and the installed
  `backoffs` script retries a real failing command.

## Considered and left out

- Retrying on a returned value (not an exception): easy to express with a small wrapper
  that raises; adding it would double the helper surface for little gain.
- Decorators: `retry(lambda: f(x))` keeps typing exact and the API small.

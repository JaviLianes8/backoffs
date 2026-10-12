# backoffs

Typed, zero-dependency backoff delays. Exponential, linear, Fibonacci or constant
growth, a cap, the AWS, gRPC and Google Cloud jitter strategies implemented exactly as
published, retry and time budgets, `Retry-After` support, optional sync and async
retry helpers, and a `backoffs` command line.

## Install

```
pip install backoffs
```

Python 3.10 or newer. No runtime dependencies.

## The delay iterator

The core of the library yields delays and nothing else. It never sleeps, so you keep
your own loop, your own clock and your own retry decision.

```python
import time
from backoffs import Exponential, FullJitter, Policy

policy = Policy(Exponential(base=0.1, factor=2.0), FullJitter(), cap=30.0, max_retries=8)

for delay in policy.delays():
    try:
        do_the_thing()
        break
    except TransientError:
        time.sleep(delay)
```

A `Policy` is frozen and reusable; every `delays()` call starts a fresh iterator.
Each delay is `jitter(min(cap, schedule delay))`.

| Schedule | Retry `n` (from 0) waits |
|---|---|
| `Constant(delay)` | `delay` |
| `Linear(start, step)` | `start + step * n` |
| `Exponential(base, factor)` | `base * factor ** n` |
| `Fibonacci(base)` | `base * F(n + 1)`: `b, b, 2b, 3b, 5b, ...` |

| Jitter | Delay, with `raw = min(cap, schedule delay)` | Source |
|---|---|---|
| `NoJitter()` | `raw` | |
| `FullJitter()` | `uniform(0, raw)` | AWS Architecture Blog |
| `EqualJitter()` | `raw / 2 + uniform(0, raw / 2)` | AWS Architecture Blog |
| `DecorrelatedJitter()` | `min(cap, uniform(base, previous * 3))` | AWS Architecture Blog |
| `ProportionalJitter(0.2)` | `raw + uniform(-0.2 raw, 0.2 raw)` | gRPC connection backoff |
| `AdditiveJitter(1.0)` | `min(raw + uniform(0, 1.0), cap)` | Google Cloud |

Presets: `Policy.grpc()` (1 s initial, x1.6, 20% jitter, 120 s max, plain first wait)
and `Policy.google_cloud()` (`min(2 ** n + up to 1 s, 32 s)`).

## Budgets and Retry-After

```python
from backoffs import Policy, parse_retry_after

policy = Policy(max_retries=10, max_elapsed=60.0)  # whichever comes first
delays = policy.delays()

# A server answered 429 with "Retry-After: 120" (or an HTTP-date):
delays.floor_next(parse_retry_after(response.headers["Retry-After"]))
wait = next(delays, None)  # at least 120 s, or None if that overruns the budget
```

`max_elapsed` stops before a delay that would push past the budget. Without a clock it
sums the delays; pass `clock=time.monotonic` to `delays()` to count your own call time
too. Pass a seeded `random.Random` as `rng` for reproducible jitter.

## Retry helpers

```python
from backoffs import Policy, aretry, retry

result = retry(
    lambda: fetch(url),
    Policy(max_retries=5),
    retry_on=(ConnectionError, TimeoutError),
    giveup=lambda exc: getattr(exc, "status", 0) == 404,
    retry_after=lambda exc: getattr(exc, "retry_after", None),
)

result = await aretry(lambda: client.get(url), Policy.grpc(max_retries=6))
```

Exceptions outside `retry_on`, or accepted by `giveup`, propagate unchanged. When the
policy runs out, `RetryError` is raised from the last exception and reports `attempts`,
`elapsed` and `reason`. `sleep`, `clock` and `rng` are injectable for tests.

## Command line

```
backoffs schedule --max-retries 6
backoffs schedule --jitter full --seed 42 --format json
backoffs schedule --preset grpc --max-retries 8
backoffs run --max-retries 4 --base 0.5 -- curl --fail https://example.com/health
backoffs retry-after "Sun, 06 Nov 1994 08:49:37 GMT"
```

`run` exits 0 once the command succeeds, and 1 (with the reason on stderr) when retries
run out, the exit code is not listed in `--retry-on-exit`, or the command cannot start.

See [GUIDE.md](GUIDE.md) for the formulas, their sources and more recipes.

## The 0.1 API

`backoff(base, factor, cap, jitter, max_attempts, rng)` still works and produces the
same seeded sequences as before. It is a thin wrapper over `Policy`.

## Why

The delay math is simple but easy to get subtly wrong, and the popular packages couple
it to a policy you may not want: `backoff` and `tenacity` keep their wait generators
inside decorators, `expbackoff` sleeps for you. `backoffs` exposes the schedule as a
plain, typed iterator first; the retry helpers and the CLI are thin layers on top that
you can ignore.

## License

MIT. See [LICENSE](LICENSE).

## Links

- Website: https://lianes8studio.com
- GitHub: https://github.com/JaviLianes8
- LinkedIn: https://www.linkedin.com/in/jlianes/

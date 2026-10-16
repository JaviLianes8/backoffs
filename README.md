# backoffs

Typed, zero-dependency backoff delays for Python. Exponential, linear, Fibonacci or
constant growth, a cap, the AWS, gRPC and Google Cloud jitter strategies implemented
exactly as published, retry and time budgets, `Retry-After` support, optional sync and
async retry helpers, and a `backoffs` command line.

## Why

Retrying with backoff is a few lines of math that are easy to get subtly wrong: jitter
applied before the cap instead of after, a decorrelated chain that restarts every
retry, a `Retry-After` date read as a number. backoffs gives you the schedule itself
as a plain, typed iterator that never sleeps, so you keep your own loop, clock and
retry decision, and you can print or test a schedule before shipping it.

How it compares, from the packages' own code (tenacity 9.2.1, backoff 2.2.1):

- tenacity's wait strategies are callables of its own retry state, and the `backoff`
  package's wait generators are primed for its decorators; both are made to run inside
  their retry loops. backoffs puts the iterator first; its retry helpers and CLI are
  thin layers you can ignore.
- Both offer Full Jitter; neither has AWS Equal or Decorrelated Jitter or the gRPC
  proportional jitter. tenacity's `wait_exponential_jitter` is Google's formula, which
  backoffs also implements.
- Neither parses a `Retry-After` HTTP-date; backoffs reads all three RFC 9110 forms.

backoffs is checked against the AWS Architecture Blog's own simulator
code, tenacity and backoff run live on the same seeds (see [GUIDE.md](https://github.com/JaviLianes8/backoffs/blob/main/GUIDE.md)).

## Install

```
pip install backoffs
```

Python 3.10 or newer. No runtime dependencies.

## Quick start

```pycon
>>> import random
>>> from backoffs import Exponential, FullJitter, Policy
>>> policy = Policy(Exponential(base=0.5), cap=4.0, max_retries=5)
>>> list(policy.delays())
[0.5, 1.0, 2.0, 4.0, 4.0]
>>> jittered = Policy(Exponential(base=0.5), FullJitter(), cap=4.0, max_retries=5)
>>> delays = list(jittered.delays(rng=random.Random(42)))
>>> len(delays), all(0.0 <= d <= 4.0 for d in delays)
(5, True)
```

Use it in your own loop; nothing sleeps unless you do:

```python
import time
from backoffs import Exponential, FullJitter, Policy

attempts = []


def call_the_service() -> str:
    attempts.append(1)
    if len(attempts) < 3:
        raise ConnectionError("not yet")
    return "ok"


policy = Policy(Exponential(base=0.01), FullJitter(), cap=0.1, max_retries=8)
for delay in policy.delays():
    try:
        result = call_the_service()
        break
    except ConnectionError:
        time.sleep(delay)
else:
    raise RuntimeError("the service never answered")
assert result == "ok"
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

```pycon
>>> from backoffs import Constant, Policy, parse_retry_after
>>> delays = Policy(Constant(1.0), max_retries=10, max_elapsed=60.0).delays()
>>> delays.floor_next(parse_retry_after("120"))  # a 429 asked for two minutes
>>> next(delays, None) is None  # 120 s would overrun the 60 s budget
True
>>> delays.stop_reason
'max_elapsed'
```

`max_elapsed` stops before a delay that would push past the budget. Without a clock it
sums the delays; pass `clock=time.monotonic` to `delays()` to count your own call time
too. Pass a seeded `random.Random` as `rng` for reproducible jitter.

## Retry helpers

```pycon
>>> from backoffs import Exponential, Policy, RetryError, retry
>>> calls = []
>>> def fetch() -> str:
...     calls.append(1)
...     if len(calls) < 3:
...         raise TimeoutError("slow")
...     return "payload"
>>> slept = []
>>> retry(fetch, Policy(Exponential(0.5), max_retries=5), retry_on=TimeoutError, sleep=slept.append)
'payload'
>>> slept
[0.5, 1.0]
```

Exceptions outside `retry_on`, or accepted by `giveup`, propagate unchanged. When the
policy runs out, `RetryError` is raised from the last exception and reports `attempts`,
`elapsed` and `reason`. `retry_after` turns an exception into a server-requested wait,
`on_retry` sees each failure, and `sleep`, `clock` and `rng` are injectable for tests.
`aretry` is the asyncio twin.

## Command line

```
backoffs schedule --max-retries 6
backoffs schedule --jitter full --seed 42 --format json
backoffs schedule --preset grpc --max-retries 8
backoffs run --max-retries 4 --base 0.5 -- curl --fail https://example.com/health
backoffs retry-after "Sun, 06 Nov 1994 08:49:37 GMT"
```

`run` exits 0 once the command succeeds. Otherwise it exits with the status of the
last attempt (124 if it timed out), 127 if the command is not found, 126 if it cannot
be executed, 2 for bad options and 130 when interrupted. `retry-after` exits 1 for a
value that is neither delay-seconds nor an HTTP-date.

## More

- [GUIDE.md](https://github.com/JaviLianes8/backoffs/blob/main/GUIDE.md): formulas,
  sources, errors, recipes and the 0.1 `backoff()` function, which still works.
- [CHANGELOG.md](https://github.com/JaviLianes8/backoffs/blob/main/CHANGELOG.md):
  what is stable in 1.0.0 and what changed since 0.2.0.

## License

MIT. See [LICENSE](https://github.com/JaviLianes8/backoffs/blob/main/LICENSE).

## Links

- Website: https://lianes8studio.com
- GitHub: https://github.com/JaviLianes8
- LinkedIn: https://www.linkedin.com/in/jlianes/

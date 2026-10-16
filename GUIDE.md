# backoffs guide

## How a delay is computed

For retry `n` (counting from 0):

1. The schedule gives a raw delay: `Constant`, `Linear`, `Exponential` or `Fibonacci`.
2. The cap clamps it: `raw = min(cap, schedule delay)` (skipped when `cap=None`).
3. The jitter strategy turns `raw` into the delay.
4. A floor set with `Delays.floor_next()` (for example from `Retry-After`) raises it.
   The floor wins over the cap, and lasts for one delay only.
5. The budgets decide whether it is produced at all: `max_retries` bounds the number of
   delays, `max_elapsed` refuses a delay when `elapsed + delay > max_elapsed`.

One delay is produced per retry, so a call guarded by `max_retries=5` runs at most six
times. Once a `Delays` iterator stops it stays stopped, and `stop_reason` says why:
`"max_retries"` or `"max_elapsed"`.

```pycon
>>> from backoffs import Exponential, Policy
>>> delays = Policy(Exponential(1.0), max_elapsed=10.0).delays()
>>> list(delays), delays.total, delays.stop_reason
([1.0, 2.0, 4.0], 7.0, 'max_elapsed')
```

Growth saturates at the largest float instead of overflowing, so an uncapped schedule
stays finite. Decorrelated jitter remembers the delay it produced last, before any
floor: a `Retry-After` floor lengthens one wait without inflating the ones after it.

## Jitter formulas and sources

### AWS: Exponential Backoff And Jitter

Marc Brooker, AWS Architecture Blog, 2015,
<https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/>. The post
links its simulator code, `aws-samples/aws-arch-backoff-simulator`, whose backoff
classes are the executable form of the formulas:

- Exponential: `sleep = min(cap, base * 2 ** attempt)`. Use `Exponential(base, 2.0)`
  with `NoJitter()`.
- Full Jitter: `sleep = random_between(0, min(cap, base * 2 ** attempt))`.
  `FullJitter()`; mean `raw / 2`.
- Equal Jitter: `temp = min(cap, base * 2 ** attempt)`,
  `sleep = temp / 2 + random_between(0, temp / 2)`. `EqualJitter()`; mean `3 raw / 4`.
- Decorrelated Jitter: `sleep = min(cap, random_between(base, sleep * 3))`, with
  `sleep` starting at `base`. `DecorrelatedJitter()`. Each delay derives from the
  previous one, so the schedule only supplies `base` (its first delay).

The simulator's client counts its first retry as attempt 1, so its first exponential
wait is `2 * base`; backoffs counts from 0. `Exponential(2 * base)` reproduces the
simulator's waits exactly.

### gRPC connection backoff

`doc/connection-backoff.md` in the gRPC repository,
<https://github.com/grpc/grpc/blob/master/doc/connection-backoff.md>: the backoff
starts at `INITIAL_BACKOFF`, is multiplied by `MULTIPLIER` after each failure up to
`MAX_BACKOFF`, and every wait after the first gets a uniform random term between
`-JITTER` and `+JITTER` times the backoff.

`Policy.grpc()` uses `INITIAL_BACKOFF = 1`, `MULTIPLIER = 1.6`, `JITTER = 0.2`,
`MAX_BACKOFF = 120` and `ProportionalJitter(0.2, jitter_first=False)`, so the first
wait is exactly one second and later waits may exceed 120 s by up to 20%, as in the
spec. grpc-go's `DefaultConfig` and its `Backoff(retries)` function behave the same way.
`MIN_CONNECT_TIMEOUT` is a connection timeout, not a delay, and is out of scope.

### Google Cloud truncated exponential backoff

Google Cloud documentation, for example
<https://cloud.google.com/memorystore/docs/redis/exponential-backoff>: wait
`2 ** n` seconds plus a random number of milliseconds up to 1000, never more than
`maximum_backoff`, which is typically 32 or 64 seconds.

`Policy.google_cloud(maximum_backoff=32.0)` is `Exponential(1.0, 2.0)` with
`AdditiveJitter(1.0)` and `cap=maximum_backoff`, so `maximum_backoff` must be at least
the first wait, 1 s.

### Retry-After (RFC 9110, section 10.2.3)

`Retry-After = HTTP-date / delay-seconds`. `parse_retry_after()` accepts:

- delay-seconds: one or more ASCII digits such as `120` (fractions, signs and other
  scripts' digits are errors, and so is a number too large for a float);
- IMF-fixdate: `Sun, 06 Nov 1994 08:49:37 GMT`;
- the obsolete forms recipients must still accept (section 5.6.7): RFC 850
  `Sunday, 06-Nov-94 08:49:37 GMT` (a two-digit year more than 50 years ahead means the
  previous century) and asctime `Sun Nov  6 08:49:37 1994`.

A date in the past yields `0.0`, and a leap second (`:60`) is read as the next second.
Spaces and tabs around the value are ignored. Names are case-sensitive, as in the RFC,
and the day name is not checked against the date. Anything else raises
`RetryAfterError`.

```pycon
>>> from datetime import datetime, timezone
>>> from backoffs import parse_retry_after
>>> now = datetime(2026, 1, 1, tzinfo=timezone.utc)
>>> parse_retry_after("Thu, 01 Jan 2026 00:02:00 GMT", now=now)
120.0
>>> parse_retry_after("Wednesday, 31-Dec-25 23:00:00 GMT", now=now)
0.0
```

## How backoffs is checked against those sources

- `tests/test_oracle.py` replays 85 recorded runs of the AWS simulator's backoff
  classes, tenacity 9.2.1 (`wait_exponential`, `wait_random_exponential`,
  `wait_exponential_jitter`, `wait_incrementing`, `wait_fixed`) and backoff 2.2.1
  (`expo`, `fibo`, `constant`, `full_jitter`, `random_jitter`), seeded alike. They match
  to the last bit, except that tenacity raises a factor other than 2 to a power where
  backoffs multiplies step by step; those agree to 12 significant digits. With the
  references installed or fetched, the test also reruns them live.
- `tests/test_sources.py` reads the fetched gRPC spec, grpc-go's defaults and backoff
  function, the Google Cloud page and RFC 9110 and checks the presets and the parser
  against them. `scripts/fetch_sources.py` downloads the copies, which stay out of git;
  `tests/sources/MANIFEST.json` records their URL, date, size, SHA-256 and licence.

## Errors

| Error | Base classes | Raised when |
|---|---|---|
| `InvalidPolicyError` | `BackoffError`, `ValueError` | an argument of a schedule, jitter, policy, `Delays` or retry helper has the wrong type or is out of range; a custom schedule ends or yields a bad delay; a clock returns something other than a number; `aretry()` gets a non-awaitable from `fn` or `sleep` |
| `RetryAfterError` | `BackoffError`, `ValueError` | `parse_retry_after()` gets anything but delay-seconds or an HTTP-date |
| `RetryError` | `BackoffError` | `retry()` or `aretry()` runs out of retries or time |

Argument types are checked when the object is built or the helper is called, before
anything runs; what a callable returns is checked when it is used (a clock must return
numbers, and `aretry()`'s `fn` and `sleep` must return awaitables). Messages show
at most a short preview of a rejected value (a long string or a huge number is reduced
to its length), and `RetryError` names only the type of the last exception, never its
text. `RetryError` keeps `attempts`, `elapsed`, `reason` and `last_exception` and
survives pickling.

## Your own schedule or jitter

`Schedule` and `Jitter` are protocols: any object with the right shape works.

```pycon
>>> import itertools
>>> from backoffs import Policy
>>> class Squares:
...     first = 1.0
...
...     def raw(self):
...         return (float(n * n) for n in itertools.count(1))
>>> class Halve:
...     def apply(self, raw: float, **_: object) -> float:
...         return raw / 2
>>> list(Policy(Squares(), Halve(), cap=None, max_retries=4).delays())
[0.5, 2.0, 4.5, 8.0]
```

A schedule must yield finite delays `>= 0` forever; a jitter must return a finite delay
`>= 0`. Anything else raises `InvalidPolicyError` when the delay is drawn.

## Threads

A `Policy` is immutable and can be shared freely, across threads too; each `delays()`
call, and each `retry()` or `aretry()` call, gets its own iterator. A single `Delays`
iterator is not thread-safe: give each thread its own.

## Recipes

### Plan a schedule before shipping it

```
backoffs schedule --preset google-cloud --max-elapsed 120
backoffs schedule --jitter decorrelated --base 0.5 --cap 20 --seed 1 --format json
```

### Honour a server hint in your own loop

```python
import time
from backoffs import Constant, Policy, parse_retry_after

answers = iter([(503, "1"), (429, None), (200, None)])  # stands in for real responses

delays = Policy(Constant(0.01), max_retries=6, max_elapsed=300).delays(clock=time.monotonic)
while True:
    status, header = next(answers)
    if status not in (429, 503):
        break
    if header is not None:
        delays.floor_next(parse_retry_after(header) / 100)  # scaled down for the example
    wait = next(delays, None)
    if wait is None:
        raise RuntimeError(f"gave up: {delays.stop_reason}")
    time.sleep(wait)
assert status == 200
```

### Retry with filters

```python
import logging
from backoffs import Constant, Policy, RetryError, retry

log = logging.getLogger("upload")


def upload() -> None:
    raise ConnectionResetError("peer went away")


try:
    retry(
        upload,
        Policy(Constant(0.0), max_retries=2),
        retry_on=(ConnectionError, TimeoutError),
        giveup=lambda exc: isinstance(exc, ConnectionRefusedError),
        on_retry=lambda s: log.warning("attempt %d failed, waiting %.1fs", s.attempt, s.delay),
    )
except RetryError as exc:
    assert exc.attempts == 3 and exc.reason == "max_retries"
```

### Retry a shell command

```
backoffs run --max-retries 5 --base 1 --jitter full -- ./deploy.sh
backoffs run --retry-on-exit 75 --attempt-timeout 30 -- python sync.py
```

`--retry-on-exit` limits retries to the listed codes (a timed out attempt is always
retried); any other failure ends the run at once with that status.

### Test code that retries

Pass a seeded `random.Random` for exact sequences, and fake `sleep` and `clock`
callables to `retry()` so tests never wait.

```pycon
>>> import random
>>> from backoffs import FullJitter, Policy, retry
>>> slept = []
>>> def flaky() -> str:
...     if len(slept) < 2:
...         raise OSError("busy")
...     return "done"
>>> retry(flaky, Policy(jitter=FullJitter()), sleep=slept.append, rng=random.Random(3))
'done'
>>> slept == list(Policy(jitter=FullJitter(), max_retries=2).delays(rng=random.Random(3)))
True
```

## The 0.1 `backoff()` function

`backoff(base, factor, cap, jitter, max_attempts, rng)` still works and produces the
same seeded sequences as 0.1 and 0.2. It is a thin wrapper over `Policy` that also
accepts what 0.1 accepted (numeric strings, an infinite cap or factor, a float count).

```pycon
>>> from backoffs import backoff
>>> list(backoff(base=1.0, cap=5.0, max_attempts=4))
[1.0, 2.0, 4.0, 5.0]
```

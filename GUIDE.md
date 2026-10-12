# backoffs guide

## How a delay is computed

For retry `n` (counting from 0):

1. The schedule gives a raw delay: `Constant`, `Linear`, `Exponential` or `Fibonacci`.
2. The cap clamps it: `raw = min(cap, schedule delay)` (skipped when `cap=None`).
3. The jitter strategy turns `raw` into the delay.
4. A floor set with `Delays.floor_next()` (for example from `Retry-After`) raises it.
5. The budgets decide whether it is produced at all: `max_retries` bounds the number of
   delays, `max_elapsed` refuses a delay when `elapsed + delay > max_elapsed`.

One delay is produced per retry, so a call guarded by `max_retries=5` runs at most six
times.

## Jitter formulas and sources

### AWS: Exponential Backoff And Jitter

Marc Brooker, AWS Architecture Blog, 2015,
<https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/>.

- Exponential: `sleep = min(cap, base * 2 ** attempt)`. Use `Exponential(base, 2.0)`
  with `NoJitter()`.
- Full Jitter: `sleep = random_between(0, min(cap, base * 2 ** attempt))`.
  `FullJitter()`; mean `raw / 2`.
- Equal Jitter: `temp = min(cap, base * 2 ** attempt)`,
  `sleep = temp / 2 + random_between(0, temp / 2)`. `EqualJitter()`; mean `3 raw / 4`.
- Decorrelated Jitter: `sleep = min(cap, random_between(base, sleep * 3))`, with
  `sleep` starting at `base`. `DecorrelatedJitter()`. Each delay derives from the
  previous one, so the schedule only supplies `base` (its first delay).

### gRPC connection backoff

`doc/connection-backoff.md` in the gRPC repository,
<https://github.com/grpc/grpc/blob/master/doc/connection-backoff.md>.

```
current_backoff = INITIAL_BACKOFF
current_deadline = now() + INITIAL_BACKOFF
...
current_backoff = Min(current_backoff * MULTIPLIER, MAX_BACKOFF)
current_deadline = now() + current_backoff +
  UniformRandom(-JITTER * current_backoff, JITTER * current_backoff)
```

`Policy.grpc()` uses `INITIAL_BACKOFF = 1`, `MULTIPLIER = 1.6`, `JITTER = 0.2`,
`MAX_BACKOFF = 120` and `ProportionalJitter(0.2, jitter_first=False)`, so the first
wait is exactly one second and later waits may exceed 120 s by up to 20%, as in the
spec. `MIN_CONNECT_TIMEOUT` is a connection timeout, not a delay, and is out of scope.

### Google Cloud truncated exponential backoff

Google Cloud documentation, for example
<https://cloud.google.com/memorystore/docs/redis/exponential-backoff>:
`wait = min(((2 ^ n) + random_number_milliseconds), maximum_backoff)`, where the random
part is up to 1000 ms and `maximum_backoff` is typically 32 or 64 seconds.

`Policy.google_cloud(maximum_backoff=32.0)` is `Exponential(1.0, 2.0)` with
`AdditiveJitter(1.0)` and `cap=maximum_backoff`.

### Retry-After (RFC 9110, section 10.2.3)

`Retry-After = HTTP-date / delay-seconds`. `parse_retry_after()` accepts:

- delay-seconds: a non-negative integer such as `120` (fractions and signs are errors);
- IMF-fixdate: `Sun, 06 Nov 1994 08:49:37 GMT`;
- the obsolete forms recipients must still accept (section 5.6.7): RFC 850
  `Sunday, 06-Nov-94 08:49:37 GMT` (a two-digit year more than 50 years ahead means the
  previous century) and asctime `Sun Nov  6 08:49:37 1994`.

A date in the past yields `0.0`. Anything else raises `RetryAfterError`.

## Recipes

### Plan a schedule before shipping it

```
backoffs schedule --preset google-cloud --max-elapsed 120
backoffs schedule --jitter decorrelated --base 0.5 --cap 20 --seed 1 --format json
```

### Honour a server hint in your own loop

```python
import time
from backoffs import Policy, parse_retry_after

delays = Policy(max_retries=6, max_elapsed=300).delays(clock=time.monotonic)
while True:
    response = session.get(url)
    if response.status_code not in (429, 503):
        break
    header = response.headers.get("Retry-After")
    if header is not None:
        delays.floor_next(parse_retry_after(header))
    wait = next(delays, None)
    if wait is None:
        raise RuntimeError(f"gave up: {delays.stop_reason}")
    time.sleep(wait)
```

### Retry with filters

```python
from backoffs import Policy, RetryError, retry

try:
    retry(
        lambda: upload(blob),
        Policy.grpc(max_elapsed=60),
        retry_on=(ConnectionError, TimeoutError),
        giveup=lambda exc: isinstance(exc, ConnectionRefusedError),
        on_retry=lambda s: log.warning("attempt %d failed, waiting %.1fs", s.attempt, s.delay),
    )
except RetryError as exc:
    log.error("upload failed after %d attempts (%s)", exc.attempts, exc.reason)
```

### Retry a shell command

```
backoffs run --max-retries 5 --base 1 --jitter full -- ./deploy.sh
backoffs run --retry-on-exit 75 --attempt-timeout 30 -- python sync.py
```

### Test code that retries

Pass a seeded `random.Random` for exact sequences, and fake `sleep` and `clock`
callables to `retry()` so tests never wait.

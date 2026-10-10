# backoffs

Pure backoff delay iterator: exponential growth, cap and jitter, never sleeps or retries.

## Install

```
pip install backoffs
```

## Usage

```python
import time
from backoffs import backoff

# Drive your own loop. backoffs only yields the delays.
for delay in backoff(base=0.1, factor=2.0, cap=30.0, jitter="full", max_attempts=8):
    try:
        do_the_thing()
        break
    except TransientError:
        time.sleep(delay)
```

The raw delay for attempt `n` is `base * factor ** n`, clamped to `cap`. The `jitter`
argument reshapes each delay following the AWS backoff strategies:

- `"none"`: the raw capped delay.
- `"full"`: uniform in `[0, raw]`.
- `"equal"`: uniform in `[raw / 2, raw]`.
- `"decorrelated"`: each delay is `min(cap, uniform(base, previous * 3))`.

`max_attempts` bounds the number of delays (`None`, the default, is an unbounded
sequence). Pass a seeded `random.Random` as `rng` for reproducible jittered runs:

```python
import random
from backoffs import backoff

delays = list(backoff(jitter="decorrelated", max_attempts=5, rng=random.Random(42)))
```

The call returns an iterator. It never sleeps, never retries, never touches the clock
or the network, so it is trivial to test and drops into any loop, async or sync.

## Why

Everyone reaches for a backoff schedule, almost nobody wants the retry framework
wrapped around it. The delay math (exponential growth, a ceiling, and the full,
equal and decorrelated jitter from the AWS Architecture Blog post
[Exponential Backoff And Jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/))
is simple, but it is tedious to get right and easy to get subtly wrong.

The popular packages couple it to a policy you may not want:

- `backoff` and `tenacity` are retry frameworks: the wait generators live inside
  decorators and context managers, not as a standalone delay sequence.
- `expbackoff` calls `sleep()` for you inside its loop, so you cannot take the delay
  and decide what to do with it.
- `backoff-utils` ships retry strategies, not a plain reusable iterator of floats.

`backoffs` is the one piece they all contain and none expose on its own: a typed,
zero-dependency iterator that yields the delay sequence and nothing else. You keep
your own loop, your own clock, and your own retry decision.

## License

MIT. See [LICENSE](LICENSE).

## Links

- Website: https://lianes8studio.com
- GitHub: https://github.com/JaviLianes8
- LinkedIn: https://www.linkedin.com/in/jlianes/

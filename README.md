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

## License

MIT. See [LICENSE](LICENSE).

## Links

- Website: https://lianes8studio.com
- GitHub: https://github.com/JaviLianes8
- LinkedIn: https://www.linkedin.com/in/jlianes/

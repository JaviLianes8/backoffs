# Contributing

Thanks for taking the time. This project keeps a small, predictable shape.

## Setup

```
pip install -r requirements-dev.txt
```

## Before you open a pull request

- Keep public API in `src/backoffs/__init__.py`; internals live in `_`-prefixed modules.
- Add a test for the behaviour you change. Unit tests inject time and randomness
  (a fake `sleep`, a fake clock, a seeded `random.Random`). The real retry tests use a
  local HTTP server and subprocesses, and `tests/test_e2e_wheel.py` builds the wheel
  and installs it into a throwaway venv.
- Jitter changes must keep matching the published formulas listed in `GUIDE.md`.
- Run `scripts/check.ps1` (format, lint, types, tests) and make sure it passes.
- One logical change per commit, imperative subject line.

Open an issue first if the change is large or shifts the public API.

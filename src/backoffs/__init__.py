"""Pure backoff delay iterator: exponential growth, cap and jitter, never sleeps or retries"""

from __future__ import annotations

from ._backoff import backoff

__version__ = "0.1.0"

__all__ = ["backoff"]

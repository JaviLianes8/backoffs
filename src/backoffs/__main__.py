"""Allow ``python -m backoffs`` as an alias for the ``backoffs`` command."""

from __future__ import annotations

from ._cli import main

raise SystemExit(main())

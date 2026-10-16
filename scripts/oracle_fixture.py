"""Record what independent backoff implementations produce, for tests/test_oracle.py.

Needs tenacity and backoff installed and the AWS simulator fetched by
``scripts/fetch_sources.py``. Writes ``tests/fixtures/oracle_runs.json``: program
output only, no third-party source text.
"""

from __future__ import annotations

import datetime
import importlib.metadata
import json
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

import oracle_cases  # noqa: E402


def main() -> int:
    manifest = json.loads((ROOT / "tests" / "sources" / "MANIFEST.json").read_text("utf-8"))
    runs = [{**case, "delays": oracle_cases.reference(case)} for case in oracle_cases.cases()]
    payload = {
        "recorded": datetime.date.today().isoformat(),
        "python": platform.python_version(),
        "tools": {
            "tenacity": importlib.metadata.version("tenacity"),
            "backoff": importlib.metadata.version("backoff"),
            "aws_backoff_simulator": manifest["files"]["aws_backoff_simulator.py.txt"]["url"],
        },
        "runs": runs,
    }
    out = ROOT / "tests" / "fixtures" / "oracle_runs.json"
    out.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    print(f"{len(runs)} runs written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

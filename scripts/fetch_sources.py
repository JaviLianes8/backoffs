"""Download the external sources the ground-truth tests read, and check their hashes.

The copies land in ``tests/sources/`` and are never committed (third-party text);
``tests/sources/MANIFEST.json`` records what was fetched: URL, date, size, SHA-256 and
licence. Run ``python scripts/fetch_sources.py`` to fetch and verify, or with
``--record`` to (re)write the manifest after a deliberate update.
"""

from __future__ import annotations

import datetime
import gzip
import hashlib
import http.client
import json
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "tests" / "sources"
MANIFEST = HERE / "MANIFEST.json"
GRPC = "https://raw.githubusercontent.com/grpc/grpc/8791d6b1ccb6a694a7369ff21dff3a4228eb8ebf"
GRPC_GO = "https://raw.githubusercontent.com/grpc/grpc-go/529d6e8613c335bd2ca3e6d8fabaee872334b7a7"
AWS_SIM = (
    "https://raw.githubusercontent.com/aws-samples/aws-arch-backoff-simulator/"
    "66cb169277051eea207dbef8c7f71767fe6af144/src/backoff_simulator.py"
)
WAYBACK = "https://web.archive.org/web/"
SOURCES = {
    "aws_blog.html": (
        WAYBACK + "20261006064638id_/"
        "https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/",
        "Amazon, all rights reserved (local copy for testing only)",
    ),
    "aws_backoff_simulator.py.txt": (AWS_SIM, "Apache-2.0"),
    "grpc_connection_backoff.md": (GRPC + "/doc/connection-backoff.md", "Apache-2.0"),
    "grpc_go_backoff_config.go": (GRPC_GO + "/backoff/backoff.go", "Apache-2.0"),
    "grpc_go_backoff_impl.go": (GRPC_GO + "/internal/backoff/backoff.go", "Apache-2.0"),
    "google_memorystore_backoff.html": (
        WAYBACK + "20250825044547id_/"
        "https://cloud.google.com/memorystore/docs/redis/exponential-backoff",
        "CC BY 4.0 (Google Cloud documentation text)",
    ),
    "rfc9110.txt": (
        "https://www.rfc-editor.org/rfc/rfc9110.txt",
        "IETF Trust Legal Provisions",
    ),
}


def fetch(url: str, tries: int = 4) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "backoffs-tests"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data: bytes = response.read()
            # The archive replays some pages with their original gzip encoding.
            return gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data
        except (OSError, http.client.HTTPException):
            if attempt == tries - 1:
                raise
            time.sleep(2.0 * 2**attempt)  # the archive drops connections now and then
    raise AssertionError("unreachable")


def main(argv: list[str]) -> int:
    record = "--record" in argv
    HERE.mkdir(parents=True, exist_ok=True)
    known = {} if record else json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
    entries, failures = {}, 0
    for name, (url, licence) in SOURCES.items():
        data = fetch(url)
        digest = hashlib.sha256(data).hexdigest()
        if not record and known.get(name, {}).get("sha256") != digest:
            print(f"{name}: SHA-256 differs from the manifest; not saved", file=sys.stderr)
            failures += 1
            continue
        (HERE / name).write_bytes(data)
        fetched = known.get(name, {}).get("fetched") or datetime.date.today().isoformat()
        entries[name] = {
            "url": url,
            "fetched": fetched,
            "size": len(data),
            "sha256": digest,
            "licence": licence,
        }
        print(f"{name}: {len(data)} bytes, ok")
    if record:
        payload = {
            "note": "Copies are git-ignored; this file only identifies them.",
            "files": entries,
        }
        MANIFEST.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

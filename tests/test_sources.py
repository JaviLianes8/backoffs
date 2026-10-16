"""backoffs against the published sources, read from copies fetched by scripts/fetch_sources.py.

Each test skips when its copy is absent (the copies are third-party text and stay out of
git; ``tests/sources/MANIFEST.json`` identifies them). Facts are extracted from the
fetched text at run time, never typed in from memory.
"""

from __future__ import annotations

import hashlib
import html
import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backoffs import AdditiveJitter, Exponential, Policy, ProportionalJitter, parse_retry_after

SOURCES = Path(__file__).parent / "sources"
MANIFEST = json.loads((SOURCES / "MANIFEST.json").read_text(encoding="utf-8"))["files"]


def raw_text(name: str) -> str:
    """The fetched copy as it is, after checking it is the one the manifest names."""
    path = SOURCES / name
    if not path.is_file():
        pytest.skip(f"{name} not fetched (run scripts/fetch_sources.py)")
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == MANIFEST[name]["sha256"], name
    return data.decode("utf-8", errors="replace")


def text(name: str) -> str:
    """The fetched copy without markup and with all whitespace runs as one space."""
    raw = raw_text(name)
    if name.endswith(".html"):
        raw = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    return " ".join(raw.split())


def number(source: str, pattern: str) -> float:
    match = re.search(pattern, source)
    assert match is not None, pattern
    return float(match.group(1))


def test_the_aws_post_names_the_three_strategies_and_its_simulator() -> None:
    post = text("aws_blog.html")
    for name in ("Full Jitter", "Equal Jitter", "Decorrelated Jitter"):
        assert name in post
    assert "aws-arch-backoff-simulator" in post.replace(" ", "")


def test_grpc_spec_constants_and_formula_match_the_grpc_preset() -> None:
    spec = text("grpc_connection_backoff.md")
    assert "Min(current_backoff * MULTIPLIER, MAX_BACKOFF)" in spec
    assert "UniformRandom(-JITTER * current_backoff, JITTER * current_backoff)" in spec
    assert "current_deadline = now() + INITIAL_BACKOFF" in spec  # no jitter on the first wait
    policy = Policy.grpc()
    assert isinstance(policy.schedule, Exponential)
    assert isinstance(policy.jitter, ProportionalJitter)
    assert policy.schedule.base == number(spec, r"INITIAL_BACKOFF = ([\d.]+) second")
    assert policy.schedule.factor == number(spec, r"MULTIPLIER = ([\d.]+)")
    assert policy.cap == number(spec, r"MAX_BACKOFF = ([\d.]+) seconds")
    assert policy.jitter.fraction == number(spec, r"JITTER = ([\d.]+)")
    assert policy.jitter.jitter_first is False


def test_grpc_go_defaults_match_the_grpc_preset() -> None:
    config = text("grpc_go_backoff_config.go")
    policy = Policy.grpc()
    assert isinstance(policy.schedule, Exponential)
    assert policy.schedule.base == number(config, r"BaseDelay: ([\d.]+) \* time.Second")
    assert policy.schedule.factor == number(config, r"Multiplier: ([\d.]+)")
    assert policy.cap == number(config, r"MaxDelay: ([\d.]+) \* time.Second")
    assert isinstance(policy.jitter, ProportionalJitter)
    assert policy.jitter.fraction == number(config, r"Jitter: ([\d.]+)")


def test_grpc_go_backoff_function_agrees_with_the_grpc_preset() -> None:
    impl = text("grpc_go_backoff_impl.go")
    # The lines this hand transcription follows, checked in the fetched code:
    for line in (
        "if retries == 0 { return bc.Config.BaseDelay }",
        "for backoff < max && retries > 0 { backoff *= bc.Config.Multiplier retries-- }",
        "if backoff > max { backoff = max }",
        "backoff *= 1 + bc.Config.Jitter*(rand.Float64()*2-1)",
    ):
        assert line in impl, line
    rng = random.Random(21)
    expected = [1.0]
    for retries in range(1, 30):
        backoff = 1.0
        while backoff < 120.0 and retries > 0:
            backoff, retries = backoff * 1.6, retries - 1
        expected.append(min(backoff, 120.0) * (1 + 0.2 * (rng.random() * 2 - 1)))
    actual = list(Policy.grpc(max_retries=30).delays(rng=random.Random(21)))
    assert actual == pytest.approx(expected, rel=1e-12)


def test_google_cloud_guidance_matches_the_google_cloud_preset() -> None:
    page = text("google_memorystore_backoff.html")
    assert "random_number_milliseconds is a random number of milliseconds less than" in page
    steps = [int(n) for n in re.findall(r"wait (\d+) \+ random_number_milliseconds", page)]
    assert steps[:3] == [1, 2, 4]
    policy = Policy.google_cloud()
    assert isinstance(policy.schedule, Exponential) and isinstance(policy.jitter, AdditiveJitter)
    raw = list(Policy(policy.schedule, cap=None, max_retries=3).delays())
    assert raw == [float(n) for n in steps[:3]]
    assert policy.jitter.amount == number(page, r"less than or equal to (\d+)") / 1000


def test_rfc9110_date_examples_all_parse_to_the_same_instant() -> None:
    rfc = raw_text("rfc9110.txt")
    labels = r"IMF-fixdate|obsolete RFC 850 format|ANSI C's asctime\(\) format"
    examples = re.findall(rf"^ +(\S.*?) +; (?:{labels})$", rfc, re.M)
    assert len(examples) == 3
    now = datetime(1994, 11, 6, 8, 0, 0, tzinfo=timezone.utc)
    assert [parse_retry_after(e, now=now) for e in examples] == [49 * 60 + 37.0] * 3


def test_rfc9110_retry_after_examples_parse() -> None:
    rfc = raw_text("rfc9110.txt")
    values = re.findall(r"^ +Retry-After: (\S.*)$", rfc, re.M)
    assert len(values) == 2
    now = datetime(1999, 12, 31, 23, 59, 0, tzinfo=timezone.utc)
    assert sorted(parse_retry_after(v, now=now) for v in values) == [59.0, 120.0]
    flat = text("rfc9110.txt")
    assert "delay-seconds = 1*DIGIT" in flat
    assert "more than 50 years in the future" in flat

"""Every example in the docstrings, README.md and GUIDE.md runs and shows what it says."""

from __future__ import annotations

import doctest
import pkgutil
import re
import shlex
from pathlib import Path

import pytest

import backoffs
from backoffs._cli import _parser, main

ROOT = Path(__file__).resolve().parents[1]
DOCS = ["README.md", "GUIDE.md"]
FENCE = re.compile(r"^```(\w*)\n(.*?)^```", re.M | re.S)
MODULES = ["backoffs"] + [f"backoffs.{m.name}" for m in pkgutil.iter_modules(backoffs.__path__)]


def blocks(name: str, language: str) -> list[str]:
    text = (ROOT / name).read_text(encoding="utf-8")
    return [body for lang, body in FENCE.findall(text) if lang == language]


def docstrings() -> dict[str, str]:
    """The package docstring, every public name's, and its own methods' and properties'."""
    found = {"backoffs": backoffs.__doc__ or ""}
    for name in backoffs.__all__:
        obj = getattr(backoffs, name)
        found[name] = obj.__doc__ or ""
        for attr, member in vars(obj).items() if isinstance(obj, type) else ():
            member = getattr(member, "__func__", member)
            member = getattr(member, "fget", member)
            doc = getattr(member, "__doc__", None)
            if callable(member) and doc and not attr.startswith("_"):
                found[f"{name}.{attr}"] = doc
    return found


DOCSTRINGS = docstrings()


@pytest.mark.parametrize("name", sorted(DOCSTRINGS))
def test_docstring_examples_pass(name: str) -> None:
    parser = doctest.DocTestParser()
    runner = doctest.DocTestRunner(optionflags=doctest.ELLIPSIS)
    runner.run(parser.get_doctest(DOCSTRINGS[name], {}, name, None, 0))
    assert runner.failures == 0


def test_every_public_name_has_a_runnable_example() -> None:
    for name in backoffs.__all__:
        assert ">>> " in DOCSTRINGS[name], name
    for name in ("Policy.delays", "Policy.grpc", "Policy.google_cloud"):
        assert ">>> " in DOCSTRINGS[name], name


def test_the_doctests_together_cover_many_examples() -> None:
    parser = doctest.DocTestParser()
    examples = sum(len(parser.get_examples(doc)) for doc in DOCSTRINGS.values())
    assert examples >= 90


def test_private_modules_hold_no_examples_the_walk_misses() -> None:
    for module in MODULES:
        if module != "backoffs.__main__":
            imported = __import__(module, fromlist=["_"])
            assert doctest.testmod(imported, verbose=False).failed == 0


@pytest.mark.parametrize("name", DOCS)
def test_pycon_examples_run_and_print_what_they_show(name: str) -> None:
    examples = blocks(name, "pycon")
    assert examples, name
    parser = doctest.DocTestParser()
    runner = doctest.DocTestRunner(optionflags=doctest.ELLIPSIS)
    for index, body in enumerate(examples):
        test = parser.get_doctest(body, {}, f"{name}[{index}]", name, 0)
        runner.run(test)
    assert runner.failures == 0


@pytest.mark.parametrize("name", DOCS)
def test_python_examples_run(name: str) -> None:
    examples = blocks(name, "python")
    assert examples, name
    for body in examples:
        exec(compile(body, name, "exec"), {"__name__": "docs_example"})


def command_lines() -> list[str]:
    lines = []
    for name in DOCS:
        for body in blocks(name, ""):
            lines += [line for line in body.splitlines() if line.startswith("backoffs ")]
    return lines


def test_every_command_example_parses_and_offline_ones_run(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lines = command_lines()
    assert len(lines) >= 8
    for line in lines:
        argv = shlex.split(line)[1:]
        _parser().parse_args(argv)
        if argv[0] in ("schedule", "retry-after"):
            assert main(argv) == 0, line
    capsys.readouterr()


def test_the_cli_help_lists_only_examples_that_parse(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--help"])
    examples = [ln.strip() for ln in capsys.readouterr().out.splitlines() if "  backoffs " in ln]
    assert len(examples) >= 6
    for line in examples:
        _parser().parse_args(shlex.split(line)[1:])

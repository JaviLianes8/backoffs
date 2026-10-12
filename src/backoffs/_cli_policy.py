"""Command-line options that describe a :class:`Policy`, shared by every subcommand."""

from __future__ import annotations

import argparse

from ._jitter import (
    AdditiveJitter,
    DecorrelatedJitter,
    EqualJitter,
    FullJitter,
    Jitter,
    NoJitter,
    ProportionalJitter,
)
from ._policy import Policy
from ._schedules import Constant, Exponential, Fibonacci, Linear, Schedule

STRATEGIES = ("exponential", "linear", "fibonacci", "constant")
JITTERS = ("none", "full", "equal", "decorrelated", "proportional", "additive")
PRESETS = ("grpc", "google-cloud")
_SHAPE_OPTIONS = ("strategy", "base", "factor", "step", "cap", "jitter", "fraction", "amount")


def add_policy_options(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("policy")
    group.add_argument("--preset", choices=PRESETS, help="use a published strategy as is")
    group.add_argument("--strategy", choices=STRATEGIES, help="growth (default: exponential)")
    group.add_argument("--base", type=float, help="first delay in seconds (default: 1.0)")
    group.add_argument("--factor", type=float, help="exponential multiplier (default: 2.0)")
    group.add_argument("--step", type=float, help="linear increment (default: --base)")
    group.add_argument("--cap", type=float, help="maximum delay before jitter (default: 30)")
    group.add_argument("--jitter", choices=JITTERS, help="jitter strategy (default: none)")
    group.add_argument("--fraction", type=float, help="proportional jitter spread (default: 0.2)")
    group.add_argument("--amount", type=float, help="additive jitter seconds (default: 1.0)")
    group.add_argument("--max-retries", type=int, metavar="N", help="stop after N delays")
    group.add_argument("--max-elapsed", type=float, metavar="S", help="time budget in seconds")
    group.add_argument("--seed", type=int, help="seed the jitter for a reproducible schedule")


def build_policy(args: argparse.Namespace, default_retries: int) -> Policy:
    """Turn parsed options into a policy; raises ``ValueError`` on bad combinations."""
    max_retries: int | None = args.max_retries
    if max_retries is None and args.max_elapsed is None:
        max_retries = default_retries
    if args.preset is not None:
        clashing = [f"--{name}" for name in _SHAPE_OPTIONS if getattr(args, name) is not None]
        if clashing:
            raise ValueError(f"--preset cannot be combined with {', '.join(clashing)}")
        maker = Policy.grpc if args.preset == "grpc" else Policy.google_cloud
        return maker(max_retries=max_retries, max_elapsed=args.max_elapsed)
    return Policy(
        _schedule(args),
        _jitter(args),
        cap=30.0 if args.cap is None else args.cap,
        max_retries=max_retries,
        max_elapsed=args.max_elapsed,
    )


def _schedule(args: argparse.Namespace) -> Schedule:
    base = 1.0 if args.base is None else args.base
    strategy = args.strategy or "exponential"
    if strategy == "exponential":
        return Exponential(base, 2.0 if args.factor is None else args.factor)
    if args.factor is not None:
        raise ValueError("--factor only applies to --strategy exponential")
    if strategy == "linear":
        return Linear(base, base if args.step is None else args.step)
    if args.step is not None:
        raise ValueError("--step only applies to --strategy linear")
    return Fibonacci(base) if strategy == "fibonacci" else Constant(base)


def _jitter(args: argparse.Namespace) -> Jitter:
    name = args.jitter or "none"
    if args.fraction is not None and name != "proportional":
        raise ValueError("--fraction only applies to --jitter proportional")
    if args.amount is not None and name != "additive":
        raise ValueError("--amount only applies to --jitter additive")
    if name == "proportional":
        return ProportionalJitter(0.2 if args.fraction is None else args.fraction)
    if name == "additive":
        return AdditiveJitter(1.0 if args.amount is None else args.amount)
    simple: dict[str, Jitter] = {
        "none": NoJitter(),
        "full": FullJitter(),
        "equal": EqualJitter(),
        "decorrelated": DecorrelatedJitter(),
    }
    return simple[name]

# backoffs 1.0.0 certification report

Progress:
- [x] Branch `release/1.0.0` created from `main` (0.2.0, a832faf; PyPI has 0.2.0)
- [x] Baseline gates run on 0.2.0
- [x] API review and 1.0.0 API changes (item 1)
- [x] Real ground truth: fetched sources and live reference implementations (item 7)
- [x] Errors, typing, docstrings and doctests (items 2 to 5)
- [x] Contract, fuzz and author mutation round (items 6, 9, 18)
- [x] Docs: README, GUIDE, CHANGELOG (items 11, 12)
- [x] Packaging, e2e and upgrade from PyPI 0.2.0 (items 8, 10, 13, 14), author run
- [x] Five QA lenses report PASS (item 19)
- [x] Independent reviewer reports PASS (item 16)
- [x] Gates (item 15), final run
- [x] PR and trace guard CLEAN (item 17); merge and publish left to the maintainer

## Scorecard

Independent review (item 16), round 2 at 87813ed; the commits after it touch only this
report and the README badge.

| # | Item | Result |
| --- | --- | --- |
| 1 | Public API reviewed for stability | PASS: all 23 names, signatures and defaults kept from 0.2.0 with identical seeded output; every behaviour change in CHANGELOG 1.0.0 with an upgrade list |
| 2 | `__all__` exact, no private imports in docs | PASS: 23 names |
| 3 | Docstrings with runnable examples, doctests | PASS: every public name plus three preset and iterator methods; every README and GUIDE example and command line runs in `tests/test_docs.py` |
| 4 | Typed end to end | PASS: `mypy --strict src tests scripts` clean, `py.typed` shipped, a strict consumer client clean (lens a) |
| 5 | Typed, documented, bounded errors | PASS: GUIDE table; hostile inputs give typed errors under 120 characters with no echo |
| 6 | Contract tests of every public name | PASS |
| 7 | Real ground truth | PASS: AWS simulator code, tenacity 9.2.1 and backoff 2.2.1 recorded and live (81 of 85 runs bit for bit, 4 within 12 digits); gRPC spec, grpc-go, Google Cloud and RFC 9110 fetched with manifest; lens b 200,881 comparisons with its own harness |
| 8 | Real e2e from the wheel | PASS: console script and `python -m backoffs` by subprocess, sabotage caught, in-place upgrade from PyPI 0.2.0 |
| 9 | Seeded fuzz, no crash, hang or blowup | PASS: suite fuzz plus lens c (520,000 cases over two rounds), linear time to 10 MB |
| 10 | Supported Pythons | PASS: CPython 3.10.19, 3.11.5, 3.12.12, 3.13.2, 3.14.2 and 3.14.2 free-threaded; 3.8 and 3.9 are below `requires-python` |
| 11 | README and `twine check` | PASS |
| 12 | Dated CHANGELOG 1.0.0 section | PASS |
| 13 | pyproject 1.0.0, Production/Stable | PASS |
| 14 | sdist and wheel contents | PASS |
| 15 | Gates each exit 0 | PASS: each alone on a fresh clone at 87813ed (591 passed, 11 skipped: fetched sources, live references and the network upgrade test) |
| 16 | Independent reviewer | PASS: round 1 FAIL at 0d98af7, round 2 PASS at 87813ed |
| 17 | PR and trace guard | PR #3, trace guard CLEAN; merge and publish left to the maintainer |
| 18 | Contracts bite (mutations) | PASS: author 50, blind lens e 184 over three rounds, reviewer 40; every non-equivalent survivor killed by a contract |
| 19 | Five independent QA lenses | PASS: a round 2, b round 2, c round 2, d round 1, e round 3 |

## Behaviour changes against PyPI 0.2.0

CHANGELOG 1.0.0's "Upgrading from 0.2.0" list is the reference; lenses a and d traced
every difference they measured to a line there. Seeded sequences, presets, `backoff()`
and `retry` results are identical. Changed: `backoffs` exit statuses (2 for usage; `run`
exits with the command's last status, 124 on timeout, 126, 127, 130); `RetryError`'s
message names only the last exception's type; eager typed argument checks
(`InvalidPolicyError`), including clock readings and `aretry` awaitables; bounded error
messages; ASCII digits only and calendar years for the RFC 850 rule in `Retry-After`;
overflowing additive jitter and totals saturate; `RetryError` pickles; public names
report `backoffs` as their module.

## Baseline on 0.2.0 (before any change)

Fresh clone of `main` (a832faf) on Elena's PC, CPython 3.14.2: `ruff format --check .`,
`ruff check .` and `mypy --strict src tests` exit 0; `pytest` 186 passed. PyPI has 0.2.0
(0.1.0 was never published there).

Defects found in 0.2.0 by the API review, the fuzzing and the ground truth work:

- A wrong schedule, jitter, policy, `rng`, `clock`, `sleep`, hook or `retry_on` failed
  late with `AttributeError` or `TypeError`; a bad `retry_on` only after the first
  failure, inside the `except` block.
- A custom schedule that ended stopped the iterator silently (and `retry` then reported
  `max_retries`); a custom schedule or jitter could hand a negative, NaN or infinite
  delay to `sleep`.
- A clock returning NaN kept a `max_elapsed` budget open forever.
- An integer too large for a float leaked `OverflowError`; error messages echoed whole
  inputs (a 100,000-character string, a 5,000-digit integer, a hostile `__repr__`);
  `RetryError` repeated the last exception's text.
- `parse_retry_after()` read other scripts' digits (`\d`), refused an RFC 850 date on
  29 February when the next century's year has none, and raised `OverflowError` for a
  leap second on 31 December 9999.
- `RetryError` could not be unpickled (keyword-only constructor).
- CLI: every failure exited 1, so a command's own status was lost; Ctrl+C, an
  `--attempt-timeout` or `--cap` longer than the platform can wait, and
  `--retry-on-exit 0` gave a traceback or nonsense.
- Found while building: the sdist include list was not anchored, so anything named
  `tests`, `LICENSE` or `README.md` under the project folder (a local venv) was packed.

## API review (item 1)

Kept from 0.2.0 with the same names, signatures, defaults and seeded results: all 23
public names. `backoff()` still produces the 0.1 sequences. Changed for 1.0.0, all in
CHANGELOG 1.0.0 with an upgrade list: CLI exit statuses (2 for usage, the command's own
status when `run` gives up, 124, 126, 127, 130); the `RetryError` message names only the
last exception's type; eager argument checks raising `InvalidPolicyError`; bounded
messages; ASCII digits only in `Retry-After`; public names report `backoffs` as their
module. Considered and kept: `InvalidPolicyError` (a `ValueError`) for wrong types as
well as bad values, as in 0.2.0, so callers catch one class; `backoff()` keeps raising
`TypeError` for `None`, as 0.1 and 0.2 did.

## Ground truth (item 7)

`scripts/fetch_sources.py` downloads seven sources into the git-ignored `tests/sources/`
and checks them against `tests/sources/MANIFEST.json` (URL, date, size, SHA-256,
licence; fetched 2026-10-16): the AWS Architecture Blog post (archived snapshot), the
blog's simulator source at a pinned commit, gRPC's `doc/connection-backoff.md` and
grpc-go's `backoff/backoff.go` and `internal/backoff/backoff.go` at pinned commits, the
Google Cloud Memorystore backoff page (archived snapshot) and RFC 9110.

- `tests/test_oracle.py`: 85 scenarios run through the simulator's own `ExpoBackoff`,
  `ExpoBackoffFullJitter`, `ExpoBackoffEqualJitter` and `ExpoBackoffDecorr` classes
  (executed from the fetched source, class definitions only), tenacity 9.2.1 and
  backoff 2.2.1, seeded alike, recorded by `scripts/oracle_fixture.py` in
  `tests/fixtures/oracle_runs.json` (program output, CPython 3.13.2). 81 match bit for
  bit; the 4 tenacity `wait_exponential` runs with factors 1.6 and 3 agree to 12
  significant digits (tenacity raises the factor to a power, backoffs multiplies step by
  step). With the references present the test reruns them live (Elena's PC, 96 passed).
- `tests/test_sources.py`: the gRPC constants and formula lines and grpc-go's
  `DefaultConfig` are read from the fetched text and compared with `Policy.grpc()`;
  grpc-go's `Backoff(retries)` (its lines checked in the fetched code; the Python form is
  a labelled hand transcription) agrees with `Policy.grpc()` over 30 seeded retries; the
  Google page's `1 + ..., 2 + ..., 4 + ...` steps and the 1000 ms bound match
  `Policy.google_cloud()`; RFC 9110's three example dates and both `Retry-After`
  examples are extracted from the text and parsed.
- `tests/test_fuzz.py`: 9,000 random IMF-fixdates against the standard library's
  `email.utils.parsedate_to_datetime` (years 100 to 9999; below 100 the standard library
  applies RFC 2822 two-digit rules, RFC 9110 has none), and 9,000 instants written in all
  three forms parse to the same seconds.

## Errors, typing, docs (items 2 to 5)

- `__all__` lists the 23 public names; `tests/test_contract.py` pins it.
- Every public name, and `Policy.delays`, `Policy.grpc` and `Policy.google_cloud`, has a
  runnable example (99 examples, run with empty globals by `tests/test_docs.py`); every
  `pycon` and `python` block of README and GUIDE runs; every command line in them and in
  `--help` parses, and the offline ones run.
- `mypy --strict src tests scripts` clean; `py.typed` shipped; no `Any` in the public API.
- Errors: GUIDE table; `tests/test_contract_errors.py` drives 17 constructors with 8
  hostile values each and checks the type and a message under 120 characters with no
  echo.

## Contracts, fuzz and mutations (items 6, 9, 18)

New contract files: `test_contract_errors.py`, `test_contract_delays.py`,
`test_contract_cli.py` (real processes for each exit status), `test_docs.py`,
`test_oracle.py`, `test_sources.py`, `test_e2e_upgrade.py`. Fuzz: `test_fuzz.py` and
`test_fuzz_retry.py` (16,000 random or mutated `Retry-After` values, 2,000 random
policies against every promise, `retry` and `aretry` identical on 600 random failure
patterns, 1 and 4 million character values refused in linear time).

Author mutation round: 50 mutations over every module, each applied alone to a fresh
clone of the pushed branch at e66b23a on Elena's PC (CPython 3.14.2), suite with `-x`
and no bytecode, the two end-to-end modules left out for time, file restored after;
baseline green before.

| Id | Module | Mutation | Caught by |
| --- | --- | --- | --- |
| D01 | `_delays` | max_retries off by one | `test_backoff::test_no_jitter_yields_the_exact_exponential_sequence` |
| D02 | `_delays` | cap applied late | `test_backoff::test_seeded_sequences_are_identical_to_the_0_1_release` |
| D03 | `_delays` | decorrelated chain remembers the floored delay | survived; killed by `test_contract_delays::test_a_floor_lengthens_one_wait_without_inflating_the_decorrelated_chain` |
| D04 | `_delays` | floor kept for every later delay | `test_docs::test_docstring_examples_pass[Delays]` |
| D05 | `_delays` | landing exactly on the budget refused | `test_policy::test_max_elapsed_allows_landing_exactly_on_the_budget` |
| D06 | `_delays` | NaN clock keeps the budget open | `test_contract_delays::test_a_broken_clock_spends_the_budget[nan]` |
| D07 | `_delays` | total never updated | `test_cli::test_schedule_table_lists_delays_and_totals` |
| D08 | `_delays` | attempt counted from 1 | `test_cli::test_schedule_strategies[args4-expected4]` |
| D09 | `_delays` | clock budget ignores the start | `test_docs::test_python_examples_run[GUIDE.md]` |
| D10 | `_delays` | custom schedule delay unchecked | `test_contract_delays::test_bad_custom_delays_are_refused[-1.0]` |
| D11 | `_delays` | two floors keep the smaller | `test_docs::test_docstring_examples_pass[Delays]` |
| J01 | `_jitter` | full jitter lower bound | `test_backoff::test_seeded_sequences_are_identical_to_the_0_1_release` |
| J02 | `_jitter` | equal jitter spread doubled | `test_backoff::test_equal_jitter_stays_within_half_and_the_raw_delay` |
| J03 | `_jitter` | decorrelated uses base not previous | `test_backoff::test_seeded_sequences_are_identical_to_the_0_1_release` |
| J04 | `_jitter` | decorrelated lower bound 0 | `test_backoff::test_decorrelated_jitter_stays_within_base_and_cap` |
| J05 | `_jitter` | decorrelated ignores the cap | `test_backoff::test_decorrelated_jitter_stays_within_base_and_cap` |
| J06 | `_jitter` | jitter_first inverted | `test_cli::test_schedule_strategies[args4-expected4]` |
| J07 | `_jitter` | proportional only adds | `test_jitter_formulas::test_proportional_jitter_matches_the_grpc_uniform_spread` |
| J08 | `_jitter` | additive ignores the cap | `test_cli::test_schedule_jitter_options` |
| J09 | `_jitter` | fraction above 1 accepted | `test_jitter_formulas::test_invalid_jitter_arguments_raise[<lambda>1]` |
| J10 | `_jitter` | multiplier 1 refused | `test_fuzz::test_random_policies_keep_every_promise[0]` |
| S01 | `_schedules` | linear skips the start | `test_cli::test_schedule_strategies[args0-expected0]` |
| S02 | `_schedules` | fibonacci doubles | `test_docs::test_docstring_examples_pass[Fibonacci]` |
| S03 | `_schedules` | exponential overflows to inf | `test_backoff::test_inputs_accepted_by_0_1_keep_working` |
| S04 | `_schedules` | factor below 1 accepted | `test_backoff::test_invalid_arguments_raise_value_error[kwargs2-factor]` |
| P01 | `_policy` | cap below the first delay accepted | `test_backoff::test_invalid_arguments_raise_value_error[kwargs4-cap]` |
| P02 | `_policy` | grpc multiplier wrong | `test_jitter_formulas::test_grpc_preset_waits_the_plain_initial_backoff_then_jitters_1_6_growth` |
| P03 | `_policy` | grpc jitters the first wait | `test_cli::test_schedule_strategies[args4-expected4]` |
| P04 | `_policy` | google random part halved | `test_jitter_formulas::test_google_cloud_preset_is_two_to_the_n_plus_up_to_a_second_truncated` |
| V01 | `_validate` | infinities accepted | `test_contract_cli::test_bad_values_exit_2_before_running_anything[args4]` |
| V02 | `_validate` | long strings echoed | `test_contract_cli::test_a_missing_program_exits_127_without_echoing_a_long_name` |
| V03 | `_validate` | booleans accepted as numbers | `test_schedules::test_invalid_schedule_arguments_raise[<lambda>7]` |
| C01 | `_controller` | giveup inverted | `test_cli::test_run_succeeds_after_real_failures` |
| C02 | `_controller` | retry_on ignored | `test_cli::test_run_reports_a_missing_program` |
| C03 | `_controller` | retry_after hint dropped | `test_retry::test_retry_after_hint_is_a_floor_for_the_next_delay` |
| C04 | `_controller` | retry_on not validated | `test_contract_errors::test_retry_and_aretry_check_every_argument_before_the_first_call[kwargs0]` |
| E01 | `_errors` | RetryError echoes the message | `test_contract_errors::test_retry_error_hides_the_last_message_and_survives_pickling` |
| E02 | `_errors` | pickling broken | `test_contract_errors::test_retry_error_hides_the_last_message_and_survives_pickling` |
| R01 | `_retry_after` | past dates negative | `test_cli::test_retry_after_prints_seconds` |
| R02 | `_retry_after` | rfc850 never rolls into the next century | `test_retry_after::test_rfc850_two_digit_year_can_roll_into_the_next_century` |
| R03 | `_retry_after` | leap second refused | `test_retry_after::test_leap_second_is_accepted` |
| R04 | `_retry_after` | digit limit removed | `test_fuzz::test_huge_values_are_refused_in_linear_time[1000000]` |
| R05 | `_retry_after` | other scripts' digits in times | survived; killed by `test_contract_errors::test_every_numeric_field_takes_ascii_digits_only` |
| L01 | `_cli_run` | signal status wrong | `test_contract_cli::test_exit_status_maps_signals_and_windows_codes[-9-linux-137]` |
| L02 | `_cli_run` | timeout status 1 | `test_cli::test_run_retries_a_timed_out_attempt` |
| L03 | `_cli_run` | cannot execute reported as not found | `test_contract_cli::test_a_file_that_cannot_be_executed_exits_126` |
| L04 | `_cli_run` | give up exits 1 | `test_cli::test_run_gives_up_with_the_last_exit_status` |
| L05 | `_cli` | interrupt during run exits 1 | `test_contract_cli::test_an_interrupt_exits_130_without_a_traceback` |
| L06 | `_cli` | retry-on-exit 0 accepted | `test_contract_cli::test_bad_values_exit_2_before_running_anything[args0]` |
| L07 | `_cli` | usage error exits 1 | `test_cli::test_errors_go_to_stderr_with_exit_two_or_one[args0---preset cannot be combined]` |

Result: 48 killed at once; 2 survivors (D03, R05) killed by the contracts added in
1bdda19, each confirmed to fail on its mutant.

## Packaging and end-to-end (items 8, 10, 13, 14), author run

- Elena's PC, fresh clone: `python -m build` and `twine check --strict` PASSED for both
  archives. Wheel: the 15 modules, `py.typed`, LICENSE, metadata and the console script
  entry point. Sdist: `src`, `tests` (fixture and manifest, no fetched copies), the two
  source scripts, README, GUIDE, CHANGELOG, CONTRIBUTING, LICENSE,
  `requirements-dev.txt`, pyproject and `.gitignore`; no report, round notes, check
  scripts or scratch files.
- `BACKOFFS_E2E_PYPI=1`: PyPI 0.2.0 installed in a fresh venv, probed, upgraded in
  place to the 1.0.0 wheel and probed again: every seeded sequence, the presets, the
  legacy function, `retry` and `parse_retry_after` identical; the exit statuses (1 to 2,
  1 to 5) and the `RetryError` message change exactly as the CHANGELOG says.
- This PC: the wheel installed in fresh venvs and the suite run from the unpacked sdist
  with `src` removed (so it imports the installed wheel and drives its console script):
  528 passed, 11 skipped (fetched sources, live references and the network upgrade
  test) on CPython 3.10.19, 3.11.5, 3.12.12, 3.13.2, 3.14.2 and 3.14.2 free-threaded.
  3.8 and 3.9 are below `requires-python`.

## Independent QA lenses (item 19)

Each lens was a fresh reviewer that read the certification rules and CERT-1.0.md first,
ran the code rather than only reading it, reported only to the author and posted nothing
to GitHub. Lenses ran one at a time. Later rounds were bounded to confirming earlier
findings plus one sweep of the code changed since.

| Lens | Round | Head | Verdict | Findings and outcome |
| --- | --- | --- | --- | --- |
| a. API and docs | 1 | e499298 | FAIL | the `jitter_first` bool check and `backoff(rng=...)` check were missing from the CHANGELOG; the CHANGELOG and GUIDE claimed every argument was checked, yet a synchronous `fn` given to `aretry` was called and retried six times, a blocking `sleep` blocked the loop and a clock returning `None` failed with a raw `TypeError`. Fixed in e30f423 (awaitables and clock readings checked, wording narrowed, `tests/test_contract_async.py`) |
| a | 2 | e30f423 | PASS | both confirmed; 88 docstring examples, every README and GUIDE example and a strict consumer client rerun. Nit (a clock reading too large for a float leaked `OverflowError`) fixed in 03df168 |
| b. Correctness and ground truth | 1 | 5ead5a7 | PASS (1 low finding) | own harness, sources fetched in its run, 200,881 seeded comparisons: AWS simulator classes, tenacity 9.2.1, backoff 2.2.1, google-api-core 2.42.0, urllib3 2.8.0, the gRPC pseudo-code and grpc-go, Google's formula, `email.utils`, urllib3 and `http.cookiejar` for dates; all bit-exact or within 4 ulp where the oracle raises to a power. Finding: the RFC 850 fifty-year limit was measured as 50 x 365.2425 days, not calendar years. Fixed in a646201 with contracts |
| b | 2 | 3e70b67 | PASS | 1,200 RFC 850 cases against its own derivation, 0 mismatches; boundaries (exactly 50 years, 29 February, year 9990) confirmed |
| c. Adversarial and robustness | 1 | 3e70b67 | FAIL | 200,000 random policies, 200,000 hostile `Retry-After` values, 100,000 retry runs, 600 hostile CLI option sets: no crash, hang, leak or exceeded budget, but `AdditiveJitter` could overflow to infinity, `backoff()` documented `InvalidPolicyError` where it raises `TypeError` for non-numbers, a `raw()` returning a list failed late, an extreme `now` leaked `OverflowError`, the CLI JSON could print `Infinity`, and `--retry-on-exit -1` never matched on Windows. Fixed in 07c5280 (saturation, iterable schedules, typed errors, signed and unsigned codes, docstring, GUIDE thread note, `tests/test_contract_limits.py`) |
| c | 2 | 07c5280 | PASS | all six confirmed; bounded sweep of 120,000 policies, 120,000 `Retry-After` values and 60,000 retry runs on the same seeds: 0 failures (round 1 hit the overflow 75 times) |
| d. Packaging and real e2e | 1 | 07c5280 | PASS | the first attempt was cut by a usage limit before reporting and was relaunched fresh; wheel and sdist from a fresh clone, `twine check --strict`, contents and metadata as above; on CPython 3.10.19, 3.11.5, 3.12.12, 3.13.2, 3.14.2 and 3.14.2 free-threaded: console script and `python -m backoffs` by subprocess from outside the tree, 560 passed and 11 skipped from the sdist with `src` removed, PyPI 0.2.0 upgraded in place with every difference matching CHANGELOG 1.0.0; 3.9 refused by `requires-python`; two sabotages caught (console script deleted: 5 failures; `__main__` replaced: 1 failure) |
| e. Contract strength (blind) | 1 | 4cfe6e2 | FAIL | 171 mutations of its own over every module (Elena's PC, CPython 3.14, end-to-end modules left out): 148 killed, 23 survivors, none equivalent: untested defaults (legacy cap and float counts, jitter fraction and amount, `aretry` and `run` retry counts, CLI linear step, CLI proportional fraction), twin paths (`google_cloud` budgets, `aretry` callable check), saturation on uncapped proportional and decorrelated chains, a zero cap, a bad custom `first`, a non-iterable `raw()`, a stopped iterator staying stopped, ASCII previews, plain format digits, `--preset` with `--max-elapsed`, and strict `Retry-After` edges (only SP and HTAB trimmed, no trailing text, years near the limits of `datetime`). All pinned in `tests/test_contract_blind.py` (32d2248), each confirmed to fail on its mutant |
| e | 2 | 32d2248 | FAIL | the 23 confirmed killed on the full suite; 13 new mutations: 10 killed, 3 survivors (a zero float count in `backoff()`, asctime years shorter than four digits, an untruncated type name in previews), pinned in 7c8c34d |
| e | 3 | 7c8c34d | PASS | the 3 confirmed killed; 184 mutations over three rounds, 0 non-equivalent survivors |

## Independent review (item 16)

| Round | Head | Verdict | Findings and outcome |
| --- | --- | --- | --- |
| 1 | 0d98af7 | FAIL (items 6, 16, 18) | gates each exit 0 alone on a fresh clone (585 passed, 11 skipped), `mypy --strict src tests` clean, wheel and sdist built and `twine check --strict` passed, fetched sources matched their hashes, `test_sources` and `test_oracle` live 96 passed, upgrade from PyPI 0.2.0 identical, suite green on 3.10 to 3.14 free-threaded; its own 40 mutations: 37 killed, 2 equivalent (M09, M24), 1 survivor (M36: `if hint is not None:` changed to `if hint:` in `_controller.py`; no contract fed `retry`/`aretry` a `retry_after` hook returning `False`, `""` or `[]`), pinned in 87813ed by `test_contract_async::test_a_bad_retry_after_hint_is_refused_by_both_helpers` |
| 2 | 87813ed | PASS | M36 killed by that contract on a fresh clone; gates each exit 0 alone on Elena's PC, CPython 3.14.2 (591 passed, 11 skipped) |

# Coding standards

The standard for new and touched Python in `backend/`, how it is enforced, and the
backlog it leaves. [AI-08] Where this file and an ADR disagree, the ADR wins.

## The standard

| Rule | Limit | Why |
| --- | --- | --- |
| Module length | 250 lines | A module that fits in a review is read whole; past that it is skimmed |
| Class length | 150 lines | A class that long has more than one reason to change |
| Function length | 40 lines | One screen: the whole function and its docstring visible together |
| Cyclomatic complexity | 10 | More than ten paths cannot be held in a reviewer's head or covered by a few tests |
| Arguments | 7 (`self`/`cls` excluded) | Past that the arguments are a missing type |
| Bare `except:` | none | It swallows `KeyboardInterrupt` and hides the bug it was written to survive |
| Module docstring | every module | A reader meets the file before the code |
| Class docstring | every public class | The name says what it is; the docstring says why it exists |
| Function docstring | public functions over 15 lines | Where a reader must decide whether to trust the body |
| Duplicated function bodies | none new | One fix should be one change |

Docstrings should say **why**, not restate the signature. No tool can check that; only
their presence is enforced, so review is where it is held.

Design: Clean Architecture and SOLID as in [ADR-003](ADR-003-clean-architecture-cqrs.md)
(layering is enforced by `tests/test_architecture.py`); DRY — a second copy of a rule
is a second place to fix it.

## How it is enforced: a ratchet

Applying a standard retroactively to 150,000 lines fails on day one and is then
ignored. So `tests/code_standards_baseline.json` records every violation that already
exists, with how bad it is, and `tests/test_code_standards.py` fails when:

1. a violation appears that is **not** in the baseline (new code broke a standard);
2. a baseline violation got **worse** (a long function grew); or
3. a baseline violation got **better or went away** and the baseline was not tightened
   (so a fixed problem cannot quietly return).

Refactoring is rewarded and never blocked: improve something, run

```
python scripts/code-standards.py          # report: counts per rule, largest offenders, verdict
python scripts/code-standards.py --update # accept the new, smaller state
```

and commit the smaller baseline. `--update` refuses to loosen the baseline. A function
that moves to another file unchanged is recognised as a move (same rule, same name, no
worse), so splitting a module is not punished as a new violation.

Tests, the synthetic-data generators in `backend/data/`, and `__pycache__` are not
measured: a long parametrised table is not a design smell, and the generators are
scripts. The measurement is pure AST (`backend/tools/code_standards/`) and imports none
of the code it measures. Each rule is shown firing on a crafted example in the same
test file.

### Baseline when it was introduced (AI-08)

| Rule | Violations |
| --- | ---: |
| function length | 155 |
| complexity | 113 |
| function docstring | 71 |
| class docstring | 68 |
| module length | 44 |
| arguments | 22 |
| class length | 9 |
| module docstring | 1 |
| **Total** | **483** |

It was 540 before the AI platform work was brought up to standard (new AI code written
to the limits; the channel layer's `numeric_guard`, `composer`, `capabilities/format`,
`capabilities/client` and `capabilities/catalog` split into siblings with every import
path unchanged; ~40 docstrings added). `test_the_new_ai_layer_has_no_baselined_violations_in_size_or_shape`
holds `application/ai/`, `infrastructure/ai/`, `domain/ai*`, `api/chat/` and the
standards tooling to the limits outright — apart from five chat-pipeline functions that
moved there unchanged from the old single module and are listed below.

## Vendored modules

The numeric guard, composer, formatter and capability catalog are copied into the
orchestrator container, so each is standard library plus its vendored siblings only
(`test_numeric_guard`, `test_composer`, `test_architecture` pin this). When one is
split, the siblings are vendored too: the unit of vendoring is the **package files
together**, not a single file.

## Backlog: the fifteen worst

By overshoot of the limit. Most are the calculation engine and its persistence, where a
refactor must be proven against the parity gate (10,236 · 539 · 656) before it merges;
none should be touched without it. The right unit of work is "extract a function, run
the gate", not a rewrite.

| Offender | Measure | Note |
| --- | ---: | --- |
| `tools/reference_step1.py::run_reference_step1` | 279 lines | Reference tooling; independent of the product path |
| `application/commands/run_client_calculation.py::_replay_unit_series` | 255 lines | The write-time engine replay — **parity-critical** |
| `domain/calculation/onezero.py::run_pay_period_method` | 244 lines | Certified method — **parity-critical** |
| `domain/calculation/onezero.py::run_min_max_method` | 239 lines | Certified method — **parity-critical** |
| `application/queries/simulate_employee.py::handle_simulate_employee` | 219 lines, complexity 52 | Extract per-lever helpers |
| `domain/calculation/onezero.py` | 1,295 lines | Certified method — **parity-critical**. Not split in RM-19: see D-141 |
| `application/queries/get_portfolio.py::portfolio_page` | 205 lines | Extract the band and filter steps |
| `tools/build_approval_package.py::_cover_sheet` | 192 lines | Document assembly; split by section |
| `application/commands/run_client_calculation.py::handle_run_client_calculation` | 178 lines | Write path — parity-critical |
| Chat pipelines (`api/chat/dispatch.py::_dispatch` 86, `pipelines_core.py::_pipeline_eligibility` 92, …) | up to 92 lines | Moved from the old single module; split per scope step |

Then the long tail: 71 public functions and 68 public classes without a docstring.
Each is a one-line fix and a good first change in a file you are already touching.

# Adding a program

A new tax incentive program is added by **data**: a registry entry plus a rule pack (and a year pack per authored tax year),
with no engine code change when it uses the supported models. Design: [ADR-013](ADR-013-program-registry.md). Statute rules:
[ADR-005](ADR-005-year-versioned-rules.md).

## Where things live

| What | Where |
|---|---|
| The registry (one entry per program) | `backend/rules/registry/programs.json`, or `PROGRAM_REGISTRY_FILE` |
| The program's base pack | `backend/rules/<code-prefix>_<credit>.json`, or under `RULES_DIR` |
| A year pack (the statute for one tax year) | `backend/rules/<program>/<year>.json` |
| The old lookups | `STATE_TO_PACK`, `PROGRAM_CODE_TO_PACK` in `tools/credit_math.py` are views over the registry |

The stored `lifecycle` is `draft`, `described` or `retired`. **`calculable` is never typed**: a program is calculable exactly when
at least one year pack is authored. A program with none is *described, not calculable* and is declined by name.

## Rules that do not bend

- **Statute is never invented and never inherited across years.** A year pack is complete on its own; a year that is not authored
  is "not authored", never an estimate from a neighbour. [ADR-005]
- **Every new value is unverified until a person verifies it.** Packs carry `_prototype_verify` flags; the portal and the API say
  "not verified". Nothing in the product asserts that a program's values are legally correct.
- **Nothing activates statute at runtime.** A database row or a portal action cannot change what the engine prices; a year pack
  arrives through a reviewed commit.

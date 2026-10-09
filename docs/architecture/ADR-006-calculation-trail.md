# ADR-006 — The calculation trail is regenerated on demand, not warehoused

> **Schema v2.0 (Platform v2):** the Warehouse schemas are now `tcc_gold` and `tcc_ops` (were the v1 `flex_*` schemas), configurable via `GOLD_SCHEMA` / `OPS_SCHEMA`. See `docs/data/schema/tcc-schema.fabric.sql`.

**Date** 2026-09-10 · **Status** Proposed — needs a decision before any code

## Context

Every figure the engine produces carries its derivation:
`{step, inputs, formula, output, citation}`, hashed with SHA-256 over the whole
trail. `tools/trail.py` holds the `ContextVar` recorder, and
`docs/architecture/CALCULATION-PROVENANCE.md` describes the shape.

**Nothing persists it.** The recorder collects during a run and the rows are
discarded when the process moves on. Two things are blocked by that:

- **The per-client evidence pack.** The pack is sealed to the certified
  reference run because that is the only place a trail survives long enough to
  render. Every other client gets a view that names what it cannot show.
- **`get_employee_drill` cannot become a Gold read.** It is the last per-client
  view still resolving through payroll, for the same reason.

Both were listed as follow-ups when the read paths moved to Gold
(`984c33a`, `2d53486`). This ADR is the decision they were waiting on.

## The obvious answer does not survive contact with the capacity

The obvious answer is a `tcc_gold.calculation_step` table keyed
`(run_id, record_token, step_id)`, written by the run alongside the other
employee-grain tables.

The volume rules it out on the current SKU:

| Grain | Rows |
| --- | --- |
| One client-year, one method | 10,236 employees × ~10 steps ≈ **102k** |
| One client-year, both methods | ≈ **205k** |
| The book — 5 clients × 6 years | **millions** |

Candle Bottle alone already takes **68 minutes** to rebuild on F2 at the
*current* Gold grain, which is roughly 10k employee rows per method. Adding an
order of magnitude to the write path does not produce a slow rebuild; it
produces one that cannot be run during a working day, on the same capacity where
a `TOP 1` against a seven-row table costs ~342 ms.

Worse, almost none of it is ever read. A trail is requested for **one employee**,
for **one claim**, when somebody disputes a number or an authority asks. Writing
millions of rows to serve a handful of lookups inverts the cost.

## Decision (proposed)

**Regenerate the trail on demand for a single employee, and prove it matches the
verdict Gold recorded.**

1. `run_client_calculation` continues to write no trail.
2. An evidence request for `(client, programme, year, record_token)` resolves
   that client-year, replays the certified method **for that employee alone**,
   and renders the recorded steps.
3. The regenerated verdict is compared against `employee_eligibility.eligible`.
   A mismatch is an error, not a footnote — it means the inputs moved since the
   run, which is exactly what an evidence pack exists to detect.
4. The run's `calculation_id` — already a hash over client, programme, year,
   window, floors, assumption ids and a payroll digest — is what ties the
   regenerated trail to the run it claims to explain.

### Why this is defensible rather than merely cheaper

Determinism is the property the whole engine is built on, and the parity gate
proves it daily: the same payroll, statute and assumptions yield 10,236 / 539 /
656 every time. A trail regenerated from those same three inputs **is** the
trail the run produced. Storing it would not make it truer.

What storage would add is protection against the inputs having *changed* — and
that is precisely what step 3 detects and step 4 identifies, without a row.

## Consequences

- The evidence pack becomes per-client without a schema change or a backfill.
- `get_employee_drill` can drop its payroll dependency for everything except the
  trail itself, which is the one thing that genuinely needs the rows.
- **A trail cannot be produced for a run whose payroll has since been corrected.**
  This is a real limit and must surface as a stated refusal, not a silent
  regeneration under new inputs. `calculation_id` is the discriminator.
- A single-employee replay still costs a payroll read for that client-year. On
  F2 that is seconds, not minutes, and it happens on request rather than on
  every write.

## What would reverse this

Either of:

- **An authority requires the trail to be immutably retained** rather than
  reproducible. That is a records-retention requirement, not a performance one,
  and no amount of determinism answers it.
- **The capacity stops being the constraint.** At F64 the write cost argument
  weakens considerably; the "almost none of it is ever read" argument does not.

## Open

- Retention is a question for the partner and is **not answered here**. If
  the partner's own audit posture requires stored derivations, this ADR is wrong
  and the table is the answer regardless of cost.
- The single-employee replay path does not exist yet. It is the only new code
  this decision requires.

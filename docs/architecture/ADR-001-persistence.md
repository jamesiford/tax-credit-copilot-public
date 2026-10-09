# ADR-001 — SQLite for decision state; the engine stays pure

**Date** 2026-08-25 · **Status** **Superseded in part by
[ADR-002](ADR-002-production-persistence.md)** · **Supersedes** the "No databases"
rule in `.github/copilot-instructions.md`

> **Superseded the same day.** This ADR was decided while the project was
> explicitly a prototype. Hours later the goal changed to a production build, and
> the *default store* decision below no longer holds: the operational store is
> Cosmos DB, with SQLite retained as the local-dev and CI adapter behind the same
> port. See [ADR-002](ADR-002-production-persistence.md).
>
> **What survives unchanged, and is the reason this ADR was still worth making:**
> the repository seam, and the rule that `backend/tools/` never learns a database
> exists. Both are load-bearing in the production design. The reasoning in §
> *Context* below — why in-memory registries holding human judgements are
> untenable — is also unchanged and is the argument for ADR-002.
>
> **The registry table below is a snapshot of 25 Aug, not of today.** Four of
> the modules it names were removed in the 30 Aug production cleanup:
> `api/eligibility.py`, `api/filing.py` and `data/alerts.py` were unreachable
> surfaces and are gone outright; `api/negotiated.py:_OVERRIDES` survives as
> `tools/negotiated.py`, still in memory and still making this ADR's point.

## Context

`.github/copilot-instructions.md` said: *"No databases — in-memory + JSON rule
packs + CSV payroll + Python list registries only. Cosmos DB is the Stage-2
production move."*

That was right for a demo prototype and wrong for what the product became. Ten
module-global registries now hold mutable state, and six of them hold **human
judgements recorded against a tax calculation**:

| Registry | Holds |
| --- | --- |
| `api/ingestion.py:_QC_RESOLUTIONS` | How a data-quality exception was dispositioned |
| `api/onezero.py:_EMPLOYEE_REVIEWS` | Whether an employee's eligibility was accepted or overridden |
| `api/eligibility.py:_RULE_VERIFICATION` | Who signed off a rule pack |
| `api/filing.py:_FILING_STATUS` | Whether a claim was filed |
| `api/negotiated.py:_OVERRIDES` | Negotiated commercial terms |
| `data/alerts.py:_ALERT_WORKFLOW` | Who acknowledged or resolved an alert |

"Who decided this, when, and on what basis" is the first question an auditor
asks. Today the answer is lost on restart and diverges across workers.

Three forces made the rule untenable:

1. **Audit.** The product's claim is that every number traces to a rule, a tool
   call and a trail row. A disposition that vanishes breaks that chain.
2. **Tenancy.** Isolation enforced by a Python `if` is a filter. Isolation
   enforced by `NOT NULL tenant_id` plus foreign keys is a boundary. F2 needs
   the second kind.
3. **Correctness under load.** Module globals do not survive `uvicorn --workers
   2`. Two requests can already see different state; nothing warns.

## Decision

**Adopt SQLite** for decision state, behind a repository layer.

**Reject Cosmos DB** for now. It requires credentials, breaks local dev and CI,
and buys nothing at this stage. The repository seam makes it a later swap.

### What moves to SQLite

Human decisions and their lifecycle: QC dispositions, employee reviews, rule
verifications, filing status, negotiated overrides, alert workflow, manual
claims, saved scenarios, agent proposals, the client registry, source snapshots,
and calculation run manifests.

Each row carries `tenant_id`, actor, timestamp and — where it bears on a
calculation — the assumption set and rule-pack version in force.

### What does NOT move

| Stays as it is | Why |
| --- | --- |
| Rule packs (`rules/*.json`) | Versioned, reviewable, diffable artifacts. A database would make statutory change harder to audit, not easier. |
| Assumption sets (`docs/data/*.json`) | Immutable published artifacts. Same reasoning. |
| Payroll (CSV / Fabric) | External source of record. The app reads it, never owns it. |
| **`backend/tools/` — the calculation engine** | **Stays pure.** See below. |

### The constraint that matters

**`tools/` must never import a repository, open a connection, or know a database
exists.** It stays pure functions over lists of dicts.

This is not architectural taste. It is what makes `test_engine_parity_reference.py`
possible: the certified engine is testable precisely because it has no
environment. Introduce a database call inside `run_pay_period_method` and the
parity gate becomes an integration test that needs fixtures, and the thing that
protects the partner reconciliation gets slower and more fragile.

Repositories live at the API layer. They read state, hand plain rows to `tools/`,
and write results back.

## Consequences

**Good.** Decisions survive restart and are queryable. Tenancy is enforceable in
the schema. Concurrency is real rather than accidental. No new infrastructure:
`sqlite3` is stdlib, the database is a gitignored file, CI is unchanged.

**Costs.** A migration mechanism is now needed, however small. The repository
layer is indirection that must be kept thin. SQLite's write concurrency is
limited — fine at prototype scale, and the signal to move to Postgres or Cosmos
when it is not.

**Explicitly deferred.** Postgres or Cosmos, connection pooling, read replicas.
Revisit when a real deployment target exists (§11 of the handoff spec).

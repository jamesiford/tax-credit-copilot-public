# ADR-003 — Clean Architecture, CQRS and the mediator pipeline

**Date** 2026-08-25 · **Status** Accepted · **Partially implemented**

> ## Where this actually stands — read before the rest
>
> An ADR describes a decision, and a reader who has just cloned the repository
> will reasonably assume it describes the code. Here is the difference, as of
> 2026-08-28:
>
> | | State |
> | --- | --- |
> | `domain/` — entities, ports, pure calculation | **Built.** `domain/claims.py` plus `domain/calculation/` (the One/Zero engine, headcount, proximity, the derivation trail) |
> | `infrastructure/` — adapters behind ports | **Built.** SQLite claim and finding repositories; payroll source adapters |
> | `application/` — use cases, commands, queries | **Built.** Mediator, wiring, first vertical slice |
> | CQRS mediator | **Built.** `application/mediator.py`; explicit registration in `application/wiring.py` |
> | Composition root | **Built.** `application/wiring.py` owns `get_claim_repository` and `get_finding_repository`. They lived in `api/claims.py` and `api/findings.py` until 30 Aug, which meant every handler imported a router to find its own store |
> | Thin routers | **One done** (`api/proximity.py`). The other twelve routers still call compute directly |
> | Warehouse adapters (ADR-007) | **Built.** `warehouse_claims.py` and `warehouse_findings.py` write to `tcc_ops` in the Fabric Warehouse, the only operational store; every statement goes through `tenant_sql.py` |
>
> **The layering is enforced, not merely asserted.**
> `backend/tests/test_architecture.py` fails the build when the domain does I/O,
> when a dependency points outward, when the application layer imports a web
> framework, or when a statutory quantity acquires a second implementation. Two
> of those rules found real defects on their first run.
>
> Two rules were added on 30 Aug after the audit found violations neither
> covered: `test_domain_does_not_import_tools` (the domain was reaching into
> `tools/` for `StatutoryFloors`, now in `domain/calculation/floors.py`) and
> `test_application_does_not_import_a_router`. The second carries a single
> named allowance, `api/_assess.py` — an application service still filed under
> `api/` because it depends on `api/_payperiods.py`, a payroll reader that
> raises `HTTPException`. Moving that pair is the next step of this migration.
>
> Migration is deliberately incremental. Each router moves behind the mediator
> only with the parity gate green — the certified figures (10,236 / 539 / 656)
> are the acceptance test for every step, because this refactor must not be able
> to change a filed number.

## Context

The backend has four packages that grew by accretion: `api/` (58 route
decorators, some 44 KB in a single module), `tools/` (calculation plus file I/O
plus HTTP), `data/` (fixtures, in-memory registries and generators), and
`agents/`. The layering is *nearly* right by accident rather than by rule, and it
has started to leak:

- `tools/portfolio.py` imports `api/_payperiods.py` — the domain reaching into
  presentation.
- `tools/credit_math.py` reads JSON from disk — infrastructure inside the domain.
- `tools/designation.py` and `tools/opportunity.py` import from `data/`.
- Business rules, HTTP concerns and persistence sit in the same route functions.

One thing, however, is right and must be protected: **`tools/onezero.py` — the
certified calculation engine — is pure.** Its only imports are the standard
library and one sibling module. That purity is why
`tests/test_engine_parity_reference.py` is a fast unit test, and that test is the
only thing standing between a refactor and a silently broken partner
reconciliation.

## Decision

Adopt Clean Architecture with four layers, and CQRS with a mediator for the
application layer.

### Layers

```
presentation/     FastAPI routers, request/response models, SSE.
                  Thin: validate, dispatch to the mediator, serialise.
        │ depends on
        ▼
application/      Commands, queries, their handlers, pipeline behaviours.
                  Orchestrates. Contains no statutory rule and no SQL.
        │ depends on
        ▼
domain/           Entities, value objects, the calculation engine, ports.
                  Pure. Stdlib only. No I/O, no framework, no async.
        ▲
        │ implements ports
infrastructure/   Fabric Warehouse, Fabric Lakehouse, Foundry/MAF, Entra,
                  rule-pack loading, file system, HTTP.
```

Dependencies point inward. `domain/` imports nothing from the other three.
`infrastructure/` implements interfaces the domain declares and is wired in at
composition root.

### Target package map

| Now | Becomes | Note |
| --- | --- | --- |
| `tools/onezero.py` | `domain/calculation/onezero.py` | **Moved verbatim.** No edit. |
| `tools/trail.py` | `domain/calculation/trail.py` | Moved verbatim |
| `tools/credit_math.py` | Split: benefit math → `domain/calculation/`, pack loading → `infrastructure/rulepacks/` | `StatutoryFloors` has moved to `domain/calculation/floors.py`; the rest is still here |
| `tools/reference_*.py` | `domain/calculation/reference/` | The parity harness |
| `tools/simulation.py` | Scenario evaluation → `domain/`, orchestration → `application/` | |
| `tools/portfolio.py` | `application/queries/` | It composes; it does not calculate |
| `tools/fabric_source.py`, `webiq.py` | `infrastructure/` | I/O adapters |
| `data/*.py` registries | `infrastructure/persistence/` | Behind ports (ADR-002) |
| `data/generate_*.py` | `tools/fixtures/` | Dev scripts, not runtime |
| `agents/` | `infrastructure/agents/` | Foundry/MAF adapters |
| `api/*.py` | `presentation/routers/` | Thin |

### CQRS

Commands change state and return an identifier or nothing. Queries read and
return data. They do not share models.

This is not decoration in this domain. **Every write in this product is a
decision recorded against a number that lands on a filed tax return.** A
disposition, a rule sign-off, a filing, an override, a proposal approval — each
must carry actor, timestamp, tenant, and the rule and assumption versions in
force. Modelling writes as explicit command objects makes that requirement
structural rather than a convention every route author must remember.

```
application/
  commands/
    resolve_qc_exception.py      ResolveQcException      + handler
    review_employee.py           ReviewEmployee          + handler
    verify_rule_pack.py          VerifyRulePack          + handler
    set_filing_status.py         SetFilingStatus         + handler
    save_scenario.py             SaveScenario            + handler
    decide_proposal.py           DecideProposal          + handler
  queries/
    get_eligibility.py           GetEligibility          + handler
    get_headcount.py             GetHeadcount            + handler
    rank_opportunities.py        RankOpportunities       + handler
    get_evidence_pack.py         GetEvidencePack         + handler
```

One file per use case, named for the use case. A reader looking for "what
happens when an analyst overrides an employee" opens
`review_employee.py` and finds all of it.

### The mediator and its pipeline

A small hand-written mediator — roughly 120 lines, `Protocol`-typed, no
dependency. Python has no MediatR and does not need one; what earns its place is
not the dispatch but the **pipeline**:

```
Request
   │
   ├─ ValidationBehaviour        shape and business-rule preconditions
   ├─ AuthorizationBehaviour     principal → tenant membership, persona, site scope
   ├─ TenantScopeBehaviour       resolve and inject the CalculationContext
   ├─ AuditBehaviour             record actor, timestamp, rule + assumption versions
   ├─ TransactionBehaviour       commands only; commit or roll back
   ├─ TelemetryBehaviour         span per use case, into App Insights
   │
   └─ Handler                    the use case itself, now free of all the above
```

Behaviours run for every command, uniformly. **The audit and authorization
guarantees stop depending on the diligence of whoever writes the next route.**
That is the whole argument; if the pipeline did not give us that, a mediator in
Python would be ceremony.

Queries skip `TransactionBehaviour` and `AuditBehaviour` — reads are not
decisions.

### Testing consequence

Handlers take ports by constructor injection, so a handler test needs no
FastAPI, no Warehouse and no network. Domain tests need nothing at all. The parity
gate stays a pure unit test, which is the point.

## The constraint that governs the migration

**`domain/calculation/onezero.py` is moved, never edited.** The certified engine
reproduces 10,236 employees, 539 Min-Max and 656 Pay Period on the partner's reference
dataset. A Clean Architecture migration is precisely the kind of change that can
break that silently — a helpfully "tidied" rounding call or a re-ordered filter
would do it.

Migration protocol, and it is not negotiable:

1. Move one module. Do not modify it in the same commit.
2. Run `pytest tests/test_engine_parity_reference.py` with
   `TCC_REQUIRE_PARITY=1`.
3. Run `python -m tools.verify_reference_independent` — the independent
   re-derivation, 17/17.
4. Commit.
5. Only then, if the module needs changing, change it in a separate commit.

If the parity gate goes red during a migration step, the migration is wrong.
Never adjust the pinned constants.

## Consequences

**Good.** Business rules become testable without a web framework or a database.
Audit and authorization are structural. The infrastructure choices in ADR-002
become swappable. `api/onezero.py` at 44 KB becomes a set of named use cases.

**Costs.** More files, and more indirection between a route and the work. That
trade is worth making here because the alternative — cross-cutting audit rules
enforced by convention — fails silently and on a tax return.

**Risk.** The migration itself. Mitigated by the protocol above and by the fact
that the highest-value module is already pure and therefore moves untouched.

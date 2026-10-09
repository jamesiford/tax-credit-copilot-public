# Target architecture

**Date** 2026-08-25 · **Status** Accepted direction · **Supersedes** the
prototype posture throughout

The project moved from prototype to production build on 25 August 2026. This
document is the target state. Five ADRs carry the reasoning:

| ADR | Decision |
| --- | --- |
| [ADR-001](ADR-001-persistence.md) | SQLite for decision state *(superseded in part; the seam survives)* |
| [ADR-002](ADR-002-production-persistence.md) | Production stores + SQLite-for-dev, behind ports *(§1 superseded by ADR-007)* |
| [ADR-003](ADR-003-clean-architecture-cqrs.md) | Clean Architecture, CQRS, mediator pipeline |
| [ADR-004](ADR-004-agentic-workflows.md) | MAF workflows, checkpointed HITL, numeric-integrity middleware |
| [ADR-007](ADR-007-warehouse-operational-store.md) | Fabric Warehouse as the only operational store; the document store retired |

---

## 1. What is non-negotiable

Everything below serves one constraint: **these numbers land on a filed tax
return.** A wrong number is not a degraded experience, it is an amended return
and a penalty.

Four rules follow, and no architectural convenience overrides them.

1. **The certified engine is inviolable.** `onezero.py` reproduces 10,236
   employees, 539 Min-Max and 656 Pay Period on the partner's reference dataset. It
   moves during the restructure; it does not change. The parity gate proves it
   after every step.
2. **Tools calculate. Agents narrate — and are checked.** Agents hold no tools.
   Additionally, every numeric claim an agent makes is validated against the
   canonical fact before it reaches a human (ADR-004 §3).
3. **The agent proposes, the human disposes.** No agentic action commits state.
   Approval is a durable, attributable record.
4. **Statute is data, and data is versioned.** Rule packs and assumption sets
   are git artifacts. Step-1 v8 is the runnable set; v1–v7 are retired history
   (ADR-005) and raise if loaded.

---

## 2. System shape

```
                     ┌──────────────────────────────────────┐
                     │  Entra ID                            │
                     │  users · app roles → personas        │
                     │  groups → tenant membership          │
                     └───────────────┬──────────────────────┘
                                     │ OIDC
┌────────────────────────────────────▼─────────────────────────────────┐
│  PRESENTATION            React SPA  ·  FastAPI routers  ·  SSE       │
│                          thin: validate → dispatch → serialise       │
└────────────────────────────────────┬─────────────────────────────────┘
                                     │ mediator.send(command | query)
┌────────────────────────────────────▼─────────────────────────────────┐
│  APPLICATION             commands · queries · handlers               │
│                                                                       │
│    pipeline:  Validation → Authorization → TenantScope →             │
│               Audit → Transaction → Telemetry → Handler              │
└──────────┬──────────────────────────────────────────┬────────────────┘
           │ calls                                    │ runs
┌──────────▼──────────────────────┐   ┌───────────────▼────────────────┐
│  DOMAIN                          │   │  MAF WORKFLOWS                 │
│                                  │   │                                │
│  ► onezero.py   CERTIFIED, PURE  │   │  WorkflowBuilder graphs        │
│    credit math, scenarios        │   │  checkpointed HITL             │
│    entities, value objects       │   │  middleware:                   │
│    PORTS (Protocol, no impl)     │   │    NumericIntegrity            │
│                                  │   │    PromptInjection             │
│  stdlib only. no I/O.            │   │    TenantScope · Cost          │
└──────────▲───────────────────────┘   └───────────────┬────────────────┘
           │ implements                                 │
┌──────────┴────────────────────────────────────────────▼────────────────┐
│  INFRASTRUCTURE                                                        │
│                                                                        │
│   Fabric Warehouse   Fabric Lakehouse       Foundry            Entra   │
│   tcc_ops            bronze→silver→gold     PromptAgents       MI      │
│   client_id bound    payroll · outputs      gpt-5.4-mini               │
│   claims             Power BI reads                                    │
│   engagements                                                          │
│   findings, runs     SQLite (dev/CI)        rule packs (git)           │
│   snapshots                                                            │
└────────────────────────────────────────────────────────────────────────┘
```

Dependencies point inward. Infrastructure implements ports the domain declares.
Nothing above infrastructure names the Warehouse, the Lakehouse, Foundry or Entra.

---

## 3. Identity and tenancy

| Concern | Mechanism |
| --- | --- |
| User authentication | Entra ID, OIDC, PKCE from the SPA |
| Persona | Entra **app role** → the four personas in `PERSONAS.md`. Server-side, not browser state. |
| Tenant membership | Entra **group** claim → `principal_tenants`. Server-derived; `X-Tenant-Id` is never trusted. |
| Site scope | Directory attribute or claim → enforced server-side on every per-employee and per-site read |
| Service-to-service | User-assigned Managed Identity, `DefaultAzureCredential`. No keys, no connection strings. |
| Data-plane authorization | Fabric workspace roles and Warehouse T-SQL grants on the same MI |

Requesting a tenant you are not a member of returns **403, not 404** — a 404
leaks whether the tenant exists.

The tenant predicate is the second line of defence. Application-layer scoping can
be forgotten; `tenant_sql.py` binds `client_id` as the first predicate of every
Warehouse statement, so a query cannot be issued without it, and the one
cross-client read takes an explicit, logged `tenant_exempt(reason)` path.

---

## 4. Data flow

```
Client payroll
    │
    ▼
BRONZE   raw, immutable, partitioned by client + load date
    │        tokenisation happens at this boundary — no PII proceeds
    ▼
SILVER   canonical Silver Record Layout, deduplicated, QC-flagged
    │
    ├──────────────▶ QC exceptions ──▶ exception_triage workflow
    │                                        │
    │                                   proposals (tcc_ops)
    │                                        │
    │                                   human disposition
    │                                        │
    ▼                                        ▼
CALCULATION (domain)  ◀── accepted source snapshot ──┘
    │  fiscal window + rule pack + assumption set,
    │  all resolved from the CalculationContext
    ▼
GOLD     employee-grain and unit-grain outputs, run manifest
    │
    ├──▶ portal
    ├──▶ Power BI
    └──▶ evidence pack ──▶ evidence_authoring workflow ──▶ auditor memo
                                    │
                          NumericIntegrityMiddleware
                          (every figure checked against the trail)
```

Every calculation writes a **run manifest**: tenant, source snapshot hash,
assumption set id, rule pack versions, engine commit, timestamp, actor. A run is
replayable from its manifest. This is what makes "why did this number change
between March and April" answerable.

---

## 5. Migration path

Five stages. The certified engine and the parity gate survive every one.

### Stage 1 — Foundations *(largely specified already)*

Identity, ports, persistence adapters, capability badge. Sequencing is tracked
internally — see §7 for how the production decisions changed it.

### Stage 2 — Layer separation

Introduce `domain/`, `application/`, `infrastructure/`, `presentation/`. Move
modules per the map in ADR-003. Fix the three known layering violations:
`portfolio.py → api/`, `credit_math.py` disk reads, `designation.py`/
`opportunity.py → data/`.

**Protocol per move:** move verbatim → parity gate → independent verifier →
commit. Change nothing in a move commit.

Add an import-linter rule to CI so a violation fails the build rather than being
discovered later.

### Stage 3 — CQRS

Mediator and pipeline behaviours. Convert routes to commands and queries, one
use case at a time, keeping HTTP contracts byte-identical so the frontend does
not move. Audit and authorization become structural.

### Stage 4 — Production stores

Warehouse adapters behind the ports ([ADR-007](ADR-007-warehouse-operational-store.md));
Fabric medallion layers behind `PayrollReader`. One contract test suite runs
against both the SQLite and Warehouse adapters, so the dev adapter cannot
silently drift from the production one.

### Stage 5 — MAF workflows

Workflows replace the keyword router, with it retained as a fallback.
`NumericIntegrityMiddleware` first — it gates F5.6 and is the one that turns a
claim into a mechanism.

---

## 6. Engineering standards

Applies to everything written from here.

**Structure.** One use case per file, named for the use case. Handlers do one
thing. Ports name capability, never technology. No module over ~400 lines
without a reason recorded in its docstring.

**SOLID, concretely in this codebase.**

- *Single responsibility* — a handler orchestrates one use case; the calculation
  is in the domain; persistence is in an adapter.
- *Open/closed* — a new state is a rule pack plus an evaluator, not an edit to
  `credit_math`. A new cross-cutting concern is a behaviour, not an edit to
  every handler.
- *Liskov* — the SQLite and Warehouse adapters pass the same contract tests.
- *Interface segregation* — `PayrollReader` and `DecisionRepository` are separate
  ports because nothing needs both.
- *Dependency inversion* — handlers take ports by constructor; the composition
  root wires the implementations.

**DRY, with a caveat.** Deduplicate logic, not coincidence. Two statutes that
currently compute the same way are not one rule — Georgia and Tennessee looking
alike today does not make them the same rule tomorrow. Rule-pack data stays
separate even when values coincide.

**Comments.** Explain *why*, and cite the source. The existing engine is the
standard to match:

```python
# BA-11. One Zero Min Max.docx Step 2: "count the number of days between the
# two and divide by 7" - no inclusive-day adjustment, so a full-year weekly
# employee lands on 51.86 weeks rather than 52.00. Confirmed against the
# partner's reported weeks for eight of the nine employees the partner detailed.
```

A reader six months from now needs to know that the missing `+1` is deliberate
and where it came from. Do not comment what the code already says.

**Tests.** Domain tests need nothing. Handler tests need fakes, not a database.
Contract tests run against every adapter. The parity gate runs fail-closed in CI.

---

## 7. What this changes about existing plans

| Document | Status |
| --- | --- |
| [`ADR-001`](ADR-001-persistence.md) | Superseded in part. Seam survives; SQLite becomes the dev adapter. |
| Task sequencing | **Needs revision.** Persistence becomes ports-plus-two-adapters; authentication becomes real Entra rather than a dev provider; new tasks for layering and the mediator. Tracked internally. |
| [`ENGINE-CONVERGENCE.md`](ENGINE-CONVERGENCE.md) | Unaffected. Phase 3 (retire the duplicate reference modules) folds into Stage 2. |
| `.github/copilot-instructions.md` | **Needs revision** — persistence, layering and agentic sections. |

---

## 8. Open questions

1. **Which Azure tenancy and subscription?** Everything below depends on it:
   Entra app registration, Fabric capacity and Warehouse, Foundry project.
2. **Who owns the Fabric capacity for production?** Dev currently borrows
   `fabvalcdemowestus3` (F2) from `rg-valc-demo-eastus`, shared with other demos
   — fine for development, unacceptable for real client payroll, since another
   demo pausing it takes the application down. Production needs its own capacity,
   sized for the medallion layers. Does the partner's existing OneLake serve, or do
   we provision?
3. **Does the partner's real payroll extract share the defects in the demo
   lakehouse?** The current `dbo/employees` carries PII in the calculation
   source, currency as formatted strings (`'$2,061.19 '`), dates as ambiguous
   `M/D/YYYY`, one wide table doing three jobs, and no tenant column
   ([audit](../data/LAKEHOUSE-SCHEMA-AUDIT.md)). If the real feed is typed and
   tokenised, most of that is a demo-fixture artefact. If it is not, the
   Bronze → Silver transformation is materially larger and Stage 4 grows.
4. **Data residency and retention.** Payroll for tax filing has statutory
   retention; what applies, and does it constrain region?
5. **Does the partner's identity provider federate**, or do client users live in our
   tenant?
6. **Warehouse load on the capacity.** Operational reads and writes now share
   the Fabric capacity with the medallion layers; production sizing needs a number.
7. **Who signs off a rule-pack change** proposed by the ingestion workflow? This
   is a governance answer, not a technical one, and it gates F5.4 and F5.5.

# ADR-002 — Production persistence: Cosmos, Fabric, and ports

> **Superseded in part by [ADR-007](ADR-007-warehouse-operational-store.md)
> (2026-10-08).** §1 below — Cosmos DB as the operational store — no longer
> holds: Cosmos is retired and the Fabric Warehouse (`tcc_ops`) is the only
> operational store. The ports-and-adapters decision and the analytical store
> stand. Kept unedited as the record of what was decided and why.

**Date** 2026-08-25 · **Status** Accepted · **Supersedes in part**
[ADR-001](ADR-001-persistence.md)

## Context

ADR-001 chose SQLite because the project was a prototype. The goal is now a
production build. Three requirements arrive with that change, none of which
SQLite satisfies on its own:

1. **Tenant isolation as an infrastructure property, not application code.** A
   `WHERE tenant_id = ?` that someone can forget is not a boundary.
2. **Payroll at real scale.** The partner's reference dataset alone is 488,968 raw
   rows for one client-year. A book of clients across multiple years is an
   analytics workload, not an OLTP one.
3. **Durable, queryable audit.** Every decision on a filed return must be
   retained, attributable and immutable.

The argument in ADR-001 for *why* the in-memory registries are untenable stands
unchanged. Only the choice of store changes.

## Decision

**Three stores, each with a distinct job. One port interface per concern, so the
domain never names any of them.**

### 1. Cosmos DB (NoSQL API) — the operational / decision store

Holds: the client registry, decisions (QC dispositions, employee reviews, rule
verifications, filing status, overrides, alert workflow), agent proposals,
saved scenarios, source-snapshot manifests, and calculation run manifests.

Why Cosmos rather than Postgres:

- **The partition key is the tenant boundary.** Partitioning on `/tenantId`
  makes cross-tenant reads a physically different partition, not a forgotten
  predicate. Combined with per-tenant authorization this gives defence in depth.
- **Change feed drives the agent activity feed.** F5.1 needs "what have agents
  done, what are they proposing" as a live stream. The change feed is that,
  natively, without polling or a message bus.
- **TTL for transient state.** Draft scenarios and superseded proposals expire
  without a reaper job.
- **Schema flexibility where it is genuinely wanted.** Proposal payloads differ
  by proposal type; forcing them into a relational schema buys nothing.

Cost control: serverless for non-production environments, provisioned autoscale
in production.

### 2. Microsoft Fabric Lakehouse — payroll and analytics

Holds: raw payroll, canonical payroll, calculation outputs at row grain, and
anything Power BI reads.

Medallion layout, as already planned:

| Layer | Contents |
| --- | --- |
| Bronze | Raw client payroll exactly as received, immutable, partitioned by client and load date |
| Silver | Canonical Silver Record Layout, tokenised, deduplicated, QC-flagged |
| Gold | Calculation outputs at employee and unit grain, plus the aggregates Power BI and the portal read |

`backend/tools/fabric_source.py` and `DATA_SOURCE=fabric` already read a
Lakehouse Delta table via `deltalake`. That is the seam; it needs the medallion
layers behind it and tokenisation enforced at the Bronze → Silver boundary.

**Design Silver from the certified calculation, not from the existing table.**
The current `dbo/employees` is a pre-reconciliation demo fixture carrying PII,
formatted-string currency, ambiguous string dates and no tenant column. It is
Bronze at best. See [`LAKEHOUSE-SCHEMA-AUDIT.md`](../data/LAKEHOUSE-SCHEMA-AUDIT.md)
for the full gap list.

### 3. SQLite — local development and CI

Retained deliberately, behind the same port. Not a fallback and not technical
debt:

- CI must not need a Cosmos account or credentials to run 443 tests.
- The reference parity gate must stay a fast unit test. If it required Cosmos it
  would become an integration test, and the gate that protects the partner
  reconciliation would get slower and more fragile — the exact outcome ADR-001's
  purity rule exists to prevent.
- A developer offline on a plane should be able to run the whole suite.

The SQLite adapter is a first-class implementation of the port and is tested
alongside the Cosmos one with the same contract test suite.

### What stays out of every database

| Artifact | Where | Why |
| --- | --- | --- |
| Rule packs (`backend/rules/*.json`) | Git | Statutory change must be diffable, reviewable and attributable to a commit and an approver. A database row is a worse audit artifact than a pull request. |
| Assumption sets (`docs/data/reference-*.json`) | Git | Immutable published artifacts. Step-1 v1–v7 are retired and no longer runnable (ADR-005); they remain as the record of how the method was reconciled. |
| Prompts and agent instructions | Git | Same reasoning: a prompt change is a behaviour change and belongs in review. |

## The port boundary

```
domain/            defines the port      (Protocol, no implementation)
     ↑
application/       depends on the port   (handlers take it by constructor)
     ↑
infrastructure/    implements the port   (CosmosDecisionRepository,
                                          SqliteDecisionRepository,
                                          FabricPayrollReader, ...)
```

Ports are `typing.Protocol` classes in the domain layer. They name **capability**,
never technology: `DecisionRepository`, `PayrollReader`, `RulePackSource`,
`ProposalStore`. There is no `CosmosDecisionRepository` type visible above the
infrastructure layer, and no `import azure.cosmos` outside it.

**The constraint from ADR-001 is retained verbatim and strengthened:** the
calculation engine imports nothing but the standard library and its own siblings.
It receives plain rows and returns plain results. It has no idea any of this
exists.

## Consequences

**Good.** Tenant isolation is enforced by partition, not predicate. The change
feed gives the agent activity feed for free. Payroll scales as an analytics
workload. CI stays fast and credential-free. Swapping a store is an
infrastructure change, invisible above that layer.

**Costs.** Two adapters per port, kept honest by one shared contract test suite.
Cosmos costs money in a way SQLite did not — mitigated by serverless outside
production. Cosmos has no cross-partition transaction, so any operation spanning
tenants must be modelled as a saga; in practice nothing in this domain legitimately
spans tenants, and a design that needs to is probably wrong.

**Explicitly deferred.** Read replicas, multi-region write, and a separate
read-model projection. Revisit when there is load to justify them.

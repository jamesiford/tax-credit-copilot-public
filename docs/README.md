# Documentation

Reference material for engineers deploying, extending, or reviewing this
system. Internal planning documents — roadmaps, call briefs, stakeholder
positioning — are deliberately not in this repository.

Start with the [root README](../README.md) for what the system does and how to
run it.

---

## Architecture

Decisions that constrain the code. Each ADR records what was decided, what was
rejected, and what would change the decision — so a reader can disagree
precisely rather than in general.

| | |
| --- | --- |
| [TARGET-ARCHITECTURE.md](architecture/TARGET-ARCHITECTURE.md) | Where the system is going, and how far along it is. **Read this before the ADRs** — it is honest about what is built versus specified. |
| [ADR-001](architecture/ADR-001-persistence.md) | Original persistence choice |
| [ADR-002](architecture/ADR-002-production-persistence.md) | Ports with interchangeable adapters, SQLite for dev and CI, one contract suite over all. **Superseded in part** (§1, the production store) by ADR-007 |
| [ADR-003](architecture/ADR-003-clean-architecture-cqrs.md) | Clean Architecture and CQRS. **Partially applied** — see TARGET-ARCHITECTURE for the current state |
| [ADR-004](architecture/ADR-004-agentic-workflows.md) | Where agents are allowed to act, and where they may only narrate |
| [ADR-005](architecture/ADR-005-year-versioned-rules.md) | Statute frozen per tax year, so a historical run replays exactly. This is what makes a retroactive audit defensible |
| [ADR-007](architecture/ADR-007-warehouse-operational-store.md) | The Fabric Warehouse is the only operational store; the document store is retired. Every statement is tenant-bound on `client_id` |
| [CALCULATION-PROVENANCE.md](architecture/CALCULATION-PROVENANCE.md) | How every figure traces back to its inputs, formula and citation |
| [DEPLOYMENT-HANDOVER.md](architecture/DEPLOYMENT-HANDOVER.md) | How to deploy: prerequisites, the two profiles, `azd up`, the CI path, verification and teardown |
| [ENGINE-CONVERGENCE.md](architecture/ENGINE-CONVERGENCE.md) | How two independent implementations were reconciled to the same figures |

## Platform (v2)

How the system is hosted, connected and run. Read the C4 model first.

| | |
| --- | --- |
| [C4 architecture](architecture/c4/TaxCreditCopilot_v2_Architecture.html) | Interactive context, container and component views, with status after Phase A ([model](architecture/c4/model.json)) |
| [FLOW-v2.md](architecture/FLOW-v2.md) | The end-to-end flow: five stages, a signed-in request, a calculation run, a claim package |
| [INFRASTRUCTURE-COMPONENT-SPEC.md](architecture/INFRASTRUCTURE-COMPONENT-SPEC.md) | Every Azure resource: SKU, settings, identity, roles, network, diagnostics, tags, and the Terraform that declares it |
| [CONNECTIVITY-MATRIX.md](architecture/CONNECTIVITY-MATRIX.md) | Who calls what, over which path, as which identity, with which permission |
| [ENV-VARS.md](architecture/ENV-VARS.md) | Every setting the app reads, where it is set, and the Terraform output that carries it |
| [RUNBOOK.md](architecture/RUNBOOK.md) | Health checks, KQL for the common failures, and routine operations |
| [Schema migrations](data/schema/migrations/README.md) | How the Warehouse DDL is versioned and applied |

## Data and calculation

| | |
| --- | --- |
| [DATA-REQUIREMENTS.md](data/DATA-REQUIREMENTS.md) | Every field the calculation consumes, why it is needed, and what happens when it is missing |
| [SOURCE-SCHEMA-MAPPING.md](data/SOURCE-SCHEMA-MAPPING.md) | Partner source schema to the internal model |
| [LAKEHOUSE-SCHEMA-AUDIT.md](data/LAKEHOUSE-SCHEMA-AUDIT.md) | Fabric lakehouse tables as they actually exist |
| [OPERATIONAL-DATA-MODEL.md](data/OPERATIONAL-DATA-MODEL.md) | Data the product itself generates — claims, engagements, findings |
| [CALCULATION-RULES-V7.md](data/CALCULATION-RULES-V7.md) | The calculation in prose, with worked examples |
| [ONEZERO-CALCULATION-MAP.md](data/ONEZERO-CALCULATION-MAP.md) | The One/Zero method step by step |
| [REFERENCE-DATASET.md](data/REFERENCE-DATASET.md) | The reference dataset and how parity is proven against it |

### Methodology sets

| | |
| --- | --- |
| [reference-dataset-assumptions.v8.json](../backend/rules/methodology/reference-dataset-assumptions.v8.json) | **Live.** Twelve decisions, BA-01 to BA-12, each with its evidence and what would disprove it |
| [reference-onezero-assumptions.v7.json](../backend/rules/methodology/reference-onezero-assumptions.v7.json) | **Live.** One/Zero methodology |

Superseded sets (v1–v7) are retired in `RETIRED_ASSUMPTION_SETS`; loading one to
run raises rather than silently producing a different answer.

## Product

| | |
| --- | --- |
| [PERSONAS.md](product/PERSONAS.md) | Who uses this and what each role is allowed to see |

---

## The one rule that matters most

The reference dataset must always produce **10,236 employees, 539 Min-Max
eligible, 656 Pay Period eligible**. These figures are defined **twice, on
purpose**: `backend/tests/certified.py` holds them as literals so a rule-pack
edit cannot move the gate along with the engine, and
`backend/rules/methodology/certified-figures.json` is the production-readable
copy the runtime equivalence gate needs. They are **never** edited to make a
test pass, and `tests/test_certified_figures_contract.py` fails if they drift
apart.

A change that moves them is either a genuine improvement that needs
re-reconciliation with the partner, or a bug. It is never a test that needs
updating.

```pwsh
cd backend ; $env:TCC_REQUIRE_PARITY=1 ; pytest tests/ -q
python backend/tools/verify_reference_independent.py
```

The second command re-derives the figures through an independent implementation
that shares no code with the engine. Agreement between two implementations is
worth more than either one passing its own tests.

With `DATA_SOURCE=flex` the same figures are recomputed from the Fabric
lakehouse, and a source that fails to reproduce them is refused rather than
served. `TCC_FABRIC_TESTS=1 pytest tests/test_reference_workspace_flex.py`.

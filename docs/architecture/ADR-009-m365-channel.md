# ADR-009 — Microsoft 365 channel

**Date** 2026-11-03 · **Status** Accepted for a proof of concept on synthetic data · **Builds on**
[ADR-003](ADR-003-clean-architecture-cqrs.md), [ADR-004](ADR-004-agentic-workflows.md),
[ADR-007](ADR-007-warehouse-operational-store.md), [ADR-008](ADR-008-channel-numeric-integrity.md)

## Context

The people who need this product's answers — tax consultants preparing a review, account teams
deciding who to call — are in Teams, Outlook and Word, and most have no access to the web app. The
request: let them use the platform from Teams, Microsoft 365 Copilot Chat and Copilot Cowork, for
reads **and** writes, under three constraints.

1. **Wording is exact.** Every figure shown is the engine's figure ([ADR-008](ADR-008-channel-numeric-integrity.md)).
2. **Every action is attributed to a person** and audited per user, separately from the app's own trail.
3. **No on-behalf-of exchange.** The platform calls the engine as itself; who is asking is audited context.

The platform before this work could not carry that. Capability logic lived in routers, the mediator's
audit was an in-memory ring, `agent_action_audit` was written by nothing, and there was no idea of a
person who may read but not write.

## Decision

**1. A Foundry hosted orchestrator behind Azure Bot Service.** A hosted agent built with Microsoft Agent
Framework, published to Teams and Copilot Chat through Bot Service, reads the message, picks tools and
**assembles the reply in code**. It is hosted code, not a prompt agent, because only code can guarantee the
reply is the platform's blocks around at most one verified sentence.

**2. A channel gateway in front of the API.** A third App Service on the existing plan authenticates
every caller, applies the writer check, rate-limits, audits per user, keeps the conversation's fact
ledger, and serves the tools twice: REST for the orchestrator and an MCP facade for Cowork. The API
accepts traffic only from the web subnet, so the orchestrator could not reach it directly; the gateway is
in that subnet. The gateway imports no router, agent or persistence adapter, and a test pins it.

**3. API capabilities.** The routers' compute moved into `application/capabilities/`: plain functions
returning an envelope (`facts`, `blocks`, `provenance`, disclaimer). The portal chat and the channel call
the same functions; `POST /api/capabilities/{tool}` runs one for an authenticated caller. The catalog
(`catalog.py`) is the one list of names, schemas and kinds that the orchestrator, the Cowork connector and
the tests share.

**4. Trusted-agent identity with channel-asserted assurance.** The orchestrator holds an app-only token
(role `Channel.Invoke` on the gateway); the gateway holds one (role `TCC.Agent` on the API). Each names
the person it acts for in a header, honoured **only** for an app-only principal of the right role, and
every audit row says `channel-asserted`. Cowork presents the person's own delegated token and is
recorded `delegated`. The assertion is weaker than a token of the person's own; it is stated, not hidden.

**5. Two-step writes.** `*_prepare` builds the real command, shows what would change, writes nothing and
mints a single-use token bound to the person, tool and exact arguments; `*_commit` presents it with an
idempotency key. The writer entitlement (an allow-list table by default, an Entra group optionally) is
checked at the gateway and again by the API's mediator, which gained a real Authorization stage for this.
No model can name a commit tool; the orchestrator commits only on the person's exact word.

**6. Per-user audit.** Every call writes a `begin` and an `end` to `tcc_ops.channel_audit` (a refusal is
one row), joined to the API's own records by correlation id; a commit carries the id of the preview it
confirmed. A call that cannot be recorded is not made. Model turns are filed separately
(`agent_action_audit`), which was previously unwritten.

**7. Cowork through skills and MCP.** Cowork composes its own answers, so it gets the same tools through
the gateway's MCP facade and two skills that teach the workflows. Its figures are protected by the skills'
rules and by `verify_figures`, a gateway-local tool that checks a draft against the conversation's own tool
results. This is weaker than the orchestrator's guarantee and is documented as such.

**8. Governed data access, in two lanes (CH-16).** The fixed tools answer what the engine concluded. Three more
read tools let a person ask questions the fixed tools cannot (the wage distribution at a location, which months
drove a shortfall): `data_catalog` says what exists, `data_query` runs a validated *specification* (never SQL,
never a model-written statement) built from a checked-in semantic model with every value bound and the client
scope first, and `data_distinct_values` lists the values of a category so a filter is not guessed. They are
capabilities like the rest (registry, gateway catalog, MCP list, audit), and the result is divided into two
**lanes** on the envelope itself. A block carries an `audience` (`both` or `user`); a result names the `facts`
keys that came from person-level values (`user_only_facts`). A result that lists employees (a record token, one
person's hours or pay, or raw rows of an employee-level dataset) puts its table in the `user` lane. The
orchestrator's model-facing projection (`capabilities/lanes.py`: `model_facts`, `model_blocks`) drops both, so a
model is told the count and the column names and never the rows, while the person's reply, composed from the full
envelope, shows them. An audience word the consumer does not know is read as `user`, never `both`. The existing
guarantee that a model is only ever shown the *names* of facts is unchanged; the lane is the second wall behind it,
and the one that holds where a model is handed text.

Copilot Cowork is that case: its model composes from the text a tool returns, so there is no way to show the
person a row and hide it from the model. **A result that lists individual employees is therefore refused over
Cowork unless the caller is a writer**, with a plain-words refusal naming Teams as the place the rows are shown to
the person alone. A writer is entitled to see person-level data and chooses Cowork knowingly, which is the same
bar the platform sets for changing it. The rule is enforced twice: the API refuses before anything is read (it
knows the specification and the channel), and the gateway refuses on the way back if any result still carries a
person-only lane for a non-writer, so neither check is the only one. An aggregate over employee-level data (a
count of people by location, an average by month) carries no person and is allowed everywhere. Not decided here:
suppressing small groups (see [KNOWN-LIMITATIONS](../m365-channel/KNOWN-LIMITATIONS.md#data-queries)).

## Alternatives considered

| Alternative | Why not |
| --- | --- |
| **On-behalf-of tokens** for the person | Foundry-managed OBO does not support custom servers, and agent-identity OBO does not currently apply to Bot Service integrations. It would also make the API's identity model do two jobs. The channel assertion plus a writer list is a lookup, not an exchange |
| **Publish a prompt agent** with a tool | A prompt agent with a tool still paraphrases the tool's output; the exactness promise cannot be an instruction to a model. It also has no place for a confirm flow a model cannot bypass |
| **A declarative agent with an API plugin** | Reaches Copilot Chat but not Teams messages as such, hands composition to Copilot's model (the same weakness as Cowork, without a figure check), and offers no confirmation the server controls |
| **Expose the API directly** | The API's ingress is the web subnet by design, its caches are warm in that process, and it has no notion of a caller acting for a person. A second process importing the application layer would pay cold Fabric reads of a minute or more |
| **Cowork only** | Leaves Teams and Copilot Chat, where most people are, without the exactness guarantee |

## Consequences

**Good.** On Teams and Copilot Chat a wrong figure cannot reach a reader. A person who may not write cannot
get as far as a token. Every action has a named person, a channel, an assurance level and a trail that joins
the gateway's view to the API's. The tool catalog is one contract with tests on each side: over 2,700 backend
tests, including whole workflows through the gateway over REST and MCP.

**Costs.** A third App Service, a Bot Service resource, a hosted agent and a publish step. A reply on the
orchestrator path is the engine's blocks with at most one sentence of prose; the strictness is the product.

## Risks, said plainly

| Risk | State |
| --- | --- |
| **The identity assertion is weaker than a token.** Anyone who can obtain a `Channel.Invoke` token can claim to act for anyone in the tenant | Flagged on every audit row. Acceptable for a PoC on synthetic data; not for customer payroll. Production needs the person's identity carried end to end (Teams SSO or OBO) or an independent review of the orchestrator's trust |
| **What the hosted runtime exposes about the user is unproven** | The orchestrator reads three documented signals in a configurable order and runs nothing without one. Settled only by a live run |
| **Cowork cannot be held to verbatim wording** | `verify_figures`, skill rules and a stated caveat. A wrong figure equal to another real figure in the same conversation is not seen (the guard matches values) |
| **The fact ledger is per process** | A restart or second worker forgets; the answer then is "no", never "yes" |
| **The hosted-agent and Cowork surfaces are in motion** | The gateway's tool API is the stable layer; the plugin build pins what it generates |
| **Data in published responses is processed under Microsoft 365 terms** | Synthetic data only in the PoC |
| **A tax-filing system with a write path from chat** | Two steps, a writer list checked twice, append-only history, a full audit, and an excluded set (calculation runs, rule-pack changes, ingestion decisions) that is not offered at all |
| **Public reach** | The demo posture leaves the gateway and the Foundry data plane reachable from the internet, authenticated. The later private posture is planned in [HARDENING-PLAN](HARDENING-PLAN.md) |

## What would change this decision

A token for the person end to end that the orchestrator can pass on would retire the assertion. A way to
constrain Cowork's composition would retire the weaker guarantee. A requirement that customer payroll be
reachable from the channel would make the hardening plan a prerequisite, not a later step.

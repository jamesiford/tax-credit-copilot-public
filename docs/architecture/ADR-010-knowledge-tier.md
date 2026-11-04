# ADR-010 — Knowledge tier: cited reference text through a port, never a figure

**Date** 2026-11-04 · **Status** Accepted as a design with a port, a fake and tests; the Foundry IQ adapter is **not built** and the tier
is **off by default** · **Builds on** [ADR-004](ADR-004-agentic-workflows.md), [ADR-008](ADR-008-channel-numeric-integrity.md),
[ADR-009](ADR-009-m365-channel.md) · Detail and the owner's provisioning steps: [KNOWLEDGE-AND-IQ.md](KNOWLEDGE-AND-IQ.md)

## Context

The channel's agent answers from deterministic tools, and a model only writes the connective sentence around the engine's blocks. Two things
a reader sometimes asks for are not tool results: what a statute or a piece of guidance *says* (a definition, a section, why a rule exists)
and where that text can be checked. Today the product cannot answer either without the model reciting statute from memory, which is the
unsourced claim this product exists to avoid ([ADR-004](ADR-004-agentic-workflows.md): "do not invent tax rules in prompts").

Microsoft's current stack names this layer. Foundry IQ is a managed knowledge layer on Azure AI Search that returns grounded passages with
citations; Fabric IQ is a semantic layer over Fabric data (ontology, semantic models, data agents); they are separate workloads
([Foundry IQ](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/what-is-foundry-iq), page dated 2026-07-31, and
[Fabric IQ](https://learn.microsoft.com/en-us/fabric/iq/overview), page dated 2026-07-08, both read 2026-11-04). The question here is which
of them may touch this product's answers, and how, given [ADR-008](ADR-008-channel-numeric-integrity.md): every figure shown is the engine's.

One property of the existing guard shapes the decision. The numeric guard accepts any numeral that is in the facts, and the fact index reads
numerals out of prose placed among the facts (a test pins this: a passage handed in as a fact would make its figures acceptable). So "a
passage is never a figure" cannot be left to the guard. It has to be a structural rule about what the knowledge tier is able to reach.

## Decision

**1. Reference text goes through one port, `KnowledgePort`.** `application/knowledge.py` defines `Passage(text, source, citation, retrieved_at)`
and `KnowledgePort.search(query, *, top) -> list[Passage]`. Standard library only, so it is vendored into the orchestrator. A passage with no
citation cannot be constructed. Whatever answers (a fake today; Foundry IQ later) sits behind it.

**2. A passage is context text and never a figure.** It enters a model's instructions only as fenced, labelled reference text with no
citation to copy, and it is shown to a reader only as a quoted block with each passage's citation, source and retrieval date, beside a
narration that survived the guard. It has no path into the fact index, the ledger, a tool result or the reader's allowed numerals. A
narration that repeats a figure found only in a passage is dropped whole by the existing guard. Architecture tests enforce the reach: the
knowledge modules import an allow-list and name nothing that carries a fact; only five orchestrator modules import the tier, none of them on
the figure path; the ledger is written by the gateway pipeline alone.

**3. The framework mechanism is a context provider.** `app/core/maf_knowledge.py` is a `ContextProvider` whose `before_run` asks the port and
calls `extend_instructions`, and nothing else (a test fails on any other call on the context). It is built only when a source was given.

**4. It is off by default.** `KNOWLEDGE_ENABLED=false`; `KNOWLEDGE_PROVIDER` is `none | fake | foundry-iq`, of which only `none` and `fake`
exist. Asking for `foundry-iq` is a start-up error that says it is designed and not built, never a quiet fall back. Nothing in Terraform,
`azure.yaml` or a profile sets either variable, and no Search resource is declared; a test fails if one appears.

**5. The first real source is a Foundry IQ knowledge base on Azure AI Search, at minimal reasoning effort and extractive output.** That
combination is the generally available surface (REST `2026-04-01`) and needs no model for query planning; LLM planning, answer synthesis and
multi-turn messages are preview ([agentic retrieval overview](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-overview), dated 2026-09-16,
read 2026-11-04). The adapter is a thin `KnowledgePort` over the stable `azure-search-documents` 12.0.0 SDK, which ships `KnowledgeBaseRetrievalClient`
for API `2026-04-01` (read from the wheel on 2026-11-04; not installed or run), not over the framework's pre-release Azure AI Search provider package
(every release of `agent-framework-azure-ai-search` is a beta; a production build installs no pre-release, D-76). The corpus is public statute and
guidance text the owner has approved, never client data, so the end-user permission trimming Foundry IQ offers is not needed.

**6. Fabric IQ, a Fabric data agent and an ontology MCP server are evaluate-only and off by default**, for the reasons in
[DATA-ACCESS.md §9](../m365-channel/DATA-ACCESS.md#9-evaluation-a-microsoft-fabric-data-agent-as-an-optional-provider-not-built) and
[KNOWLEDGE-AND-IQ.md](KNOWLEDGE-AND-IQ.md): they run with the end user's identity (this channel holds an assertion of the person, not a token),
they let a model write the statement that reads tenant rows (past the lanes, the small-group rule and tenant-first SQL), and they are preview
and moving (the Foundry tool for a Fabric data agent is scheduled for retirement on 2026-11-06). Tenant rows stay on the governed `data_*` tools.

## Alternatives considered

- **Let the model recite statute.** What happens without a tier. Unsourced, unreviewable, and the exact failure the product is built to prevent.
- **Put reference text in the facts, so a narrator can cite it with a placeholder.** Rejected: the guard would then accept every figure in the
  text, including one the model attached to the wrong rule. The engine's rule packs ([ADR-005](ADR-005-year-versioned-rules.md)) are the only
  statutory figures, versioned by year with a hash.
- **Adopt the framework's Azure AI Search context provider directly.** Rejected for now, not on merit: its package is pre-release (D-76) and I
  did not inspect its code, so I cannot say whether it would keep the citations where the turn can print them. Revisit at GA.
- **Query the knowledge base as the end user (Foundry IQ can run under the caller's Entra identity).** Not available: the orchestrator holds
  a channel assertion of the person, not their token (ADR-009, no on-behalf-of). Unneeded for a public-text corpus.
- **A Fabric data agent or ontology MCP for "ask anything about the data".** Evaluate-only, above.
- **Build the Foundry IQ adapter now.** Out of scope: it needs Azure resources and a live check (RM-16 is the only package allowed to deploy).

## Consequences

- **Gains.** A reader can see what a statute says with a citation to check, a model can answer a definitional question without reciting
  from memory, and nothing the model reads can become a figure. The seam (`KnowledgePort`) means the source can be replaced without touching
  the orchestrator; the fake keeps the tests offline.
- **Costs.** A knowledge call adds latency to a turn that uses it (unmeasured). A reader-visible quoted passage may itself contain figures
  (a dollar threshold in a section), which are not the engine's. The reply says so in a fixed header, but whether quoted statute figures may
  appear at all is an owner decision (below).
- **What does not change with the tier off:** every reply, the audit rows, the numeric guard, the composer, the ledger, Terraform, `azure.yaml`.

## Risks, said plainly

- **Prompt injection through the corpus.** Passage text is fenced as untrusted before it reaches a model, and a model's words are still
  screened by the guard and the output policy. The corpus is owner-authored, which is the main control.
- **A reader mistakes quoted text for the engine's figure.** Mitigations: the fixed header, the citation on every passage, and the block
  appearing only beside a narration that passed the guard. Not eliminated.
- **Stale or wrong statute text.** The knowledge base is only as current as its index; each passage carries `retrieved_at`, and the engine's
  versioned rule packs remain the source for anything that prices a credit.
- **Unverified.** Per-tier agentic retrieval limits and prices, regional availability, which knowledge source types are generally available,
  and latency inside a Teams turn were not verified; see KNOWLEDGE-AND-IQ.md.

## What would change this decision

- A generally available framework provider that keeps citations addressable by the turn: adopt it behind the same port.
- Per-person tokens carried end to end (the condition that retires the channel assertion): the identity argument against Fabric IQ and a data
  agent weakens, though the lanes, the small-group rule and tenant-first SQL would still apply to anything that writes its own statement.
- An owner decision that reader-visible statute quotes must not carry numerals: the block would render citations only.

## Open decisions for the owner

1. May the reader-visible quote include figures that appear in the statute text (labelled as quoted, not computed), or citations only?
2. Which sources form the corpus, who approves a change to it, and how often it is refreshed.
3. Whether the knowledge tier is wanted at all before the data-access work (RM-01 to RM-05) has run live.

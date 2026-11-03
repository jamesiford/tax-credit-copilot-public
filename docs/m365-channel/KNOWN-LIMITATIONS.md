# Known limitations

What the Microsoft 365 channel does not do, or does less well than it may appear. Each is a decision or a
fact, not an oversight; where one is closed by later work, the right-hand column says what closes it. The
PoC runs on synthetic data, and several of these are fine there and unacceptable with real payroll.

## The figures

| Limitation | Detail | What closes it |
| --- | --- | --- |
| **The fact ledger is per process** | `verify_figures` checks a draft against the results this gateway **process** returned to this conversation. The ledger is in memory, bounded (200 results a conversation, 1,000 conversations) and forgotten after eight hours. A restart, a scale-out to a second worker, or an old conversation loses it. The answer then is "no", never "yes": a figure that cannot be traced is reported. Keep `WEB_CONCURRENCY=1` (the default) | A shared store for the ledger. Not built: the cost of a repeated question is small and the strict direction is safe |
| **The guard compares values, not meaning** | A wrong figure that equals **another real figure in the same conversation** passes: "$1" beside a real count of 1 is not a figure the guard can call wrong. The tests pin this (`test_known_limit_*`) and the one-digit mutation tests leave such collisions out for that reason. Likewise a correct figure inside a false sentence passes ([ADR-008](../architecture/ADR-008-channel-numeric-integrity.md)) | A guard that binds each numeral to the fact it cites, which needs the author to cite |
| **Number words are invisible** | "twelve" is not a numeral. The narrator is told not to write figures as words; the guard does not guess at English | None planned |
| **Cowork's wording is not guaranteed** | Cowork's model composes its answers and documents. The skills say to quote verbatim and `verify_figures` checks a draft, but a model can reword text between a tool result and a document, and a draft that is never checked is never caught. Exact wording is guaranteed on Teams and Copilot Chat, where code assembles the reply. Say so in any demo | An author-side check Cowork cannot skip |
| **The author supplies the reader's own numbers** | Dates, counts of emails found and slide numbers are not engine facts, so the skills pass them as `allowed_context`. A model that omits one fails the check and fixes the draft; one that adds a wrong one gets through for that number only | None |
| **The portal chat is still not number-checked** | Only the channel path runs the numeric guard. The portal's briefs come from the same capabilities, but nothing checks what its narrator says about them | Extending the composer to the portal stream |

## Identity and access

| Limitation | Detail | What closes it |
| --- | --- | --- |
| **Channel-asserted identity is weaker than a token** | On Teams and Copilot Chat the orchestrator tells the gateway who is asking. It is trusted because the caller holds `Channel.Invoke` and the tenant matches, and every audit row says `channel-asserted`. Cowork presents the person's own token (`delegated`) | Teams SSO or OBO carrying the person's identity end to end |
| **What the hosted runtime tells us about the user is unproven** | The orchestrator reads three documented signals in a configurable order and runs **nothing** if none resolves. Which one a real Teams or Copilot Chat message carries is settled only by a live run | The live smoke test (Prompt 6) |
| **Graph consent is needed for group-based writers and for UPN lookup** | The default writer source is an allow-list table. An Entra-group source needs the gateway's identity to hold Graph `GroupMember.Read.All`, which a privileged administrator must grant. A UPN lookup is **not built**: the audit stores the object id and the display name the channel supplied, and a UPN only where a person's own token carried it | A privileged role assignment; a `User.ReadBasic.All` lookup if wanted |
| **No per-client entitlement** | Any signed-in person the platform admits may read every client. Writers are a list, not a per-client scope | A per-user client entitlement behind the existing authorizer port |
| **Writers are managed by script** | `scripts/channel-writers.py` or the group. There is no chat or portal screen for it, deliberately | None |

## What it will not do

| Limitation | Detail |
| --- | --- |
| **No calculation run from chat** | A run is synchronous and can take longer than a front-end's timeout (a cold read is about a minute). The tools read recorded or warm results; a client-year nobody has calculated answers `not_calculated`, never zero. Starting a run needs an asynchronous job pattern that does not exist |
| **An excluded set of writes** | Rule-pack verify and apply, rules ingestion, ingestion-exception decisions and schema or configuration changes are not offered at all: they need tax-counsel sign-off or carry a caller-supplied reviewer. Eight person-only write routes are refused to the agent |
| **No employee identifier in a chat** | Employee-level tools take an opaque record token. An employee id never appears in a URL, log or prompt |
| **No Adaptive Cards** | Replies are text: tables as text, choices as a numbered list |

## Downloads

A claim package link is a **ticket** on the gateway: 256 bits, single use, valid fifteen minutes, bound to the
person it was minted for, stored only as a hash, redeemed through the API and streamed through the artifact
service. No storage address or SAS is ever produced, and the download is audited as that person. In practice:

- a link copied to someone else, or opened by someone else's token, is refused, and the owner's link survives
  the attempt;
- a link opened twice, or after fifteen minutes, is `410`; ask for a new one with `claim_package_link`;
- a browser with no token can use it (the ticket is the credential); a client that follows or previews a link
  (some chat clients do) can **spend** it before the person clicks. If a link fails with 410 on first use,
  that is the likely cause;
- tickets live in the confirmation store (`tcc_ops.channel_confirmation`, the Warehouse when deployed), so a
  restart does not lose or resurrect one.

## Publishing and platform

| Limitation | Detail |
| --- | --- |
| **Org-wide publish needs a Microsoft 365 administrator** | `scripts/publish-m365.ps1` publishes to *Just you* by default and never approves organisation scope itself; tenant-wide publish needs `-ConfirmTenantPublish` and an admin ([PUBLISHING](PUBLISHING.md)). Listing the Cowork plugin in Discover is an admin upload ([COWORK-SETUP](COWORK-SETUP.md)) |
| **Hosted-agent and Cowork features are in motion** | Both are new and the CLIs are in preview. The gateway's tool API is the stable layer; the plugin build pins what it generates; the documentation is re-read before each release. Annotation-driven confirmation for non-Microsoft MCP servers is still rolling out, so the skills do not rely on it |
| **Information Barriers** | Microsoft Purview Information Barriers are not supported for plugin or skill management; in a tenant where they are on, embedded knowledge file uploads are blocked tenant-wide, which blocks uploading a plugin that carries skills |
| **Cowork on mobile** | Custom plugins are not supported there |
| **Published responses are processed under Microsoft 365 terms** | Fine for synthetic data; a data-handling decision before customer data |
| **The demo posture is public** | The channel gateway and (with the demo toggle) the Foundry data plane are reachable from the internet, authenticated. See [HARDENING-PLAN](../architecture/HARDENING-PLAN.md); the hardened Foundry path is per the documentation and unproven until spike S6 |

## The external model gateway

The platform can send model calls through an external OpenAI-compatible gateway instead of Foundry directly
([AI-GATEWAY](../architecture/AI-GATEWAY.md)). Limits that matter for the channel:

- **Foundry bring-your-own-model supports prompt agents only.** It does not support the Responses API, so it
  cannot carry the hosted orchestrator. The hosted orchestrator calls the gateway **directly**, with the same
  settings contract, not through a Foundry connection.
- A *Foundry* BYOM connection on a network-isolated Foundry needs the gateway reachable from the Agent Service
  network, not only from the app.
- **The egress policy defaults to `allow_all`**: the owner has confirmed no payroll PII needs redaction for the
  providers outside Microsoft's boundary. `aggregates_only` and `block` are levers, not defaults. One thing is
  not configurable: an employee identifier or record token never enters a prompt, under any policy.
- The mock gateway is a proof-of-concept tool; it validates token shape, not signatures, and is refused in the
  enterprise profile.

## What the tests do not prove

The suite drives whole workflows through the gateway over REST and MCP against the real capability layer, with
Entra on, on SQLite and synthetic data. It does **not** prove: a live Teams, Copilot Chat or Cowork round trip;
what identity signal a real message carries; that Cowork's model obeys the skills; the Warehouse stores under
load; or the hardened network. The manual checklist in [DEMO-SCRIPT](DEMO-SCRIPT.md) is where those are
checked, after the live deployment.

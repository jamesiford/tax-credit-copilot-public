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
| **Graph consent is needed for group-based writers and for UPN lookup** | The default writer source is an allow-list table. An Entra-group source needs the gateway's identity to hold Graph `GroupMember.Read.All`, which a privileged administrator must grant. A display-name and UPN lookup **is built** (CH-15a) and is **off by default**: with `CHANNEL_RESOLVE_DISPLAY_NAMES` on and `User.ReadBasic.All` granted to the gateway identity, a Teams or Copilot Chat user whose name is missing or `(name not provided)` is named in the audit rows and a write is authored by their UPN. Without the role (or with the switch off) the lookup fails soft and the audit stores the object id and the placeholder, as before. It is **not verified live**: whether the cached-token retry recovers a role granted after the first refused call is only confirmable on the redeploy. The orchestrator is unchanged and still says `(name not provided)`; the gateway fixes it | A privileged role assignment (`assign-channel-roles.ps1 -GrantUserReadBasic`); the live redeploy |
| **No per-client entitlement** | Any signed-in person the platform admits may read every client. Writers are a list, not a per-client scope | A per-user client entitlement behind the existing authorizer port |
| **Writers are managed by script** | `scripts/channel-writers.py` or the group. There is no chat or portal screen for it, deliberately | None |

## What it will not do

| Limitation | Detail |
| --- | --- |
| **No calculation run from chat** | A run is synchronous and can take longer than a front-end's timeout (a cold read is about a minute). The tools read recorded or warm results; a client-year nobody has calculated answers `not_calculated`, never zero. Starting a run needs an asynchronous job pattern that does not exist |
| **An excluded set of writes** | Rule-pack verify and apply, rules ingestion, ingestion-exception decisions and schema or configuration changes are not offered at all: they need tax-counsel sign-off or carry a caller-supplied reviewer. Eight person-only write routes are refused to the agent |
| **No employee identifier in a chat** | Employee-level tools take an opaque record token. An employee id never appears in a URL, log or prompt |
| **No Adaptive Cards** | Replies are text: tables as text, choices as a numbered list |

## Data queries

| Limitation | Detail | What closes it |
| --- | --- | --- |
| **Small groups still reach the model (Copilot Cowork)** | An aggregate over one or two people (a count by a location that has one employee, an average by a rare designation) is close to a person's own figure, and over Cowork the aggregate's text is what its model reads. There is **no minimum-group-size suppression**: hiding a small group would make an aggregate silently differ from what the data holds, which breaks the exactness this product is built on, and the person asking is entitled to the figure in Teams, where the model is shown names only. The control is the lane (an employee-level *row* never goes to a model) plus the writer rule for Cowork, not suppression | A suppression policy that withholds a group below a size **and says that it did**, decided with the partner; or refusing group-by on a dimension finer than a location for Cowork. Neither is built |
| **The table shows at most 50 rows** | The facts keep every row the cap allowed (500 at most); the table in the reply shows the first 50 and says how many it cut, because a message of five hundred rows is not delivered. The person is told to narrow the question or ask for an aggregate | Paging, or a downloadable result. Not built |
| **A model sees at most 50 rows' worth of fact names** | The narrator can cite the first 50 rows by placeholder; a longer list is cut for the model only. The person's table is unaffected | None planned |
| **Row counts, not people** | A count over a pay-period dataset counts pay periods; `count_distinct` on `record_token` counts people. The catalog's `engine_notes` say which, and the fixed tools remain authoritative for eligibility and credit | None: said in the catalog |
| **Not run against a live Fabric capacity** | Everything is verified offline over SQLite and fakes shaped like the drivers; T-SQL execution, the pyodbc timeout and the lakehouse endpoint are first exercised on the live redeploy | The live redeploy (CH-17) |

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
| **The demo posture is public** | The channel gateway and (with the demo toggle) the Foundry data plane are reachable from the internet, authenticated. See [HARDENING-PLAN](../architecture/HARDENING-PLAN.md) and the switch-off list in [DEMO-CLEANUP](DEMO-CLEANUP.md); the hardened Foundry path is per the documentation and unproven until spike S6 |

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

## Found in the live sandbox (CH-13, 3 November 2026)

What the first live deployment showed that the tests could not. Each is a fact about this deployment, not a promise.

| Finding | Detail | What closes it |
| --- | --- | --- |
| **M-01 (resolved): the hosted agent could not reach the model** | Cause: from the hosted runtime `<account>.services.ai.azure.com` and `.cognitiveservices.azure.com` do not resolve; `<account>.openai.azure.com` does. The `foundry` provider now uses that host ([D-101](DECISIONS.md)). Still true: why the runtime resolves one of the account's three names and not the others is unknown, and a hardened (private) network may change it, so re-run `/netcheck` then | Spike S6 (hardening) |
| **The model reads figures it cannot see, so it can attribute them wrongly** | With the model on, the engine's figures are exact and the numeric guard passes, yet the model said "rounded to the nearest thousand" about an unrounded figure, and narrated the first-ranked client's figures as the asked-about client's when it chose the wrong tool. The guard compares values, not meaning (above). CH-15c closes the hedge structurally (an approximation qualifier within three tokens of a figure drops the narration) and sharpens the planner prompt and tool descriptions (`book_rank` is whole-book only; client tools need a client), but a hedge farther than three tokens from its figure, rank prose built from a placeholder (`position`), and a wrong tool choice for a client question are still only discouraged by the prompt, not refused by code | A guard that binds each figure to the fact it cites |
| **Teams "delivered, no reply": `activity` as a container protocol** | `azure.yaml` declared `activity` on the container, which serves Responses only, so every Teams message was posted to `/activity/messages` and got a 404 in the container log while Bot Service reported 200. Fixed ([D-100](DECISIONS.md)): `activity` only on the endpoint, which makes the platform bridge it to Responses. Re-check `GET /agents/<name>` after every deploy: `definition.protocol_versions` must list `responses` only | Serving the Activity protocol in the container, if streaming or cards are wanted |
| **Teams-side traps seen in the sibling projects** | One app id and one bot id are shared by both app packages (the publish package and azd's sideload package): install **one**, never both. `developer.name` must be at most 32 characters. A user-uploaded custom app can become an admin "submission"; uploading as an admin (Teams admin center, Manage apps, Upload new app) publishes directly. "You cannot send messages to this bot" and "delivered but nothing reaches the bot" cleared there only after re-uploading as a **new version** (bump `appVersion`) and a client refresh. Check the app is Allowed in the Teams admin center. A one-off 403 `BotDisabledByAdmin` was seen once. Test in Teams on the web, InPrivate. A Tenant-scope publish takes about an hour to show in the store (never used here) | Owner action |
| **The account firewall must admit the agent, so the demo posture is open to any address** | With the data plane limited to the operator's address, the hosted runtime's own calls to the project were refused (403, "Virtual Network/Firewall rules"). The demo therefore runs `foundry_allowed_ip_ranges` empty: public, Entra-only, local keys off, synthetic data | The hardening plan: a delegated agent subnet and private endpoints |
| **`x-ms-user-identity` needs delegation the caller does not have** | A direct call carrying it was refused by the platform ("Caller is not authorized to delegate to another user"). The default identity sources therefore depend on `x-ms-original-subject`, which only a real Teams or Copilot message supplies. Direct calls carry no identity and run nothing | The live Teams spike (S1, S2) |
| **A role granted to an identity that has already asked for a token may be seen late** | The API's identity asked Microsoft Graph for a token, was refused, and was then granted `GroupMember.Read.All`; the platform keeps the first token until it expires. Since CH-15e the shared Graph client drops the cached token and retries once on that refusal (at most once a minute; still fail-closed). **Verified offline only**: whether the platform's managed-identity endpoint honours the cache bypass is confirmed by the live redeploy. Until then, grant the role **before** the first call, or put the writer on the allow-list | The live redeploy's check |
| **The API reads the writer source too** | It enforces the writer entitlement itself, so Terraform now gives it `CHANNEL_WRITER_SOURCE` and the group id (and its identity needs the Graph role for a group source). Before this, `either` at the gateway still meant allow-list at the API | Fixed in infra |
| **One gateway worker, one process** | A 40-way burst of 200 calls took 129 seconds and 19 answered 502. The rate limit (60 a minute) cannot be outrun at about 1.5 calls a second, so its 429 is proven offline, not live | Workers behind a shared ledger and limiter |
| **The deployment hook can report a start failure for a gateway that started** | `az webapp deploy` said the site did not start in ten minutes; the app was serving and ready minutes earlier (its first build is slow). Check `/channel/ready` before believing it | A longer wait in the hook |
| **The mock model gateway was unreachable until its port matched the platform's probe** | Fixed in Terraform. It is reachable only from the integration subnet, so it was checked from the API app's Kudu console, not from a workstation | n/a |
| **Portal HTTP endpoints cannot be compared from a workstation** | Behind Easy Auth and the API's subnet rule. The live smoke compares the gateway with the same capability run in process against the same Warehouse; a person compares the portal by eye (the manual checklist) | A signed-in browser session |
| **No finding exists to resolve** | Findings detection found none for any synthetic client, so `finding_resolve` was not exercised live | A client with an open finding |

# Security

## Reporting a vulnerability

**Do not report security vulnerabilities through public GitHub issues.**

Report them to the Microsoft Security Response Center (MSRC) at
[https://msrc.microsoft.com/create-report](https://aka.ms/opensource/security/create-report),
or by email to [secure@microsoft.com](mailto:secure@microsoft.com). If possible,
encrypt with the [PGP key](https://aka.ms/opensource/security/pgpkey).

Include as much of the following as you can: the type of issue, the file paths
involved, the location of the affected source, any special configuration
required to reproduce, step-by-step reproduction instructions, proof-of-concept
code if you have it, and the impact as you see it.

More at [aka.ms/opensource/security/policy](https://aka.ms/opensource/security/policy).

## Security posture

Stated plainly so nobody has to infer it from the code. **This software has not
been through an independent security review. Do not connect it to real payroll
data until you have reviewed it against your own requirements.**

| Area | State today | Needed before production |
| --- | --- | --- |
| **Authentication** | `AUTH_MODE=entra`: Easy Auth on the web app, and the API validates every bearer token (issuer, audience, scope and the `TCC.User` app role) in `backend/api/auth.py`. Network position alone is never trusted. The `public` profile runs `AUTH_MODE=none` with synthetic data only; the API **refuses to start** with `none` when `DATA_CLASSIFICATION=customer` outside local development (`backend/application/deployment.py`) | The customer's two app registrations. Entra mode is unit-tested; it has not yet been exercised end to end in a deployed environment |
| **Authorization** | Every client id named in a path, query or JSON body is checked by the request guard before the route runs. The deployed entitlement is `AllClientsAuthorizer`: any `TCC.User` may act on every client. The Microsoft 365 channel gateway holds an app-only token (`TCC.Agent`) and names the person it acts for in `X-TCC-Acting-User`; that person must be a listed writer (`CHANNEL_WRITER_SOURCE`) before a command runs, and the write is attributed to them, never to the gateway. Eight person-only write routes are refused to the agent outright (`AGENT_FORBIDDEN_WRITES`) | A per-user client entitlement source behind the same `ClientAuthorizer` port, if analysts must be restricted to some clients. The customer assigns `TCC.Agent` to the gateway's service principal and, for `entra_group`, grants Graph `GroupMember.Read.All` |
| **Tenant isolation in the store** | Every Warehouse statement binds `client_id` as its first predicate (`tenant_sql.py`); `tests/test_architecture.py` fails the build otherwise | Unchanged |
| **Ingress** | The API accepts traffic only from the web app's integration subnet (access restriction, default deny); a direct call returns 403. The web app is public in the `public` profile; the `enterprise` profile chooses an access restriction or a private endpoint | Per the customer's network design |
| **CORS** | The API allows any origin (`backend/main.py`), but browsers never reach it: the web app's server proxies `/api` on the same origin | Restrict to the web origin if the API is ever exposed directly |
| **Secrets** | **None.** Every dependency authenticates with a managed identity | No change — see below |
| **Downloads** | Files are streamed by the API after an authorization check; no SAS URL ever reaches a browser; every attempt is recorded in `tcc_ops.artifact_access`. A Teams card's link is a **ticket** on the channel gateway: 256 bits, single use, 15 minutes, bound to one person, kept only as a hash, redeemed through the API, never a storage address | Unchanged |
| **Channel gateway (Microsoft 365)** | The one new public surface, and off unless `enable_m365_channel`. It authenticates every call in the app (`backend/channel/auth.py`): an agent token with the role `Channel.Invoke`, or a delegated user token with the scope `Channel.Access`; there is no unauthenticated mode and `AUTH_MODE=none` is refused. It audits every call per user (`tcc_ops.channel_audit`), rate-limits per user, caps bodies (64 KB) and responses (1 MB), and routes only to `POST /api/capabilities/{tool}`, health and artifacts. It imports no router, agent or persistence adapter (`tests/channel/test_gw_architecture.py`) | Enterprise profile refuses it. For production: an Entra-protected front, a network policy for the Foundry egress path, and independent review |
| **Identity asserted by the channel** | An orchestrator tells the gateway which person it acts for. That is **weaker than a token of the person's own**: it is trusted because the caller holds `Channel.Invoke` and the tenant matches. Every audit row says `channel-asserted` (Teams, Copilot) or `delegated` (Cowork, the person's own token). The API honours the acting user only for an app-only `TCC.Agent` principal | A token carrying the person's identity end to end (OBO or Teams SSO) if the assertion is not acceptable |
| **Writes from chat** | Two steps: `*_prepare` shows what will change and mints a single-use token bound to the person, the tool and the exact arguments; `*_commit` presents it with an idempotency key. The writer entitlement (`CHANNEL_WRITER_SOURCE`: an allow-list table by default, an Entra group optionally) is checked at the gateway **and** by the API's mediator, whatever the caller claims. Eight state-changing routes that are not writer-gated commands are refused to agent tokens | Per the customer's change-control policy |
| **PoC default** | `CHANNEL_ALLOWED_CALLER_APP_IDS` lets a named application call as the orchestrator **without** the `Channel.Invoke` role, for a sandbox where the role cannot be assigned. The default is empty (role only); the path that admitted each call is logged. `channel_allowed_ip_ranges` is empty by default (every address), because authentication is in the app | Empty the allow-list and assign the role; set the IP ranges |
| **Network posture: demo and hardened** | Two postures, named by the Terraform output `network_posture`. **`private`** (the default, and the only one for the enterprise profile or customer data): the Foundry data plane has public access off and is reached by the API over a private endpoint. **`demo-public-foundry`** (`foundry_public_network_access = true`, demo only; refused with the enterprise profile and with `data_classification = customer`): the Foundry account's public endpoint is on so an operator's workstation can deploy and smoke-test the hosted agent. It stays Entra-only with local auth off, can be firewalled to listed ranges, and keeps its private endpoint and DNS; the plan prints a warning. In the demo the channel gateway is also public (Entra-only). **What stays strong:** every call is authenticated, no secrets, the API is not public, writes need a writer and two confirmations, every call is audited per user. **What is weaker, and must be stated in any demo:** the gateway and the Foundry data plane are reachable from the internet (authenticated), and the acting user is a channel assertion. Acceptable only because the data is synthetic | The hardened posture ([HARDENING-PLAN](docs/architecture/HARDENING-PLAN.md)): network-injected Foundry, a private gateway, an ops host. Per the documentation and unproven until spike S6 ([HARDENING-SPIKE](docs/m365-channel/HARDENING-SPIKE.md)), with no Cosmos DB |
| **Transport** | HTTPS only, TLS 1.2 minimum, FTPS disabled, on both App Service apps | Unchanged |
| **Data at rest** | Azure platform encryption | Customer-managed keys if required by policy |
| **Model access** | Foundry by default; an optional OpenAI-compatible gateway ([AI-GATEWAY.md](docs/architecture/AI-GATEWAY.md)). No model produces a figure. A prompt carrying an employee record token, an SSN shape or an identifier key is refused to every provider (`AI_EGRESS_POLICY` tightens further). A deployed process refuses a gateway with TLS verification off or no authentication. Gateway secrets are Key Vault references only. Calls are time-limited, retried, circuit-broken, concurrency-limited and optionally token-budgeted ([AI-RESILIENCE.md](docs/architecture/AI-RESILIENCE.md)); spans and metrics carry shape only, never text or identifiers ([AI-OPERATIONS.md](docs/architecture/AI-OPERATIONS.md)) | The customer's gateway contract, TLS trust and network path; review of the egress rule against their data-handling policy |
| **Prompt injection and model output** | Reader text is fenced as data and screened for instruction-override attempts before any model is called; model prose is reviewed for links, addresses, identifier shapes, code blocks and legal-advice claims before a reader sees it ([ADR-008](docs/architecture/ADR-008-channel-numeric-integrity.md)). Pattern-based, with stated limits | Extend the corpus from real attempts; decide the link allow-list (`AI_OUTPUT_ALLOWED_HOSTS`) |

## Key Vault is optional, and off by default

Nothing in either app's environment is a secret, so a vault would hold nothing.
Terraform creates one only when `enable_key_vault = true`. Every dependency
authenticates as a user-assigned managed identity:

| Dependency | How | Key auth |
| --- | --- | --- |
| Fabric Warehouse | Workspace role + T-SQL schema grants on the API identity | Entra-only; no SQL logins |
| Fabric / OneLake | Workspace role on the API identity | — |
| Foundry | `Azure AI User` (shown as *Foundry User*), assigned by role id | Local auth disabled |
| Storage | `Storage Blob Data Contributor` on the API identity | Shared key disabled |
| Application Insights | `Monitoring Metrics Publisher` per identity | Entra-authorised ingestion |
| Channel gateway (when enabled) | Managed-identity token carrying the API's `TCC.Agent` role; object-level `INSERT, SELECT` on `tcc_ops.channel_audit` only; no schema grant | Entra-only; no SQL logins |
| App Service logs | Diagnostic settings to Log Analytics | No shared key |

Application Insights ingestion passes a credential, so the InstrumentationKey in
the connection string is not sufficient on its own.

`backend/tests/test_architecture.py` fails the build if a key is reintroduced,
which is the moment to ask whether the dependency supports Entra before reaching
for a vault. Add Key Vault only when something genuinely requires a secret, such
as a third-party API that does not support Entra.
## Data handling

All payroll data committed to this repository is synthetic — see
[DISCLAIMER.md](DISCLAIMER.md) for how that is verifiable rather than asserted.

If you connect this software to real payroll data, you are responsible for its
protection, and the gaps in the table above become your gaps.

## Dependencies

Python dependencies are pinned in `backend/requirements.txt`; JavaScript
dependencies in `frontend/package-lock.json`. Neither has been through a formal
supply-chain review. Run your own scanning before deploying into your
environment.

# Hardening plan (deferred) and the demo posture

**Status** Plan, deferred until after the demo · **Decided** 2 November 2026 · **Owner decisions** in §7

The demo of Teams, Copilot Chat and Cowork comes first. Full network hardening is **planned and
documented, not built**, so it cannot get in the way of the demo. The infrastructure change the demo
needs is one toggle (§2). Everything else here is for a later spike and build. Nothing in this document
is a claim that the hardened posture works: the Foundry paths in §3 are **per the documentation, unproven
until spike S6** ([HARDENING-SPIKE](../m365-channel/HARDENING-SPIKE.md)).

## 1. Two postures

| | **Demo posture (now)** | **Hardened posture (later)** |
| --- | --- | --- |
| Data | Synthetic only | Customer data allowed |
| Web portal | Public (public profile today), Entra sign-in | Private endpoint; reached by VPN or an ops VM |
| API | Private (VNet access restriction, unchanged) | Private |
| Channel gateway | **Public**, Entra-only (role and tenant checks), per-user rate limit | Private endpoint; reached by the orchestrator from the delegated agent subnet |
| Foundry data plane | **Public network access enabled**, Entra-only, local auth off (the toggle, §2); the private endpoint is still created | Public access off; account created **with network injection** |
| Hosted orchestrator | Microsoft-managed egress, calls the public gateway | Runs in the customer-delegated agent subnet; calls the gateway privately |
| Teams and Copilot Chat | Microsoft-managed Activity route (source-IP filtered) | Same (Microsoft requires a public route; it stays scoped and authenticated) |
| Cowork | Works (the gateway is public) | Needs a public MCP endpoint: off by default, behind a restricted toggle |
| Deployment | From the operator's workstation | From an in-VNet ops VM driven by `az vm run-command`, or a self-hosted runner |
| Spend | Lower | Adds Bastion, an ops VM, a private registry if an image is used, extra private endpoints |

**What stays strong in the demo posture:** every call is authenticated with Entra; there are no secrets;
the API is not public; writes need a writer and a two-step confirmation; every call is audited per user;
the data is synthetic. **What is weaker, and must be stated plainly in any demo:** the gateway and the
Foundry data plane are reachable from the internet (authenticated), and the acting user is a channel
assertion.

## 2. The one change the demo needs (built: CH-12b)

`infra/modules/foundry` creates the account with `publicNetworkAccess = "Disabled"` and
`networkAcls.defaultAction = "Deny"`. With that, **nothing outside the VNet can call the Foundry data
plane**: not the operator's `azd ai agent` deploy, not `scripts/publish-m365.ps1`, not
`scripts/create-model-connection.ps1`, not a workstation smoke test. The demo therefore has a switch.

| Input | azd value | Default | Meaning |
| --- | --- | --- | --- |
| `foundry_public_network_access` | `TCC_FOUNDRY_PUBLIC_NETWORK_ACCESS` | `false` | `true` sets `publicNetworkAccess = "Enabled"`. With no ranges `networkAcls.defaultAction = "Allow"`; with ranges it is `Deny` plus an `ipRules` entry per range. `disableLocalAuth` stays `true`; the private endpoint, DNS and the API's private path are unchanged |
| `foundry_allowed_ip_ranges` | `TCC_FOUNDRY_ALLOWED_IP_RANGES` | empty | IPv4 CIDRs allowed through the account firewall: a list, or a comma-separated string (what azd passes). A `/32` is sent as a bare address; `/31` is not supported by the firewall |
| `foundry_allow_any_ip` | (overlay only) | `false` | Permits `0.0.0.0/0` (any `/0`) in the list. A second, deliberate switch: an open range defeats the point of listing ranges |

Guards (all tested in `infra/tests/foundry_network*.tftest.hcl`): refused with the enterprise profile;
refused when `data_classification = customer`; every range must be an IPv4 CIDR; `/31` and any `/0`
refused unless the second switch is set; ranges without the toggle are refused rather than silently
ignored. The default plan is unchanged: the account body is byte for byte what it was and no extra resource
appears. The output `network_posture` reads `private` or `demo-public-foundry`, and turning the toggle on
prints a warning in the plan (a failed `check`, so it cannot be missed and does not block the demo).

**Tear it down after the demo.** Set the toggle back to `false` and apply: the account returns to
private. Anything the demo created while public (a hosted agent, a publish) stays valid.

## 3. The hardened build (later): requirements from the Foundry documentation

Sources, read on 2 November 2026: *Set up private networking for Foundry Agent Service*, *Deep dive into
Foundry Agent Service networking*, *Configure network isolation for Microsoft Foundry*, *Publish agents to
Microsoft Copilot and Teams by using the REST API*, and the hosted-agent runtime contract. **Re-read them
before building**: these features are in preview and move.

1. **Network injection must be set when the Foundry account is first created.** It cannot be added to an
   existing account for hosted agents. Hardening therefore means a **new account**, a replacement rather
   than an in-place edit. A deleted account soft-deletes for 48 hours and holds its custom subdomain; the
   module already purges on destroy.
2. **Agent subnet.** Dedicated, delegated to `Microsoft.App/environments`, a /24 recommended (/27 minimum),
   in an RFC 1918 or CGNAT range, name at most 63 bytes, **not shared** with another Foundry account, not
   overlapping the reserved ranges (`169.254.0.0/16`, `172.30.0.0/16`, `172.31.0.0/16`, `192.0.2.0/24`,
   `0.0.0.0/8`, `127.0.0.0/8`, `100.100.0.0/17`, `100.100.192.0/19`, `100.100.224.0/19`). The Foundry account
   must be in the **same region as the VNet**. Resource providers to register (an **operator** step;
   Terraform never registers them): `Microsoft.App`, `Microsoft.ContainerService`,
   `Microsoft.CognitiveServices`, `Microsoft.Network`, `Microsoft.BotService`.
3. **The Cosmos DB question (spike S6).** The documented *Standard setup with private networking* requires
   bring-your-own Cosmos DB, Storage and AI Search plus a capability host: the classic (Assistants-style)
   design for threads, files and vector stores. The hosted-agent path and the networking deep dive describe
   only a delegated subnet plus private endpoints to the customer's own Storage, SQL and Key Vault, with **no
   Cosmos, no Search and no capability host**. Our agents use no threads, files or vector stores.
   **The customer has ruled Cosmos DB out.** The hardened path must therefore prove a network-injected account
   running hosted and prompt agents with **no capability host and no Cosmos**, or **stop and escalate**. Do
   not add Cosmos to make it work.
4. **Container registry.** Prefer **source-code deployment** (no registry). If an image is used, a private
   registry (private endpoint, public access off) is supported for projects created after 25 June 2026; the
   registry then needs its own private endpoint and DNS. Source-code deployment from inside a private network
   needs outbound access to the endpoints under *Firewall requirements for private virtual networks*.
5. **Egress.** If an NSG or firewall is applied, allow the `AzureActiveDirectory` service tag and
   `control-{region}.identity.azure.net`, `{region}.login.microsoft.com`, `login.microsoftonline.com`, and the
   documented Container Apps managed-identity FQDNs; no TLS inspection on that path. Prefer an NSG over a
   firewall for the first build.
6. **Private endpoints and DNS zones.** Foundry (`privatelink.cognitiveservices.azure.com`,
   `privatelink.openai.azure.com`, `privatelink.services.ai.azure.com`), Storage (`blob`), Key Vault, App
   Service sites (`privatelink.azurewebsites.net`) for the web app and the gateway, a registry
   (`privatelink.azurecr.io`) if used, and Application Insights through an Azure Monitor Private Link Scope.
   Zones linked to the VNet; verify with `nslookup` from inside.
7. **Gateway private inbound.** A private endpoint on the gateway app, public network access off; the
   orchestrator (in the agent subnet) reaches it by private DNS. The gateway keeps its Entra validation.
   **Cowork** cannot reach a private endpoint: ship it **off** (`enable_cowork_public_mcp = false`); when on,
   it publishes a restricted public MCP surface (delegated token only, rate limited, optional IP allow-list)
   and the document states the exception.
8. **Bot Service.** `publicNetworkAccess: Disabled` on the bot resource, as in the Foundry documentation; the
   Activity route stays public but source-IP filtered and authenticated (`enable_m365_public_endpoint`), a
   Microsoft requirement.
9. **Deployment from inside.** An **ops VM** in the VNet (no public IP), reached by **Azure Bastion**,
   created by Terraform behind `enable_ops_host`; deployment scripts run on it through `az vm run-command
   invoke` (a control-plane call, no inbound network path) or a self-hosted runner; the VM has a managed
   identity with the minimum roles. Everything that calls a private data plane (azd, publish, smoke tests,
   grants) runs there.
10. **Identity and data.** Managed identities only; local auth disabled everywhere; Entra-only SQL; no shared
    keys; optional customer-managed keys; diagnostic settings to Log Analytics; Defender for Cloud
    recommendations reviewed.
11. **Fabric.** Private link is the customer's decision and is unchanged by this plan.

## 4. Verification design (built with the hardened posture)

- **`scripts/check-hardening.py`** (read-only; runs on the ops VM or anywhere with ARM access plus in-VNet
  DNS). For every resource it asserts: public network access disabled except the documented exceptions;
  private endpoints approved; private DNS zone links present; subnet delegation correct; no `0.0.0.0/0`
  rules; no local auth; the bot's `publicNetworkAccess` disabled; `enable_m365_public_endpoint` present on the
  agent only. It runs `nslookup` for each private FQDN from inside and asserts a private address. It prints a
  table and exits non-zero on any failure.
- **Terraform tests.** The hardened settings produce no public-access property anywhere except the
  documented exceptions; the agent subnet has the delegation and size; the gateway has a private endpoint.
- **Live.** From a workstation every data-plane call **fails** (403 or no route); from the ops VM they
  succeed; the Teams round trip works; Cowork returns "off" unless its toggle is on.

## 5. Spike S6: prove the hardened path (after the demo)

The runnable checklist, acceptance criteria and results template are in
[HARDENING-SPIKE](../m365-channel/HARDENING-SPIKE.md). In outline:

1. A new resource group and VNet, an agent subnet (/24, delegated), a private-endpoint subnet, DNS zones.
2. A Foundry account **with network injection** and a project: **no capability host, no bring-your-own
   Cosmos, Search or Storage for agents**; public access off; a private endpoint.
3. Deploy the stub orchestrator by source-code deployment from the ops VM; call it over the Responses
   protocol from the ops VM.
4. The agent calls a stub private endpoint (a gateway on an App Service with a private endpoint) and a model
   deployment.
5. Publish with `enable_m365_public_endpoint`; send a Teams message.

**Pass:** all of it, with no Cosmos. **Fail:** record the exact error; escalate to Microsoft Foundry
engineering and to the customer. The fallback is the demo posture with `data_classification = synthetic`.

## 6. Work packages for the later build

| ID | Work |
| --- | --- |
| HD-01 | Spike S6 as above; decision record |
| HD-02 | `network` module: agent subnet (delegated), private-endpoint subnet sizing, NSG, reserved-range validation |
| HD-03 | `foundry` module v2: account created with network injection (replace, not edit); private endpoints and DNS; purge-on-destroy kept |
| HD-04 | Gateway private endpoint; the `enable_cowork_public_mcp` toggle and a restricted public MCP surface |
| HD-05 | Ops host: Bastion, VM, managed identity, run-command wrapper scripts; deployment scripts parameterised to run there |
| HD-06 | A private registry only if an image is required; otherwise none |
| HD-07 | Azure Monitor Private Link Scope for Application Insights; diagnostic settings; Policy and Defender notes |
| HD-08 | `check-hardening.py`, Terraform tests, runbook, security review sign-off |

## 7. Owner decisions already taken

An ops host with Bastion driven by `az vm run-command`. The web portal stays public for the demo. Cowork and
Copilot Chat must work for the demo, so the demo posture keeps the gateway public; a pre-deployment toggle
controls the later private posture. **Cosmos DB is not acceptable.**

## 8. What this plan does not build

No agent subnet, no ops VM, no Bastion, no new private endpoints and no registry exist yet, and none is added
by the demo toggle. The toggle changes two properties on one resource.

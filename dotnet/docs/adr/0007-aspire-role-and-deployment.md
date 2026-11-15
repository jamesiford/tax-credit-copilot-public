# ADR 0007: Aspire's role and the multi-deployment story

Status: accepted (spike). Date: 2026-11-14.

## Decision

- **Aspire is a local developer and test orchestrator, and a source of defaults.** `TaxCredit.AppHost` (Aspire 13.6.5,
  MIT) describes local resources only: the API and a SQL Server container standing in for the warehouse. It builds and
  describes the resources; **no cloud deployment is performed or configured here.**
- `TaxCredit.ServiceDefaults` carries the shared OpenTelemetry, health (`/health`, `/alive`) and standard resilience
  defaults, so every host behaves the same whether started by Aspire, App Service or a container platform.
- The product's deployment contract stays what Python has today: `azd up`, Terraform, App Service (Linux), code-deployed,
  both apps on one plan. Aspire must not become a second way to deploy.

## Container Apps versus App Service (note, not a decision)

| | App Service (today) | Container Apps |
|---|---|---|
| Fit | Matches the current Terraform profiles and the "no container registry" rule | First-class Aspire publish target (`azd` can deploy an Aspire app host) |
| Cost of change | None | New registry, new networking and identity modules, a new operations story |
| Open question | A .NET 10 App Service deployment is straightforward | Who in the customer operates containers? (See SPIKE-REPORT open questions.) |

Recommendation: keep App Service for the first .NET deployment; use the app host only for local runs and integration tests.

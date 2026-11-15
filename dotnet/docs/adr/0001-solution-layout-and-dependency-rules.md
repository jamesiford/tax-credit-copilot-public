# ADR 0001: Solution layout and project dependency rules

Status: accepted (spike). Date: 2026-11-14.

## Context

The Python backend is layered `presentation -> application -> domain` with `infrastructure` implementing ports the
domain declares, composition in `bootstrap/`, and seventeen architecture tests that fail the build on a breach
(Python ADR-003). A .NET port must keep that property, and keep it enforced rather than described.

## Decision

```
dotnet/src/
  TaxCredit.Domain/          BCL only. Engine, value objects, Numerics (the Python compatibility layer).
  TaxCredit.Application/     Commands, queries, handlers, mediator, pipeline, ports. -> Domain only.
  TaxCredit.Infrastructure/  Adapters for the ports (rule packs, SQL, Delta/SQL endpoint, blob, Foundry). -> Application.
  TaxCredit.Api/             Minimal HTTP host and composition root. -> Application, Infrastructure, ServiceDefaults.
  TaxCredit.ServiceDefaults/ Telemetry, health, resilience. Knows no TaxCredit project.
  TaxCredit.AppHost/         Aspire app host (local orchestration only). -> Api.
dotnet/tests/
  TaxCredit.Domain.Tests / TaxCredit.Parity.Tests / TaxCredit.Architecture.Tests
```

Rules, all enforced by `TaxCredit.Architecture.Tests` against both the project files (declared) and the compiled
assemblies (used):

1. Dependencies point inward only. Domain references nothing but the BCL (no packages, no frameworks, no
   `System.Net`, `System.Data`, file system or process APIs).
2. Application references Domain and `Microsoft.Extensions.DependencyInjection.Abstractions` only; never
   Infrastructure, never a web framework.
3. Infrastructure implements Application's ports and never references Api.
4. Only Api (the composition root) names an adapter. Routers stay thin: parse, dispatch through the mediator, shape.
5. Public classes are `sealed`, `static` or `abstract`; no mutable public statics.
6. Each rule has a mutation self-test proving it can fail.

## Consequences

- The Domain stays a fast unit-test target: the parity gates need no I/O.
- Adding an adapter dependency in the wrong layer fails the build, not a review.
- The layout intentionally mirrors the Python packages so each slice of the strangler port has an obvious home.

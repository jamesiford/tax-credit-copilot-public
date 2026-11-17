# ADR 0003: Mediator choice

Status: accepted (spike). Date: 2026-11-14.

## Context

The architecture needs CQRS with pipeline behaviours (authorization, validation, audit). MediatR is the default
choice, but it changed licensing in 2025. Licence terms were re-read from the repositories on 2026-11-14.

## Options and licences (verified)

| Option | Licence as published | Notes |
|---|---|---|
| MediatR (`LuckyPennySoftware/MediatR`) | LICENSE says access is governed by the **Reciprocal Public License 1.5**; commercial licence keys are sold for use without RPL obligations | Reciprocal licence obligations are unacceptable for a product we ship or host for customers without legal review. |
| Mediator by martinothamar (`martinothamar/Mediator`) | **MIT** (GitHub licence detection) | Source generated, MediatR-shaped API, fast. Active (pushed 2026-09). |
| In-house mediator | Ours | About 50 lines (`Mediator.cs`), reflection-free after first call per request type, no third-party surface. |

## Decision

Start with the **in-house mediator** (`TaxCredit.Application.Messaging`). The abstractions (`IRequest`, `ICommand`,
`IQuery`, `IRequestHandler`, `IPipelineBehavior`) are the MediatR vocabulary, so swapping to the MIT source-generated
`Mediator` package later is a registration change, not a rewrite. Revisit if profiling shows the per-request dispatch
cost matters (the spike makes no performance claim).

## Consequences

- No licence exposure and no dependency to track.
- We own about 50 lines of dispatch code and its tests (`PipelineTests`).
- Open question to confirm with legal if MediatR is ever preferred: how RPL 1.5 applies to a hosted service.

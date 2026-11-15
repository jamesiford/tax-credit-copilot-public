# ADR 0002: Coding standards and conventions

Status: accepted (spike). Date: 2026-11-14.

## Decision

- **Clean Architecture, CQRS, SOLID, DRY.** Writes are commands, reads are queries; one use case per file, named for the
  use case. Every write passes the pipeline `Audit (outermost) -> Authorization -> Validation -> Handler`. There is
  deliberately no `TenantScope` stage: with no employer binding it would run and always pass, which reads as a control
  (Python ADR-008 and `test_the_pipeline_does_not_claim_stages_it_does_not_have`).
- **C# style.** File-scoped namespaces, `sealed` by default, immutable `record`s, `IReadOnlyList<T>`, `DateOnly`,
  constructor injection, no mutable statics. `Nullable` enabled, `TreatWarningsAsErrors`, analysis level
  `latest-recommended`, `.editorconfig` enforced in the build (`EnforceCodeStyleInBuild`), `dotnet format --verify-no-changes`.
- **Comments.** XML documentation on every public member of production code (CS1591 is an error). "Why" comments where a
  decision or a Python quirk is mirrored, citing the Python file and function and the rule id (BA-xx, CALC-xx).
- **Culture.** `InvariantGlobalization` is on, and CA1304/CA1305/CA1307/CA1309/CA1310 are errors: nothing in the engine may
  depend on the thread culture or on culture-sensitive comparison.
- **Python compatibility layer.** Anything Python does differently from the BCL lives in `TaxCredit.Domain.Numerics`
  with the Python behaviour it mirrors and why a built-in call is not equivalent. The engine never calls `Math.Round`,
  `(decimal)someDouble`, `string.CompareOrdinal`, `List<T>.Sort` or LINQ aggregates where Python semantics differ.
- **Line endings.** `dotnet/.gitattributes` fixes LF so `dotnet format` is stable on Windows and Linux.

## Deliberate relaxations

CA1711 (type name ends in `Delegate`) and CA1716 (parameter named `next`) are disabled: `RequestHandlerDelegate` and `next`
are the established mediator vocabulary.

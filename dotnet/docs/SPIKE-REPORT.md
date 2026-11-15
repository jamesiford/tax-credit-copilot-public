# Spike report: can the Python calculation engine be reproduced exactly in C#?

Branch `dotnet/spike` (local only, nothing pushed). Oracle: CPython 3.14.2, `backend/domain/calculation`. Date: 2026-11-14.

## Recommendation: GO, WITH CONDITIONS

The engine reproduced bit for bit: **zero mismatches** across 398,980 primitive vectors, 3,939 recorded engine scenarios and
520,000 differential-fuzz scenarios (20,000 + 500,000 under two seeds), comparing result trees, calculation trails with
their SHA-256 evidence hashes, and Python exception types. Nothing was found that cannot be matched, and no tolerance was
needed beyond treating NaN as NaN.

Conditions for a full port:

1. **The oracle interpreter is part of the contract.** Behaviour such as `sum()` compensation of ints (T-04) is specific to
   CPython 3.12+/3.14. Pin one Python version for goldens, and regenerate and re-run G1-G3 whenever it changes.
2. **Keep the compatibility layer and the harness as permanent assets**, not spike scaffolding: every later slice ports more
   Python behaviour through `Numerics`, and G1-G3 are what make each slice certifiable (ADR 0008).
3. **Decide the Delta read path before the data slice** (ADR 0005). It is the one genuinely open technical risk.
4. **Port, do not improve.** The engine has quirks (F-01..F-04); fixing them belongs after certification, with the partner.
5. **Scope of the proof is the pure calculation.** Rule-pack loading and credit math (S6) were not attempted in this spike.

## Results per gate

| Gate | Result | Evidence |
|---|---|---|
| **G1** numeric primitives | **PASS**, 100% identical | 398,980 vectors; 20 parity tests; mutation test shows BCL equivalents diverge |
| **G2** goldens | **PASS**, 0 of 3,939 scenarios differ | `parity-report.md`; 13 op groups; trail hashes and float-bit digests match |
| **G3** differential fuzz | **PASS**, 0 mismatches at N = 20,000 (seed 20261114) and N = 500,000 (seed 7) | 6,735 + 266 scenarios where Python raised were matched by exception type; each batch ran in a fresh Python process (fresh hash seed) |
| Mutation self-test | **PASS**, 3 of 3 caught | half-up becomes half-even, `>=` becomes `>`, sort tie-break reversed, each in a copy of the port, each failing both goldens and fuzz |
| **G4** rule packs and credit math (S6) | **not run** | stretch stage; `RUN_STRETCH_S6` was not set |

Build quality: `dotnet build -warnaserror` 0 warnings, `dotnet format --verify-no-changes` clean, 18 domain + 13 architecture +
51 parity tests green.

## Catalogue of Python-to-C# traps (details in `findings.md`)

Found and handled: `round()` half-even on the exact binary value (T-01); `Decimal(str(x))` and the 28-digit
`InvalidOperation` (T-02); `repr` layout (T-03); **`sum()` Neumaier compensation, including ints after the first float in
3.14 (T-04)**; floor division and modulo (T-05); division by zero (T-06); date overflow and ISO week dates (T-07);
`min`/`max` with signed zero and NaN (T-08); code point string ordering (T-09); full-Unicode `upper()` and `strip()` (T-10);
`float(str)` grammar (T-11); NaN sign (T-12); oracle version (T-13); **C# `?:` silently promoting `long` to `double`
(T-14)**; `List.Sort` wrapping exceptions (T-15); `None` keys and ordering (T-16); `json.dumps` canonical bytes for the
evidence hash (T-17); `None` versus absent versus `""` cells (T-18).

**Biggest trap:** a numeric one that is easy to miss: the C# conditional operator turning an int into a float made 1,160
results print `2023.0` for `2023`. It does not fail a numeric comparison, only a type-aware one, which is why the harness
compares int against float and key order, not just values.

## What was ported, and what it implies

| | Python | C# |
|---|---|---|
| Engine (`onezero` run methods and helpers, `headcount`, `fiscal`, `floors`, `trail`) | about 1,400 lines | about 2,050 lines (with XML docs) |
| Python compatibility layer (`Numerics`) | n/a | about 1,500 lines plus a generated 1,552-entry case table |
| Parity harness (tests) | about 900 lines of exporters | about 2,400 lines |

The pure-logic expansion is about 1.5x including documentation. The backend has about 70,000 non-test Python lines in 540
files, but most of that is adapters, agents, scripts and data generation, not statutory arithmetic; the calculation core is
small and, as this spike shows, well specified by its own outputs. The harness (not the port) is where the effort sits, and
it is reusable.

## Micro-benchmark (numbers only, single thread, minimum of 5)

| Data | Python | C# (Release, unoptimised first port) |
|---|---|---|
| synthetic 9,477 rows, Pay Period | 97.5 ms | 43.7 ms |
| synthetic 9,477 rows, Min-Max | 42.8 ms | 30.6 ms |
| generated 189,540 rows, Pay Period | 1,756 ms | 400 ms |
| generated 189,540 rows, Min-Max | 865 ms | 279 ms |

The port deliberately re-parses dates on every use exactly as Python does; caching parsed dates would change nothing
observable and is an obvious later optimisation. No performance claim is made beyond these numbers.

## Risks found

- **Oracle drift:** a new Python version can change float and `sum` behaviour (T-04). Mitigation: condition 1.
- **Set iteration order (F-02):** Python sums weeks over a `set` of strings, so order depends on the hash seed. No output
  difference was seen across nine fixed seeds and 520,000 random-seed fuzz scenarios, and the compensated sum explains why
  (benign, not provably impossible). The port sums in first-seen order.
- **Unmodelled input shapes:** numeric identifier or date cells, NaN/infinite hours, `Decimal` NaN. They raise
  `PyUnsupportedException` instead of diverging; confirm production inputs never carry them (the lakehouse adapter emits ISO strings).
- **Latent engine quirks (F-01, F-03):** a part-time weight of 0 disables the band; the measuring date accepts Unicode digits.
- **Data read path (ADR 0005):** the Delta version gap is not solved by .NET; it is a platform question.

## Proposed slice order for the full port

1. **Domain and Application first.** The rest of `domain/` (proximity, reconciliation, rollups, performance), then
   `tools/credit_math.py`, `program_credit.py`, rule-pack loading behind `IRulePackSource` (this is stretch stage S6 / gate G4).
   Same harness: add scenario families to `parity/matrix.py`, port, replay.
2. **API.** Slice by route group behind a reverse proxy (ADR 0008). The recordings from `D-KICKOFF-CONTRACT-CAPTURE.md`
   are the contract for the 88 routes (about 70 untyped). The .NET host should reuse that harness's recorded exchanges and its
   comparison conventions (ordered keys, int versus float, exception names), and `ParityTests/JsonTree.Diff` is a ready-made
   strict comparer for it. The pipeline, mediator and architecture rules are already in place.
3. **Channel gateway and orchestrator.** Microsoft Agent Framework (`Microsoft.Agents.AI` 1.28.0 is stable in the feed;
   `Microsoft.Agents.AI.Foundry` and `.Hosting` are `1.28.0-preview`; `Azure.AI.AgentServer.Responses` is `1.0.0-beta.9`).
   The numeric guard of ADR-008 (agents narrate, tools calculate) ports as is.
4. **Scripts** (migrations, grants, seeding, packaging) last; they are operational, not statutory.

**Delta read gap:** build the SQL-endpoint adapter (ADR 0005 option A) behind `IPayrollSource` first, carry the "no Delta
version" gap as a named risk, and decide on a fingerprint or Silver version marker with the data owners before the data slice.

## Open questions

- **Delta reading from .NET.** Throughput over the Fabric SQL endpoint at row grain; whether a content fingerprint can
  stand in for a Delta version; `DeltaLake` is `0.1.0-rc.8` (pre-1.0, native binaries, not Microsoft-supported); `Parquet.Net`
  is at `6.1.1-pre.1` in this feed. All unverified against a real capacity.
- **EF Core on Fabric Warehouse.** Tenant filters on the `tcc_ops` tables are straightforward; whether `SqlBulkCopy` is
  supported on Fabric Warehouse is **unverified** (tested nowhere in this spike) and migrations are never run against it (ADR 0006).
- **Hosted agent and Teams pieces on .NET.** Verify the maturity of the Foundry hosting packages (preview) and
  `Azure.AI.AgentServer.Responses` (beta). The official C# MCP SDK is `ModelContextProtocol` 2.4.0 in this feed without a
  preview suffix, which supersedes the earlier "v1.0 with a preview notice" picture: re-check the NuGet page and licence
  (the repository states an MIT to Apache-2.0 transition).
- **Mediator and library licences.** MediatR is RPL 1.5 or commercial; the spike uses an in-house mediator (ADR 0003).
  FluentAssertions 8 is under the Xceed community licence; not used (ADR 0004).
- **What the customer's engineers can operate.** The skeleton uses App Service-friendly defaults and treats Aspire as a
  local tool (ADR 0007); whether Experian's engineers can run containers, Terraform and .NET services is not answered here.
- **Python interpreter pinning** for the oracle in CI (condition 1).

## Reviewer attention (`NEEDS-HUMAN-REVIEW`)

1. **T-12 NaN equality.** The only relaxation of bit equality (all NaNs equal; .NET's NaN has the sign bit set, Python's does not). Low risk; flagged as required.
2. **Float encoding in goldens.** Engine goldens store doubles as JSON `repr` numbers, not repr plus hex per value (size); a separate SHA-256 over the IEEE bytes of every double backs bit equality. The brief asked for repr and hex.
3. **Python files.** Only new files under `parity/` were added; no existing Python file was edited.

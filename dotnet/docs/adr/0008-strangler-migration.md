# ADR 0008: Strangler migration approach

Status: proposed. Date: 2026-11-14.

## Decision

Python and .NET run **side by side behind a reverse proxy**, and the API moves **slice by slice**. A slice is a route group
plus the use cases behind it. Each slice is certified against **recorded Python behaviour** before traffic moves:

1. **Engine first (this spike).** The pure calculation is proven bit-for-bit against goldens and differential fuzzing (gates
   G1-G3; G4 for rule packs and credit math).
2. **Contract recordings.** For the HTTP surface, the recordings produced by `D-KICKOFF-CONTRACT-CAPTURE.md` are the contract
   (the routes are mostly untyped, so no schema can stand in for them). A slice is done when the .NET host reproduces its
   recorded exchanges.
3. **Shadow, then switch.** The proxy mirrors a slice to both stacks, compares responses off the hot path, and flips the route
   when the diff is clean for an agreed window. The Python route stays deployable until the next release.
4. **Order.** Domain and Application, then API, then the channel gateway and orchestrator, then scripts.

## Rules

- The Python engine remains the oracle; a C# result that disagrees is a C# bug unless it is recorded in `findings.md` as a Python defect and approved.
- No behaviour change rides along with a port. Improvements land after the slice is certified.
- The certified figures (10,236 employees, 539 Min-Max eligible, 656 Pay Period eligible) are a gate for every slice that can move them.

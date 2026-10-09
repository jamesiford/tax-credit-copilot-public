"""The domain layer: entities, value objects, and ports. [ADR-003]

Pure. Standard library only — no framework, no I/O, no async. Everything here
is either a fact about the business or an interface the outer layers implement.

`infrastructure/` implements the ports this layer declares; `api/` orchestrates.
Dependencies point inward, so nothing in here may import from either.
"""

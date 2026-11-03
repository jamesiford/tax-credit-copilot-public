"""Capability layer: transport-neutral tools over the application's queries.

A capability is a plain function that returns a `ToolResult` — the engine's
figures (`facts`), platform-rendered text built only from them (`blocks`), and
where they came from (`provenance`). The portal chat and the Microsoft 365
channel both call these; neither owns the compute.

This package imports no web framework, no `api.*` module and no agent code, and
`catalog.py` and `format.py` import nothing outside the standard library so they
can be vendored into the orchestrator container unchanged. `test_architecture`
enforces all three.

This file is deliberately empty of imports: importing a single module (the
catalog, say) must not pull in the engine. `registry.py` is the one place that
does.
"""

"""The composition root: the only package that names an adapter. [ADR-003, RM-17]

`presentation -> application -> domain`, and `infrastructure` implements the ports
the inner layers declare. Something has to know which adapter backs which port, and
that something cannot sit inside `application` (it would import `infrastructure`) or
inside `infrastructure` (it would import the use cases). It sits outside both.

Named `bootstrap`, not `wiring` or `composition`: `wiring` is what the modules in it
do, and the word was already a module name in three layers (the gateway's, the
orchestrator's and this one); `bootstrap` says WHEN it runs (process start-up) and
that it is the outermost ring, which is the rule the architecture test enforces:
nothing in `application`, `domain` or `infrastructure` imports it.

- `wiring`          claims, findings, runs, Gold, artifacts, identity, the mediator
- `channel_wiring`  the channel's stores; imports no handler, so the gateway can use it alone
- `data_wiring`     the governed data-query service
- `ai_wiring`       model access, narration, telemetry
- `source_binding`  payroll and source-catalogue adapters behind `application.source_ports`

This file imports nothing: importing the package must not load the engine, because
the channel gateway imports `bootstrap.channel_wiring` and must stay light.
"""

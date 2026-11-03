"""Use cases. What the system does, expressed independently of how it is called.

A router turns HTTP into a request object and a result into JSON. A handler here
performs the actual use case. The split means the same use case can be driven by
an HTTP call, a scheduled job, or a data pipeline without being rewritten - and
moving the calculation into Fabric is on the roadmap.

`mediator` dispatches; `wiring` is the composition root and holds every binding.
"""

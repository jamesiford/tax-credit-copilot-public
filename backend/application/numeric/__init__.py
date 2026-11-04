"""The numeric integrity guard and the parts it is built from. [ADR-008]

One package so the guard, its numeral extraction, the reader-supplied context and the fact
index sit together; `from application.numeric import check` is the short path. Submodules:
`guard` (the rule), `types`, `extract`, `context`, `facts`. Standard library only, and all of
it is vendored into the orchestrator container.
"""
from application.numeric.guard import (  # noqa: F401 - the package's public surface
    PASS, REJECTED, AllowedContext, FactIndex, GuardResult, Numeral, Violation, check, check_raw,
)

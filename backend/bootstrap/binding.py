"""Binding a composition module's getters into the application's service names. [ADR-003]

`application.services` holds the names a handler may ask for; this registers, for each,
a provider that looks the getter up on its module at CALL time. A lookup at call time
(not a captured function) is what keeps `monkeypatch.setattr(wiring, "get_x", ...)`
and a re-export's `set_x` effective for the handlers that ask.
"""
from __future__ import annotations

import sys

from application.services import provide


def bind(module_name: str, **services: str) -> None:
    """Register `service=getter_name` pairs, resolving `getter_name` on `module_name` per call."""
    module = sys.modules[module_name]
    for service, getter in services.items():
        provide(service, lambda getter=getter: getattr(module, getter)())

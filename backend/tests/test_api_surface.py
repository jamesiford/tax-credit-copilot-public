"""The public API surface, pinned.

Splitting a router is mechanical and usually safe — but a copy that starts at
the `def` line and not at the decorator above it moves the function and leaves
the route behind. That deletes an endpoint **silently**: the module imports, the
tests that call the function directly still pass, and only a client discovers
the 404. It happened during exactly such a split, and nine routes disappeared at
once.

`route_inventory.json` is the contract. Adding a route means updating it
deliberately; removing one means saying so out loud. Neither should be possible
by accident during a refactor.
"""
from __future__ import annotations

import json
from pathlib import Path

INVENTORY = Path(__file__).resolve().parent / "route_inventory.json"


def _live_routes() -> list[str]:
    from main import app

    return sorted(
        f"{method} {route.path}"
        for route in app.routes
        for method in (getattr(route, "methods", set()) or {"GET"})
        if method not in {"HEAD", "OPTIONS"} and str(route.path).startswith("/api")
    )


def test_no_route_has_disappeared():
    """The failure mode this exists for: a refactor that drops an endpoint."""
    expected = set(json.loads(INVENTORY.read_text(encoding="utf-8")))
    actual = set(_live_routes())

    missing = sorted(expected - actual)
    assert not missing, (
        f"{len(missing)} route(s) vanished:\n  " + "\n  ".join(missing)
        + "\n\nIf this is deliberate, update tests/route_inventory.json in the "
        "same commit so the removal is reviewable. If it is not, a decorator "
        "was probably left behind when a handler moved."
    )


def test_new_routes_are_declared():
    """Additions are fine; undeclared additions are how the surface sprawls."""
    expected = set(json.loads(INVENTORY.read_text(encoding="utf-8")))
    actual = set(_live_routes())

    added = sorted(actual - expected)
    assert not added, (
        f"{len(added)} undeclared route(s):\n  " + "\n  ".join(added)
        + "\n\nAdd them to tests/route_inventory.json so the API surface stays "
        "something we decide rather than something that accumulates."
    )


def test_every_route_is_reachable_through_a_registered_router():
    """A handler defined but never included is dead code that looks alive."""
    from main import app

    # The floor is a canary against a router silently dropping out of
    # `include_router`, not a target. It was 70 while the app still carried the
    # pre-portal routers; the surface is now deliberately 53. `route_inventory`
    # pins the exact set — this only catches wholesale collapse.
    assert len(_live_routes()) >= 50, (
        "the API surface collapsed — check that every router is still passed to "
        "app.include_router()"
    )
    duplicates = [r for r in _live_routes() if _live_routes().count(r) > 1]
    assert not duplicates, f"the same route is registered twice: {sorted(set(duplicates))}"

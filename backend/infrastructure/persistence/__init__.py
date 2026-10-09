"""Persistence adapters. One per port per store. [ADR-007]

SQLite is the dev and CI adapter, the Fabric Warehouse the production one, and both are
first-class implementations tested against the same contract suite — the SQLite
one is not a fallback or technical debt. CI must not need a Warehouse to
run the suite, and the reference parity gate must stay a fast unit test rather than
becoming an integration test.
"""

"""Builds and validates the Copilot Cowork plugin package. [CH-10]

The package is an ordinary Microsoft 365 app package: a manifest, two icons and a
set of skills, plus one connector that points at the channel gateway's `/mcp`.
Everything deployment-specific arrives through `settings`, so the committed tree
is customer-neutral and the same sources build for any tenant.

Run it through `scripts/build-cowork-plugin.py`; the tests import the modules.
"""

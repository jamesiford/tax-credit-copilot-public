"""Governed, structured, read-only data access for the agent. [CH-16]

Nothing in this package writes SQL on a model's behalf. A reviewed *semantic model* says
what can be queried; a *specification* says what is being asked; the builder turns the
second into a statement using only the first. Standard library only, so the same code
runs in the API, in tests and in a future pipeline.
"""

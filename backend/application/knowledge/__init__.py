"""Cited reference text for the agents, never a figure. [RM-15, ADR-010]

`port` is the contract (`KnowledgePort`, `Passage` and how a passage is rendered), `fake` the
synthetic in-memory implementation and `settings` the disabled-by-default configuration. The
names below are the port's, so `from application.knowledge import Passage` is the import path;
`fake` and `settings` are imported by their full name, which keeps this package importable
without either. Vendored into the orchestrator.
"""
from application.knowledge.port import (  # noqa: F401 - the package's public surface
    MODEL_HEADER, READER_HEADER, KnowledgeError, KnowledgePort, Passage, model_context,
    render_passage, render_reference,
)

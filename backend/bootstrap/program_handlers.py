"""The program catalog and program draft handlers, bound to their requests. [F05]

Kept beside `handlers.py` rather than in it: that module is the dispatch table for the engine's own requests and sits at the
size standard. `register_handlers` calls `register_program_handlers`, so the one table is still composed in one root.
"""
from __future__ import annotations

from application.mediator import Mediator
from application.queries.program_catalog_reads import (
    GetProgramDetailQuery, ListProgramCatalogQuery, handle_get_program_detail, handle_list_program_catalog,
)


def register_program_handlers(mediator: Mediator) -> Mediator:
    mediator.register(ListProgramCatalogQuery, handle_list_program_catalog)
    mediator.register(GetProgramDetailQuery, handle_get_program_detail)
    return mediator

"""Read the program catalog: the list and one program's detail. [F05.1]

Two small queries so the router and the channel capability go through the mediator like every other read. The work is
`application/program_catalog.py`; a read changes nothing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.mediator import Query
from application.program_catalog import catalog_detail, list_catalog


@dataclass(frozen=True)
class ListProgramCatalogQuery(Query):
    """Every registered program with its lifecycle, authored years, engagement counts and whether it can be calculated."""


@dataclass(frozen=True)
class GetProgramDetailQuery(Query):
    """One program: pack metadata, per-year status, validation results and what blocks calculation."""
    code: str = ""


def handle_list_program_catalog(query: ListProgramCatalogQuery) -> dict[str, Any]:
    return list_catalog()


def handle_get_program_detail(query: GetProgramDetailQuery) -> dict[str, Any]:
    return catalog_detail(query.code)

"""Fixtures for the data-capability tests: a real service over the shared two-client SQLite database. [CH-16d]"""
from __future__ import annotations

import pytest

from bootstrap.channel_wiring import set_writer_entitlement
from application.data.limits import QueryLimits
from application.data.semantic_model import Source, default_model
from application.data.service import DataQueryService
from bootstrap.data_wiring import set_data_query_service
from application.identity import PRINCIPAL_AGENT, ActingUser, Principal
from infrastructure.persistence.sqlite_data_query import SqliteDataQueryExecutor
from tests.data_fixture import CLIENT_A, build_database

WRITER_OID = "bbbbbbbb-0000-4000-8000-000000000002"
READER_OID = "cccccccc-0000-4000-8000-000000000003"
MODEL = default_model()


class Writers:
    """The entitlement: `WRITER_OID` may change things, nobody else may."""

    def is_writer(self, oid: str) -> bool:
        return oid == WRITER_OID


def person(oid: str = READER_OID, channel: str | None = "teams") -> Principal:
    """The channel gateway acting for a person, as the API sees it (`channel` None is a signed-in portal user)."""
    if channel is None:
        return Principal(oid=oid, authenticated=True)
    acting = ActingUser(oid=oid, display_name="Pat", channel=channel, conversation_id="c1", correlation_id="x1")
    return Principal(oid="gateway", principal_type=PRINCIPAL_AGENT, acting_for=acting, authenticated=True)


#: The fixture holds two people per client, so the shared service runs at the smallest K the rule allows;
#: `tests/test_data_small_groups.py` runs the default K=5 over a database built for it.
FIXTURE_LIMITS = QueryLimits(min_group_size=2)


def make_service(sources=(Source.WAREHOUSE, Source.LAKEHOUSE), **kwargs) -> DataQueryService:
    executor = SqliteDataQueryExecutor(lambda db=build_database(MODEL): db)
    kwargs.setdefault("limits", FIXTURE_LIMITS)
    return DataQueryService(MODEL, {s: executor for s in sources}, **kwargs)


@pytest.fixture()
def data_service():
    service = make_service(limits=FIXTURE_LIMITS)
    set_data_query_service(service)
    set_writer_entitlement(Writers())
    yield service
    set_data_query_service(None)
    set_writer_entitlement(None)


CLIENT = CLIENT_A

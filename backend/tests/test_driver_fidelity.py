"""The pyodbc doubles refuse what the real driver refuses. [F07.1]

The footprint guard once assigned `cursor.timeout`, which `pyodbc.Cursor` does not have; the
hand-written cursor double took any assignment, so the suite passed while every live read
failed. These tests pin the model that closes that gap and the doubles that now use it.
"""

from __future__ import annotations

import importlib

import pytest

from tests.driver_fidelity import (
    CONNECTION_READ_ONLY,
    CONNECTION_WRITABLE,
    CURSOR_READ_ONLY,
    CURSOR_WRITABLE,
    PyodbcConnectionModel,
    PyodbcCursorModel,
)

pyodbc = pytest.importorskip("pyodbc")


def _writable(cls: type) -> set[str]:
    """Public data members a Python caller may assign (a getset/member descriptor with a setter)."""
    out = set()
    for name in dir(cls):
        if name.startswith("_"):
            continue
        member = getattr(cls, name)
        if type(member).__name__ in ("member_descriptor", "getset_descriptor"):
            out.add(name)
    return out


def test_the_model_names_exactly_the_data_members_of_the_installed_driver():
    assert CURSOR_WRITABLE | CURSOR_READ_ONLY == _writable(pyodbc.Cursor)
    assert CONNECTION_WRITABLE | CONNECTION_READ_ONLY == _writable(pyodbc.Connection)


def test_a_real_cursor_has_no_timeout_and_the_model_agrees():
    assert not hasattr(pyodbc.Cursor, "timeout")
    with pytest.raises(AttributeError):
        PyodbcCursorModel().timeout = 5


def test_read_only_members_cannot_be_assigned_on_the_model():
    cursor = PyodbcCursorModel()
    for name in CURSOR_READ_ONLY:
        with pytest.raises(AttributeError):
            setattr(cursor, name, 1)
    connection = PyodbcConnectionModel()
    connection.autocommit = True
    connection.timeout = 5
    with pytest.raises(AttributeError):
        connection.closed = True
    with pytest.raises(AttributeError):
        connection.rollbacks = 0


_DOUBLES = [
    ("tests.sql_endpoint_fake", "_Cursor"),
    ("tests.data_query_fakes", "FakeCursor"),
    ("tests.test_channel_audit", "_Cursor"),
    ("tests.test_schema_admin", "FakeCursor"),
    ("tests.test_stranded_runs", "_FakeCursor"),
    ("tests.test_pooled_cursors_close", "_Cursor"),
]


@pytest.mark.parametrize(("module", "name"), _DOUBLES, ids=[f"{m}.{n}" for m, n in _DOUBLES])
def test_every_cursor_double_models_the_driver(module, name):
    cls = getattr(importlib.import_module(module), name)
    assert issubclass(cls, PyodbcCursorModel), "a cursor double that takes any assignment hides driver misuse"


def test_the_lakehouse_endpoint_double_no_longer_carries_a_cursor_timeout():
    """The old double set `timeout = 0` on its cursor, which is how a cursor-level assignment passed."""
    from tests.sql_endpoint_fake import _Cursor

    assert "timeout" not in vars(_Cursor)
    with pytest.raises(AttributeError):
        _Cursor.__new__(_Cursor).timeout = 20


def test_credential_doubles_hand_back_the_driver_token_type():
    """`azure.core` tokens carry `token` and `expires_on`; a double returning only `token` hides a read of the second."""
    from azure.core.credentials import AccessToken

    from tests.test_ai_gateway import _FakeCredential

    token = _FakeCredential("api://x").get_token("api://x/.default", claims="c")
    assert isinstance(token, AccessToken) and token.expires_on

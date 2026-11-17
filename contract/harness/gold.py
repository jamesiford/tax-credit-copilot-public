"""The Gold reader the harness serves from: the fixture's `SqliteGoldReader`, plus the T-SQL forms it does not yet translate.

`backend/tests/data_engine_fixture.py` translates `SELECT TOP n` and the OFFSET/FETCH page clause. The unit drill also issues
`SELECT DISTINCT TOP n`, which SQLite rejects (a 500 in the fixture world that the deployed Warehouse would not give). The
translation lives here, in the harness, because the product and the test helper must not be edited; every statement is still the
product's own.
"""
from __future__ import annotations

import re
from typing import Any

from tests.data_engine_fixture import SqliteGoldReader

_DISTINCT_TOP = re.compile(r"SELECT DISTINCT TOP\s*\(?(\d+)\)?\s+", re.IGNORECASE)


class ContractGoldReader(SqliteGoldReader):
    def _run(self, statement: tuple[str, list[Any]]) -> list[dict[str, Any]]:
        sql, values = statement[0], list(statement[1])
        match = _DISTINCT_TOP.search(sql)
        if match:
            sql = f"{_DISTINCT_TOP.sub('SELECT DISTINCT ', sql, count=1).rstrip().rstrip(';')} LIMIT {int(match.group(1))}"
        return super()._run((sql, values))

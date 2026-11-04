"""Execute a built data query on the Lakehouse SQL analytics endpoint. [CH-16c]

The Warehouse executor's T-SQL core over the lakehouse's own endpoint, for the source payroll
datasets (`tcc_source`, keyed on `AccountId`). Held under the same tenant rule as the Warehouse
adapters in `tests/test_architecture.py`.
"""
from __future__ import annotations

from typing import Any

from infrastructure.persistence.lakehouse_sql_connection import LakehouseSqlConnection
from infrastructure.persistence.warehouse_data_query import TsqlDataQueryExecutor


class LakehouseDataQueryExecutor(TsqlDataQueryExecutor):
    """T-SQL on the lakehouse endpoint; unavailable (typed) until its server and database are set."""

    label = "lakehouse"

    def __init__(self, connection: Any = None) -> None:
        super().__init__(connection or LakehouseSqlConnection())

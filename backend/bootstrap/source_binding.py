"""Payroll, source-catalogue and Gold-store adapters, bound behind the application's ports. [RM-17]

`application.source_ports` and `application.gold_ports` name what a use case needs;
this is the one place that says the answer is `infrastructure.payroll` and the Fabric
warehouse. Each method imports its adapter at call time, as the use cases did before,
so a test that replaces an adapter function, or an environment that changes
`DATA_SOURCE`, is honoured exactly as it was.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from application.services import provide


class InfrastructurePayrollSource:
    """`PayrollSource` over `infrastructure.payroll`."""

    def configured_account_id(self) -> int:
        from infrastructure.payroll import pay_period_source

        return pay_period_source.configured_account_id()

    def load_pay_periods(self, account_id: int | None = None) -> list[dict[str, Any]]:
        from infrastructure.payroll import pay_period_source

        return pay_period_source.load_pay_periods(account_id)

    def load_portfolio_pay_periods(self) -> dict[int, list[dict[str, Any]]]:
        from infrastructure.payroll import pay_period_source

        return pay_period_source.load_portfolio_pay_periods()

    def client_fiscal_window(self, account_id: int | None, tax_year: int, convention: Any) -> Any:
        from infrastructure.payroll import fiscal_source

        return fiscal_source.client_fiscal_window(account_id, tax_year, convention)

    def window_for_state_year(self, account_id: int | None, state: str, tax_year: int) -> tuple[date, date] | None:
        from infrastructure.payroll import fiscal_source

        return fiscal_source.window_for_state_year(account_id, state, tax_year)


def _new_source_reader() -> Any:
    from infrastructure.persistence import source_sql

    return source_sql.SourceSqlReader()


class InfrastructureSourceCatalogue:
    """`SourceCatalogue` over the source SQL reader, falling back to the rows the payroll source yields."""

    def payroll_scope(self, account_id: int) -> Any:
        """Asked as a `GROUP BY` where the source supports one.

        The row path is still correct and still used by the fixture sources, but it
        materialises 384,433 dicts to answer three `DISTINCT`s — ~3s of GIL-bound CPU
        per request, on an endpoint that returns half a kilobyte.
        """
        from infrastructure.payroll.pay_period_source import load_pay_periods
        from infrastructure.persistence.source_sql import SourceSqlReader, payroll_scope_from_rows
        from tools.fabric_source import active_data_source

        if active_data_source() == "lakehouse":
            reader = SourceSqlReader()
            if reader.is_configured():
                return reader.payroll_scope(account_id)
        return payroll_scope_from_rows(load_pay_periods(account_id))

    def shared_scope(self) -> Any:
        from infrastructure.persistence.source_sql import shared_scope

        return shared_scope()


def _section_9_query_count() -> int:
    from infrastructure.persistence import warehouse_gold

    return len(warehouse_gold.SECTION_9_QUERIES)


def _reap_stranded_runs() -> int:
    from infrastructure.persistence import warehouse_gold

    return warehouse_gold.GoldWriter().reap_stranded_runs()


def _gold_run_envelope() -> Any:
    from infrastructure.persistence import gold_reader

    return gold_reader.run_envelope


def _gold_filters(name: str) -> Any:
    from infrastructure.persistence import gold_reader

    return getattr(gold_reader, name)


_payroll = InfrastructurePayrollSource()
_catalogue = InfrastructureSourceCatalogue()

provide("payroll_source", lambda: _payroll)
provide("source_catalogue", lambda: _catalogue)
provide("source_reader_factory", lambda: _new_source_reader)
provide("section_9_query_count", lambda: _section_9_query_count)
provide("reap_stranded_runs", lambda: _reap_stranded_runs)
provide("gold_run_envelope", _gold_run_envelope)
provide("gold_employee_filters", lambda: _gold_filters("EMPLOYEE_FILTERS"))
provide("gold_near_filters", lambda: _gold_filters("NEAR_FILTERS"))

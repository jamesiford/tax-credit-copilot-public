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


def _section_9_query_count() -> int:
    from infrastructure.persistence import warehouse_gold

    return len(warehouse_gold.SECTION_9_QUERIES)


def _reap_stranded_runs() -> int:
    from infrastructure.persistence import warehouse_gold

    return warehouse_gold.GoldWriter().reap_stranded_runs()


_payroll = InfrastructurePayrollSource()

provide("payroll_source", lambda: _payroll)
provide("source_reader_factory", lambda: _new_source_reader)
provide("section_9_query_count", lambda: _section_9_query_count)
provide("reap_stranded_runs", lambda: _reap_stranded_runs)

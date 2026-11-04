"""The payroll and source-catalogue ports the use cases read through. [ADR-003]

Handlers used to import `infrastructure.payroll` and `infrastructure.persistence.source_sql`
directly, which put the layer that implements these reads underneath the one that asks
for them. The Protocols name the capability; the module-level functions keep every call
site as it was (`load_pay_periods(client_id)`) and resolve the bound adapter on each call,
so a test that swaps the source, or an environment that changes `DATA_SOURCE`, is honoured.
The composition root (`bootstrap/source_binding.py`) is the only place that names the adapters.
"""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any, Protocol

from application.services import resolve

if TYPE_CHECKING:
    from domain.calculation.fiscal import FiscalWindow, TaxYearLabel


class PayrollSource(Protocol):
    """Where pay-period rows and a client's fiscal calendar physically come from."""

    def configured_account_id(self) -> int: ...

    def load_pay_periods(self, account_id: int | None = None) -> list[dict[str, Any]]: ...

    def load_portfolio_pay_periods(self) -> dict[int, list[dict[str, Any]]]: ...

    def client_fiscal_window(
        self, account_id: int | None, tax_year: int, convention: TaxYearLabel
    ) -> FiscalWindow: ...

    def window_for_state_year(
        self, account_id: int | None, state: str, tax_year: int
    ) -> tuple[date, date] | None: ...


class SourceReader(Protocol):
    """The client book and the payroll footprint, over the source schema."""

    def is_configured(self) -> bool: ...

    def list_accounts(self) -> list[dict[str, Any]]: ...

    def footprint(self) -> dict[int, list[str]]: ...


def _payroll() -> PayrollSource:
    return resolve("payroll_source")


def configured_account_id() -> int:
    return _payroll().configured_account_id()


def load_pay_periods(account_id: int | None = None) -> list[dict[str, Any]]:
    return _payroll().load_pay_periods(account_id)


def load_portfolio_pay_periods() -> dict[int, list[dict[str, Any]]]:
    return _payroll().load_portfolio_pay_periods()


def client_fiscal_window(account_id: int | None, tax_year: int, convention: TaxYearLabel) -> FiscalWindow:
    return _payroll().client_fiscal_window(account_id, tax_year, convention)


def window_for_state_year(account_id: int | None, state: str, tax_year: int) -> tuple[date, date] | None:
    return _payroll().window_for_state_year(account_id, state, tax_year)


def new_source_reader() -> SourceReader:
    """A fresh reader over the source schema; cheap, and cached state lives in the adapter."""
    return resolve("source_reader_factory")()

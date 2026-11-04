"""What a use case may ask of the Gold store's read side, without naming the adapter. [RM-19, ADR-003]

`GoldReadPort` is the whole read surface, composed from one small protocol per group of
reads. `infrastructure.persistence.gold_reader.GoldReader` (Fabric Warehouse, T-SQL) is the
implementation; the offline suite runs the same class over SQLite by replacing its two
execution hooks, so every statement and every coercion is the real one. A handler gets
the port from `application.services.get_gold_reader()` and never imports the package.

`tests/test_gold_read_port.py` fails if an implementation lacks a method, takes different
parameters, or offers a public read the port does not declare, so a read cannot be added
on one side only.

Every read answers from rows a run already wrote: `run` is None (and the rest empty)
when a client has never been calculated, which is `not_calculated` and never a zero.
"""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Protocol, TypedDict, Unpack

Row = dict[str, Any]
Rows = list[Row]


class UnitDrillOptions(TypedDict, total=False):
    """The optional narrowing of a unit drawer: one month, a sort, a limit and one filter per cohort."""

    month: int | None
    sort: str | None
    order: str | None
    near_min_hours: float | None
    limit: int | None
    employee_filters: str | None
    near_filters: str | None


class EligibilityOptions(TypedDict, total=False):
    """The optional shape of an eligibility page: the near-floor band, the status and text filters, the page and its sort.

    Carried as options, not as twelve parameters, which is past the standard of seven.
    The adapter's own signature carries the defaults (`band` 0.05, `status` "all",
    `limit` 50 and so on); the contract test requires it to take exactly these names.
    """

    band: float
    status: str
    near_floor: bool
    q: str
    limit: int
    offset: int
    sort: str
    order: str


class GoldConnection(Protocol):
    """The pooled link a reader holds; the warm-up keeps it alive and fills it before the first request."""

    def keepalive(self) -> int: ...

    def prewarm(self, count: int = ...) -> int: ...


class RunIdentityPort(Protocol):
    """Which run is live for a client, and the connection the reads share."""

    @property
    def connection(self) -> GoldConnection: ...

    def scope(self) -> AbstractContextManager[Any]: ...

    def latest_run(self, client_id: int) -> Row | None: ...

    def run_in_flight(self, client_id: int) -> Row | None: ...


class UnitGridPort(Protocol):
    """The location grid: unit-year rows, month grain, credit tranches and per-unit money."""

    def unit_page(
        self, client_id: int, *, method: str, tax_year: int | None = None,
        program_code: str | None = None, limit: int = 25, offset: int = 0,
    ) -> Row: ...

    def unit_years(
        self, client_id: int, *, method: str, tax_year: int | None = None,
        program_code: str | None = None, limit: int = 25, offset: int = 0,
    ) -> tuple[Rows, int]: ...

    def unit(self, client_id: int, worksite_id: str, *, tax_year: int, method: str) -> Row | None: ...

    def unit_months(
        self, client_id: int, worksite_id: str, *, tax_year: int, method: str, run_id: str
    ) -> Row | None: ...

    def month_summaries(
        self, client_id: int, *, method: str, run_id: str, tax_year: int | None = None
    ) -> Rows: ...

    def installments(self, client_id: int, *, method: str, program_code: str | None = None) -> Rows: ...

    def credit_columns(self, client_id: int, *, method: str, program_code: str | None = None) -> Rows: ...

    def unit_totals(self, client_id: int, *, method: str, program_code: str | None = None) -> Rows: ...


class UnitPeoplePort(Protocol):
    """The people at one location: those counted, the near misses, and the drawer that shows both."""

    def unit_employees(
        self, client_id: int, worksite_id: str, *, tax_year: int, method: str, run_id: str,
        month: int | None = None,
    ) -> Rows: ...

    def unit_near_threshold(
        self, client_id: int, worksite_id: str, *, tax_year: int, method: str, run_id: str
    ) -> Rows: ...

    def unit_drill(
        self, client_id: int, worksite_id: str, *, tax_year: int, method: str,
        **options: Unpack[UnitDrillOptions],
    ) -> Row: ...


class RunSeriesPort(Protocol):
    """What the run recorded across months and years."""

    def headcount_series(self, client_id: int, *, tax_year: int, method: str) -> Row: ...

    def client_year_series(self, client_id: int, *, method: str = "pay_period") -> Row: ...

    def onezero_matrix(self, client_id: int, *, tax_year: int, method: str) -> Row: ...


class RiskPort(Protocol):
    """Employees near a floor: inside the credit and able to fall out, or outside and able to reach it."""

    def at_risk(
        self, client_id: int, *, tax_year: int, method: str, min_weekly_hours: float,
        min_weekly_wages: float, band: float = 0.10,
    ) -> Row: ...

    def proximity_candidates(
        self, client_id: int, *, tax_year: int, method: str, min_weekly_hours: float,
        min_weekly_wages: float, widest_band_hours: float,
    ) -> Row: ...

    def cohort_periods(
        self, client_id: int, *, tax_year: int, run_id: str, tokens: list[str]
    ) -> dict[str, Rows]: ...


class EmployeePort(Protocol):
    """Who qualifies, and one employee's derivation, looked up by record token."""

    def eligibility_population(
        self, client_id: int, *, tax_year: int, min_weekly_hours: float, min_weekly_wages: float,
        **options: Unpack[EligibilityOptions],
    ) -> Row: ...

    def employee_drill(self, client_id: int, *, tax_year: int, record_token: str) -> Row: ...

    def employee(self, record_token: str, *, client_id: int, tax_year: int, run_id: str) -> Rows: ...

    def employee_units(
        self, record_token: str, *, client_id: int, tax_year: int, run_id: str, method: str
    ) -> Rows: ...


class GoldReadPort(
    RunIdentityPort, UnitGridPort, UnitPeoplePort, RunSeriesPort, RiskPort, EmployeePort, Protocol
):
    """Every read a screen, a capability or the claim package makes of `tcc_gold`."""

"""Where a client's fiscal year actually comes from.

`EntityFiscalYearRules` has been in the source schema, populated for every
tenant and round-tripped through Delta since the schema was written — and
nothing read it. The engine took its fiscal year from a single global setting
instead, which is one accounting year for the whole application.

This is the adapter that reads the fact. When the fact is absent it says so
rather than inventing one; `assumed_calendar_window` carries the flag.
"""
from __future__ import annotations

from datetime import date

from domain.calculation.fiscal import (
    FiscalWindow,
    TaxYearLabel,
    assumed_calendar_window,
    window_from_client_rules,
)


def _as_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _fiscal_rules(account_id: int) -> list | None:
    """The client's fiscal rules, by the cheapest route that can answer.

    SQL first. The Delta path reads ten tables including every payroll row to
    reach this one lookup — ~132s cold — and it is on the request path of every
    screen that resolves a tax year.

    None means "could not read", which the caller turns into a flagged
    assumption. An empty list means "read it, the client has no rule", and those
    are different facts: the second is a real gap in the source, the first is an
    outage, and a lakehouse outage must not silently decide statute.
    """
    from infrastructure.persistence.source_sql import SourceSqlReader

    reader = SourceSqlReader()
    if reader.is_configured():
        try:
            return reader.fiscal_year_rules(int(account_id))
        except Exception:  # noqa: BLE001 - fall through to the Delta reader
            pass

    from data.source.from_fabric import FabricLakehouseReader

    delta = FabricLakehouseReader()
    if not delta.is_configured():
        return None
    try:
        dataset = delta.for_account(int(account_id))
    except Exception:  # noqa: BLE001 - an outage must not decide statute
        return None
    return list(dataset.fiscal_year_rules or []) if dataset else None


def client_fiscal_window(
    account_id: int | None,
    tax_year: int,
    convention: TaxYearLabel,
) -> FiscalWindow:
    """The client's own fiscal window for a tax year, or an flagged assumption.

    The stored rule is one window (the client's base year); later years shift by
    whole years, which is how a repeating fiscal calendar works. A 53-week
    calendar drifts a few days a year and this does not model that — so the
    shifted window is returned only when it still lands on the requested tax
    year under the programme's own convention.
    """
    if account_id is None:
        return assumed_calendar_window(tax_year, convention)

    # Only the lakehouse source holds per-client fiscal rules. Reading them
    # while payroll comes from somewhere else pairs one client's calendar with
    # another source's paychecks — a window that matches neither.
    from tools.fabric_source import active_data_source

    if active_data_source() != "lakehouse":
        return assumed_calendar_window(tax_year, convention)

    rules = _fiscal_rules(account_id)
    if rules is None:
        return assumed_calendar_window(tax_year, convention)

    for rule in rules:
        begin = _as_date(rule.fiscal_year_begin)
        end = _as_date(rule.fiscal_year_end)
        if not begin or not end or end < begin:
            continue

        shift = tax_year - (begin.year if convention == "begins" else end.year)
        try:
            shifted_begin = begin.replace(year=begin.year + shift)
            shifted_end = end.replace(year=end.year + shift)
        except ValueError:  # 29 Feb into a common year
            continue

        return window_from_client_rules(
            shifted_begin,
            shifted_end,
            convention,
            note=(
                f"From EntityFiscalYearRules for account {account_id}"
                + (f" ({rule.rule_expression})" if rule.rule_expression else "")
                + (
                    f", shifted {shift:+d} year(s) from the stored base window "
                    f"{begin.isoformat()}..{end.isoformat()}."
                    if shift
                    else "."
                )
            ),
        )

    return assumed_calendar_window(tax_year, convention)


def window_for_state_year(
    account_id: int | None, state: str, tax_year: int
) -> tuple[date, date] | None:
    """The client's fiscal window for a state-year, as plain dates.

    One resolver for every caller that measures Average Headcount. The
    assessment and the two what-if simulators each took their own view of "the
    twelve months", and the last time they disagreed Position quoted $0 for a
    client-year while Plan quoted $252,280.

    Returns None only when the state has no programme to take a convention
    from — `client_fiscal_window` already falls back to an assumed calendar
    window, which is what every caller did before this existed.
    """
    from tools.credit_math import (
        PROGRAM_CODE_TO_PACK, STATE_TO_PACK, resolve_tax_year_convention,
    )

    pack_file = STATE_TO_PACK.get((state or "").upper())
    if not pack_file:
        return None
    code = next((c for c, f in PROGRAM_CODE_TO_PACK.items() if f == pack_file), None)
    if not code:
        return None
    try:
        convention = resolve_tax_year_convention(code, tax_year)
        window = client_fiscal_window(account_id, tax_year, convention["label"])
    except Exception:  # noqa: BLE001 - an unresolvable window is not a failed assessment
        return None
    return (window.begin, window.end) if window else None
